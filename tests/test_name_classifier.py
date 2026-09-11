"""文件名密级解析测试 - 单文件解析 + 批量校验 + 边界情况。

测试覆盖：
1. 四种密级后缀正确解析：_PUBLIC / _INTERNAL / _CONFIDENTIAL / _SECRET
2. 大小写不敏感
3. 无后缀 -> 不合法
4. 只有后缀无名称 -> 不合法
5. 不同扩展名
6. 批量校验：全部合法
7. 批量校验：有不合法的
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.contracts import ChunkTypeClassification
from app.ingest.name_classifier import (
    parse_classification_from_filename,
    validate_batch_files,
)


class TestParseClassification:
    """单文件密级解析测试。"""

    def test_public_suffix(self):
        r = parse_classification_from_filename("公司简介_PUBLIC.txt")
        assert r.is_valid
        assert r.clean_name == "公司简介"
        assert r.classification == ChunkTypeClassification.PUBLIC

    def test_internal_suffix(self):
        r = parse_classification_from_filename("内部纪要_INTERNAL.docx")
        assert r.is_valid
        assert r.classification == ChunkTypeClassification.INTERNAL

    def test_confidential_suffix(self):
        r = parse_classification_from_filename("核心财务_CONFIDENTIAL.pdf")
        assert r.is_valid
        assert r.classification == ChunkTypeClassification.CONFIDENTIAL

    def test_secret_suffix(self):
        r = parse_classification_from_filename("战略规划_SECRET.md")
        assert r.is_valid
        assert r.classification == ChunkTypeClassification.SECRET

    def test_case_insensitive(self):
        r = parse_classification_from_filename("文档_public.txt")
        assert r.is_valid
        assert r.classification == ChunkTypeClassification.PUBLIC

        r = parse_classification_from_filename("文档_Internal.docx")
        assert r.is_valid
        assert r.classification == ChunkTypeClassification.INTERNAL

    def test_no_suffix(self):
        r = parse_classification_from_filename("普通文档.txt")
        assert not r.is_valid
        assert "权限后缀" in r.error

    def test_invalid_suffix(self):
        r = parse_classification_from_filename("文档_TOPSECRET.txt")
        assert not r.is_valid

    def test_suffix_only_no_name(self):
        r = parse_classification_from_filename("_PUBLIC.txt")
        assert not r.is_valid
        assert "实际名称" in r.error

    def test_different_extensions(self):
        for ext in [".txt", ".md", ".docx", ".pdf"]:
            r = parse_classification_from_filename(f"文档_PUBLIC{ext}")
            assert r.is_valid, f"extension {ext} should parse"

    def test_underscore_in_name(self):
        r = parse_classification_from_filename("我的_文档_PUBLIC.txt")
        assert r.is_valid
        assert r.clean_name == "我的_文档"


class TestValidateBatch:
    """批量校验测试。"""

    def setup_method(self):
        self.tmp_files = []
        for name in ["文档A_PUBLIC.txt", "文档B_INTERNAL.txt", "文档C_SECRET.txt"]:
            f = tempfile.NamedTemporaryFile(suffix=f"_{name}", delete=False)
            f.write(b"test content")
            f.close()
            self.tmp_files.append(f.name)

    def teardown_method(self):
        for f in self.tmp_files:
            if os.path.exists(f):
                os.unlink(f)

    def test_all_valid(self):
        results = validate_batch_files(self.tmp_files)
        assert len(results) == 3
        assert all(r.is_valid for r in results)

    def test_one_invalid(self):
        bad_file = "C:/nonexistent/普通文件.txt"
        results = validate_batch_files(self.tmp_files + [bad_file])
        assert len(results) == 4
        invalid = [r for r in results if not r.is_valid]
        assert len(invalid) == 1
