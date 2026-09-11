"""
测试"东数西算"PDF 检索效果
============================

用法: python scripts/test_pdf_dongshisuan.py
"""

import os, sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

os.environ["HF_HOME"] = str(project_root / "data" / "models")
os.environ["HF_HUB_CACHE"] = str(project_root / "data" / "models")
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

DATA_DIR = project_root / "data"

# 测试文件
PDF_FILE = Path(r'E:\workbuddy\8.16\题7\附件2：《关于深入实施“东数西算”工程加快构建全国一体化算力网的实施意见》.pdf')

# 测试问题
TEST_QUESTIONS = [
    "东数西算工程的目标是什么",
    "全国一体化算力网是什么",
    "算力基础设施有哪些",
    "东数西算的实施意见提出了什么",
    "算力网怎么构建",
    "算力调度是什么",
    "算力枢纽节点有哪些",
    "数据中心布局有什么要求",
    "算力网络的架构是什么",
    "算力与电力协同是什么",
    "算力网络的安全怎么保障",
    "算力资源池怎么建设",
    "算力网的算力调度机制是什么",
    "算力网络如何实现统一调度",
    "算力网络的数据传输有什么要求",
    "算力网络如何保障数据安全",
    "算力网络的能耗管理",
    "算力网络如何实现绿色低碳",
    "算力网络的标准体系怎么建",
    "算力网络如何与产业融合",
]


def print_header(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}")


def test():
    from app.ingest.pdf_reader import PdfReader
    from app.index.embedder import SentenceEmbedder
    from app.index.chroma_repo import ChromaRepository

    print_header("PDF 检索测试：东数西算实施意见")

    # 1. 读取并分块
    reader = PdfReader()
    chunks = reader.read(PDF_FILE, doc_name="东数西算实施意见")
    print(f"\n 文件: {PDF_FILE}")
    print(f" 分块数: {len(chunks)}")
    print(f" 模式: {'法律条款模式' if any('第' in (c.meta.heading_number or '') and '条' in (c.meta.heading_number or '') for c in chunks) else '逐页/段落模式'}")

    for i, c in enumerate(chunks):
        heading = c.meta.heading_number or "(无标题)"
        page = f"第{c.meta.page_num}页" if c.meta.page_num and c.meta.page_num > 0 else ""
        preview = c.content[:80].replace("\n", " ").strip()
        print(f"  {i+1:>2}. [{page}] {heading:20s} | {preview}...")

    # 2. 嵌入 + 索引
    print(f"\n 加载模型 + 入库...")
    embedder = SentenceEmbedder()
    repo = ChromaRepository(embedder)
    n = repo.upsert(chunks)
    print(f" 已入库: {n} 个分块")

    # 3. 检索测试
    print(f"\n 检索测试 ({len(TEST_QUESTIONS)} 个问题):")
    hits_total = 0
    for i, q in enumerate(TEST_QUESTIONS, 1):
        hits = repo.search(embedder.embed_query(q), top_k=3)
        if hits:
            top = hits[0]
            preview = top.content[:60].replace("\n", " ").strip()
            heading = top.meta.heading_number or "(无标题)"
            page = f"第{top.meta.page_num}页" if top.meta.page_num and top.meta.page_num > 0 else ""
            print(f"  [{i:>2}] {q:30s}  →  {page} {heading:20s}  |  {preview}...")
            hits_total += 1
        else:
            print(f"  [{i:>2}] {q:30s}  →  ❌ 未命中")

    print(f"\n 命中率: {hits_total}/{len(TEST_QUESTIONS)} ({hits_total/len(TEST_QUESTIONS)*100:.1f}%)")


if __name__ == "__main__":
    # 清理旧索引
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