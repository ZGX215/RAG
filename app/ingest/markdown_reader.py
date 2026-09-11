"""Markdown 资料来源 -- 实现 SourceReader 接口。

企业技术文档、知识库最常用格式，支持按标题分块。
默认跳过代码块内容，避免代码中的关键词污染检索结果。
自动净化 Markdown 格式，去掉格式标记，只保留纯文本。
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import List

from app.contracts import Chunk, ChunkMeta, ChunkType, ChunkTypeClassification, SourceReader
from app.cross.logging import get_logger

logger = get_logger(__name__)

_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$")
# Markdown 格式去除正则
_BOLD_PATTERN = re.compile(r"\*\*(.*?)\*\*")
_ITALIC_PATTERN = re.compile(r"\*(.*?)\*")
_INLINE_CODE_PATTERN = re.compile(r"`(.*?)`")
_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_IMAGE_PATTERN = re.compile(r"!\[[^\]]*\]\([^)]+\)")
_HORIZONTAL_PATTERN = re.compile(r"^\s*([-*_])\1{2,}\s*$")
_BLOCKQUOTE_PATTERN = re.compile(r"^>\s*")
_TABLE_SEP_PATTERN = re.compile(r"^\|?\s*[-=]+:?\s*\|")  # 表格分隔线
_LIST_BULLET_PATTERN = re.compile(r"^\s*([-*+]|\d+\.)\s+")


class MarkdownReader(SourceReader):
    """Markdown 文档读取，按标题分块，默认跳过代码块内容。

    自动净化处理：
    - 跳过所有代码块（可配置）
    - 去除所有 Markdown 格式标记（** * ` [](...) > | --- 等）
    - 只保留纯文本，嵌入效果更好
    """

    def __init__(self, skip_code_blocks: bool = True, clean_format: bool = True):
        """初始化 MarkdownReader。

        Args:
            skip_code_blocks: 是否跳过代码块内容（默认 True）
            clean_format: 是否去除 Markdown 格式标记（默认 True）
                - True: 去除 ** * ` [](...) 等格式标记，只留纯文本
                - False: 保留原始格式
        """
        self._skip_code_blocks = skip_code_blocks
        self._clean_format = clean_format

    def read(self, source: str, doc_name: str = "") -> List[Chunk]:
        path = Path(source)
        if not doc_name:
            doc_name = path.stem
        doc_id = hashlib.md5(str(path).encode()).hexdigest()[:16]
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error("failed to read Markdown file: %s", e)
            return []
        lines = text.splitlines()
        chunks: List[Chunk] = []
        current_heading = ""
        current_level = 0
        current_lines: List[str] = []
        in_code_block = False
        found_first_heading = False  # 跳过第一个标题之前的通用介绍文字（关键词海绵问题）
        chunk_idx = 0

        for line in lines:
            stripped = line.strip()

            # 跟踪代码块状态
            if stripped.startswith("```"):
                in_code_block = not in_code_block
                continue

            if in_code_block:
                continue

            # 处理标题
            match = _HEADING_PATTERN.match(stripped)

            # 只跳过"首个标题之前的导语"——规避关键词海绵（文档开头的通用介绍
            # 会匹配一切查询）。注意：标题本身【不】按层级跳过，任意层级
            # （# / ## / ### …）都成块，这样与 WordReader 按样式分块的语义保持一致，
            # 满足"所有来源输出统一 Chunk 结构、检索层无需区分来源"的目标。
            # 海绵的进一步压制由检索层 hybrid.py 的 _overview_penalty 负责，不在
            # ingest 层用丢数据的方式重复处理。
            if not found_first_heading:
                if match:
                    found_first_heading = True
                    current_heading = match.group(2).strip()
                    current_level = len(match.group(1))
                    current_lines = []
                continue
            if match:
                if current_lines:
                    chunks.append(self._make_chunk(
                        content="\n".join(current_lines),
                        doc_id=doc_id, doc_name=doc_name,
                        heading_number=current_heading, heading_level=current_level,
                        chunk_index=chunk_idx,
                    ))
                    chunk_idx += 1
                current_heading = match.group(2).strip()
                current_level = len(match.group(1))
                current_lines = []
            else:
                # 净化处理本行（去除 ** * > ` [](...) 等格式标记）
                if self._clean_format:
                    line = self._clean_line(line)
                stripped_line = line.strip()
                # 跳过纯分隔线（--- / *** / ___）和表格分隔线
                if _HORIZONTAL_PATTERN.match(stripped_line):
                    continue
                if _TABLE_SEP_PATTERN.match(stripped_line):
                    continue
                current_lines.append(line)

        if current_lines:
            chunks.append(self._make_chunk(
                content="\n".join(current_lines),
                doc_id=doc_id, doc_name=doc_name,
                heading_number=current_heading, heading_level=current_level,
                chunk_index=chunk_idx,
            ))

        # 兜底：上面的"跳过首个标题之前的内容"是为规避关键词海绵（文档标题/通用介绍
        # 匹配一切）。但当文档【没有 ## 及以下标题】时，整篇会被丢光 → 该文档对检索
        # 完全不可见。此处兜底把全文作为一个 chunk 返回，宁可有轻微海绵也不丢数据。
        if not chunks:
            fb_lines: List[str] = []
            fb_heading, fb_level = "", 0
            in_fb_code = False
            for line in lines:
                s = line.strip()
                if s.startswith("```"):
                    in_fb_code = not in_fb_code
                    continue
                if in_fb_code or not s:
                    continue
                m = _HEADING_PATTERN.match(s)
                if m:
                    if not fb_heading:
                        fb_heading = m.group(2).strip()
                        fb_level = len(m.group(1))
                    continue
                if self._clean_format:
                    line = self._clean_line(line)
                fb_lines.append(line)
            body = re.sub(r"\n\s*\n+", r"\n\n", "\n".join(fb_lines)).strip()
            if body:
                chunks.append(self._make_chunk(
                    content=body, doc_id=doc_id, doc_name=doc_name,
                    heading_number=fb_heading, heading_level=fb_level, chunk_index=0,
                ))

        logger.info("MarkdownReader: %d chunks from %s (skip_code=%s, clean=%s)",
                    len(chunks), path, self._skip_code_blocks, self._clean_format)
        return chunks

    def _clean_line(self, line: str) -> str:
        """去除 Markdown 格式标记，返回纯文本。"""
        # 块引用开头：> 文字 → 文字
        line = _BLOCKQUOTE_PATTERN.sub("", line)
        # 列表项目：- 文字 / 1. 文字 → 文字
        line = _LIST_BULLET_PATTERN.sub("", line)
        # 粗体：**文字** → 文字
        line = _BOLD_PATTERN.sub(r"\1", line)
        # 斜体：*文字* → 文字
        line = _ITALIC_PATTERN.sub(r"\1", line)
        # 行内代码：`code` → code
        line = _INLINE_CODE_PATTERN.sub(r"\1", line)
        # 链接：[文字](url) → 文字
        line = _LINK_PATTERN.sub(r"\1", line)
        # 图片：![alt](url) → 空
        line = _IMAGE_PATTERN.sub("", line)
        return line

    def _make_chunk(self, content, doc_id, doc_name, heading_number, heading_level, chunk_index=0):
        if heading_number:
            content = heading_number + "\n" + content
        # 去除首尾空行
        content = content.strip()
        # 连续空行合并成一个
        content = re.sub(r"\n\s*\n+", r"\n\n", content)
        meta = ChunkMeta(
            doc_id=doc_id, doc_name=doc_name, mcu_model="", page_num=0,
            heading_number=heading_number, heading_title=heading_number,
            heading_level=heading_level, chunk_type=ChunkType.TEXT, chunk_index=chunk_index,
            token_count=len(content) // 4,
            classification=ChunkTypeClassification.PUBLIC,
        )
        return Chunk(content=content.strip(), meta=meta)
