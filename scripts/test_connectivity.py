"""前后端连接测试：从静态资源到完整问答+反馈闭环。

逐层验证（任一层失败都明确报出来，不静默跳过）：
  1. 后端就绪（/health 轮询）
  2. 前端静态资源由 FastAPI 托管（GET / 返回 index.html）
  3. 登录换取 token（/auth/login）
  4. 带 token 取当前身份（/auth/me）
  5. 统计接口（/stats）
  6. 非流式问答（/qa）→ 检查 answer / degraded / degrade_reason / query_log_id
     / elapsed_ms / cache_hit，并断言 elapsed_ms 是实测值而非硬编码 0
  6b. 缓存收益：同一问题再问一次，断言被标记 cache_hit 且耗时显著下降
  7. 用返回的 query_log_id 反查 /query-logs，确认能**精确定位**，且日志耗时为真实值
  8. 用该 id 提交反馈（/feedback），确认闭环
  9. 流式问答（/qa stream=true）→ 确认 SSE 正常、"注释行不破坏解析"
"""
import json
import time
import urllib.error
import urllib.request

HOST = "http://127.0.0.1:8000"
API = HOST + "/api/v1"
USER = ("admin", "admin123")     # 来自 scripts/init_users.py

results = []


def rec(step, ok, detail=""):
    results.append((step, ok, detail))
    print(("  [OK]   " if ok else "  [FAIL] ") + step + ("  " + detail if detail else ""), flush=True)


def http(method, url, body=None, token=None, timeout=180):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read(), dict(r.headers)


def wait_ready(max_wait=180):
    print("=== 1) 等待后端就绪 ===", flush=True)
    t0 = time.time()
    while time.time() - t0 < max_wait:
        try:
            st, body, _ = http("GET", HOST + "/health", timeout=5)
            if st == 200:
                rec("后端就绪", True, f"{time.time()-t0:.1f}s  {body[:120].decode('utf-8','replace')}")
                return True
        except Exception:
            pass
        time.sleep(3)
    rec("后端就绪", False, f"{max_wait}s 内未就绪")
    return False


def main():
    if not wait_ready():
        return

    # 2) 静态资源
    print("=== 2) 前端静态资源 ===", flush=True)
    try:
        st, body, hdr = http("GET", HOST + "/", timeout=20)
        text = body.decode("utf-8", "replace")
        rec("GET / 返回 200", st == 200, f"status={st} content-type={hdr.get('Content-Type')}")
        rec("返回的是前端页面", ("MCU RAG QA" in text) or ("<script>" in text and "问答" in text),
            f"{len(body)} bytes")
        # 顺便确认本次前端改动已经生效（服务的是磁盘上的最新文件）
        rec("页面含本轮修复(query_log_id 精确关联)", "data-logid" in text and "query_log_id" in text)
    except Exception as e:
        rec("GET /", False, f"{type(e).__name__}: {e}")

    # 3) 登录
    print("=== 3) 登录 ===", flush=True)
    token = None
    try:
        st, body, _ = http("POST", API + "/auth/login",
                           {"username": USER[0], "password": USER[1]}, timeout=30)
        j = json.loads(body)
        token = j.get("token")
        rec("POST /auth/login", st == 200 and bool(token),
            f"user={j.get('user', {}).get('username')} clearance={j.get('user', {}).get('clearance')} expires_in={j.get('expires_in')}")
    except Exception as e:
        rec("POST /auth/login", False, f"{type(e).__name__}: {e}")
    if not token:
        return

    # 4) 身份
    print("=== 4) 当前身份 ===", flush=True)
    try:
        st, body, _ = http("GET", API + "/auth/me", token=token, timeout=20)
        j = json.loads(body)
        rec("GET /auth/me", st == 200, f"{str(j)[:150]}")
    except Exception as e:
        rec("GET /auth/me", False, f"{type(e).__name__}: {e}")

    # 5) 统计
    print("=== 5) 统计接口 ===", flush=True)
    try:
        st, body, _ = http("GET", API + "/stats", token=token, timeout=20)
        rec("GET /stats", st == 200, body[:180].decode("utf-8", "replace"))
    except Exception as e:
        rec("GET /stats", False, f"{type(e).__name__}: {e}")

    # 6) 非流式问答
    print("=== 6) 非流式问答（完整链路）===", flush=True)
    log_id = None
    q6 = "STM32F103C8T6 的系统时钟最高频率是多少？"
    e6 = 0
    try:
        t0 = time.time()
        st, body, _ = http("POST", API + "/qa",
                           {"question": q6, "top_k": 5, "stream": False},
                           token=token, timeout=300)
        j = json.loads(body)
        dt = time.time() - t0
        rec("POST /qa 返回 200", st == 200, f"{dt:.1f}s")
        rec("响应含 answer 字段", "answer" in j, f"answer 长度={len(j.get('answer') or '')}")
        rec("响应含 degraded 字段", "degraded" in j,
            f"degraded={j.get('degraded')} reason={j.get('degrade_reason')!r}")
        rec("响应含 query_log_id 字段", "query_log_id" in j, f"query_log_id={j.get('query_log_id')}")
        rec("响应含 elapsed_ms 字段（本轮新增）", "elapsed_ms" in j, f"elapsed_ms={j.get('elapsed_ms')}ms")
        e6 = j.get("elapsed_ms") or 0
        rec("elapsed_ms 是实测值而非硬编码 0", e6 > 0, f"elapsed_ms={e6}ms")
        rec("响应含 cache_hit 字段（本轮新增）", "cache_hit" in j, f"cache_hit={j.get('cache_hit')}")
        rec("响应含分阶段耗时（本轮新增）", "retrieval_ms" in j and "generate_ms" in j,
            f"检索={j.get('retrieval_ms')}ms 生成={j.get('generate_ms')}ms")
        r_ms, g_ms = j.get("retrieval_ms") or 0, j.get("generate_ms") or 0
        if g_ms > 0:
            rec("瓶颈定位：检索远快于生成（瓶颈在外部 LLM API）", r_ms < g_ms,
                f"检索 {r_ms}ms vs 生成 {g_ms}ms，检索仅占 {r_ms / (r_ms + g_ms) * 100:.1f}%")
        log_id = j.get("query_log_id")
        print("      answer 前 160 字:", (j.get("answer") or "")[:160].replace("\n", " "), flush=True)
    except Exception as e:
        rec("POST /qa", False, f"{type(e).__name__}: {e}")

    # 6b) 缓存收益：同一问题再问一次，应命中答案缓存
    print("=== 6b) 缓存收益（同一问题重复请求）===", flush=True)
    if e6 > 0:
        try:
            t0 = time.time()
            st, body, _ = http("POST", API + "/qa",
                               {"question": q6, "top_k": 5, "stream": False},
                               token=token, timeout=300)
            j = json.loads(body)
            dt_ms = (time.time() - t0) * 1000
            e_hit = j.get("elapsed_ms") or 0
            rec("第二次同问被标记为缓存命中", j.get("cache_hit") is True,
                f"cache_hit={j.get('cache_hit')} elapsed_ms={e_hit}ms")
            # 注意不能用 `0 < e_hit`：命中缓存仅需数毫秒，取整后就是 0，
            # 那会把"正常的 0ms"误判为失败。只比较两者大小即可。
            rec("命中缓存后耗时显著下降", e_hit < e6,
                f"未命中={e6}ms → 命中={e_hit}ms（客户端实测 {dt_ms:.0f}ms）")
            if e6 > 0:
                print(f"      >>> 缓存加速 {e6 / max(e_hit, 1):.0f}x：{e6}ms → {e_hit}ms", flush=True)
        except Exception as e:
            rec("缓存收益", False, f"{type(e).__name__}: {e}")
    else:
        rec("缓存收益", False, "上一步没拿到真实 elapsed_ms，无法对比")

    # 7) 用返回的 id 精确反查日志
    print("=== 7) 用 query_log_id 精确反查日志 ===", flush=True)
    if log_id:
        try:
            st, body, _ = http("GET", API + "/query-logs?limit=20", token=token, timeout=30)
            j = json.loads(body)
            logs = j.get("logs", [])
            hit = [lg for lg in logs if lg.get("id") == log_id]
            rec("按 id 能在日志列表中找到该条", bool(hit),
                f"共 {len(logs)} 条，匹配 {len(hit)} 条")
            if hit:
                rec("日志中的 elapsed_ms 已非硬编码 0（本轮修复）",
                    (hit[0].get("elapsed_ms") or 0) > 0,
                    f"elapsed_ms={hit[0].get('elapsed_ms')} cache_hit={hit[0].get('cache_hit')}")
                print("      该日志: question=%r degraded=%s llm_used=%s sources=%s elapsed=%sms" % (
                    (hit[0].get("question") or "")[:40], hit[0].get("degraded"),
                    hit[0].get("llm_used"), hit[0].get("sources_count"),
                    hit[0].get("elapsed_ms")), flush=True)
        except Exception as e:
            rec("GET /query-logs", False, f"{type(e).__name__}: {e}")
    else:
        rec("按 id 反查日志", False, "上一步没拿到 query_log_id，无法验证")

    # 8) 反馈闭环
    print("=== 8) 反馈闭环 ===", flush=True)
    if log_id:
        try:
            st, body, _ = http("POST", API + "/feedback",
                               {"query_log_id": log_id, "feedback_type": "up",
                                "corrected_answer": "", "comment": "连接测试"},
                               token=token, timeout=30)
            rec("POST /feedback 用 query_log_id 关联成功", st == 200, body[:140].decode("utf-8", "replace"))
            st2, body2, _ = http("GET", API + "/feedbacks?limit=10", token=token, timeout=30)
            j2 = json.loads(body2)
            same = [f for f in j2.get("feedbacks", []) if f.get("query_log_id") == log_id]
            rec("反馈确实挂到了该 query_log_id 下", bool(same),
                f"total={j2.get('total')} 匹配={len(same)}")
        except Exception as e:
            rec("反馈闭环", False, f"{type(e).__name__}: {e}")

    # 9) 流式
    print("=== 9) 流式问答（SSE）===", flush=True)
    try:
        req = urllib.request.Request(API + "/qa", method="POST",
                                     data=json.dumps({"question": "GPIO 有哪几种输出模式？",
                                                      "top_k": 3, "stream": True}).encode())
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", "Bearer " + token)
        with urllib.request.urlopen(req, timeout=300) as r:
            ctype = r.headers.get("Content-Type", "")
            raw = r.read().decode("utf-8", "replace")
        rec("流式返回 text/event-stream", "text/event-stream" in ctype, f"content-type={ctype}")
        rec("流内含 data: 分片", "data: " in raw, f"{len(raw)} bytes")
        rec("流以 [DONE] 结束", "[DONE]" in raw)
        # 关键：注释行不能破坏"只取 data: 行"的解析（前端就是这么解析的）
        blocks = [b for b in raw.split("\n\n") if b.strip()]
        data_only = [b for b in blocks if any(ln.startswith("data: ") for ln in b.split("\n"))]
        comment_only = [b for b in blocks if b.strip().startswith(":")]
        rec("注释行与 data 行可分离解析（前端兼容）",
            all(all(ln.startswith("data: ") or ln.startswith(":") for ln in b.split("\n")) for b in blocks),
            f"data 块={len(data_only)} 注释块={len(comment_only)}")
        if comment_only:
            print("      SSE 注释:", comment_only[0].strip()[:80], flush=True)
    except Exception as e:
        rec("流式问答", False, f"{type(e).__name__}: {e}")

    # 汇总
    print()
    print("=" * 66)
    ok = sum(1 for _, o, _ in results if o)
    bad = [r for r in results if not r[1]]
    print(f"结果: {ok}/{len(results)} 项通过")
    if bad:
        print("未通过:")
        for s, _, d in bad:
            print(f"  - {s}  {d}")
    print("=" * 66)


if __name__ == "__main__":
    main()
