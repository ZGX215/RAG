"""config.settings 配置治理测试（P4 生产化补入）。

覆盖三件事：
1. 占位符判定（假 key / 空值 / 开发默认密钥）；
2. 启动校验的策略差异：生产严格抛错、开发仅告警；
3. 可移植性护栏：默认 DATABASE_URL 由项目根推导，不写死某台机器的路径。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.cross.exceptions import ConfigError
from config.settings import (
    DEV_AUTH_SECRET,
    LLMSettings,
    is_placeholder_auth_secret,
    is_placeholder_llm_key,
    settings,
    validate_runtime_config,
)


class TestPlaceholderDetection:
    """占位符判定。"""

    def test_llm_key_blank_is_placeholder(self):
        assert is_placeholder_llm_key("") is True
        assert is_placeholder_llm_key(None) is True
        assert is_placeholder_llm_key("   ") is True

    def test_llm_key_with_xxxx_is_placeholder(self):
        assert is_placeholder_llm_key("sk-xxxxxxxxxxxxxxxxxxxx") is True

    def test_llm_key_short_sk_is_placeholder(self):
        """真实 key 通常 30+ 字符；sk- 开头但过短的视为占位符。

        （.env 中曾长期存在一个 20 字符的 sk- 占位符，靠这条规则识别出来。）
        """
        assert is_placeholder_llm_key("sk-" + "a" * 17) is True

    def test_llm_key_real_is_not_placeholder(self):
        assert is_placeholder_llm_key("sk-" + "a" * 32) is False
        # 非 sk- 前缀的 key（部分厂商如此）长度足够即视为有效
        assert is_placeholder_llm_key("a" * 50) is False

    def test_llm_key_with_whitespace_or_equals_is_invalid(self):
        """格式明显非法的值（含空白或 '='）必须判为无效。

        回归背景（真实验证时发现）：本机环境变量 deepseek_api_key 的值其实是
        " LLM_API_KEY = sk-…"（一整行赋值语句被粘进了变量值）。原先它会被判为
        "有效" → 配置校验假通过 → 调用时 401 → DeepSeekClient 吞掉异常返回空串，
        表现为"服务看起来正常，但每个答案都是空的"。
        """
        assert is_placeholder_llm_key(" LLM_API_KEY = sk-" + "a" * 32) is True
        assert is_placeholder_llm_key("sk-abcdefgh ijklmnopqrstuvwxyz") is True

    def test_auth_secret_blank_or_dev_default_is_placeholder(self):
        assert is_placeholder_auth_secret("") is True
        assert is_placeholder_auth_secret(None) is True
        assert is_placeholder_auth_secret(DEV_AUTH_SECRET) is True
        assert is_placeholder_auth_secret("x" * 64) is False


class TestValidateRuntimeConfig:
    """启动校验：生产严格 / 开发告警。"""

    def test_complete_config_returns_empty(self, monkeypatch):
        monkeypatch.setattr(settings.llm, "api_key", "sk-" + "a" * 32)
        monkeypatch.setattr(settings.auth, "secret_key", "b" * 64)
        # 无问题时即使生产模式也不应抛错
        assert validate_runtime_config(strict=True) == []

    def test_dev_mode_reports_but_does_not_raise(self, monkeypatch):
        """开发模式：返回问题清单但不阻断启动（保证本地调试可用）。"""
        monkeypatch.setattr(settings.llm, "api_key", "")
        monkeypatch.setattr(settings.auth, "secret_key", "")

        problems = validate_runtime_config(strict=False)

        assert len(problems) == 2
        assert any("LLM_API_KEY" in p for p in problems)
        assert any("AUTH_SECRET_KEY" in p for p in problems)

    def test_production_mode_raises_config_error(self, monkeypatch):
        """生产模式：缺关键配置必须拒绝启动，而不是带着假 key 上线。"""
        monkeypatch.setattr(settings.llm, "api_key", "")
        monkeypatch.setattr(settings.auth, "secret_key", "")

        with pytest.raises(ConfigError):
            validate_runtime_config(strict=True)

    def test_dev_default_secret_is_rejected(self, monkeypatch):
        """仍是开发默认密钥时，生产模式同样要拦住。"""
        monkeypatch.setattr(settings.llm, "api_key", "sk-" + "a" * 32)
        monkeypatch.setattr(settings.auth, "secret_key", DEV_AUTH_SECRET)

        with pytest.raises(ConfigError):
            validate_runtime_config(strict=True)


class TestPortableDefaults:
    """可移植性护栏。"""

    def test_default_database_url_is_derived_from_project_root(self):
        """默认 DATABASE_URL 必须由项目根推导，不得写死某台机器的绝对路径。

        回归背景：原默认值是 sqlite:///E:/trae/cede/mcu-rag-qa-v2/data/structured.db，
        换机器 / 进容器 / CI（无 .env）都会失效。
        """
        if os.environ.get("DATABASE_URL"):
            pytest.skip("本机已显式配置 DATABASE_URL，默认值不生效")

        expected = f"sqlite:///{(_PROJECT_ROOT / 'data' / 'structured.db').as_posix()}"
        assert settings.database.url == expected


class TestLLMKeyFallback:
    """LLM key 的显式回退（替代旧实现里改写 os.environ 的暗逻辑）。

    回退以"厂商配置组"为单位：key + base_url + model 同进同出，避免跨厂商 401。
    """

    def test_falls_back_to_declared_env_var(self, monkeypatch):
        """LLM_API_KEY 为占位符时，回退到显式声明的环境变量名。

        ⚠️ Windows 环境变量大小写不敏感：DEEPSEEK_API_KEY 与 deepseek_api_key
        是同一个变量。不要在本用例里 setenv 一个再 delenv 另一个 —— 那会把刚设置的删掉
        （本用例最初就踩了这个坑）。
        """
        monkeypatch.setenv("DEEPSEEK_API_KEY", "c" * 50)

        s = LLMSettings(LLM_API_KEY="sk-xxxxxxxxxxxxxxxxxxxx")

        assert s.api_key == "c" * 50

    def test_falls_back_to_lowercase_env_var(self, monkeypatch):
        """小写写法（历史遗留的系统环境变量名）同样受支持。"""
        monkeypatch.setenv("deepseek_api_key", "e" * 50)

        s = LLMSettings(LLM_API_KEY="")

        assert s.api_key == "e" * 50

    def test_fallback_aligns_vendor_triple(self, monkeypatch):
        """回退必须把 key + base_url + model **一起**对齐到同一厂商。

        回归背景（真实验证时踩到的线上级问题）：.env 残留火山方舟的 base_url 与
        ep- 占位 model，而真实 key 是 DeepSeek 的。只换 key 不换 endpoint 会得到
        401 "The API key format is incorrect"，而 DeepSeekClient.generate() 会吞掉
        异常返回空串 —— 表现为"服务看起来正常，但每个答案都是空的"。
        """
        monkeypatch.setenv("DEEPSEEK_API_KEY", "c" * 50)

        s = LLMSettings(
            LLM_API_KEY="",
            LLM_BASE_URL="https://ark.cn-beijing.volces.com/api/v3",
            LLM_MODEL="ep-20250101000000-xxxxx",
        )

        assert s.api_key == "c" * 50
        assert s.base_url == "https://api.deepseek.com"
        assert s.model == "deepseek-chat"

    def test_valid_key_keeps_configured_vendor(self, monkeypatch):
        """LLM_API_KEY 有效时，绝不覆盖用户配置的 base_url / model。"""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "c" * 50)

        s = LLMSettings(
            LLM_API_KEY="sk-" + "d" * 32,
            LLM_BASE_URL="https://ark.cn-beijing.volces.com/api/v3",
            LLM_MODEL="ep-20250101000000-xxxxx",
        )

        assert s.api_key == "sk-" + "d" * 32
        assert s.base_url == "https://ark.cn-beijing.volces.com/api/v3"
        assert s.model == "ep-20250101000000-xxxxx"
