"""纯文本资料来源 — 实现 SourceReader 接口。

通用兜底格式，支持按段落分块。
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import List

from app.contracts import Chunk, ChunkMeta, ChunkType, ChunkTypeClassification, SourceReader
from app.cross.logging import get_logger

logger = get_logger(__name__)

# 法律条款匹配（优先按条款分块）
_ARTICLE_PATTERN = re.compile(r"^(第[一二三四五六七八九十零百]+[条章节])")

# 空行 = 段落分隔
_EMPTY_LINE_PATTERN = re.compile(r"^\s*$")


class TxtReader(SourceReader):
    """纯文本文件读取，按段落分块。

    优先检测法律条款模式（"第X条"），匹配则按条款分块；
    否则按空行分隔的段落分块。

    用法::
        reader = TxtReader()
        chunks = reader.read("笔记.txt")
    """

    def read(self, source: str, doc_name: str = "") -> List[Chunk]:
        path = Path(source)
        if not doc_name:
            doc_name = path.stem
        doc_id = hashlib.md5(str(path).encode()).hexdigest()[:16]

        try:
            text = path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error("failed to read text file: %s", e)
            return []

        logger.info("reading text file: %s (%d chars)", path, len(text))

        # 检测是否包含法律条款模式
        if _ARTICLE_PATTERN.search(text):
            chunks = self._split_by_articles(text, doc_id, doc_name)
        else:
            chunks = self._split_by_paragraphs(text, doc_id, doc_name)

        chunks = self._merge_short_chunks(chunks)
        return chunks

    def _split_by_articles(self, text: str, doc_id: str, doc_name: str) -> List[Chunk]:
        """按法律条款分块。"""
        lines = text.splitlines()
        chunks: List[Chunk] = []
        current_lines: List[str] = []
        current_article = ""
        chunk_idx = 0

        for line in lines:
            match = _ARTICLE_PATTERN.match(line.strip())
            if match:
                if current_lines:
                    chunks.append(self._make_chunk(
                        content="\n".join(current_lines),
                        doc_id=doc_id,
                        doc_name=doc_name,
                        heading_number=current_article,
                        chunk_index=chunk_idx,
                    ))
                    chunk_idx += 1
                current_lines = [line]
                current_article = match.group(1)
            else:
                current_lines.append(line)

        if current_lines:
            chunks.append(self._make_chunk(
                content="\n".join(current_lines),
                doc_id=doc_id,
                doc_name=doc_name,
                heading_number=current_article,
                chunk_index=chunk_idx,
            ))

        return chunks

    def _split_by_paragraphs(self, text: str, doc_id: str, doc_name: str) -> List[Chunk]:
        """按段落分块（空行分隔）。"""
        paragraphs = re.split(r"\n\s*\n", text.strip())
        chunks = []
        for i, para in enumerate(paragraphs):
            para = para.strip()
            if not para:
                continue
            chunks.append(self._make_chunk(
                content=para,
                doc_id=doc_id,
                doc_name=doc_name,
                heading_number=f"段落{i+1}",
                chunk_index=i,
            ))
        return chunks

    def _merge_short_chunks(self, chunks):
        """合并过短分块（< 20 字）到相邻分块，避免无意义碎片。"""
        MIN_LEN = 20
        if not chunks:
            return chunks

        result = []
        buffer = []  # 暂存短分块内容
        next_idx = 0

        for chunk in chunks:
            content = chunk.content.strip()
            if len(content) < MIN_LEN:
                buffer.append(content)
            else:
                if buffer:
                    content = "\n".join(buffer) + "\n" + content
                    buffer = []
                result.append(self._make_chunk(
                    content=content,
                    doc_id=chunk.meta.doc_id,
                    doc_name=chunk.meta.doc_name,
                    heading_number=chunk.meta.heading_number,
                    chunk_index=next_idx,
                ))
                next_idx += 1

        # 剩余 buffer 合并到最后一个分块
        if buffer and result:
            last = result[-1]
            result[-1] = self._make_chunk(
                content=last.content + "\n" + "\n".join(buffer),
                doc_id=last.meta.doc_id,
                doc_name=last.meta.doc_name,
                heading_number=last.meta.heading_number,
                chunk_index=last.meta.chunk_index,
            )
        elif buffer and not result:
            # 全部都是短分块，兜底
            result.append(self._make_chunk(
                content="\n".join(buffer),
                doc_id=chunks[0].meta.doc_id,
                doc_name=chunks[0].meta.doc_name,
                heading_number="内容",
                chunk_index=0,
            ))

        return result

    def _make_chunk(
        self,
        content: str,
        doc_id: str,
        doc_name: str,
        heading_number: str,
        chunk_index: int = 0,
    ) -> Chunk:
        meta = ChunkMeta(
            doc_id=doc_id,
            doc_name=doc_name,
            mcu_model="",
            page_num=0,
            heading_number=heading_number,
            heading_title=heading_number,
            heading_level=1,
            chunk_type=ChunkType.TEXT,
            chunk_index=chunk_index,
            token_count=len(content) // 4,
            classification=ChunkTypeClassification.PUBLIC,
        )
        return Chunk(
            content=content.strip(),
            meta=meta,
        )