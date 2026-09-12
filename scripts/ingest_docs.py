"""文档入库工具（同步执行，不依赖 Celery / Redis）。

用法：
    python scripts/ingest_docs.py <文件或目录> [密级]

示例：
    python scripts/ingest_docs.py data/raw_docs/STM32F103/STM32F103C8T6_中文数据手册.pdf
    python scripts/ingest_docs.py data/batch_test/          # 目录：按文件名后缀解析密级
    python scripts/ingest_docs.py some.pdf internal         # 强制指定密级

密级解析：显式参数优先；未给出时从文件名后缀 _PUBLIC / _INTERNAL /
_CONFIDENTIAL / _SECRET 推断；都没有则默认 public。

为什么提供同步版本：
    正式入库链路是 API → Celery → Worker（需要 Redis）。但在新环境或本地
    只想快速把手册灌进去验证检索效果时，为此拉起 Redis + worker 过重。
    本脚本直接调用 reader → embedder → ChromaRepository，跳过消息队列。

支持格式：PDF / DOCX / Markdown / TXT（由 ReaderFactory 按扩展名分发）。
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.contracts import ChunkTypeClassification  # noqa: E402
from app.index.chroma_repo import ChromaRepository  # noqa: E402
from app.index.embedder import SentenceEmbedder  # noqa: E402
from app.ingest.reader_factory import get_reader_factory  # noqa: E402
from config.settings import settings  # noqa: E402

SUPPORTED_SUFFIXES = {".pdf", ".docx", ".md", ".txt"}

LEVEL_BY_SUFFIX = {
    "_PUBLIC": ChunkTypeClassification.PUBLIC,
    "_INTERNAL": ChunkTypeClassification.INTERNAL,
    "_CONFIDENTIAL": ChunkTypeClassification.CONFIDENTIAL,
    "_SECRET": ChunkTypeClassification.SECRET,
}

LEVEL_BY_NAME = {level.value: level for level in ChunkTypeClassification}


def resolve_level(path: Path, forced: str | None) -> ChunkTypeClassification:
    """确定密级：显式参数 > 文件名后缀 > 默认 public。"""
    if forced:
        level = LEVEL_BY_NAME.get(forced.lower())
        if level is None:
            raise SystemExit(
                f"非法密级 {forced!r}，可选：{sorted(LEVEL_BY_NAME)}"
            )
        return level

    stem = path.stem.upper()
    for suffix, level in LEVEL_BY_SUFFIX.items():
        if stem.endswith(suffix):
            return level
    return ChunkTypeClassification.PUBLIC


def collect_files(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    return sorted(
        p for p in target.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES
    )


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    target = Path(sys.argv[1])
    forced = sys.argv[2] if len(sys.argv) > 2 else None

    if not target.exists():
        print(f"路径不存在: {target}")
        return 1

    files = collect_files(target)
    if not files:
        print(f"未找到可入库文件（支持 {sorted(SUPPORTED_SUFFIXES)}）: {target}")
        return 1

    embedder = SentenceEmbedder()
    repo = ChromaRepository(
        embedder=embedder,
        persist_dir=settings.index.persist_dir,
        collection_name=settings.index.collection_name,
    )
    factory = get_reader_factory()

    before = repo.count()
    print(f"入库前库内片段数: {before}")
    print(f"待处理文件: {len(files)}\n")

    added = 0
    for f in files:
        level = resolve_level(f, forced)
        try:
            reader = factory.get_reader(str(f))
            chunks = reader.read(str(f), doc_name=f.stem)
        except Exception as e:
            print(f"  [跳过] {f.name}: {type(e).__name__}: {e}")
            continue

        if not chunks:
            print(f"  [空]   {f.name}: 未切出任何片段")
            continue

        for c in chunks:
            c.meta.classification = level
            c.meta.extras["tenant_id"] = "default"
            c.meta.extras["dept"] = "default"

        n = repo.upsert(chunks)
        added += n
        print(f"  [OK]   {f.name}: {n} 片段（密级 {level.value}）")

    print(f"\n入库完成：新增 {added} 片段，库内共 {repo.count()}")

    dist = Counter(c.meta.classification.value for c in repo.get_all_chunks())
    print("密级分布:", dict(sorted(dist.items())))
    print("\n提示：检索侧 BM25 索引如需刷新，请再执行 scripts/rebuild_bm25.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
