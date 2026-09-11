#!/usr/bin/env python
import os, sys, shutil
from pathlib import Path
from collections import Counter, defaultdict
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
TEST_PDF = "E:/trae/cede/mcu-rag-qa-v2/data/test_normal_pdf.pdf"
TEST_QUESTIONS = [
    ("Python是什么语言", "high-level", "Python基础"),
    ("Python是谁创建的", "Guido", "Python基础"),
    ("Python有哪些特点", "dynamically-typed", "Python基础"),
    ("Python支持哪些编程范式", "paradigms", "Python基础"),
    ("Python有哪些数据类型", "int", "数据类型"),
    ("Python的列表是什么", "list", "数据类型"),
    ("Python的字典是什么", "dict", "数据类型"),
    ("Python的if语句怎么用", "if", "控制流"),
    ("Python的for循环怎么用", "for", "控制流"),
    ("列表推导式是什么", "comprehensions", "控制流"),
    ("range函数的作用", "range", "控制流"),
    ("Python的函数怎么定义", "def", "函数"),
    ("lambda函数是什么", "lambda", "函数"),
    ("Python的模块是什么", "Module", "函数"),
    ("Python的包是什么", "Package", "函数"),
    ("Python怎么读写文件", "open", "文件IO"),
    ("Python的异常处理怎么用", "try", "文件IO"),
    ("Python的类怎么定义", "class", "OOP"),
    ("Python支持继承吗", "Inheritance", "OOP"),
    ("Python的@property是什么", "property", "OOP"),
    ("Python怎么处理JSON", "json", "数据处理"),
    ("Python的正则表达式怎么用", "re", "数据处理"),
    ("Python的datetime怎么用", "datetime", "数据处理"),
    ("collections模块有哪些", "defaultdict", "数据处理"),
    ("Python的元组是什么", "tuple", "数据类型"),
    ("try/except/finally的作用", "finally", "文件IO"),
]
def run_test():
    print("=" * 70)
    print("  普通文档（非法律）PDF 检索能力专项测试")
    print("=" * 70)
    print("\n[1/5] 验证 PDF 内容...")
    from pypdf import PdfReader as _PdfReader
    reader = _PdfReader(TEST_PDF)
    print(f"  页数: {len(reader.pages)}")
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        first_line = text.splitlines()[0] if text.splitlines() else "(空)"
        print(f"    第{i+1}页: {len(text)} 字符, 首行: {first_line}")
    print("\n[2/5] 验证 PdfReader 模式选择...")
    from app.ingest.pdf_reader import PdfReader as OurPdfReader
    pdf_reader = OurPdfReader()
    chunks = pdf_reader.read(TEST_PDF, doc_name="Python编程指南")
    print(f"  分块数: {len(chunks)}")
    all_heading = [c.meta.heading_number for c in chunks]
    all_page = [c.meta.page_num for c in chunks]
    print(f"  heading_number: {all_heading}")
    print(f"  page_num: {all_page}")
    is_page_mode = all(c.meta.page_num > 0 for c in chunks)
    print(f"  是否逐页模式: {'是' if is_page_mode else '否，是条款模式'}")
    print("\n[3/5] 清理旧数据并入库...")
    from app.cross.paths import get_project_root
    chroma_dir = get_project_root() / "data" / "chroma_db"
    if chroma_dir.exists():
        shutil.rmtree(chroma_dir)
        print("  已清理旧数据")
    from app.index.embedder import SentenceEmbedder
    from app.index.chroma_repo import ChromaRepository
    embedder = SentenceEmbedder()
    repo = ChromaRepository(embedder=embedder)
    repo.upsert(chunks)
    all_chunks = repo.get_all_chunks()
    print(f"  入库: {len(all_chunks)} 分块")
    for dn, cnt in Counter(c.meta.doc_name for c in all_chunks).most_common():
        print(f"    {dn}: {cnt}")
    print("\n[4/5] 初始化检索器...")
    from app.retrieve.query_understanding import QueryUnderstanding
    from app.retrieve.hybrid import HybridRetriever
    qu = QueryUnderstanding()
    retriever = HybridRetriever(repo=repo, embedder=embedder, query_understanding=qu)
    print("\n" + "=" * 70)
    print("   [5/5] 执行 26 个测试查询")
    print("=" * 70)
    results = []
    for qi, (q, kw, domain) in enumerate(TEST_QUESTIONS, 1):
        intent = qu.analyze(q)
        hits = retriever.search(q, top_k=5, boost_sparse=intent.boost_sparse)
        top1 = hits[0] if hits else None
        kw_lower = kw.lower()
        top1_ok = top1 and (kw_lower in top1.content.lower() or kw_lower in top1.meta.heading_number.lower())
        top5_ok = any(kw_lower in h.content.lower() or kw_lower in h.meta.heading_number.lower() for h in hits)
        top1_doc = top1.meta.doc_name if top1 else "N/A"
        top1_page = top1.meta.page_num if top1 else 0
        top1_content = (top1.content[:80] + "...") if top1 and len(top1.content) > 80 else (top1.content if top1 else "")
        boost_tag = " [BM25+]" if intent.boost_sparse else " [均衡]"
        verdict = "PASS" if top1_ok else ("WEAK" if top5_ok else "FAIL")
        if top1:
            print(f"\n  [{verdict}{boost_tag}] 测试 {qi:2d}: [{domain:8s}] {q}")
            print(f"    Top-1: 第{top1_page}页 [{top1_doc}] {top1_content}")
            if top1_ok:
                print(f"    命中关键词: {kw}")
            elif top5_ok:
                print(f"    Top-5 命中关键词: {kw}")
            else:
                print(f"    Top-5 均未命中: {kw}")
        else:
            print(f"\n  [FAIL] 测试 {qi}: [{domain}] {q} - 无命中")
        results.append({"qi": qi, "domain": domain, "question": q, "top1_doc": top1_doc, "top1_page": top1_page, "top1_ok": top1_ok, "top5_ok": top5_ok, "verdict": verdict, "boost_sparse": intent.boost_sparse})
    print("\n\n" + "=" * 70)
    print("   测试汇总")
    print("=" * 70)
    passed = sum(1 for r in results if r["verdict"] == "PASS")
    weak = sum(1 for r in results if r["verdict"] == "WEAK")
    failed = sum(1 for r in results if r["verdict"] == "FAIL")
    print(f"\n  PASS: {passed}  WEAK: {weak}  FAIL: {failed}  TOTAL: {len(results)}")
    print(f"  通过率: {passed/len(results)*100:.1f}%")
    by_domain = defaultdict(list)
    for r in results:
        by_domain[r["domain"]].append(r)
    for domain, items in by_domain.items():
        dp = sum(1 for r in items if r["verdict"] == "PASS")
        print(f"  [{domain}] {dp}/{len(items)} 通过 ({dp/len(items)*100:.0f}%)")
    print(f"\n{'#':<4} {'领域':<10} {'BM25':<6} {'页码':<5} {'问题':<30} {'判定':<8}")
    print("-" * 70)
    for r in results:
        bm = "ON" if r["boost_sparse"] else "OFF"
        pg = str(r["top1_page"]) if r["top1_page"] else "N/A"
        print(f"{r['qi']:<4} {r['domain']:<10} {bm:<6} {pg:<5} {r['question']:<30} {r['verdict']:<8}")
    page_hits = Counter(r["top1_page"] for r in results if r["top1_page"] > 0)
    print(f"\n  Top-1 页命中分布: {dict(sorted(page_hits.items()))}")
    print(f"  覆盖页数: {len(page_hits)}/{len(reader.pages)}")
    avg_chars = sum(len(c.content) for c in chunks) / len(chunks) if chunks else 0
    print(f"  平均分块大小: {avg_chars:.0f} 字符")
    print("=" * 70)
    return results
if __name__ == "__main__":
    run_test()
