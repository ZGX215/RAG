"""MarkdownReader 单元测试。"""

from app.ingest.markdown_reader import MarkdownReader


class TestMarkdownReader:
    """Markdown 文档读取测试。"""

    def test_read_with_headings(self, sample_markdown):
        """有标题的 Markdown 应正确按标题分块。"""
        file_path, expected = sample_markdown
        reader = MarkdownReader()
        chunks = reader.read(file_path)

        assert len(chunks) == expected, f"期望 {expected} 个分块，实际 {len(chunks)}"
        assert chunks[0].meta.heading_number == "第一章 总则"
        assert chunks[0].meta.heading_level == 1
        assert "第一条" in chunks[0].content

    def test_heading_levels(self, sample_markdown):
        """不同标题层级应正确解析。"""
        file_path, _ = sample_markdown
        reader = MarkdownReader()
        chunks = reader.read(file_path)

        assert chunks[0].meta.heading_level == 1
        assert chunks[1].meta.heading_level == 2
        assert chunks[2].meta.heading_level == 3

    def test_heading_numbers(self, sample_markdown):
        """标题号在 heading_number 中。"""
        file_path, _ = sample_markdown
        reader = MarkdownReader()
        chunks = reader.read(file_path)

        assert chunks[0].meta.heading_number == "第一章 总则"
        assert chunks[1].meta.heading_number == "第二节 基本原则"
        assert chunks[2].meta.heading_number == "1. 核心概念"

    def test_read_no_headings(self, sample_md_no_headings):
        """无标题的 Markdown 应返回 1 个分块。"""
        file_path, _ = sample_md_no_headings
        reader = MarkdownReader()
        chunks = reader.read(file_path)
        assert len(chunks) == 1

    def test_read_empty(self, sample_md_empty):
        """空文件应返回空列表。"""
        file_path, _ = sample_md_empty
        reader = MarkdownReader()
        chunks = reader.read(file_path)
        assert len(chunks) == 0

    def test_read_no_headings_only_code_block(self, tmp_path):
        """无标题、只有代码块：代码块按设计被跳过 → 无有效内容 → 返回空列表。

        覆盖兜底分支里的"代码块开关"路径（此时不能产出空内容的 chunk）。
        """
        p = tmp_path / "code_only.md"
        p.write_text("```python\nprint('hello')\n```\n", encoding="utf-8")
        chunks = MarkdownReader().read(str(p))
        assert chunks == []

    def test_read_heading_without_body(self, tmp_path):
        """只有标题、没有正文：无可索引内容 → 返回空列表（且不崩溃）。

        覆盖兜底分支里的"遇到标题行"路径。
        """
        p = tmp_path / "title_only.md"
        p.write_text("# 标题\n## 子标题\n", encoding="utf-8")
        chunks = MarkdownReader().read(str(p))
        assert chunks == []

    def test_read_nonexistent_file(self):
        """不存在的文件应返回空列表不抛异常。"""
        reader = MarkdownReader()
        chunks = reader.read("/nonexistent/path/test.md")
        assert chunks == []

    def test_source_reader_protocol(self):
        """验证 MarkdownReader 实现了 SourceReader 协议。"""
        from app.contracts import SourceReader
        assert isinstance(MarkdownReader(), SourceReader)