"""WordReader 单元测试。"""

from app.ingest.word_reader import WordReader


class TestWordReader:
    """Word 文档读取测试。"""

    def test_read_with_headings(self, sample_docx):
        """有标题的 Word 文档应正确按标题分块。"""
        file_path, expected = sample_docx
        reader = WordReader()
        chunks = reader.read(file_path)

        assert len(chunks) == expected, f"期望 {expected} 个分块，实际 {len(chunks)}"
        assert chunks[0].meta.heading_number == "第一章 总则"
        assert "第一条" in chunks[0].content

    def test_heading_levels(self, sample_docx):
        """不同标题层级应正确解析。"""
        file_path, _ = sample_docx
        reader = WordReader()
        chunks = reader.read(file_path)

        assert chunks[0].meta.heading_level == 1
        assert chunks[1].meta.heading_level == 2
        assert chunks[2].meta.heading_level == 3

    def test_read_no_headings(self, sample_docx_no_headings):
        """无标题的 Word 文档应返回 1 个分块。"""
        file_path, _ = sample_docx_no_headings
        reader = WordReader()
        chunks = reader.read(file_path)
        assert len(chunks) == 1

    def test_read_nonexistent_file(self):
        """不存在的文件应返回空列表不抛异常。"""
        reader = WordReader()
        chunks = reader.read("/nonexistent/path/test.docx")
        assert chunks == []

    def test_source_reader_protocol(self):
        """验证 WordReader 实现了 SourceReader 协议。"""
        from app.contracts import SourceReader
        assert isinstance(WordReader(), SourceReader)

    def test_doc_name_custom(self, sample_docx):
        """自定义 doc_name 应正确传递。"""
        file_path, _ = sample_docx
        reader = WordReader()
        chunks = reader.read(file_path, doc_name="自定义文档名")
        assert chunks[0].meta.doc_name == "自定义文档名"

    def test_heading_numbers(self, sample_docx):
        """标题号在 heading_number 中。"""
        file_path, _ = sample_docx
        reader = WordReader()
        chunks = reader.read(file_path)

        assert chunks[0].meta.heading_number == "第一章 总则"
        assert chunks[1].meta.heading_number == "第二节 基本原则"
        assert chunks[2].meta.heading_number == "1. 核心概念"