"""兜底规则提供者 — 从 JSON 配置文件加载规则，匹配用户问题。

降级链路：主模型 → 备用模型 → 兜底规则 → 友好提示

P3 Step 4 新增：当 LLM 完全不可用时，用预定义的规则回答常见问题。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from app.contracts import FallbackMatchMode, FallbackRule
from app.cross.logging import get_logger
from app.cross.paths import get_project_root

logger = get_logger(__name__)


class FallbackProvider:
    """兜底规则提供者，从 JSON 文件加载规则并匹配问题。

    用法::
        provider = FallbackProvider("config/fallback_rules.json")
        rule = provider.match("个人信息保护法是什么")
        if rule:
            print(rule.answer)
    """

    def __init__(self, rules_path: str):
        # 相对路径转相对于项目根目录的绝对路径
        path = Path(rules_path)
        if not path.is_absolute():
            path = get_project_root() / path
        self._rules_path = path.as_posix()
        self._rules: List[FallbackRule] = []
        self._fallback_rule: Optional[FallbackRule] = None
        self.reload()

    def reload(self) -> int:
        """重新加载配置文件，返回规则数量（不含通用兜底）。"""
        path = Path(self._rules_path)
        if not path.exists():
            logger.warning("fallback rules file not found: %s", self._rules_path)
            self._rules = []
            return 0

        try:
            with open(path, "r", encoding="utf-8") as f:
                raw_rules = json.load(f)
        except Exception as e:
            logger.error("failed to load fallback rules: %s", e)
            self._rules = []
            return 0

        self._rules = []
        self._fallback_rule = None

        for raw in raw_rules:
            rule = FallbackRule(
                keywords=raw.get("keywords", []),
                answer=raw.get("answer", ""),
                exclude_keywords=raw.get("exclude_keywords", []),
                mode=FallbackMatchMode(raw.get("mode", "any")),
            )
            # 空关键词 → 通用兜底（最后一条）
            if not rule.keywords:
                self._fallback_rule = rule
            else:
                self._rules.append(rule)

        logger.info(
            "fallback rules loaded: %d rules + 1 fallback, from %s",
            len(self._rules), self._rules_path,
        )
        return len(self._rules)

    def match(self, question: str) -> Optional[FallbackRule]:
        """匹配最合适的兜底规则，未命中返回 None。

        先按配置顺序匹配关键词规则，命中直接返回。
        未命中返回 None（不包含通用兜底，由调用方按需使用）。
        """
        if not question or not self._rules:
            return None

        for rule in self._rules:
            if self._match_rule(question, rule):
                logger.debug("fallback rule matched: keywords=%s", rule.keywords)
                return rule

        logger.debug("no fallback rule matched for: %s", question[:50])
        return None

    def get_fallback_rule(self) -> Optional[FallbackRule]:
        """获取通用兜底规则（大模型完全不可用时用）。"""
        return self._fallback_rule

    @staticmethod
    def _match_rule(question: str, rule: FallbackRule) -> bool:
        """检查问题是否匹配规则。"""
        q = question.lower()

        # 排除关键词优先
        if rule.exclude_keywords:
            for kw in rule.exclude_keywords:
                if kw.lower() in q:
                    return False

        if rule.mode == FallbackMatchMode.EXACT:
            return any(kw.lower() == q for kw in rule.keywords)

        if rule.mode == FallbackMatchMode.ALL:
            return all(kw.lower() in q for kw in rule.keywords)

        # ANY 模式：任一关键词命中即可
        return any(kw.lower() in q for kw in rule.keywords)