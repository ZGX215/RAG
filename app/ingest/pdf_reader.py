"""PDF 资料来源 — 实现 SourceReader 接口。

双模式分块：
  1. 法律条款模式：检测到"第X条"模式时，按条款分块，每条一个 Chunk；
  2. 逐页段落模式：未检测到条款模式时，先按页切分，再按行级启发式分组，
     将连续行按主题分组为段落，每个段落一个 Chunk。
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import List

from pypdf import PdfReader as _PdfReader

from app.contracts import Chunk, ChunkMeta, ChunkType, ChunkTypeClassification, SourceReader
from app.cross.logging import get_logger

logger = get_logger(__name__)

# 匹配 "第一条"、"第二条" ... "第八十三条"
_ARTICLE_PATTERN = re.compile(r"^(第[一二三四五六七八九十零百]+条)")

# 短分块合并阈值（字符）
_MIN_CHUNK_LEN = 20

# 行级分组：一组最多连续行数（防止单行成块）
_MAX_LINES_PER_CHUNK = 4
# 行级分组：一组最少字符数
_MIN_CHARS_PER_CHUNK = 30


def _normalize_pdf_text(text: str) -> str:
    """修正 pypdf 在部分中文 PDF 上提取出的错位文本。

    现象：PDF 嵌入某些字体时（Linux 上的 Noto CJK 即可复现），pypdf 会返回
    ``'\\x00第\\x00一\\x00条'`` 这种"每个字符前夹一个 NUL"的文本。后果很严重：
    条款正则匹配不上 → 本该走"条款模式"的法律文档退回"逐页段落模式"，
    且关键词检索全部失效（用户看到的是答非所问）。该问题在 Linux CI 上首次暴露，
    但真实中文 PDF 同样会遇到，因此在产品侧处理而不是改测试。

    做法：剔除 NUL 字符。之所以够用——这类错位输出的共同点是"每个有效字符前夹一个
    NUL"（CJK 字符其实已被正确解码），或者是纯 ASCII 文本被按 UTF-16 展开；
    两种情况剔除 NUL 后都能还原。对不含 NUL 的正常文本是完全无操作的。

    局限：若 PDF 字体连 ToUnicode 映射都缺失（字符本身就被解错），剔除 NUL 也救不回来，
    那种情况需要更换 PDF 解析器，不在当前范围内。
    """
    if not text or "\x00" not in text:
        return text
    return text.replace("\x00", "")


class PdfReader(SourceReader):
    """PDF 资料来源实现。

    双模式分块：
    - 法律文档（含"第X条"）：按条款分块，每条一个 Chunk
    - 普通文档：先按页切分，再按行级启发式分组（每 2-4 行一组）

    行级分组避免"概述页"成为全能检索结果，每个 Chunk 更聚焦。
    """

    def read(self, source: str, doc_name: str = "") -> List[Chunk]:
        """读取 PDF 文件，返回 Chunk 列表。

        参数:
            source: PDF 文件路径
            doc_name: 文档名称（留空时自动从文件名提取）
        """
        pdf_path = Path(source)
        if not doc_name:
            doc_name = pdf_path.stem
        doc_id = hashlib.md5(str(pdf_path).encode()).hexdigest()[:16]

        reader = _PdfReader(str(pdf_path))
        total_pages = len(reader.pages)

        # 先提取所有页的文本，判断是否法律条款模式
        pages_text = []
        full_text = ""
        for page_num, page in enumerate(reader.pages, 1):
            # 清洗：pypdf 在部分中文 PDF 上会输出夹带 NUL 的错位文本，直接使用会让
            # 条款识别与关键词匹配全部失效（见 _normalize_pdf_text 的说明）。
            page_text = _normalize_pdf_text(page.extract_text() or "")
            pages_text.append((page_num, page_text))
            full_text += page_text + "\n\n"

        logger.info("extracted %d chars from %s (%d pages)", len(full_text), pdf_path, total_pages)

        # 检测是否法律条款模式
        if _ARTICLE_PATTERN.search(full_text):
            chunks = self._split_by_articles(full_text, doc_id, doc_name)
            logger.info("article mode: split into %d chunks", len(chunks))
        else:
            chunks = self._split_by_page_chunks(pages_text, doc_id, doc_name)
            logger.info("page-chunk mode: split into %d chunks", len(chunks))

        return chunks

    # ---------------------------------------------------------------
    # 模式一：法律条款分块
    # ---------------------------------------------------------------

    def _split_by_articles(
        self,
        text: str,
        doc_id: str,
        doc_name: str,
    ) -> List[Chunk]:
        lines = text.splitlines()
        chunks: List[Chunk] = []
        current_lines: List[str] = []
        current_article = ""

        for line in lines:
            match = _ARTICLE_PATTERN.match(line.strip())
            if match:
                if current_lines:
                    chunks.append(self._make_chunk(
                        content="\n".join(current_lines),
                        doc_id=doc_id,
                        doc_name=doc_name,
                        heading_number=current_article,
                        page_num=0,
                    ))
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
                page_num=0,
            ))

        return chunks

    # ---------------------------------------------------------------
    # 模式二：逐页行级分组（非法律文档）
    # ---------------------------------------------------------------

    def _split_by_page_chunks(
        self,
        pages_text: List[tuple],
        doc_id: str,
        doc_name: str,
    ) -> List[Chunk]:
        """先按页切分，再按行级启发式分组。

        对每页文本，按行分割后基于主题线索分组：
        - 单行且内容很多（如长句）→ 独占一组
        - 连续短行（如描述性内容）→ 合并为 2-4 行一组
        - 避免跨主题切分
        """
        chunks: List[Chunk] = []
        for page_num, page_text in pages_text:
            page_text = page_text.strip()
            if not page_text:
                continue

            # 按行分割
            lines = [line.strip() for line in page_text.splitlines() if line.strip()]
            if not lines:
                continue

            page_chunks = self._group_lines(lines, page_num, doc_id, doc_name)
            chunks.extend(page_chunks)

        chunks = self._merge_short_chunks(chunks)
        return chunks

    def _group_lines(
        self,
        lines: List[str],
        page_num: int,
        doc_id: str,
        doc_name: str,
    ) -> List[Chunk]:
        """将行分组为语义段落，每段一个 Chunk。"""
        chunks: List[Chunk] = []
        group: List[str] = []
        group_chars = 0
        chunk_index = 0

        def flush():
            nonlocal group, group_chars, chunk_index
            if group:
                chunk_index += 1
                chunks.append(self._make_chunk(
                    content="\n".join(group),
                    doc_id=doc_id,
                    doc_name=doc_name,
                    heading_number=f"第{page_num}页-段{chunk_index}",
                    page_num=page_num,
                ))
                group = []
                group_chars = 0

        for line in lines:
            line_len = len(line)

            # 单行超长（> 100 字）→ 独立成段
            if line_len > 100:
                flush()
                chunk_index += 1
                chunks.append(self._make_chunk(
                    content=line,
                    doc_id=doc_id,
                    doc_name=doc_name,
                    heading_number=f"第{page_num}页-段{chunk_index}",
                    page_num=page_num,
                ))
                continue

            # 当前组已满 4 行 → 刷出
            if len(group) >= _MAX_LINES_PER_CHUNK:
                flush()

            # 当前组已有内容且新行是话题开头（冒号结尾的行）→ 新段落
            if group and re.search(r"[:：]$", line):
                flush()

            # 当前组累积字符超过 260 字 → 刷出（防止 Chunk 太大）
            if group and group_chars + line_len > 260:
                flush()

            group.append(line)
            group_chars += line_len

        flush()
        return chunks

    def _merge_short_chunks(self, chunks: List[Chunk]) -> List[Chunk]:
        """合并过短分块（< 20 字）到相邻分块。"""
        if not chunks:
            return chunks

        result = []
        buffer = []

        for chunk in chunks:
            content = chunk.content.strip()
            if len(content) < _MIN_CHUNK_LEN:
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
                    page_num=chunk.meta.page_num,
                ))

        if buffer and result:
            last = result[-1]
            result[-1] = self._make_chunk(
                content=last.content + "\n" + "\n".join(buffer),
                doc_id=last.meta.doc_id,
                doc_name=last.meta.doc_name,
                heading_number=last.meta.heading_number,
                page_num=last.meta.page_num,
            )
        elif buffer and not result:
            result.append(self._make_chunk(
                content="\n".join(buffer),
                doc_id=chunks[0].meta.doc_id,
                doc_name=chunks[0].meta.doc_name,
                heading_number="内容",
                page_num=chunks[0].meta.page_num if chunks else 0,
            ))

        return result

    # ---------------------------------------------------------------
    # 统一 Chunk 构造
    # ---------------------------------------------------------------

    def _make_chunk(
        self,
        content: str,
        doc_id: str,
        doc_name: str,
        heading_number: str,
        page_num: int = 0,
    ) -> Chunk:
        meta = ChunkMeta(
            doc_id=doc_id,
            doc_name=doc_name,
            mcu_model="",
            page_num=page_num,
            heading_number=heading_number,
            heading_title=heading_number,
            heading_level=1,
            chunk_type=ChunkType.TEXT,
            chunk_index=0,
            token_count=len(content) // 4,
            classification=ChunkTypeClassification.PUBLIC,
        )
        return Chunk(
            content=content.strip(),
            meta=meta,
        )
