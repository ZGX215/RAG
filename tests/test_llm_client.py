"""DeepSeekClient 失败语义测试。

本文件锁的是一个**真实踩过的坑**：generate() 原先在所有模型失败时
`return ""`（吞掉异常只留一条日志）。后果是"模型挂了"与"模型答了空内容"
在调用方看来完全一样 —— 服务看起来一切正常、日志无 ERROR，
但每个答案都是空的，悄悄走兜底规则。本项目一个已失效的 API key
配置因此长期未被发现（401 被静默吞掉）。

所以下面的断言重点不在"能返回文本"，而在：
  - 失败必须**抛 LLMError**，不能返回空串；
  - "调用失败"（LLM_ERROR）与"返回空内容"（LLM_EMPTY）必须**可区分**。

全部用假客户端，不发真实网络请求。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.cross.exceptions import LLMError
from app.generate.llm_client import DeepSeekClient

_FAKE_KEY = "sk-test-dummy-not-a-real-key"
_FAKE_URL = "https://example.invalid/v1"


# ============================================================
# 假 OpenAI 客户端
# ============================================================

def _resp(content: str):
    """构造一个看起来像 ChatCompletion 的对象。"""
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


async def _aiter_chunks(items: list[str]):
    """构造异步可迭代的流式分片。"""
    for it in items:
        yield SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content=it))]
        )


class _FakeCompletions:
    """按脚本依次响应；脚本元素为 str（内容）/ list[str]（流式分片）/ Exception。"""

    def __init__(self, script: list):
        self._script = list(script)
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self._script:
            raise AssertionError("假客户端脚本已用完，却被再次调用")
        item = self._script.pop(0)
        if isinstance(item, BaseException):
            raise item
        if kwargs.get("stream"):
            return _aiter_chunks(item)
        return _resp(item)


def _fake_client(script: list):
    comp = _FakeCompletions(script)
    return SimpleNamespace(chat=SimpleNamespace(completions=comp)), comp


def _make_client(script_primary: list, script_fallback: list | None = None, **overrides):
    """构造一个 DeepSeekClient，并把内部 OpenAI 客户端换成假的。

    Returns:
        (client, primary_completions, fallback_completions|None)
    """
    kwargs = dict(api_key=_FAKE_KEY, base_url=_FAKE_URL, model="primary-model")
    if script_fallback is not None:
        kwargs.update(
            fallback_api_key=_FAKE_KEY,
            fallback_base_url=_FAKE_URL,
            fallback_model="fallback-model",
        )
    kwargs.update(overrides)

    llm = DeepSeekClient(**kwargs)
    primary, primary_comp = _fake_client(script_primary)
    llm._client = primary

    fallback_comp = None
    if script_fallback is not None:
        fallback, fallback_comp = _fake_client(script_fallback)
        llm._fallback_client = fallback

    return llm, primary_comp, fallback_comp


def _run(coro):
    return asyncio.run(coro)


# ============================================================
# 正常路径
# ============================================================

class TestGenerateSuccess:

    def test_returns_primary_content(self):
        llm, primary, _ = _make_client(["72MHz 是系统最高时钟频率。"])
        out = _run(llm.generate("sys", "user"))
        assert out == "72MHz 是系统最高时钟频率。"
        assert len(primary.calls) == 1
        assert primary.calls[0]["model"] == "primary-model"

    def test_passes_both_prompts_as_messages(self):
        llm, primary, _ = _make_client(["ok"])
        _run(llm.generate("SYS-PROMPT", "USER-PROMPT"))
        messages = primary.calls[0]["messages"]
        assert messages[0] == {"role": "system", "content": "SYS-PROMPT"}
        assert messages[1] == {"role": "user", "content": "USER-PROMPT"}

    def test_explicit_model_override_is_used(self):
        llm, primary, _ = _make_client(["ok"])
        _run(llm.generate("s", "u", model="override-model"))
        assert primary.calls[0]["model"] == "override-model"

    def test_success_does_not_touch_fallback(self):
        """主模型成功时不得调用备用模型（避免白白多花一次调用）。"""
        llm, _, fallback = _make_client(["primary ok"], ["fallback ok"])
        out = _run(llm.generate("s", "u"))
        assert out == "primary ok"
        assert fallback.calls == []


# ============================================================
# 失败必须抛出，不能静默返回空串
# ============================================================

class TestGenerateFailure:

    def test_primary_failure_raises_llm_error(self):
        """核心回归：主模型失败必须抛 LLMError，绝不能返回 ""。"""
        llm, _, _ = _make_client([RuntimeError("boom")])

        with pytest.raises(LLMError) as ei:
            _run(llm.generate("s", "u"))

        assert ei.value.code == "LLM_ERROR"
        # 错误信息要带上模型名与原始异常，便于定位
        assert "primary-model" in ei.value.message
        assert "boom" in ei.value.message

    def test_both_fail_raises_llm_error(self):
        llm, _, fallback = _make_client(
            [RuntimeError("primary down")], [RuntimeError("fallback down")]
        )

        with pytest.raises(LLMError) as ei:
            _run(llm.generate("s", "u"))

        assert ei.value.code == "LLM_ERROR"
        assert len(fallback.calls) == 1
        assert "fallback down" in ei.value.message

    def test_falls_back_and_returns_fallback_content(self):
        """主模型失败 → 备用模型成功 → 返回备用内容（降级链路仍可用）。"""
        llm, _, fallback = _make_client(
            [RuntimeError("401 unauthorized")], ["备用模型给出的答案"]
        )
        out = _run(llm.generate("s", "u"))
        assert out == "备用模型给出的答案"
        assert fallback.calls[0]["model"] == "fallback-model"

    def test_401_like_error_is_not_silenced(self):
        """复现真实事故：401 被返回空串吞掉。

        原实现下这个用例会失败（拿到 ""，且在调用方看来与"模型答了空内容"无异）。
        """
        llm, _, _ = _make_client([Exception("Error code: 401 - AuthenticationError")])

        with pytest.raises(LLMError):
            _run(llm.generate("s", "u"))


# ============================================================
# 空内容与调用失败必须可区分
# ============================================================

class TestEmptyVsFailure:
    """这两类成因的排查方向完全不同，混在一起会浪费时间：
    前者查 key / 配额 / 网络，后者查提示词与模型行为。
    """

    def test_empty_content_raises_llm_empty(self):
        llm, _, _ = _make_client([""])

        with pytest.raises(LLMError) as ei:
            _run(llm.generate("s", "u"))

        assert ei.value.code == "LLM_EMPTY"

    def test_whitespace_only_content_counts_as_empty(self):
        llm, _, _ = _make_client(["   \n\t  "])

        with pytest.raises(LLMError) as ei:
            _run(llm.generate("s", "u"))

        assert ei.value.code == "LLM_EMPTY"

    def test_failure_takes_precedence_over_empty_in_code(self):
        """主模型失败 + 备用返回空 → 应归因为 LLM_ERROR（有真实故障，更需告警）。"""
        llm, _, _ = _make_client([RuntimeError("down")], [""])

        with pytest.raises(LLMError) as ei:
            _run(llm.generate("s", "u"))

        assert ei.value.code == "LLM_ERROR"

    def test_primary_empty_still_tries_fallback(self):
        """主模型返回空内容时，仍应尝试备用模型。"""
        llm, _, fallback = _make_client([""], ["备用补上了"])
        out = _run(llm.generate("s", "u"))
        assert out == "备用补上了"
        assert len(fallback.calls) == 1

    def test_empty_message_mentions_empty_not_failed(self):
        """LLM_EMPTY 的文案不应说"调用失败"，否则会误导排查方向。"""
        llm, _, _ = _make_client([""])

        with pytest.raises(LLMError) as ei:
            _run(llm.generate("s", "u"))

        assert "空内容" in ei.value.message


# ============================================================
# 流式与可用性探针
# ============================================================

class TestGenerateStream:

    def test_stream_yields_chunks_in_order(self):
        llm, _, _ = _make_client([["系统", "时钟", "为 72MHz"]])

        async def collect():
            return [c async for c in llm.generate_stream("s", "u")]

        assert _run(collect()) == ["系统", "时钟", "为 72MHz"]

    def test_stream_skips_empty_fragments(self):
        """delta.content 可能为 None/空串，不应产出空分片。"""
        llm, _, _ = _make_client([["A", "", "B"]])

        async def collect():
            return [c async for c in llm.generate_stream("s", "u")]

        assert _run(collect()) == ["A", "B"]


class TestIsAvailable:

    def test_true_when_primary_responds(self):
        llm, _, _ = _make_client(["pong"])
        assert _run(llm.is_available()) is True

    def test_false_when_primary_fails_without_fallback(self):
        llm, _, _ = _make_client([RuntimeError("down")])
        assert _run(llm.is_available()) is False

    def test_true_when_only_fallback_responds(self):
        llm, _, _ = _make_client([RuntimeError("down")], ["pong"])
        assert _run(llm.is_available()) is True

    def test_false_when_both_fail(self):
        llm, _, _ = _make_client([RuntimeError("a")], [RuntimeError("b")])
        assert _run(llm.is_available()) is False
