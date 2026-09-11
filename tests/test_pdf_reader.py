"""PdfReader 单元测试 — 双模式分块验证。"""

from app.ingest.pdf_reader import PdfReader, _normalize_pdf_text


class TestNormalizePdfText:
    """pypdf 错位文本清洗。

    回归背景：Linux CI 上 pypdf 从 Noto CJK 字体的 PDF 里提取出的文本形如
    '\\x00第\\x00一\\x00条'（每个字符前夹一个 NUL），导致条款正则匹配不上、
    文档退回逐页模式，测试断言 '第1页-段1' == '第一条' 失败。
    """

    def test_plain_text_unchanged(self):
        """不含 NUL 的正常文本必须原样返回（零副作用）。"""
        assert _normalize_pdf_text("第一条 为了保护个人信息权益") == "第一条 为了保护个人信息权益"
        assert _normalize_pdf_text("plain ascii text") == "plain ascii text"

    def test_strips_interleaved_nul_before_cjk(self):
        """NUL + 已正确解码的汉字 → 剔除 NUL 后还原。"""
        raw = "".join("\x00" + ch for ch in "第一条 为了避免")
        assert _normalize_pdf_text(raw) == "第一条 为了避免"

    def test_strips_nul_in_utf16_expanded_ascii(self):
        """纯 ASCII 被按 UTF-16 展开（P\\x00D\\x00F）→ 剔除 NUL 后还原。"""
        assert _normalize_pdf_text("P\x00D\x00F") == "PDF"

    def test_empty_and_none_like(self):
        assert _normalize_pdf_text("") == ""

    def test_restores_article_detection(self):
        """清洗后应能重新被条款正则命中——这才是真正要保的行为。"""
        from app.ingest.pdf_reader import _ARTICLE_PATTERN

        raw = "".join("\x00" + ch for ch in "第一条 为了保护个人信息权益")
        assert _ARTICLE_PATTERN.search(raw) is None, "清洗前应识别不出条款"
        assert _ARTICLE_PATTERN.search(_normalize_pdf_text(raw)) is not None


class TestPdfReader:
    """PDF 双模式读取测试。"""

    def test_read_articles(self, sample_pdf_articles):
        """含法律条款的 PDF 应触发条款模式，按条款分块。"""
        file_path, expected = sample_pdf_articles
        reader = PdfReader()
        chunks = reader.read(file_path)
        assert len(chunks) == expected
        assert chunks[0].meta.heading_number == "第一条"
        assert chunks[1].meta.heading_number == "第二条"
        assert "个人信息权益" in chunks[0].content

    def test_article_heading_numbers(self, sample_pdf_articles):
        """条款模式下 heading_number 应保留条款号。"""
        file_path, _ = sample_pdf_articles
        reader = PdfReader()
        chunks = reader.read(file_path)
        assert chunks[0].meta.heading_number == "第一条"
        assert chunks[1].meta.heading_number == "第二条"

    def test_article_content_integrity(self, sample_pdf_articles):
        """条款模式每条内容应完整，不遗漏。"""
        file_path, _ = sample_pdf_articles
        reader = PdfReader()
        chunks = reader.read(file_path)
        assert "保护个人信息权益" in chunks[0].content
        assert "个人信息受法律保护" in chunks[1].content

    def test_read_normal_pages(self, sample_pdf_normal):
        """普通 PDF 应触发逐页段落模式，按行级分组。"""
        file_path, expected = sample_pdf_normal
        reader = PdfReader()
        chunks = reader.read(file_path)
        assert len(chunks) == expected
        assert chunks[0].meta.heading_number.startswith("第1页-段")
        assert chunks[0].meta.page_num == 1

    def test_normal_page_numbers(self, sample_pdf_normal):
        """逐页段落模式下 page_num 应正确。"""
        file_path, _ = sample_pdf_normal
        reader = PdfReader()
        chunks = reader.read(file_path)
        for c in chunks:
            assert c.meta.page_num >= 1
            assert c.meta.page_num <= 3

    def test_normal_page_content(self, sample_pdf_normal):
        """逐页段落模式每段内容应完整。"""
        file_path, _ = sample_pdf_normal
        reader = PdfReader()
        chunks = reader.read(file_path)
        assert any("page 1" in c.content for c in chunks)
        assert any("page 2" in c.content for c in chunks)
        assert any("page 3" in c.content for c in chunks)

    def test_single_page(self, sample_pdf_single_page):
        """单页普通 PDF 应按行级分组返回 1 个分块。"""
        file_path, expected = sample_pdf_single_page
        reader = PdfReader()
        chunks = reader.read(file_path)
        assert len(chunks) == expected
        assert chunks[0].meta.heading_number.startswith("第1页-段")
        assert chunks[0].meta.page_num == 1

    def test_read_empty(self, sample_pdf_empty):
        """空 PDF（无提取文本）应返回空列表。"""
        file_path, expected = sample_pdf_empty
        reader = PdfReader()
        chunks = reader.read(file_path)
        assert len(chunks) == expected

    def test_read_nonexistent_file(self):
        """不存在的文件应抛出异常。"""
        reader = PdfReader()
        try:
            reader.read("/nonexistent/path/test.pdf")
            assert False
        except Exception:
            pass

    def test_doc_name_custom(self, sample_pdf_articles):
        """自定义 doc_name 应正确传递。"""
        file_path, _ = sample_pdf_articles
        reader = PdfReader()
        chunks = reader.read(file_path, doc_name="自定义文档名")
        assert chunks[0].meta.doc_name == "自定义文档名"

    def test_chunk_metadata(self, sample_pdf_articles):
        """分块元数据应完整。"""
        file_path, _ = sample_pdf_articles
        reader = PdfReader()
        chunks = reader.read(file_path)
        for c in chunks:
            assert c.meta.doc_id != ""
            assert c.meta.doc_name != ""
            assert c.meta.chunk_type == "text"
            assert c.meta.heading_number != ""

    def test_source_reader_protocol(self):
        """验证 PdfReader 实现了 SourceReader 协议。"""
        from app.contracts import SourceReader
        assert isinstance(PdfReader(), SourceReader)

    def test_article_mode_has_no_page_num(self, sample_pdf_articles):
        """条款模式的分块 page_num 应为 0。"""
        file_path, _ = sample_pdf_articles
        reader = PdfReader()
        chunks = reader.read(file_path)
        for c in chunks:
            assert c.meta.page_num == 0

    def test_normal_mode_has_correct_heading(self, sample_pdf_normal):
        """逐页段落模式的 heading_number 包含页码和段号。"""
        file_path, _ = sample_pdf_normal
        reader = PdfReader()
        chunks = reader.read(file_path)
        for c in chunks:
            assert c.meta.heading_number.startswith("第")
            assert "页-段" in c.meta.heading_number
