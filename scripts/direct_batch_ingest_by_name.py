"""直接批量入库（同步方式，不依赖 Celery），测试文件名解析功能。"""
import sys
sys.path.insert(0, 'E:/trae/cede/mcu-rag-qa-v2')

from pathlib import Path
from app.ingest.name_classifier import parse_classification_from_filename, validate_batch_files
from app.ingest.reader_factory import get_reader_factory
from app.index.chroma_repo import ChromaRepository
from app.index.embedder import SentenceEmbedder, CachedEmbedder

from config.settings import settings

# 待批量入库的文件
DATA_DIR = Path("E:/trae/cede/mcu-rag-qa-v2/data/batch_test")
file_paths = [
    str(DATA_DIR / "公司简介_PUBLIC.txt"),
    str(DATA_DIR / "组织架构_INTERNAL.txt"),
    str(DATA_DIR / "财务数据_CONFIDENTIAL.txt"),
]

print("=" * 70)
print("批量入库（文件名解析密级）- 同步直接入库测试")
print("=" * 70)

# 第一步：校验全部文件名
print("\n=== Step 1: 校验文件名格式 ===")
results = validate_batch_files(file_paths)
total = len(results)
passed = [r for r in results if r.is_valid]
rejected = [r for r in results if not r.is_valid]

print(f"总文件: {total}")
print(f"通过: {len(passed)}")
print(f"拒绝: {len(rejected)}")

if rejected:
    for r in rejected:
        print(f"  ❌ {Path(r.file_path).name}: {r.error}")
    print("\n按照规则，发现不合格文件 → 整批拒绝")
    sys.exit(1)

for r in passed:
    print(f"  ✅ {Path(r.file_path).name} → name='{r.clean_name}' 密级={r.classification.value}")

# 第二步：全部合格，逐个读取并入库
print("\n=== Step 2: 读取分块并入库 ===")

factory = get_reader_factory()
embedder = CachedEmbedder(SentenceEmbedder())
repo = ChromaRepository(
    embedder=embedder,
    persist_dir=settings.index.persist_dir,
    collection_name=settings.index.collection_name,
)

total_upserted = 0
for r in passed:
    print(f"\n处理: {Path(r.file_path).name}")
    reader = factory.get_reader(r.file_path)
    chunks = reader.read(r.file_path, doc_name=r.clean_name)
    print(f"  提取分块: {len(chunks)}")

    # 应用密级
    for chunk in chunks:
        chunk.meta.classification = r.classification
        chunk.meta.extras["tenant_id"] = "default"
        chunk.meta.extras["dept"] = "default"

    count = repo.upsert(chunks)
    total_upserted += count
    print(f"  写入数据库: {count} chunks (密级={r.classification.value})")

print(f"\n=== 入库完成 ===")
print(f"总计: {total_upserted} chunks 写入数据库")

# 第三步：验证密级分布
print("\n=== Step 3: 验证密级分布 ===")
all_chunks = repo.get_all_chunks()
from collections import Counter
counter = Counter()
for c in all_chunks:
    counter[c.meta.classification.value] += 1

print("当前数据库密级分布:")
for cls, cnt in sorted(counter.items()):
    print(f"  {cls}: {cnt} chunks")

print("\n🎉 批量入库完成！可以测试权限过滤了。")
