"""查询理解模块测试 — 条款号/章节号/实操/定义/主题关键词检测。

测试覆盖：
1. 中文条款号检测（第X条）
2. 阿拉伯数字条款号检测（第X条）
3. 章节号检测（第X章/第X节）
4. 实操类问题（如何/怎样/怎么）
5. 定义类问题（什么是/是什么）
6. 主题关键词检测（算力、安全、人才）
7. boost_sparse 触发逻辑
8. extract_keywords 排除条款号
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.retrieve.query_understanding import QueryUnderstanding, QueryIntent


class TestQueryUnderstanding:
    """查询意图分析测试。"""

    def setup_method(self):
        self.qu = QueryUnderstanding()

    # --- 条款号检测 ---

    def test_chinese_clause_number(self):
        """中文数字条款号：第三十九条。"""
        intent = self.qu.analyze("第三十九条是什么")
        assert intent.has_clause_number is True
        assert intent.clause_number == "第三十九条"
        assert intent.boost_sparse is True

    def test_arabic_clause_number(self):
        """阿拉伯数字条款号：第39条。"""
        intent = self.qu.analyze("第39条的内容")
        assert intent.has_clause_number is True
        assert intent.clause_number == "第39条"
        assert intent.boost_sparse is True

    def test_no_clause_number(self):
        """普通问题没有条款号。"""
        intent = self.qu.analyze("什么是算力基础设施")
        assert intent.has_clause_number is False
        assert intent.clause_number == ""
        assert intent.boost_sparse is False

    # --- 章节号检测 ---

    def test_chinese_chapter_number(self):
        """中文数字章节号：第三章。"""
        intent = self.qu.analyze("第三章讲了什么")
        assert intent.has_chapter_number is True
        assert intent.chapter_number == "第三章"
        assert intent.boost_sparse is True

    def test_arabic_chapter_number(self):
        """阿拉伯数字章节号：第3章。"""
        intent = self.qu.analyze("第3章的标题")
        assert intent.has_chapter_number is True
        assert intent.chapter_number == "第3章"

    def test_section_number(self):
        """节号检测：第二节。"""
        intent = self.qu.analyze("第二节的内容是什么")
        assert intent.has_chapter_number is True
        assert intent.chapter_number == "第二节"

    # --- 实操类问题 ---

    def test_is_how_to_ruhe(self):
        """如何 → 实操类。"""
        intent = self.qu.analyze("如何配置环境")
        assert intent.is_how_to is True

    def test_is_how_to_zenyang(self):
        """怎样 → 实操类。"""
        intent = self.qu.analyze("怎样部署服务")
        assert intent.is_how_to is True

    def test_is_how_to_zenme(self):
        """怎么 → 实操类。"""
        intent = self.qu.analyze("怎么使用API")
        assert intent.is_how_to is True

    def test_not_how_to(self):
        """非实操问题。"""
        intent = self.qu.analyze("算力是什么")
        assert intent.is_how_to is False

    # --- 定义类问题 ---

    def test_is_definition_shenme_shi(self):
        """什么是 → 定义类。"""
        intent = self.qu.analyze("什么是算力")
        assert intent.is_definition is True

    def test_is_definition_shi_shenme(self):
        """是什么 → 定义类。"""
        intent = self.qu.analyze("算力是什么")
        assert intent.is_definition is True

    def test_not_definition(self):
        """非定义类。"""
        intent = self.qu.analyze("如何部署算力集群")
        assert intent.is_definition is False

    # --- 主题关键词检测 ---

    def test_topic_keyword_suanli(self):
        """算力 → 主题关键词。"""
        intent = self.qu.analyze("算力的发展趋势")
        assert intent.has_topic_keyword is True

    def test_topic_keyword_anquan(self):
        """安全 → 主题关键词。"""
        intent = self.qu.analyze("安全合规要求")
        assert intent.has_topic_keyword is True

    def test_topic_keyword_rencai(self):
        """人才 → 主题关键词。"""
        intent = self.qu.analyze("人才培养政策")
        assert intent.has_topic_keyword is True

    def test_no_topic_keyword(self):
        """无主题关键词。"""
        intent = self.qu.analyze("你好")
        assert intent.has_topic_keyword is False

    # --- boost_sparse 逻辑 ---

    def test_boost_sparse_only_for_clause_chapter(self):
        """只有条款号/章节号才触发 boost_sparse。"""
        # 实操类不触发
        intent = self.qu.analyze("如何配置环境")
        assert intent.boost_sparse is False

        # 定义类不触发
        intent = self.qu.analyze("什么是算力")
        assert intent.boost_sparse is False

        # 主题关键词不触发
        intent = self.qu.analyze("算力发展趋势")
        assert intent.boost_sparse is False

        # 条款号触发
        intent = self.qu.analyze("第三十九条")
        assert intent.boost_sparse is True

    # --- extract_keywords ---

    def test_extract_keywords_strips_clause(self):
        """extract_keywords 去掉条款号后的剩余文本。"""
        kws = self.qu.extract_keywords("第三十九条 适用范围")
        assert "第三十九条" not in kws
        assert len(kws) > 0

    # --- rewrite ---

    def test_rewrite_returns_original(self):
        """P2 阶段 rewrite 直接返回原问题。"""
        assert self.qu.rewrite("什么是算力") == "什么是算力"
