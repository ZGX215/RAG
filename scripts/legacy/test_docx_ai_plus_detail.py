"""
详细测试 DOCX "人工智能+" 检索命中率，统计 Top-1/Top-3
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
DOCX_DIR = Path(r'E:\workbuddy\8.16\题7')
docx_files = [f for f in os.listdir(str(DOCX_DIR)) if f.endswith('.docx') and '人工智能' in f and not f.startswith('~$')]
DOCX_FILE = DOCX_DIR / docx_files[0] if docx_files else None

# 测试问题 + 正确标题关键词匹配
# 格式: (问题, 应该命中的标题包含什么关键词)
TEST_QUESTIONS = [
    ("人工智能+行动的目标是什么", "总体要求"),
    ("人工智能如何赋能产业发展", "培育智能原生新模式"),
    ("人工智能+行动的重点任务有哪些", "二、"),
    ("人工智能与实体经济怎么融合", "推进工业全要素智能化"),
    ("人工智能+行动的实施路径是什么", "总体要求"),
    ("人工智能在哪些行业重点应用", "农业数智化|服务业|工业"),
    ("人工智能+行动的保障措施有哪些", "保障措施|政策法规"),
    ("人工智能+行动的政策支持", "强化政策法规"),
    ("人工智能+的数据安全怎么保障", "安全能力"),
    ("人工智能+行动由哪些部门负责", "组织实施"),
    ("人工智能+行动的试点示范", "生态|开放"),
    ("人工智能+行动的人才培养", "人才队伍"),
    ("人工智能+行动的技术创新体系", "基础能力|模型基础能力"),
    ("人工智能+行动的基础设施建设", "算力统筹"),
    ("人工智能+行动的算力支持", "强化智能算力统筹"),
    ("人工智能+行动的开放合作", "普惠共享|全球治理"),
    ("人工智能+行动的监管机制", "安全能力"),
    ("人工智能+行动的产业生态怎么构建", "开源生态"),
    ("人工智能+行动的标准化工作", "标准"),
]


def print_header(text):
    print(f"\n{'='*70}")
    print(f"  {text}")
    print(f"{'='*70}")


def check_hit(hit_heading: str, correct_keywords: str) -> tuple[bool, bool]:
    """检查是否命中正确标题。返回 (top1_hit, top3_hit)。"""
    keywords = [kw.strip() for kw in correct_keywords.split('|') if kw.strip()]
    hit_heading_lower = hit_heading.lower()
    for kw in keywords:
        if kw.lower() in hit_heading_lower:
            return True, True
    return False, False


def test():
    from app.index.chroma_repo import ChromaRepository
    from app.index.embedder import SentenceEmbedder
    from app.ingest.word_reader import WordReader
    from app.retrieve.hybrid import HybridRetriever
    from app.retrieve.query_understanding import QueryUnderstanding

    print_header("DOCX 详细检索测试：人工智能+行动意见")

    if not DOCX_FILE or not DOCX_FILE.exists():
        print(f"\n ❌ 文件不存在: {DOCX_FILE}")
        return
    print(f"\n 文件: {DOCX_FILE.name}")
    print(f" 路径: {DOCX_FILE}")
    print(f" 存在: {DOCX_FILE.exists()}")

    # 1. 读取并分块
    reader = WordReader()
    chunks = reader.read(DOCX_FILE, doc_name="人工智能+行动意见")
    print("\n 分块结果:")
    print(f"  总分块数: {len(chunks)}")

    for i, c in enumerate(chunks[:10]):  # 只显示前 10 个
        heading = c.meta.heading_number or "(无标题)"
        level = c.meta.heading_level
        preview = c.content[:60].replace("\n", " ").strip()
        indent = "  " * (level - 1)
        print(f"  {i+1:>2}. {indent}[L{level}] {heading:30s} | {preview}...")
    if len(chunks) > 10:
        print(f"  ... 还有 {len(chunks) - 10} 个块")

    # 2. 嵌入 + 索引 + 混合检索
    print("\n 加载模型 + 入库...")
    embedder = SentenceEmbedder()
    repo = ChromaRepository(embedder)
    n = repo.upsert(chunks)
    qu = QueryUnderstanding()
    retriever = HybridRetriever(repo=repo, embedder=embedder, query_understanding=qu)
    print(f" 已入库: {n} 个分块")
    print(f" 模型维度: {embedder.dimension}")
    print(" 使用混合检索（稠密+稀疏，带降权）")

    # 3. 详细检索测试
    print(f"\n 详细检索测试 ({len(TEST_QUESTIONS)} 个问题):")
    print(f"\n {'序号':<3} {'问题':<32} {'Top-1':<28} {'命中?':<6} {'Top-3':<6}")
    print(f" {'-'*3} {'-'*32} {'-'*28} {'-'*6} {'-'*6}")

    top1_hits = 0
    top3_hits = 0

    for i, (q, correct_kws) in enumerate(TEST_QUESTIONS, 1):
        hits = retriever.search(q, top_k=5)
        if not hits:
            print(f" [{i:>2}] {q:<32}  ❌ 未命中")
            continue

        top1_heading = hits[0].meta.heading_number or "(无标题)"
        top1_short = top1_heading[:25] + ('...' if len(top1_heading) > 25 else '')

        # 检查 Top-1 和 Top-3
        top1_hit, _ = check_hit(top1_heading, correct_kws)
        top3_hit = False
        for h in hits[:3]:
            h_heading = h.meta.heading_number or ""
            hit, _ = check_hit(h_heading, correct_kws)
            if hit:
                top3_hit = True
                break

        if top1_hit:
            top1_hits += 1
        if top3_hit:
            top3_hits += 1

        status1 = "✓" if top1_hit else "✗"
        status3 = "✓" if top3_hit else "✗"
        print(f" [{i:>2}] {q:<32} {top1_short:<28} {status1:^6} {status3:^6}")

    # 统计
    total = len(TEST_QUESTIONS)
    top1_rate = top1_hits / total * 100
    top3_rate = top3_hits / total * 100

    print(f"\n{'='*70}")
    print(" 统计结果:")
    print(f"    总问题数: {total}")
    print(f"    Top-1 命中: {top1_hits}/{total}  ({top1_rate:.1f}%)")
    print(f"    Top-3 命中: {top3_hits}/{total}  ({top3_rate:.1f}%)")
    print(f"{'='*70}")


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