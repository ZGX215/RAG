"""资料来源工厂 — 根据文件扩展名自动选择对应的 Reader。

P3 新增：统一入口，新增来源时只需要在 _SUPPORTED_EXTENSIONS 注册即可。
"""

from __future__ import annotations

from typing import Dict, List, Type

from app.contracts import SourceReader
from app.cross.logging import get_logger

logger = get_logger(__name__)


class ReaderFactory:
    """资料来源工厂，根据文件扩展名自动选择 Reader。

    用法::
        factory = ReaderFactory()
        reader = factory.get_reader("合同.docx")  # 返回 WordReader
        chunks = reader.read("合同.docx")

    新增来源::
        from app.ingest.my_reader import MyReader
        factory.register(".xyz", MyReader)
    """

    def __init__(self):
        self._readers: Dict[str, SourceReader] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """注册内置支持的格式。"""
        from app.ingest.pdf_reader import PdfReader
        from app.ingest.word_reader import WordReader
        from app.ingest.markdown_reader import MarkdownReader
        from app.ingest.txt_reader import TxtReader

        self._readers = {
            ".pdf": PdfReader(),
            ".docx": WordReader(),
            ".md": MarkdownReader(),
            ".markdown": MarkdownReader(),
            ".txt": TxtReader(),
        }
        logger.info(
            "ReaderFactory: registered %d formats: %s",
            len(self._readers),
            list(self._readers.keys()),
        )

    def register(self, extension: str, reader: SourceReader) -> None:
        """注册新的来源格式。

        Args:
            extension: 文件扩展名（如 ".html"）
            reader: 实现 SourceReader 接口的实例
        """
        ext = extension.lower().strip()
        if not ext.startswith("."):
            ext = f".{ext}"
        self._readers[ext] = reader
        logger.info("ReaderFactory: registered format %s", ext)

    def get_reader(self, source: str) -> SourceReader:
        """根据文件路径返回对应的 Reader。

        Args:
            source: 文件路径

        Returns:
            SourceReader 实例

        Raises:
            ValueError: 不支持的格式
        """
        import os
        _, ext = os.path.splitext(source)
        ext = ext.lower()

        if ext in self._readers:
            logger.debug("ReaderFactory: %s -> %s", ext, type(self._readers[ext]).__name__)
            return self._readers[ext]

        # 无扩展名时尝试按文件名猜测
        if not ext:
            from pathlib import Path
            name = Path(source).stem
            if name:
                return self._readers.get(".txt", self._readers[".txt"])

        raise ValueError(f"unsupported file format: {ext} (source={source})")

    def supported_formats(self) -> List[str]:
        """返回支持的格式列表。"""
        return list(self._readers.keys())

    def has_reader(self, source: str) -> bool:
        """检查是否支持该格式。"""
        import os
        _, ext = os.path.splitext(source)
        return ext.lower() in self._readers


# 全局单例（懒加载）
_factory: ReaderFactory = None  # type: ignore


def get_reader_factory() -> ReaderFactory:
    """获取全局工厂实例。"""
    global _factory
    if _factory is None:
        _factory = ReaderFactory()
    return _factory