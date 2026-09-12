"""直接通过代码方式批量入库带分级的文档。"""
import sys

sys.path.insert(0, 'E:/trae/cede/mcu-rag-qa-v2')

from app.contracts import ChunkTypeClassification
from app.index.chroma_repo import ChromaRepository
from app.index.embedder import SentenceEmbedder
from app.ingest.reader_factory import get_reader_factory

embedder = SentenceEmbedder()
repo = ChromaRepository(
    embedder=embedder,
    persist_dir='E:/trae/cede/mcu-rag-qa-v2/data/chroma_db',
    collection_name='mcu_qa',
)

# 待入库文档
files = [
    ("E:/trae/cede/mcu-rag-qa-v2/data/test_permission_public.txt", "公开信息", "public"),
    ("E:/trae/cede/mcu-rag-qa-v2/data/test_permission_internal.txt", "内部信息", "internal"),
    ("E:/trae/cede/mcu-rag-qa-v2/data/test_permission_confidential.txt", "机密信息", "confidential"),
]

factory = get_reader_factory()
total = 0

for file_path, doc_name, classification_str in files:
    print(f"\n处理: {file_path}")
    reader = factory.get_reader(file_path)
    chunks = reader.read(file_path, doc_name=doc_name)
    
    # 应用密级
    try:
        cls_level = ChunkTypeClassification(classification_str)
    except ValueError:
        cls_level = ChunkTypeClassification.PUBLIC
    for chunk in chunks:
        chunk.meta.classification = cls_level
        chunk.meta.extras["tenant_id"] = "default"
        chunk.meta.extras["dept"] = "default"
    
    count = repo.upsert(chunks)
    print(f"  成功入库: {count} chunks (classification={classification_str})")
    total += count

print("\n=== 入库完成 ===")
print(f"总计: {total} chunks")
print(f"数据库总数: {repo.count()}")

# 验证密级分布
all_chunks = repo.get_all_chunks()
from collections import Counter

counter = Counter()
for c in all_chunks:
    counter[c.meta.classification.value] += 1

print("\n密级分布:")
for cls, cnt in sorted(counter.items()):
    print(f"  {cls}: {cnt} chunks")
