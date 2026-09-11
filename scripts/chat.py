"""
交互式 RAG 问答终端
====================

用法: python scripts/chat.py

在终端输入问题，实时检索知识库并返回结果。
输入 exit 或 quit 退出。
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


def main():
    from app.ingest.reader_factory import get_reader_factory
    from app.index.embedder import SentenceEmbedder
    from app.index.chroma_repo import ChromaRepository

    print("=" * 55)
    print("  RAG 交互式问答终端")
    print("=" * 55)

    # 1. 加载模型
    print("\n🔧 加载模型...")
    embedder = SentenceEmbedder()
    repo = ChromaRepository(embedder)
    print(f"   模型维度: {embedder.dimension}")

    # 2. 查询已有文档数
    count = repo.count()
    print(f"   知识库文档数: {count}")

    if count == 0:
        print("\n⚠️  知识库为空！请先入库文档。")
        print("   用法: python scripts/ingest.py <文件路径>")
        return

    # 3. 交互循环
    print("\n💡 输入问题开始检索，输入 exit 退出\n")
    while True:
        try:
            question = input("🧑 你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not question:
            continue
        if question.lower() in ("exit", "quit", "退出"):
            break

        # 检索
        hits = repo.search(embedder.embed_query(question), top_k=5)

        if not hits:
            print("🤖 助手: 未找到相关内容\n")
            continue

        print(f"🤖 助手: 找到 {len(hits)} 个相关片段\n")
        for i, h in enumerate(hits):
            heading = h.meta.heading_number or "(无标题)"
            page = f"第{h.meta.page_num}页 | " if h.meta.page_num and h.meta.page_num > 0 else ""
            preview = h.content[:120].replace("\n", " ")
            print(f"  [{i+1}] {page}{heading}")
            print(f"      {preview}...")
            print()

        if len(hits) >= 3:
            print(f"  (Top-1 来源: {hits[0].meta.heading_number or '无标题'})\n")


if __name__ == "__main__":
    main()
