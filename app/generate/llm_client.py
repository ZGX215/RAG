"""LLM 客户端 — 对齐 contracts.py 的 LLMClient Protocol。

P3 Step 4 升级：支持主模型 + 备用模型自动降级。
降级链路：主模型失败 → 试备用模型 → 备用也失败 → 兜底规则。
"""

from __future__ import annotations

from typing import AsyncGenerator, Optional

from openai import AsyncOpenAI, OpenAI

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

        主模型失败时自动切到备用模型（如果配置了）。
        """
        # 尝试主模型
        try:
            model_name = model or self._model
            resp = await self._client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=1024,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            logger.warning("primary model failed: %s", e)

        # 尝试备用模型
        if self._has_fallback:
            try:
                logger.info("trying fallback model: %s", self._fallback_model)
                resp = await self._fallback_client.chat.completions.create(
                    model=self._fallback_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.1,
                    max_tokens=1024,
                )
                return resp.choices[0].message.content or ""
            except Exception as e:
                logger.warning("fallback model also failed: %s", e)

        # 都失败了，返回空字符串，让调用方走兜底规则
        logger.error("all LLM models failed, returning empty")
        return ""

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