"""LLM 客户端 — 对齐 contracts.py 的 LLMClient Protocol。

P3 Step 4 升级：支持主模型 + 备用模型自动降级。
降级链路：主模型失败 → 试备用模型 → 备用也失败 → 调用方兜底规则。

**失败语义（重要）**：generate() 全部失败时**抛 LLMError，不返回空串**。
返回空串会让"模型调用失败"与"模型答了但内容为空"在调用方看来完全一样，
表现为"服务一切正常、日志无异常，但每个答案都是空的"。
本项目的真实案例：一个已失效的 API key 配置因此长期未被发现。
现在两种情形都抛 LLMError，并用 code 区分：
  - "LLM_ERROR"：调用本身失败（401 / 超时 / 限流 / 网络）
  - "LLM_EMPTY"：调用成功但模型返回空内容
调用方据此分别打指标，并把降级状态暴露到 API 响应里。
"""

from __future__ import annotations

from typing import AsyncGenerator, Optional

from openai import AsyncOpenAI, OpenAI

from app.cross.exceptions import LLMError
from app.cross.logging import get_logger

logger = get_logger(__name__)


class DeepSeekClient:
    """DeepSeek API 调用封装，对齐 LLMClient Protocol。

    支持主模型 + 备用模型，主模型不可用时自动切备用。

    用法:
        # 只有主模型
        llm = DeepSeekClient(api_key=..., base_url=..., model=...)

        # 主+备
        llm = DeepSeekClient(api_key=..., base_url=..., model=...,
                            fallback_api_key=..., fallback_base_url=..., fallback_model=...)
        answer = await llm.generate("system prompt", "user prompt")
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        fallback_api_key: Optional[str] = None,
        fallback_base_url: Optional[str] = None,
        fallback_model: Optional[str] = None,
    ):
        # 主模型
        self._model = model
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._sync_client = OpenAI(api_key=api_key, base_url=base_url)

        # 备用模型（可选）
        self._has_fallback = (
            fallback_api_key is not None
            and fallback_base_url is not None
            and fallback_model is not None
        )
        if self._has_fallback:
            self._fallback_client = AsyncOpenAI(
                api_key=fallback_api_key, base_url=fallback_base_url
            )
            self._fallback_sync_client = OpenAI(
                api_key=fallback_api_key, base_url=fallback_base_url
            )
            self._fallback_model = fallback_model
            logger.info(
                "DeepSeekClient ready: primary=%s fallback=%s",
                model, fallback_model,
            )
        else:
            logger.info("DeepSeekClient ready: model=%s (no fallback)", model)

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = None,
    ) -> str:
        """非流式生成，自动降级：主模型 → 备用模型。

        所有模型都没拿到有效内容时**抛 LLMError**（不再返回空串）。
        返回空串会让调用方无法区分"模型失败"与"模型答了空内容"，
        而前者是必须被告警的故障。

        Raises:
            LLMError: 全部模型均未返回有效内容。
                code="LLM_ERROR" 表示调用失败；code="LLM_EMPTY" 表示调用成功但内容为空。
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        failures: list[str] = []        # 调用抛异常的尝试
        empty_attempts: list[str] = []  # 调用成功但内容为空的尝试

        # 尝试主模型
        model_name = model or self._model
        try:
            resp = await self._client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=0.1,
                max_tokens=1024,
            )
            content = resp.choices[0].message.content or ""
            if content.strip():
                return content
            empty_attempts.append(f"primary({model_name})")
            logger.warning("primary model returned empty content: model=%s", model_name)
        except Exception as e:
            failures.append(f"primary({model_name}): {e}")
            logger.warning("primary model failed: %s", e)

        # 尝试备用模型
        if self._has_fallback:
            try:
                logger.info("trying fallback model: %s", self._fallback_model)
                resp = await self._fallback_client.chat.completions.create(
                    model=self._fallback_model,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=1024,
                )
                content = resp.choices[0].message.content or ""
                if content.strip():
                    return content
                empty_attempts.append(f"fallback({self._fallback_model})")
                logger.warning("fallback model returned empty content")
            except Exception as e:
                failures.append(f"fallback({self._fallback_model}): {e}")
                logger.warning("fallback model also failed: %s", e)

        # 全部尝试都没拿到内容 —— 明确抛出，让上层能感知并告警。
        # 区分两种成因：调用失败（需告警排查）vs 内容为空（可能是提示词问题）。
        detail = "; ".join(failures + [f"{a} 返回空内容" for a in empty_attempts])
        if failures:
            logger.error("all LLM models failed: %s", detail)
            raise LLMError(f"所有 LLM 模型调用失败：{detail}", code="LLM_ERROR")
        logger.error("all LLM models returned empty content: %s", detail)
        raise LLMError(f"所有 LLM 模型均返回空内容：{detail}", code="LLM_EMPTY")

    async def generate_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """流式生成（异步生成器）。"""
        model_name = model or self._model
        stream = await self._client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=1024,
            stream=True,
        )
        async for chunk in stream:
            content = chunk.choices[0].delta.content or ""
            if content:
                yield content

    async def is_available(self) -> bool:
        """检查主模型是否可用。"""
        try:
            await self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
            )
            return True
        except Exception as e:
            logger.warning("primary model unavailable: %s", e)
            # 如果有备用模型，检查备用
            if self._has_fallback:
                try:
                    await self._fallback_client.chat.completions.create(
                        model=self._fallback_model,
                        messages=[{"role": "user", "content": "ping"}],
                        max_tokens=1,
                    )
                    logger.info("fallback model is available")
                    return True
                except Exception as e2:
                    logger.warning("fallback model also unavailable: %s", e2)
            return False