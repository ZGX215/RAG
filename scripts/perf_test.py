"""端到端性能测试：统计问答延迟，并把耗时拆解为「检索段 / 生成段」。

为什么必须拆解：
    检索在本地完成（向量检索 + BM25 + RRF 融合 + 重排），生成要调外部 LLM API。
    只看一个总数无法判断优化该往哪做，也无法说明瓶颈到底在本地还是外部依赖。
    实测中这两段的占比差异可以非常大，不做拆解就会得出错误结论。

用法：
    python scripts/perf_test.py            # 默认 20 次
    python scripts/perf_test.py 30         # 30 次
    python scripts/perf_test.py 30 out.json  # 同时把统计结果落盘

说明：
    - 同一个问题第二次会被答案缓存命中（仅数毫秒），因此轮流使用不同问题，
      并把缓存命中的请求单独计数、不混入检索延迟统计，否则会低估真实延迟。
    - 首次请求含模型冷启动开销（除非预热已覆盖检索链路），统计时请注意首条。
"""

from __future__ import annotations

import json
import statistics
import sys
import time
import urllib.request

HOST = "http://127.0.0.1:8000"
API = HOST + "/api/v1"
USER = ("admin", "admin123")  # 来自 scripts/init_users.py

QUESTIONS = [
    "STM32F103C8T6 的 Flash 容量是多少？",
    "STM32 的 GPIO 有哪几种输出模式？",
    "ADC 的分辨率是多少位？",
    "SPI 总线支持哪些工作模式？",
    "串口通信的波特率如何配置？",
    "定时器有哪些计数模式？",
    "中断优先级如何设置？",
    "独立看门狗的作用是什么？",
]


def http(method, url, body=None, token=None, timeout=180):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read())


def login():
    _st, j = http("POST", API + "/auth/login",
                  {"username": USER[0], "password": USER[1]}, timeout=30)
    return j.get("token")


def pct(values, p):
    if not values:
        return 0
    s = sorted(values)
    return s[min(int(len(s) * p / 100), len(s) - 1)]


def stat_line(name, values):
    if not values:
        return f"  {name}: 无数据"
    return (f"  {name:6s} n={len(values):3d}  min={min(values):6.0f}  p50={pct(values, 50):6.0f}  "
            f"p90={pct(values, 90):6.0f}  p95={pct(values, 95):6.0f}  max={max(values):6.0f}  "
            f"avg={statistics.mean(values):6.0f}")


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    out_path = sys.argv[2] if len(sys.argv) > 2 else None

    _st, health = http("GET", HOST + "/health", timeout=10)
    print(f"健康检查: {health}")
    token = login()
    if not token:
        print("登录失败，无法继续")
        return 1
    print(f"已登录。串行 {n} 次，轮流使用 {len(QUESTIONS)} 个不同问题以避开缓存\n")

    e2e, retr, gen = [], [], []
    cached = degraded = errors = 0
    t_all = time.perf_counter()

    for i in range(n):
        q = QUESTIONS[i % len(QUESTIONS)]
        t0 = time.perf_counter()
        try:
            _st, j = http("POST", API + "/qa",
                          {"question": q, "top_k": 5, "stream": False},
                          token=token, timeout=180)
        except Exception as e:
            errors += 1
            print(f"  [{i + 1}/{n}] 失败 {type(e).__name__}: {e}")
            continue

        dt = (time.perf_counter() - t0) * 1000
        e2e.append(dt)
        if j.get("cache_hit"):
            cached += 1
        else:
            retr.append(j.get("retrieval_ms") or 0)
            gen.append(j.get("generate_ms") or 0)
        if j.get("degraded"):
            degraded += 1

        if i == 0 or (i + 1) % 5 == 0:
            print(f"  [{i + 1}/{n}] e2e={dt:7.0f}ms  检索={j.get('retrieval_ms'):>6}ms  "
                  f"生成={j.get('generate_ms'):>6}ms  cache={j.get('cache_hit')}  "
                  f"degraded={j.get('degraded')}")

    total = (time.perf_counter() - t_all) * 1000
    print()
    print("=" * 84)
    print(f"请求 {n} | 总耗时 {total / 1000:.1f}s | QPS {n / (total / 1000):.1f} | "
          f"失败 {errors} | 缓存命中 {cached} | 降级 {degraded}")
    print("-" * 84)
    print(stat_line("端到端", e2e))
    print(stat_line("检索段", retr))
    print(stat_line("生成段", gen))
    print("=" * 84)

    if retr and gen:
        r_avg, g_avg = statistics.mean(retr), statistics.mean(gen)
        print(f"耗时构成：检索 {r_avg:.0f}ms ({r_avg / (r_avg + g_avg) * 100:.1f}%)  |  "
              f"生成 {g_avg:.0f}ms ({g_avg / (r_avg + g_avg) * 100:.1f}%)")
        print("检索在本地（向量库 + BM25 + RRF 融合 + 重排）；")
        print("生成受外部 LLM API 的网络与推理影响，非本地可优化项。")

    if out_path:
        payload = {
            "n": n, "errors": errors, "cache_hit_count": cached, "degraded_count": degraded,
            "e2e_ms": {"p50": pct(e2e, 50), "p95": pct(e2e, 95),
                       "avg": round(statistics.mean(e2e)) if e2e else 0,
                       "max": max(e2e) if e2e else 0},
            "retrieval_ms": {"p50": pct(retr, 50), "p95": pct(retr, 95),
                             "avg": round(statistics.mean(retr)) if retr else 0},
            "generate_ms": {"p50": pct(gen, 50), "p95": pct(gen, 95),
                            "avg": round(statistics.mean(gen)) if gen else 0},
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"\n统计结果已保存: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
