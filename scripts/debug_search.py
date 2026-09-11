"""调试：直接测试 ChromaDB 搜索，验证 MetaFilter 正确性。"""
import sys
sys.path.insert(0, 'E:/trae/cede/mcu-rag-qa-v2')

from app.contracts import MetaFilter, ChunkTypeClassification
from app.index.chroma_repo import ChromaRepository
from app.index.embedder import SentenceEmbedder

embedder = SentenceEmbedder()
repo = ChromaRepository(
    embedder=embedder,
    persist_dir='E:/trae/cede/mcu-rag-qa-v2/data/chroma_db',
    collection_name='mcu_qa',
)

test_queries = ["公司官网是什么", "融资金额是多少", "CEO年薪", "公司有哪些部门"]
clearance_levels = [
    ("PUBLIC", ChunkTypeClassification.PUBLIC),
    ("INTERNAL", ChunkTypeClassification.INTERNAL),
    ("CONFIDENTIAL", ChunkTypeClassification.CONFIDENTIAL),
]

for query in test_queries:
    print(f"=== 查询: {query} ===")
    query_vec = embedder.embed_query(query)
    
    for label, clearance in clearance_levels:
        mf = MetaFilter(tenant_id="default", max_classification=clearance)
        hits = repo.search(query_vec, top_k=5, meta_filter=mf)
        print(f"  [{label}] clearance={clearance.value}: {len(hits)} hits")
        for h in hits:
            print(f"    [{h.meta.classification.value}] score={h.dense_score:.3f} | {h.meta.doc_name}: {h.content[:50]}...")
    print()