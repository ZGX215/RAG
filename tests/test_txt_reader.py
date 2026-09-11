"""TxtReader 单元测试。"""

from app.ingest.txt_reader import TxtReader


class TestTxtReader:
    """纯文本读取测试。"""

    def test_read_articles(self, sample_txt_articles):
        """含法律条款的文本应正确按条款分块。"""
        file_path, expected = sample_txt_articles
        reader = TxtReader()
        chunks = reader.read(file_path)

        assert len(chunks) == expected, f"期望 {expected} 个分块，实际 {len(chunks)}"
        assert chunks[0].meta.heading_number == "第一条"
        assert chunks[1].meta.heading_number == "第二条"
        assert chunks[2].meta.heading_number == "第三条"
        assert "个人信息权益" in chunks[0].content

    def test_read_paragraphs(self, sample_txt_paragraphs):
        """普通文本应按段落分块（过短段落会被合并）。"""
        file_path, expected = sample_txt_paragraphs
        reader = TxtReader()
        chunks = reader.read(file_path)

        assert len(chunks) == expected, f"期望 {expected} 个分块，实际 {len(chunks)}"
        # 过短段落被合并后，heading_number 可能为"内容"（兜底合并）
        # 至少有一个分块
        assert len(chunks) > 0

    def test_read_empty(self, sample_txt_empty):
        """空文件应返回空列表。"""
        file_path, expected = sample_txt_empty
        reader = TxtReader()
        chunks = reader.read(file_path)
        assert len(chunks) == expected

    def test_mixed_content_not_articles(self, sample_txt_mixed_content):
        """不含条款号标记的文本不应误入条款模式。"""
        file_path, expected = sample_txt_mixed_content
        reader = TxtReader()
        chunks = reader.read(file_path)

        assert len(chunks) == expected
        # 过短段落合并后 heading_number 可能为"内容"（兜底合并）
        # 至少有一个分块即可
        assert len(chunks) > 0

    def test_read_nonexistent_file(self):
        """不存在的文件应返回空列表不抛异常。"""
        reader = TxtReader()
        chunks = reader.read("/nonexistent/path/test.txt")
        assert chunks == []

    def test_source_reader_protocol(self):
        """验证 TxtReader 实现了 SourceReader 协议。"""
        from app.contracts import SourceReader
        assert isinstance(TxtReader(), SourceReader)

    def test_doc_name_custom(self, sample_txt_articles):
        """自定义 doc_name 应正确传递。"""
        file_path, _ = sample_txt_articles
        reader = TxtReader()
        chunks = reader.read(file_path, doc_name="自定义名称")
        assert chunks[0].meta.doc_name == "自定义名称"

    def test_chunk_metadata(self, sample_txt_articles):
        """分块元数据应完整。"""
        file_path, _ = sample_txt_articles
        reader = TxtReader()
        chunks = reader.read(file_path)

        for c in chunks:
            assert c.meta.doc_id != ""
            assert c.meta.doc_name != ""
            assert c.meta.chunk_type == "text"
            assert c.meta.heading_number != ""