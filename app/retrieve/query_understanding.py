"""
QueryUnderstanding — 查询意图分析。

P2 只做一件事情：检测条款号（如"第三十九条"、"第39条"），
标记 boost_sparse=True，让 HybridRetriever 提高 BM25 权重。

P3 再扩展：关键词提取、查询改写、对话历史融合。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# 中文数字 → 正则片段
_CN_NUM = r"[一二三四五六七八九十百零]+"
_CN_CLAUSE = re.compile(rf"第{_CN_NUM}条")
_CN_CHAPTER = re.compile(rf"第{_CN_NUM}[章节]")
_ARAB_CLAUSE = re.compile(r"第\d+条")
_ARAB_CHAPTER = re.compile(r"第\d+[章节]")


@dataclass
class QueryIntent:
    """查询意图分析结果。"""

    has_clause_number: bool = False
    clause_number: str = ""  # 匹配到的条款号原文，如"第三十九条"
    has_chapter_number: bool = False
    chapter_number: str = ""  # 匹配到的章节号原文，如"第三章"
    boost_sparse: bool = False  # 是否提高 BM25 权重
    is_how_to: bool = False  # 是否实操类问题（如何/怎样/怎么）
    is_definition: bool = False  # 是否定义类问题（什么是/是什么/的定义）
    has_topic_keyword: bool = False  # 是否包含具体主题的关键词（如"算力"、"安全"、"人才"）
    keywords: List[str] = field(default_factory=list)  # 排除条款号后的关键词


class QueryUnderstanding:
    """查询意图分析。

    用法:
        qu = QueryUnderstanding()
        intent = qu.analyze("第三十九条是什么")
        # intent.boost_sparse → True
        # intent.clause_number → "第三十九条"
    """

    # -----------------------------------------------------------
    # 公开接口（对齐 contracts.py 的 QueryUnderstanding Protocol）
    # -----------------------------------------------------------

    def rewrite(self, question: str, history: Optional[List[Dict[str, str]]] = None) -> str:
        """重写问题（P2 简单实现：直接返回原问题，P3 再加历史融合）。"""
        # P2 不做重写，直接返回原问题
        # P3 再实现：基于对话历史融合上下文
        return question

    def extract_keywords(self, query: str) -> List[str]:
        """提取关键词（去掉条款号和章节号后的剩余词语）。"""
        intent = self.analyze(query)
        return intent.keywords

    # -----------------------------------------------------------
    # 内部方法
    # -----------------------------------------------------------

    # 主题关键词：检测到这些词说明用户在问具体话题，不是泛泛概述
    # 当检测到具体话题时，提高 BM25 权重让精确匹配的章节排上来
    _TOPIC_KEYWORDS = [
        # 行业与领域
        "产业", "工业", "农业", "服务业", "行业",
        # 技术与基础设施
        "算力", "芯片", "模型", "算法", "数据", "基础设施", "技术",
        # 安全与监管
        "安全", "监管", "治理", "风险", "伦理",
        # 保障与政策
        "人才", "培养", "教育", "资金", "财政", "税收", "金融", "政策",
        "标准", "标准化", "法规", "法律", "制度",
        # 应用与场景
        "应用", "场景", "消费", "产品", "服务",
        # 资源与生态
        "生态", "开源", "平台", "基地", "枢纽",
    ]
    _TOPIC_RE = re.compile("|".join(_TOPIC_KEYWORDS))

    def analyze(self, query: str) -> QueryIntent:
        """分析查询，返回意图结构。"""
        intent = QueryIntent()

        # 1. 检测条款号（中文数字优先）
        m = _CN_CLAUSE.search(query)
        if m:
            intent.has_clause_number = True
            intent.clause_number = m.group()
        else:
            m = _ARAB_CLAUSE.search(query)
            if m:
                intent.has_clause_number = True
                intent.clause_number = m.group()

        # 2. 检测章节号
        m = _CN_CHAPTER.search(query)
        if m:
            intent.has_chapter_number = True
            intent.chapter_number = m.group()
        else:
            m = _ARAB_CHAPTER.search(query)
            if m:
                intent.has_chapter_number = True
                intent.chapter_number = m.group()

        # 3. 检测实操类问题（如何/怎样/怎么配置）
        _HOW_TO_RE = re.compile(r"(如何|怎样|怎么)")
        intent.is_how_to = bool(_HOW_TO_RE.search(query))

        # 4. 检测定义类问题（什么是/是什么/的定义）
        _DEFINITION_RE = re.compile(r"(什么是|是什么|的定义)")
        intent.is_definition = bool(_DEFINITION_RE.search(query))

        # 5. 检测具体主题关键词（如"算力"、"安全"、"人才"）
        #    当检测到具体话题时，提高 BM25 权重让精确匹配的章节排上来
        intent.has_topic_keyword = bool(self._TOPIC_RE.search(query))

        # 6. 仅对条款号/章节号查询提高 BM25 权重
        # 实操/定义/主题关键词不再触发 boost_sparse，因为稠密检索已足够准确
        if intent.has_clause_number or intent.has_chapter_number:
            intent.boost_sparse = True

        # 7. 提取关键词（排除条款号和章节号后的剩余文本）
        cleaned = query
        if intent.clause_number:
            cleaned = cleaned.replace(intent.clause_number, "")
        if intent.chapter_number:
            cleaned = cleaned.replace(intent.chapter_number, "")
        intent.keywords = [kw for kw in cleaned.strip().split() if kw]

        return intent