"""验证权限过滤是否仍然正确工作。"""
import sys
sys.path.insert(0, 'E:/trae/cede/mcu-rag-qa-v2')

from app.contracts import ChunkTypeClassification, MetaFilter
from app.index.chroma_repo import ChromaRepository
from app.index.embedder import SentenceEmbedder
from app.retrieve.hybrid import HybridRetriever

embedder = SentenceEmbedder()
repo = ChromaRepository(
    embedder=embedder,
    persist_dir='E:/trae/cede/mcu-rag-qa-v2/data/chroma_db',
    collection_name='mcu_qa',
)

retriever = HybridRetriever(repo=repo, embedder=embedder)
# 强制重新构建 BM25 索引
retriever._ensure_bm25()
print(f"BM25 索引: {len(retriever._bm25_chunks)} chunks\n")

test_cases = [
    ("融资金额", "public"),
    ("融资金额", "internal"),
    ("融资金额", "confidential"),
    ("CEO年薪", "public"),
    ("CEO年薪", "internal"),
    ("CEO年薪", "confidential"),
    ("部门设置", "public"),
    ("部门设置", "internal"),
    ("部门设置", "confidential"),
]

print("=" * 70)
print("权限过滤验证")
print("=" * 70)

all_pass = True
for query, clearance_str in test_cases:
    clearance = ChunkTypeClassification(clearance_str)
    mf = MetaFilter(tenant_id="default", max_classification=clearance)
    hits = retriever.search(query, top_k=5, meta_filter=mf)
    
    # 检查权限
    from app.contracts import CLASSIFICATION_LEVELS
    clearance_level = CLASSIFICATION_LEVELS[clearance]
    classified = [h.meta.classification.value for h in hits]
    unauthorized = [c for c in classified if CLASSIFICATION_LEVELS[ChunkTypeClassification(c)] > clearance_level]
    
    if unauthorized:
        print(f"❌ [{clearance_str}] '{query}' 发现越权: {unauthorized}")
        all_pass = False
    else:
        print(f"✅ [{clearance_str}] '{query}' → {len(hits)} hits: {classified}")

print("\n" + "=" * 70)
if all_pass:
    print("🎉 所有权限验证通过！")
else:
    print("❌ 存在权限问题")
print("=" * 70)
