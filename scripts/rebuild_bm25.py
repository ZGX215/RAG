"""重新构建 BM25 索引（注入新数据后需要）。"""
import sys
sys.path.insert(0, 'E:/trae/cede/mcu-rag-qa-v2')

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
# 强制触发重新构建
retriever._ensure_bm25()
print(f"BM25 索引重新构建完成：{len(retriever._bm25_chunks)} chunks")
