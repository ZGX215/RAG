"""权限测试数据准备脚本。
创建三个不同密级的文档切片并写入 ChromaDB，然后执行权限查询测试。
"""
import sys
sys.path.insert(0, 'E:/trae/cede/mcu-rag-qa-v2')

import uuid
from pathlib import Path

from app.contracts import (
    Chunk, ChunkMeta, ChunkType, ChunkTypeClassification,
    CLASSIFICATION_LEVELS, MetaFilter, Hit,
)
from app.index.chroma_repo import ChromaRepository
from app.index.embedder import SentenceEmbedder
from app.ingest.txt_reader import TxtReader


def ingest_with_classification(
    repo: ChromaRepository,
    file_path: str,
    doc_name: str,
    classification: ChunkTypeClassification,
) -> int:
    """读取文件并用指定密级写入 ChromaDB。"""
    reader = TxtReader()
    chunks = reader.read(file_path, doc_name=doc_name)
    
    for chunk in chunks:
        chunk.meta.classification = classification
        chunk.meta.extras["tenant_id"] = "default"
        chunk.meta.extras["dept"] = "default"
        # 重新生成 chunk_id 确保唯一
        chunk.chunk_id = uuid.uuid4().hex
    
    count = repo.upsert(chunks)
    print(f"  [{classification.value}] {doc_name}: {len(chunks)} chunks upserted")
    return count


def test_qa_with_clearance(
    repo: ChromaRepository,
    embedder: SentenceEmbedder,
    query: str,
    clearance: ChunkTypeClassification,
    top_k: int = 5,
) -> list[Hit]:
    """模拟 QA 请求，用指定密级查询。"""
    meta_filter = MetaFilter(
        tenant_id="default",
        max_classification=clearance,
    )
    
    query_emb = embedder.embed_query(query)
    hits = repo.search(query_emb, top_k=top_k, meta_filter=meta_filter)
    return hits


def main():
    print("=" * 60)
    print("权限 Pre-Filter 测试")
    print("=" * 60)
    
    # 初始化
    embedder = SentenceEmbedder()
    repo = ChromaRepository(
        embedder=embedder,
        persist_dir='E:/trae/cede/mcu-rag-qa-v2/data/chroma_db',
        collection_name='mcu_qa',
    )
    
    # 先清空已有数据
    print(f"\n当前数据量: {repo.count()} chunks")
    if repo.count() > 0:
        print("已有数据，跳过注入（如需重新注入请先手动清空）")
    else:
        print("\n注入测试数据...")
        data_dir = Path('E:/trae/cede/mcu-rag-qa-v2/data')
        files = [
            (str(data_dir / "test_permission_public.txt"), "公开信息", ChunkTypeClassification.PUBLIC),
            (str(data_dir / "test_permission_internal.txt"), "内部信息", ChunkTypeClassification.INTERNAL),
            (str(data_dir / "test_permission_confidential.txt"), "机密信息", ChunkTypeClassification.CONFIDENTIAL),
        ]
        total = 0
        for file_path, doc_name, classification in files:
            count = ingest_with_classification(repo, file_path, doc_name, classification)
            total += count
        print(f"\n总计注入: {total} chunks")
    
    print(f"\n当前数据量: {repo.count()} chunks")
    
    # 验证数据
    all_chunks = repo.get_all_chunks()
    print(f"\n已索引文档: {len(all_chunks)} chunks")
    by_level = {}
    for c in all_chunks:
        lvl = c.meta.classification.value
        by_level.setdefault(lvl, 0)
        by_level[lvl] += 1
    for lvl, cnt in sorted(by_level.items()):
        print(f"  {lvl}: {cnt} chunks")
    
    # ============================================================
    # 权限测试用例
    # ============================================================
    test_queries = [
        "公司官网",
        "公司组织架构",
        "融资金额",
        "公司有哪些部门",
        "CEO年薪",
        "公司联系方式",
    ]
    
    test_cases = [
        ("PUBLIC 用户", ChunkTypeClassification.PUBLIC, 0),
        ("INTERNAL 用户", ChunkTypeClassification.INTERNAL, 1),
        ("CONFIDENTIAL 用户", ChunkTypeClassification.CONFIDENTIAL, 2),
    ]
    
    # 预期结果：密级数值 <= 用户密级数值的才应该返回
    print("\n" + "=" * 60)
    print("权限过滤测试结果")
    print("=" * 60)
    
    all_pass = True
    for query in test_queries:
        print(f"\n查询: [{query}]")
        for label, clearance, _ in test_cases:
            hits = test_qa_with_clearance(repo, embedder, query, clearance)
            
            # 检查返回的 chunks 是否都 <= 用户密级
            violated = False
            for h in hits:
                chunk_level = CLASSIFICATION_LEVELS.get(h.meta.classification, 0)
                user_level = CLASSIFICATION_LEVELS.get(clearance, 0)
                if chunk_level > user_level:
                    violated = True
                    print(f"  [越权] {h.meta.classification.value} > {clearance.value} | {h.content[:50]}")
            
            if violated:
                print(f"  ❌ {label}: 存在越权数据!")
                all_pass = False
            else:
                classifications = [h.meta.classification.value for h in hits]
                print(f"  ✅ {label}: {len(hits)} hits, 密级分布={classifications}")
    
    print("\n" + "=" * 60)
    if all_pass:
        print("🎉 所有权限测试通过！越权数据未进入候选。")
    else:
        print("❌ 存在权限越权问题！")
    print("=" * 60)


if __name__ == "__main__":
    main()