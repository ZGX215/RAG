"""诊断检索质量：分析每个问题 Top-5 的匹配情况。"""

import os
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

os.environ["HF_HOME"] = str(project_root / "data" / "models")
os.environ["HF_HUB_CACHE"] = str(project_root / "data" / "models")
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

from app.index.chroma_repo import ChromaRepository
from app.index.embedder import SentenceEmbedder

embedder = SentenceEmbedder()
repo = ChromaRepository(embedder)
count = repo.count()
print(f"知识库: {count} 个分块\n")

# 用户觉得不准确的几个问题
queries = [
    "RAG解决哪三个痛点",
    "RAG的三阶段是什么",
    "Naive RAG 和 Advanced RAG 的区别",
    "什么是混合检索",
    "RAG的评估维度有哪些",
    "RAG项目用什么向量数据库",
    "大语言模型的三大痛点",
]

for q in queries:
    hits = repo.search(embedder.embed_query(q), top_k=5)
    print(f"Q: {q}")

    # 获取所有分块的标题，标注"正确"答案
    all_chunks = repo.get_all_chunks() if hasattr(repo, 'get_all_chunks') else []
    correct_heading = ""
    if "痛点" in q:
        correct_heading = "1. RAG 是什么 + 为什么存在（面试第一问）"
    elif "三阶段" in q:
        correct_heading = "3. 核心流程（RAG 三阶段，必须能默画出来）"
    elif "Naive" in q or "Advanced" in q:
        correct_heading = "2. 三大范式（了解演进，面试显深度）"
    elif "混合检索" in q:
        correct_heading = "4.3 检索召回（单路不够，要双路）"
    elif "评估维度" in q:
        correct_heading = "7. RAG 的坑与评估（面试加分，体现经验）"
    elif "向量数据库" in q:
        correct_heading = "5. 向量数据库选型"

    for i, h in enumerate(hits):
        heading = h.meta.heading_number or "(无标题)"
        preview = h.content[:80].replace("\n", " ").strip()
        is_correct = " ✓" if heading == correct_heading else ""
        print(f"  [{i+1}] {heading}{is_correct}")
        print(f"      {preview}...")
    print()

    # 分析问题
    if correct_heading:
        rank = next((i+1 for i, h in enumerate(hits) if h.meta.heading_number == correct_heading), -1)
        if rank == 1:
            print("  >> 结果: 正确，Top-1 命中")
        elif rank > 1:
            print(f"  >> 结果: 排在第 {rank} 位，但未进 Top-1")
        else:
            print("  >> 结果: 未进入 Top-5")
        print()