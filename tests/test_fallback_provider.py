"""兜底规则提供者测试 — 规则加载 + 三种匹配模式 + 通用兜底。

测试覆盖：
1. 从 JSON 文件加载规则
2. ANY 模式：任一关键词命中
3. ALL 模式：所有关键词都要命中
4. EXACT 模式：精确匹配
5. exclude_keywords 排除
6. 通用兜底规则
7. 文件不存在时的降级
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.generate.fallback_provider import FallbackProvider


class TestFallbackProvider:
    """兜底规则提供者测试。"""

    def setup_method(self):
        """每个测试创建临时 JSON 规则文件。"""
        self.rules = [
            {
                "keywords": ["算力", "基础设施"],
                "answer": "算力基础设施说明。",
                "mode": "any",
            },
            {
                "keywords": ["安全", "合规"],
                "answer": "安全合规要求说明。",
                "mode": "all",
                "exclude_keywords": ["漏洞"],
            },
            {
                "keywords": ["你好"],
                "answer": "你好！我是企业知识库助手。",
                "mode": "exact",
            },
            {
                "keywords": [],
                "answer": "通用兜底回答。",
                "mode": "any",
            },
        ]
        self.tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        json.dump(self.rules, self.tmp, ensure_ascii=False)
        self.tmp.close()
        self.provider = FallbackProvider(self.tmp.name)

    def teardown_method(self):
        os.unlink(self.tmp.name)

    # --- 规则加载 ---

    def test_loaded_rules_count(self):
        """加载了 3 条规则（不含通用兜底）。"""
        assert len(self.provider._rules) == 3

    def test_fallback_rule_loaded(self):
        """通用兜底规则已加载。"""
        assert self.provider._fallback_rule is not None
        assert self.provider._fallback_rule.answer == "通用兜底回答。"

    # --- ANY 模式 ---

    def test_any_mode_one_keyword(self):
        """ANY 模式：命中一个关键词就返回。"""
        rule = self.provider.match("算力发展趋势")
        assert rule is not None
        assert rule.answer == "算力基础设施说明。"

    def test_any_mode_other_keyword(self):
        """ANY 模式：命中另一个关键词也返回。"""
        rule = self.provider.match("基础设施规划")
        assert rule is not None
        assert rule.answer == "算力基础设施说明。"

    def test_any_mode_no_match(self):
        """ANY 模式：没有命中关键词返回 None。"""
        rule = self.provider.match("完全不相关的问题")
        assert rule is None

    # --- ALL 模式 ---

    def test_all_mode_both_keywords(self):
        """ALL 模式：两个关键词都命中才返回。"""
        rule = self.provider.match("安全和合规要求")
        assert rule is not None
        assert rule.answer == "安全合规要求说明。"

    def test_all_mode_one_keyword_only(self):
        """ALL 模式：只命中一个不返回。"""
        rule = self.provider.match("安全要求")
        assert rule is None

    def test_all_mode_exclude_keyword(self):
        """ALL 模式：包含排除关键词不返回。"""
        rule = self.provider.match("安全合规和漏洞")
        assert rule is None

    # --- EXACT 模式 ---

    def test_exact_mode_match(self):
        """EXACT 模式：精确匹配。"""
        rule = self.provider.match("你好")
        assert rule is not None
        assert rule.answer == "你好！我是企业知识库助手。"

    def test_exact_mode_partial_no_match(self):
        """EXACT 模式：部分匹配不返回。"""
        rule = self.provider.match("你好世界")
        assert rule is None

    # --- 通用兜底 ---

    def test_get_fallback_rule(self):
        """get_fallback_rule 返回通用兜底。"""
        rule = self.provider.get_fallback_rule()
        assert rule is not None
        assert rule.answer == "通用兜底回答。"

    # --- 文件不存在 ---

    def test_file_not_exist(self):
        """规则文件不存在：加载 0 条规则，不崩溃。"""
        provider = FallbackProvider("/nonexistent/path/rules.json")
        assert provider._rules == []
        assert provider._fallback_rule is None
        assert provider.match("任何问题") is None
        assert provider.get_fallback_rule() is None

    # --- 空问题 ---

    def test_empty_question(self):
        """空问题返回 None。"""
        assert self.provider.match("") is None
