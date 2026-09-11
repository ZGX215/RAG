"""交互式知识库问答测试。

用法: python scripts/interactive_qa.py
输入 exit 退出。
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


def _strip_heading(content: str, heading: str) -> str:
    """去掉内容中重复的标题行，避免展示时标题显示两次。"""
    if not heading or heading == "(无标题)":
        return content
    lines = content.split("\n")
    if not lines:
        return content
    first = lines[0].strip()
    if first == heading or first.startswith(heading):
        return "\n".join(lines[1:]).strip()
    return content


def main():
    from app.index.chroma_repo import ChromaRepository
    from app.index.embedder import SentenceEmbedder

    print("=" * 56)
    print("  RAG 交互式问答测试")
    print("=" * 56)

    print("\n 加载模型...")
    try:
        embedder = SentenceEmbedder()
        repo = ChromaRepository(embedder)
        count = repo.count()
        print(f"  维度: {embedder.dimension} | 知识库: {count} 个分块")
        if count == 0:
            print("\n 知识库为空, 先入库再提问")
            print("  python scripts/test_rag_md.py")
            return
    except Exception as e:
        print(f" 加载失败: {e}")
        return

    print("\n 输入问题, exit 退出\n")

    while True:
        try:
            q = input("你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not q:
            continue
        if q.lower() in ("exit", "quit", "退出"):
            break

        try:
            hits = repo.search(embedder.embed_query(q), top_k=5)
        except Exception as e:
            print(f" 出错: {e}\n")
            continue

        if not hits:
            print(" 未找到相关内容\n")
            continue

        for i, h in enumerate(hits):
            heading = h.meta.heading_number or "(无标题)"
            page = f"第{h.meta.page_num}页 | " if h.meta.page_num and h.meta.page_num > 0 else ""
            clean = _strip_heading(h.content, h.meta.heading_number or "")
            preview = clean[:150].replace("\n", " ").strip()
            print(f"  [{i+1}] {page}{heading}")
            print(f"      {preview}")
            if len(clean) > 150:
                print("      ...")
            print()
        print("-" * 40)


if __name__ == "__main__":
    main()
