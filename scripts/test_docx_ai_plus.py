"""
测试《国务院关于深入实施"人工智能+"行动的意见》DOCX 检索效果
============================================================

用法: python scripts/test_docx_ai_plus.py
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

# 测试文件（从目录读取，避免引号编码不一致）
DOCX_DIR = Path(r'E:\workbuddy\8.16\题7')
docx_files = [f for f in os.listdir(str(DOCX_DIR)) if f.endswith('.docx') and '人工智能' in f and not f.startswith('~$')]
DOCX_FILE = DOCX_DIR / docx_files[0] if docx_files else None

# 测试问题
TEST_QUESTIONS = [
    "人工智能+行动的目标是什么",
    "人工智能如何赋能产业发展",
    "人工智能+行动的重点任务有哪些",
    "人工智能与实体经济怎么融合",
    "人工智能+行动的实施路径是什么",
    "人工智能在哪些行业重点应用",
    "人工智能+行动的保障措施有哪些",
    "人工智能+行动的政策支持",
    "人工智能+的数据安全怎么保障",
    "人工智能+行动的时间节点是什么",
    "人工智能+行动由哪些部门负责",
    "人工智能+行动的试点示范",
    "人工智能+行动的人才培养",
    "人工智能+行动的技术创新体系",
    "人工智能+行动的基础设施建设",
    "人工智能+行动的算力支持",
    "人工智能+行动的开放合作",
    "人工智能+行动的监管机制",
    "人工智能+行动的产业生态怎么构建",
    "人工智能+行动的标准化工作",
]


def print_header(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}")


def test():
    from app.ingest.word_reader import WordReader
    from app.index.embedder import SentenceEmbedder
    from app.index.chroma_repo import ChromaRepository

    print_header("DOCX 检索测试：人工智能+行动意见")

    # 1. 读取并分块
    if not DOCX_FILE or not DOCX_FILE.exists():
        print(f"\n ❌ 文件不存在: {DOCX_FILE}")
        return
    reader = WordReader()
    chunks = reader.read(DOCX_FILE, doc_name="人工智能+行动意见")
    print(f"\n 文件: {DOCX_FILE.name}")
    print(f"  路径: {DOCX_FILE}")
    print(f"  存在: {DOCX_FILE.exists()}")
    print(f" 分块数: {len(chunks)}")
    print(f" 模式: {'按标题样式分块' if any('标题' in (c.meta.heading_number or '') or '第' in (c.meta.heading_number or '') for c in chunks) else '按段落/条款分块'}")

    for i, c in enumerate(chunks):
        heading = c.meta.heading_number or "(无标题)"
        level = c.meta.heading_level
        preview = c.content[:80].replace("\n", " ").strip()
        level_indent = "  " * (level - 1) if level > 0 else ""
        print(f"  {i+1:>2}. {level_indent}[L{level}] {heading:30s} | {preview}...")

    # 2. 嵌入 + 索引
    print(f"\n 加载模型 + 入库...")
    embedder = SentenceEmbedder()
    repo = ChromaRepository(embedder)
    n = repo.upsert(chunks)
    print(f" 已入库: {n} 个分块")

    # 3. 检索测试
    print(f"\n 检索测试 ({len(TEST_QUESTIONS)} 个问题):")
    hits_total = 0
    top3_total = 0
    for i, q in enumerate(TEST_QUESTIONS, 1):
        hits = repo.search(embedder.embed_query(q), top_k=5)
        if hits:
            top = hits[0]
            preview = top.content[:60].replace("\n", " ").strip()
            heading = top.meta.heading_number or "(无标题)"
            level = f"L{top.meta.heading_level}" if top.meta.heading_level else ""
            print(f"  [{i:>2}] {q:30s}  →  {level} {heading:25s} | {preview}...")
            hits_total += 1
            # 检查 Top-3 是否包含正确答案
            for h in hits[:3]:
                hn = h.meta.heading_number or ""
                if any(kw in hn.lower() for kw in q.lower().replace("人工智能+", "人工智能").replace("怎么", "").replace("有什么", "").replace("如何", "").replace("哪些", "").replace("是什么", "").split()[:3] if len(kw) > 2):
                    top3_total += 1
                    break
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