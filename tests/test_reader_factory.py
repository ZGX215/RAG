"""ReaderFactory 单元测试。"""

import pytest

from app.ingest.reader_factory import ReaderFactory, get_reader_factory


class TestReaderFactory:
    """工厂模式测试。"""

    def setup_method(self):
        self.factory = ReaderFactory()

    def test_pdf_reader(self):
        """.pdf 应返回 PdfReader。"""
        from app.ingest.pdf_reader import PdfReader
        reader = self.factory.get_reader("test.pdf")
        assert isinstance(reader, PdfReader)

    def test_word_reader(self):
        """.docx 应返回 WordReader。"""
        from app.ingest.word_reader import WordReader
        reader = self.factory.get_reader("test.docx")
        assert isinstance(reader, WordReader)

    def test_markdown_reader(self):
        """.md 应返回 MarkdownReader。"""
        from app.ingest.markdown_reader import MarkdownReader
        reader = self.factory.get_reader("test.md")
        assert isinstance(reader, MarkdownReader)

    def test_markdown_reader_alt(self):
        """.markdown 也应返回 MarkdownReader。"""
        from app.ingest.markdown_reader import MarkdownReader
        reader = self.factory.get_reader("test.markdown")
        assert isinstance(reader, MarkdownReader)

    def test_txt_reader(self):
        """.txt 应返回 TxtReader。"""
        from app.ingest.txt_reader import TxtReader
        reader = self.factory.get_reader("test.txt")
        assert isinstance(reader, TxtReader)

    def test_uppercase_extension(self):
        """大写扩展名也应正确匹配。"""
        from app.ingest.word_reader import WordReader
        reader = self.factory.get_reader("test.DOCX")
        assert isinstance(reader, WordReader)

    def test_unsupported_format(self):
        """不支持的格式应抛出 ValueError。"""
        with pytest.raises(ValueError, match="unsupported file format"):
            self.factory.get_reader("test.xyz")

    def test_has_reader_supported(self):
        """支持的格式 has_reader 返回 True。"""
        assert self.factory.has_reader("test.pdf")
        assert self.factory.has_reader("test.docx")
        assert self.factory.has_reader("test.md")
        assert self.factory.has_reader("test.txt")

    def test_has_reader_unsupported(self):
        """不支持的格式 has_reader 返回 False。"""
        assert not self.factory.has_reader("test.xyz")
        assert not self.factory.has_reader("test.html")

    def test_supported_formats(self):
        """supported_formats 应返回所有支持的格式。"""
        formats = self.factory.supported_formats()
        assert ".pdf" in formats
        assert ".docx" in formats
        assert ".md" in formats
        assert ".txt" in formats

    def test_register_new_format(self):
        """注册新格式后应能正确返回。"""
        from app.contracts import SourceReader
        from typing import List
        from app.contracts import Chunk

        class MockReader:
            def read(self, source: str, doc_name: str = "") -> List[Chunk]:
                return []

        self.factory.register(".html", MockReader())
        reader = self.factory.get_reader("test.html")
        assert isinstance(reader, MockReader)

    def test_register_without_dot(self):
        """注册时扩展名不带点也应正确处理。"""
        from app.ingest.txt_reader import TxtReader
        self.factory.register("csv", TxtReader())
        reader = self.factory.get_reader("test.csv")
        assert isinstance(reader, TxtReader)

    def test_get_reader_factory_singleton(self):
        """get_reader_factory 应返回同一个实例。"""
        f1 = get_reader_factory()
        f2 = get_reader_factory()
        assert f1 is f2


class TestReaderFactoryIntegration:
    """工厂+Reader 集成测试。"""

    def test_factory_with_markdown(self, sample_markdown):
        """通过工厂读取 Markdown 文件。"""
        file_path, expected = sample_markdown
        factory = ReaderFactory()
        reader = factory.get_reader(file_path)
        chunks = reader.read(file_path)
        assert len(chunks) == expected

    def test_factory_with_txt(self, sample_txt_articles):
        """通过工厂读取 TXT 文件。"""
        file_path, expected = sample_txt_articles
        factory = ReaderFactory()
        reader = factory.get_reader(file_path)
        chunks = reader.read(file_path)
        assert len(chunks) == expected

    def test_factory_with_docx(self, sample_docx):
        """通过工厂读取 Word 文件。"""
        file_path, expected = sample_docx
        factory = ReaderFactory()
        reader = factory.get_reader(file_path)
        chunks = reader.read(file_path)
        assert len(chunks) == expected