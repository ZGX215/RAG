"""
测试 RAG 学习模块 Markdown 文档
================================

用法: python scripts/test_rag_md.py

测试文件: D:\AI知识库\基础知识\14-RAG学习模块.md
"""

import os
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

os.environ["HF_HOME"] = str(project_root / "data" / "models")
os.environ["HF_HUB_CACHE"] = str(project_root / "data" / "models")
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

DATA_DIR = project_root / "data"

# 测试文件
MD_FILE = "D:/AI知识库/基础知识/14-RAG学习模块.md"

# 测试问题
TEST_QUESTIONS = [
    "RAG 的全称是什么",
    "RAG 解决哪三个痛点",
    "RAG 的三阶段是什么",
    "RAG 与微调的区别是什么",
    "Naive RAG 和 Advanced RAG 的区别",
    "什么是 chunking 切分",
    "什么是 embedding 向量化",
    "向量检索和 BM25 的区别",
    "什么是混合检索",
    "什么是 ReRank 重排",
    "RAG 的常见坑有哪些",
    "RAG 的评估维度有哪些",
    "GraphRAG 和 RAG 的关系",
    "RAG 的 Prompt 需要包含什么",
    "RAG 项目用什么向量数据库",
]


def print_header(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}")


def test():
    from app.index.chroma_repo import ChromaRepository
    from app.index.embedder import SentenceEmbedder
    from app.ingest.markdown_reader import MarkdownReader

    print_header("RAG 学习模块 Markdown 检索测试")
    print(f"  文件: {MD_FILE}")

    # 1. 读取并分块
    reader = MarkdownReader()
    chunks = reader.read(MD_FILE, doc_name="RAG学习模块")
    print(f"\n📦 分块数: {len(chunks)}")
    for i, c in enumerate(chunks):
        heading = c.meta.heading_number or "(无标题)"
        preview = c.content[:50].replace("\n", " ")
        print(f"  {i+1:>2}. [{heading}] {preview}...")

    # 2. 嵌入 + 索引
    print("\n🔧 加载模型 + 入库...")
    embedder = SentenceEmbedder()
    repo = ChromaRepository(embedder)
    n = repo.upsert(chunks)
    print(f"  已入库: {n} 个分块")

    # 3. 检索测试
    print(f"\n🔍 检索测试 ({len(TEST_QUESTIONS)} 个问题):")
    passed = 0
    for i, q in enumerate(TEST_QUESTIONS, 1):
        hits = repo.search(embedder.embed_query(q), top_k=3)
        if hits:
            top = hits[0]
            preview = top.content[:40].replace("\n", " ")
            heading = top.meta.heading_number or "(无标题)"
            print(f"  [{i:>2}] {q:30s} → {heading:20s} | {preview}...")
            passed += 1
        else:
            print(f"  [{i:>2}] {q:30s} → ❌ 未命中")

    print(f"\n✅ 命中: {passed}/{len(TEST_QUESTIONS)} ({passed/len(TEST_QUESTIONS)*100:.1f}%)")

    print("\n  💡 修改 TEST_QUESTIONS 列表即可换问题测试")


if __name__ == "__main__":
    # 清理旧索引（Python 内部删除，避免 shell 权限问题）
    chroma_dir = DATA_DIR / "chroma_db"
    if chroma_dir.exists():
        for item in chroma_dir.iterdir():
            if item.is_dir():
                for f in item.iterdir():
                    f.unlink(missing_ok=True)
                item.rmdir()
            else:
                item.unlink(missing_ok=True)
        chroma_dir.rmdir()
        print(" 已清理旧索引")
    test()
