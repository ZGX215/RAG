import hashlib, json, os, sys, tempfile, shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import Counter, defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.contracts import Chunk, ChunkMeta, ChunkType, ChunkTypeClassification, SourceReader

# ============================
# 1. Create test files
# ============================

_TEST_CONTENT = """# 第一章 总则

第一条 为了保护个人信息权益，规范个人信息处理活动，促进个人信息合理利用，根据宪法，制定本法。

第二条 自然人的个人信息受法律保护，任何组织、个人不得侵害自然人的个人信息权益。

# 第二章 个人信息处理规则

第三条 在中华人民共和国境内处理自然人个人信息的活动，适用本法。

第四条 个人信息是以电子或者其他方式记录的与已识别或者可识别的自然人有关的各种信息，不包括匿名化处理后的信息。

第五条 处理个人信息应当遵循合法、正当、必要和诚信原则，不得通过误导、欺诈、胁迫等方式处理个人信息。

第六条 处理个人信息应当具有明确、合理的目的，并应当与处理目的直接相关，采取对个人权益影响最小的方式。

# 第三章 敏感个人信息

第二十八条 敏感个人信息是一旦泄露或者非法使用，容易导致自然人的人格尊严受到侵害或者人身、财产安全受到危害的个人信息，包括生物识别、宗教信仰、特定身份、医疗健康、金融账户、行踪轨迹等信息，以及不满十四周岁未成年人的个人信息。

第二十九条 处理敏感个人信息应当取得个人的单独同意，法律、行政法规规定处理敏感个人信息应当取得书面同意的，从其规定。

第三十条 处理敏感个人信息的，应当向个人告知处理敏感个人信息的必要性和对个人权益的影响。

# 第四章 法律责任

第六十六条 违反本法规定处理个人信息，或者处理个人信息未履行本法规定的个人信息保护义务的，由履行个人信息保护职责的部门责令改正，给予警告，没收违法所得。

第六十七条 有前款规定的违法行为，情节严重的，由省级以上履行个人信息保护职责的部门责令改正，并处五千万元以下或者上一年度营业额百分之五以下罚款。
"""

def create_pdf(path):
    from fpdf import FPDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Personal Information Protection Law", ln=True, align="C")
    pdf.ln(5)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "Chapter 1 General Provisions", ln=True)
    pdf.ln(3)
    pdf.set_font("Helvetica", "", 11)
    lines = [
        "Article 1 This Law is formulated to protect the rights and interests of natural persons in personal information.",
        "Article 2 The personal information of natural persons shall be protected by law.",
        "Article 3 This Law shall apply to the processing of personal information of natural persons within the territory of the People's Republic of China.",
        "",
        "Chapter 2 Rules on Personal Information Processing",
        "Article 4 Personal information refers to all kinds of information recorded by electronic or other means.",
        "Article 5 The processing of personal information shall follow the principles of legality, legitimacy, necessity and good faith.",
        "Article 6 The processing of personal information should have a clear and reasonable purpose.",
        "",
        "Chapter 3 Sensitive Personal Information",
        "Article 28 Sensitive personal information is information that may cause harm to the dignity of natural persons.",
        "Article 29 Separate consent shall be obtained for processing sensitive personal information.",
        "",
        "Chapter 4 Legal Liability",
        "Article 66 Violations of this Law shall be ordered to make corrections and given warnings.",
        "Article 67 For serious violations, a fine of up to 50 million yuan or 5 percent of the previous year turnover."
    ]
    for line in lines:
        pdf.cell(0, 8, line, ln=True)
    pdf.output(path)
    return path

def create_docx(path):
    from docx import Document
    doc = Document()
    doc.add_heading("第一章 总则", level=1)
    doc.add_paragraph("第一条 为了保护个人信息权益，规范个人信息处理活动，促进个人信息合理利用，根据宪法，制定本法。")
    doc.add_paragraph("第二条 自然人的个人信息受法律保护，任何组织、个人不得侵害自然人的个人信息权益。")
    doc.add_heading("第二章 个人信息处理规则", level=1)
    doc.add_paragraph("第三条 在中华人民共和国境内处理自然人个人信息的活动，适用本法。")
    doc.add_paragraph("第四条 个人信息是以电子或者其他方式记录的与已识别或者可识别的自然人有关的各种信息。")
    doc.add_paragraph("第五条 处理个人信息应当遵循合法、正当、必要和诚信原则。")
    doc.add_paragraph("第六条 处理个人信息应当具有明确、合理的目的，并应当与处理目的直接相关。")
    doc.add_heading("第三章 敏感个人信息", level=1)
    doc.add_paragraph("第二十八条 敏感个人信息是一旦泄露或者非法使用，容易导致自然人的人格尊严受到侵害或者人身、财产安全受到危害的个人信息。")
    doc.add_paragraph("第二十九条 处理敏感个人信息应当取得个人的单独同意。")
    doc.add_paragraph("第三十条 处理敏感个人信息的，应当向个人告知处理敏感个人信息的必要性和对个人权益的影响。")
    doc.add_heading("第四章 法律责任", level=1)
    doc.add_paragraph("第六十六条 违反本法规定处理个人信息，或者处理个人信息未履行本法规定的个人信息保护义务的，由履行个人信息保护职责的部门责令改正。")
    doc.add_paragraph("第六十七条 情节严重的，由省级以上履行个人信息保护职责的部门责令改正，并处五千万元以下罚款。")
    doc.save(path)
    return path

def create_md(path):
    with open(path, "w", encoding="utf-8") as f:
        f.write(_TEST_CONTENT)
    return path

def create_txt(path):
    plain = """第一章 总则

第一条 为了保护个人信息权益，规范个人信息处理活动，促进个人信息合理利用，根据宪法，制定本法。

第二条 自然人的个人信息受法律保护，任何组织、个人不得侵害自然人的个人信息权益。

第二章 个人信息处理规则

第三条 在中华人民共和国境内处理自然人个人信息的活动，适用本法。

第四条 个人信息是以电子或者其他方式记录的与已识别或者可识别的自然人有关的各种信息，不包括匿名化处理后的信息。

第五条 处理个人信息应当遵循合法、正当、必要和诚信原则，不得通过误导、欺诈、胁迫等方式处理个人信息。

第六条 处理个人信息应当具有明确、合理的目的，并应当与处理目的直接相关，采取对个人权益影响最小的方式。

第三章 敏感个人信息

第二十八条 敏感个人信息是一旦泄露或者非法使用，容易导致自然人的人格尊严受到侵害或者人身、财产安全受到危害的个人信息，包括生物识别、宗教信仰、特定身份、医疗健康、金融账户、行踪轨迹等信息，以及不满十四周岁未成年人的个人信息。

第二十九条 处理敏感个人信息应当取得个人的单独同意，法律、行政法规规定处理敏感个人信息应当取得书面同意的，从其规定。

第三十条 处理敏感个人信息的，应当向个人告知处理敏感个人信息的必要性和对个人权益的影响。

第四章 法律责任

第六十六条 违反本法规定处理个人信息，或者处理个人信息未履行本法规定的个人信息保护义务的，由履行个人信息保护职责的部门责令改正，给予警告，没收违法所得。

第六十七条 有前款规定的违法行为，情节严重的，由省级以上履行个人信息保护职责的部门责令改正，并处五千万元以下或者上一年度营业额百分之五以下罚款。"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(plain)
    return path

# ============================
# 2. Test questions
# ============================

TEST_QUESTIONS = [
    ("个人信息保护法是用来做什么的", "保护个人信息", "语义搜索"),
    ("个人信息的定义是什么", "电子或者其他方式", "语义搜索"),
    ("处理个人信息要遵循什么原则", "合法、正当、必要", "语义搜索"),
    ("第二十八条说了什么", "敏感个人信息", "条款号搜索"),
    ("第六十六条是什么", "责令改正", "条款号搜索"),
    ("第三十条是什么", "处理敏感个人信息", "条款号搜索"),
    ("第一章讲的是什么", "总则", "章节标题搜索"),
    ("敏感个人信息包括哪些", "生物识别", "具体概念搜索"),
    ("违反个人信息保护法有什么后果", "罚款", "语义搜索"),
    ("处理敏感个人信息需要什么条件", "单独同意", "语义搜索"),
]

def check_hits(retriever, query, top_k=5):
    from app.retrieve.query_understanding import QueryUnderstanding
    qu = QueryUnderstanding()
    intent = qu.analyze(query)
    hits = retriever.search(query, top_k=top_k, boost_sparse=intent.boost_sparse)
    results = []
    for i, hit in enumerate(hits):
        results.append({
            "rank": i+1, "score": round(hit.dense_score, 3),
            "content_slice": hit.content[:80],
            "doc_name": hit.meta.doc_name,
            "heading": hit.meta.heading_number,
            "clen": len(hit.content),
        })
    return results

def main():
    print("=" * 70)
    print("   跨格式检索与回答准确性测试")
    print("=" * 70)

    # 1. Create test files
    print("\n[1/5] 创建 4 种格式测试文件...")
    tmp = tempfile.mkdtemp(prefix="cft_")
    files = {
        "PDF": create_pdf(os.path.join(tmp, "pdf_test.pdf")),
        "DOCX": create_docx(os.path.join(tmp, "docx_test.docx")),
        "MD": create_md(os.path.join(tmp, "md_test.md")),
        "TXT": create_txt(os.path.join(tmp, "txt_test.txt")),
    }
    for fmt, p in files.items():
        print(f"  {fmt}: {p} ({os.path.getsize(p)} bytes)")

    # 2. Init
    print("\n[2/5] 初始化 Embedder 和 ChromaDB...")
    from app.cross.paths import get_project_root
    chroma_dir = get_project_root() / "data" / "chroma_db"
    if chroma_dir.exists():
        shutil.rmtree(chroma_dir)
        print("  已清理旧 ChromaDB")
    from app.index.embedder import SentenceEmbedder
    from app.index.chroma_repo import ChromaRepository
    embedder = SentenceEmbedder()
    repo = ChromaRepository(embedder=embedder)
    print(f"  Embedder: {embedder.dimension} 维")

    # 3. Ingest
    print("\n[3/5] 入库 4 种格式...")
    from app.ingest.reader_factory import ReaderFactory
    factory = ReaderFactory()
    for fmt, p in files.items():
        reader = factory.get_reader(p)
        doc_name = Path(p).stem
        chunks = reader.read(p, doc_name=doc_name)
        repo.upsert(chunks)
        print(f"  {fmt}: {doc_name} -> {len(chunks)} chunks")

    all_chunks = repo.get_all_chunks()
    print(f"\n  总入库: {len(all_chunks)} chunks")
    doc_counter = Counter(c.meta.doc_name for c in all_chunks)
    for dn, cnt in doc_counter.most_common():
        print(f"    {dn}: {cnt}")

    # 4. Init retriever
    print("\n[4/5] 初始化检索器...")
    from app.retrieve.query_understanding import QueryUnderstanding
    from app.retrieve.hybrid import HybridRetriever
    qu = QueryUnderstanding()
    retriever = HybridRetriever(repo=repo, embedder=embedder, query_understanding=qu)
    print("  检索器就绪")

    # 5. Run tests
    print("\n" + "=" * 70)
    print("   [5/5] 执行测试查询")
    print("=" * 70)

    results = []
    for qi, (q, kw, tp) in enumerate(TEST_QUESTIONS, 1):
        print(f"\n--- 测试 {qi}: [{tp}] {q} ---")
        hits = check_hits(retriever, q)
        hit_docs = [h["doc_name"] for h in hits]
        top1 = hits[0] if hits else None
        top1_ok = top1 and (kw in top1["content_slice"] or kw in top1["heading"])
        top5_ok = any(kw in h["content_slice"] or kw in h["heading"] for h in hits)

        if top1:
            print(f"  Top-1: [{top1['doc_name']}] {top1['content_slice'][:60]}...")
            print(f"  Score: {top1['score']}")
        else:
            print("  Top-1: 无命中")

        verdict = "PASS" if top1_ok else ("WEAK" if top5_ok else "FAIL")
        print(f"  Top-1 含关键词: {'YES' if top1_ok else 'NO'}")
        print(f"  Top-5 含关键词: {'YES' if top5_ok else 'NO'}")
        print(f"  判定: {verdict}")

        results.append({
            "qi": qi, "type": tp, "question": q,
            "top1_doc": top1["doc_name"] if top1 else "N/A",
            "top1_score": top1["score"] if top1 else 0,
            "top1_ok": top1_ok, "top5_ok": top5_ok,
            "verdict": verdict, "hit_docs": hit_docs,
        })

    # Summary
    print("\n" + "=" * 70)
    print("   测试汇总")
    print("=" * 70)
    passed = sum(1 for r in results if r["verdict"] == "PASS")
    weak = sum(1 for r in results if r["verdict"] == "WEAK")
    failed = sum(1 for r in results if r["verdict"] == "FAIL")
    print(f"\n  PASS: {passed}  WEAK: {weak}  FAIL: {failed}  TOTAL: {len(results)}")

    print(f"\n{'#':<4} {'类型':<12} {'问题':<30} {'Top-1来源':<12} {'判定':<8}")
    print("-" * 70)
    for r in results:
        print(f"{r['qi']:<4} {r['type']:<12} {r['question']:<30} {r['top1_doc']:<12} {r['verdict']:<8}")

    # Format coverage
    expected = {"pdf_test", "docx_test", "md_test", "txt_test"}
    found = set()
    for r in results:
        for d in r["hit_docs"]:
            if d in expected:
                found.add(d)
    missing = expected - found
    if missing:
        print(f"\n  WARNING: 以下格式从未出现在 Top-5: {missing}")
    else:
        print(f"\n  所有 4 种格式均出现在 Top-5 命中中")

    shutil.rmtree(tmp)
    print(f"\n  临时文件已清理: {tmp}")
    print("=" * 70)
    return results

if __name__ == "__main__":
    main()
