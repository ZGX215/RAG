import os
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def create_pdf(path):
    from fpdf import FPDF
    pdf = FPDF()
    pdf.add_page()
    pdf.add_font("SimSun", "", "C:/Windows/Fonts/simsun.ttc", uni=True)
    pdf.set_font("SimSun", "", 16)
    pdf.cell(0, 10, "中华人民共和国个人信息保护法", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(5)
    pdf.set_font("SimSun", "", 12)
    articles = [
        "第一章 总则", "第一条 为了保护个人信息权益，规范个人信息处理活动，促进个人信息合理利用，根据宪法，制定本法。",
        "第二条 自然人的个人信息受法律保护，任何组织、个人不得侵害自然人的个人信息权益。",
        "第三条 在中华人民共和国境内处理自然人个人信息的活动，适用本法。",
        "", "第二章 个人信息处理规则",
        "第四条 个人信息是以电子或者其他方式记录的与已识别或者可识别的自然人有关的各种信息。",
        "第五条 处理个人信息应当遵循合法、正当、必要和诚信原则。",
        "第六条 处理个人信息应当具有明确、合理的目的，并应当与处理目的直接相关。",
        "第十三条 符合下列情形之一的，个人信息处理者方可处理个人信息：（一）取得个人的同意。",
        "", "第三章 敏感个人信息",
        "第二十八条 敏感个人信息是一旦泄露或者非法使用，容易导致自然人的人格尊严受到侵害或者人身、财产安全受到危害的个人信息。",
        "第二十九条 处理敏感个人信息应当取得个人的单独同意。",
        "第三十条 处理敏感个人信息的，应当向个人告知处理敏感个人信息的必要性和对个人权益的影响。",
        "", "第四章 法律责任",
        "第六十六条 违反本法规定处理个人信息，由履行个人信息保护职责的部门责令改正，给予警告，没收违法所得。",
        "第六十七条 情节严重的，由省级以上履行个人信息保护职责的部门责令改正，并处五千万元以下罚款。",
        "第六十八条 违反本法规定，构成违反治安管理行为的，依法给予治安管理处罚。",
    ]
    for line in articles:
        pdf.cell(0, 8, line, new_x="LMARGIN", new_y="NEXT")
    pdf.output(path)
    return path

def create_docx(path):
    from docx import Document
    doc = Document()
    doc.add_heading("中华人民共和国个人信息保护法", level=0)
    doc.add_heading("第一章 总则", level=1)
    doc.add_paragraph("第一条 为了保护个人信息权益，规范个人信息处理活动，促进个人信息合理利用，根据宪法，制定本法。")
    doc.add_paragraph("第二条 自然人的个人信息受法律保护，任何组织、个人不得侵害自然人的个人信息权益。")
    doc.add_paragraph("第三条 在中华人民共和国境内处理自然人个人信息的活动，适用本法。")
    doc.add_heading("第二章 个人信息处理规则", level=1)
    doc.add_paragraph("第四条 个人信息是以电子或者其他方式记录的与已识别或者可识别的自然人有关的各种信息。")
    doc.add_paragraph("第五条 处理个人信息应当遵循合法、正当、必要和诚信原则。")
    doc.add_paragraph("第六条 处理个人信息应当具有明确、合理的目的，并应当与处理目的直接相关。")
    doc.add_paragraph("第十三条 符合下列情形之一的，个人信息处理者方可处理个人信息：（一）取得个人的同意。")
    doc.add_heading("第三章 敏感个人信息", level=1)
    doc.add_paragraph("第二十八条 敏感个人信息是一旦泄露或者非法使用，容易导致自然人的人格尊严受到侵害或者人身、财产安全受到危害的个人信息。")
    doc.add_paragraph("第二十九条 处理敏感个人信息应当取得个人的单独同意。")
    doc.add_paragraph("第三十条 处理敏感个人信息的，应当向个人告知处理敏感个人信息的必要性和对个人权益的影响。")
    doc.add_heading("第四章 法律责任", level=1)
    doc.add_paragraph("第六十六条 违反本法规定处理个人信息，由履行个人信息保护职责的部门责令改正，给予警告，没收违法所得。")
    doc.add_paragraph("第六十七条 情节严重的，由省级以上履行个人信息保护职责的部门责令改正，并处五千万元以下罚款。")
    doc.add_paragraph("第六十八条 违反本法规定，构成违反治安管理行为的，依法给予治安管理处罚。")
    doc.save(path)
    return path

# 25 个测试问题，覆盖 4 种来源
TEST_QUESTIONS = [
    # 法律法规类（PDF / DOCX）
    ("个人信息保护法第一条说了什么", "保护个人信息权益", "法律"),
    ("个人信息的定义是什么", "电子或者其他方式", "法律"),
    ("处理个人信息要遵循什么原则", "合法、正当、必要", "法律"),
    ("第二十八条说的是什么", "敏感个人信息", "法律"),
    ("第六十六条是什么", "责令改正", "法律"),
    ("处理敏感个人信息需要什么条件", "单独同意", "法律"),
    ("什么情况下可以处理个人信息", "个人的同意", "法律"),
    ("违反个人信息保护法会有什么后果", "罚款", "法律"),
    # API 调用类（MD01）
    ("什么是API调用", "API", "API"),
    ("如何配置环境变量", "环境变量", "API"),
    ("什么是token计费", "Token", "API"),
    ("如何发起一次API请求", "API", "API"),
    ("API请求中需要配置什么参数", "api_key", "API"),
    ("什么是流式调用", "流式", "API"),
    # 知识库类（TXT）
    ("什么是知识图谱", "知识图谱", "知识库"),
    ("什么是RAG", "检索增强", "知识库"),
    ("向量数据库是什么", "向量", "知识库"),
    ("什么是Prompt工程", "提示词", "知识库"),
    ("什么是模型微调", "微调", "知识库"),
    ("什么是MCP", "MCP", "知识库"),
    ("什么是Function Calling", "Function", "知识库"),
    ("什么是LangChain", "LangChain", "知识库"),
    ("什么是GraphRAG", "GraphRAG", "知识库"),
    ("FastAPI是什么", "FastAPI", "知识库"),
    ("什么是意图识别", "意图", "知识库"),
]

def run_test():
    print("=" * 70)
    print("   跨格式检索测试 v2 — 25 题覆盖 4 来源")
    print("=" * 70)

    tmp = tempfile.mkdtemp(prefix="cft_v2_")

    REAL_FILES = {
        "PDF": ("D:/AI知识库/法律法规/个人信息保护法.pdf", False),
        "DOCX": ("D:/AI知识库/法律法规/个人信息保护法.docx", False),
        "MD01": ("D:/AI知识库/基础知识/01-API调用学习模块.md", True),
        "MD02": ("D:/AI知识库/基础知识/02-Prompt工程学习模块.md", True),
        "MD04": ("D:/AI知识库/基础知识/04-关系型知识库学习模块.md", True),
        "MD06": ("D:/AI知识库/基础知识/06-向量数据库学习模块.md", True),
        "MD07": ("D:/AI知识库/基础知识/07-MCP学习模块.md", True),
        "MD08": ("D:/AI知识库/基础知识/08-模型微调实践.md", True),
        "MD14": ("D:/AI知识库/基础知识/14-RAG学习模块.md", True),
        "TXT": ("D:/AI知识库/AI知识库完整版.txt", True),
    }

    ingest_files = {}
    for name, (path, required) in REAL_FILES.items():
        if os.path.exists(path):
            ingest_files[name] = path
            print(f"  {name}: {os.path.getsize(path)/1024:.1f} KB")
        else:
            if name == "PDF":
                p = os.path.join(tmp, "pdf_test.pdf")
                create_pdf(p)
                ingest_files[name] = p
                print(f"  {name}: 创建测试文件")
            elif name == "DOCX":
                p = os.path.join(tmp, "docx_test.docx")
                create_docx(p)
                ingest_files[name] = p
                print(f"  {name}: 创建测试文件")
            else:
                print(f"  {name}: 不存在")

    print("\n[2/5] 初始化...")
    from app.cross.paths import get_project_root
    chroma_dir = get_project_root() / "data" / "chroma_db"
    if chroma_dir.exists():
        shutil.rmtree(chroma_dir)
        print("  已清理旧数据")
    from app.index.chroma_repo import ChromaRepository
    from app.index.embedder import SentenceEmbedder
    embedder = SentenceEmbedder()
    repo = ChromaRepository(embedder=embedder)

    print("\n[3/5] 入库...")
    from app.ingest.reader_factory import ReaderFactory
    factory = ReaderFactory()
    for name, path in ingest_files.items():
        reader = factory.get_reader(path)
        doc_name = Path(path).stem
        chunks = reader.read(path, doc_name=doc_name)
        repo.upsert(chunks)
        print(f"  {name}: {doc_name} -> {len(chunks)} 分块")

    all_chunks = repo.get_all_chunks()
    print(f"\n  总入库: {len(all_chunks)} 分块")
    for dn, cnt in Counter(c.meta.doc_name for c in all_chunks).most_common():
        print(f"    {dn}: {cnt}")

    print("\n[4/5] 初始化检索器...")
    from app.retrieve.hybrid import HybridRetriever
    from app.retrieve.query_understanding import QueryUnderstanding
    qu = QueryUnderstanding()
    retriever = HybridRetriever(repo=repo, embedder=embedder, query_understanding=qu)

    print("\n" + "=" * 70)
    print("   [5/5] 执行 25 个测试查询")
    print("=" * 70)

    results = []
    for qi, (q, kw, domain) in enumerate(TEST_QUESTIONS, 1):
        intent = qu.analyze(q)
        hits = retriever.search(q, top_k=5, boost_sparse=intent.boost_sparse)

        hit_docs = [h.meta.doc_name for h in hits]
        top1 = hits[0] if hits else None

        # 检查全文，不限于前 50 字
        top1_ok = top1 and (kw in top1.content or kw in top1.meta.heading_number)
        top5_ok = any(kw in h.content or kw in h.meta.heading_number for h in hits)

        top1_doc = top1.meta.doc_name if top1 else "N/A"
        top1_content = (top1.content[:60] + "...") if top1 and len(top1.content) > 60 else (top1.content if top1 else "")
        boost_tag = " [BM25+" if intent.boost_sparse else " [均衡]"

        verdict = "PASS" if top1_ok else ("WEAK" if top5_ok else "FAIL")
        icon = "PASS" if top1_ok else ("WEAK" if top5_ok else "FAIL")

        if top1:
            print(f"\n  [{icon}{boost_tag}] 测试 {qi}: [{domain}] {q}")
            print(f"    Top-1: [{top1_doc}] {top1_content}")
            if top1_ok:
                print(f"    TOP-1 命中关键词: {kw}")
            elif top5_ok:
                print(f"    TOP-5 命中关键词: {kw}")
            else:
                print(f"    TOP-5 均未命中: {kw}")
        else:
            print(f"\n  [FAIL] 测试 {qi}: [{domain}] {q} - 无命中")

        results.append({
            "qi": qi, "domain": domain, "question": q,
            "top1_doc": top1_doc, "top1_ok": top1_ok, "top5_ok": top5_ok,
            "verdict": verdict, "boost_sparse": intent.boost_sparse,
            "hit_docs": hit_docs,
        })

    # 汇总
    print("\n\n" + "=" * 70)
    print("   测试汇总")
    print("=" * 70)

    passed = sum(1 for r in results if r["verdict"] == "PASS")
    weak = sum(1 for r in results if r["verdict"] == "WEAK")
    failed = sum(1 for r in results if r["verdict"] == "FAIL")
    print(f"\n  PASS: {passed}  WEAK: {weak}  FAIL: {failed}  TOTAL: {len(results)}")

    by_domain = defaultdict(list)
    for r in results:
        by_domain[r["domain"]].append(r)
    for domain, items in by_domain.items():
        dp = sum(1 for r in items if r["verdict"] == "PASS")
        print(f"  [{domain}] {dp}/{len(items)} 通过")

    print(f"\n{'#':<4} {'领域':<6} {'BM25':<6} {'问题':<30} {'Top-1来源':<15} {'判定':<8}")
    print("-" * 70)
    for r in results:
        bm = "ON" if r["boost_sparse"] else "OFF"
        print(f"{r['qi']:<4} {r['domain']:<6} {bm:<6} {r['question']:<30} {r['top1_doc']:<15} {r['verdict']:<8}")

    # 来源覆盖
    all_hit_docs = set()
    for r in results:
        for d in r["hit_docs"]:
            all_hit_docs.add(d)
    print(f"\n  所有 Top-5 来源: {sorted(all_hit_docs)}")

    # 格式命中分析
    law_hits = set()
    for r in results:
        if r["domain"] == "法律":
            for d in r["hit_docs"]:
                if "pdf" in d or "docx" in d:
                    law_hits.add(d)
    print(f"  法律问题命中 PDF/DOCX: {law_hits if law_hits else '无'}")

    api_hits = set()
    for r in results:
        if r["domain"] == "API":
            for d in r["hit_docs"]:
                if "API" in d or "01-" in d:
                    api_hits.add(d)
    print(f"  API 问题命中 MD 来源: {api_hits if api_hits else '无'}")

    shutil.rmtree(tmp)
    print("\n  临时文件已清理")
    print("=" * 70)
    return results

if __name__ == "__main__":
    run_test()
