"""从文件名解析密级：文件名_权限等级.扩展名 → 密级。

文件名规范：
  {任意名称}_{PUBLIC|INTERNAL|CONFIDENTIAL|SECRET}.{ext}

示例：
  公司简介_PUBLIC.txt        → name="公司简介", classification="public"
  内部纪要_INTERNAL.docx     → name="内部纪要", classification="internal"
  核心财务_confidential.pdf  → name="核心财务", classification="confidential"

校验规则：
  - 后缀不区分大小写
  - 后缀必须是 _PUBLIC / _INTERNAL / _CONFIDENTIAL / _SECRET 之一
  - 文件名中不能只有后缀而无实际名称（如 _PUBLIC.txt 不合法）
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from app.contracts import ChunkTypeClassification
from app.cross.logging import get_logger

logger = get_logger(__name__)

# 合法后缀 → 密级映射（不区分大小写）
_SUFFIX_MAP: dict[str, ChunkTypeClassification] = {
    "public": ChunkTypeClassification.PUBLIC,
    "internal": ChunkTypeClassification.INTERNAL,
    "confidential": ChunkTypeClassification.CONFIDENTIAL,
    "secret": ChunkTypeClassification.SECRET,
}

# 后缀正则：_PUBLIC / _INTERNAL / _CONFIDENTIAL / _SECRET（不区分大小写）
_SUFFIX_PATTERN = re.compile(
    r"_(public|internal|confidential|secret)$", re.IGNORECASE
)


class FileNameParseResult:
    """文件名解析结果。"""

    def __init__(
        self,
        file_path: str,
        clean_name: str = "",
        classification: Optional[ChunkTypeClassification] = None,
        error: str = "",
    ):
        self.file_path = file_path
        self.clean_name = clean_name
        self.classification = classification
        self.error = error

    @property
    def is_valid(self) -> bool:
        return not self.error and self.classification is not None


def parse_classification_from_filename(file_path: str) -> FileNameParseResult:
    """从文件名解析密级。

    Args:
        file_path: 完整文件路径

    Returns:
        FileNameParseResult: 解析结果（is_valid=False 表示格式不合法）
    """
    path = Path(file_path)
    stem = path.stem  # 不含扩展名的文件名

    if not stem:
        return FileNameParseResult(file_path, error="文件名为空")

    # 匹配后缀
    match = _SUFFIX_PATTERN.search(stem)
    if not match:
        return FileNameParseResult(
            file_path,
            error=f"文件名缺少权限后缀，格式应为：文件名_PUBLIC/INTERNAL/CONFIDENTIAL/SECRET（当前: {stem}）",
        )

    suffix_raw = match.group(1).lower()
    classification = _SUFFIX_MAP.get(suffix_raw)
    if classification is None:
        return FileNameParseResult(
            file_path,
            error=f"不支持的权限后缀: {match.group(1)}（合法值: PUBLIC/INTERNAL/CONFIDENTIAL/SECRET）",
        )

    # 提取干净名称（去掉后缀）
    clean_name = stem[: match.start()]

    if not clean_name:
        return FileNameParseResult(
            file_path,
            error=f"文件名不能只有后缀而无实际名称（{stem}），请改为 文件名_PUBLIC 格式",
        )

    return FileNameParseResult(
        file_path=file_path,
        clean_name=clean_name,
        classification=classification,
    )


def validate_batch_files(file_paths: list[str]) -> list[FileNameParseResult]:
    """批量校验文件名，全部合法才返回成功。

    Returns:
        所有文件的解析结果列表。如果任一文件不合法，会包含错误信息。
    """
    results = []
    for fp in file_paths:
        # 检查文件是否存在
        path = Path(fp)
        if not path.exists():
            results.append(FileNameParseResult(fp, error=f"文件不存在: {fp}"))
            continue

        result = parse_classification_from_filename(fp)
        results.append(result)

    return results