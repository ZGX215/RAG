"""
全格式检索能力自测脚本
======================

用法: python scripts/run_all_formats_test.py

测试格式:
  - PDF  → 法律文档（按条款分块） + 普通文档（按段落分块）
  - DOCX → Word 文档（按标题分块）
  - MD   → Markdown 文档（按标题分块）
  - TXT  → 纯文本文档（按段落分块）

流程:
  1. 自动生成所有格式的测试数据
  2. 自动清理旧索引
  3. 按格式逐个测试
  4. 输出汇总结果
"""

import os
import shutil
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

os.environ["HF_HOME"] = str(project_root / "data" / "models")
os.environ["HF_HUB_CACHE"] = str(project_root / "data" / "models")
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

DATA_DIR = project_root / "data"


# ============ 测试数据生成 ============

def ensure_test_data():
    """确保所有测试数据都存在。"""
    created = []

    # PDF — 普通文档
    pdf_path = DATA_DIR / "test_normal_pdf.pdf"
    if not pdf_path.exists():
        from fpdf import FPDF
        pdf = FPDF()
        cjk = Path("C:/Windows/Fonts/msyh.ttc")
        if cjk.exists():
            pdf.add_font("CJK", "", str(cjk), uni=True)
            pdf.set_font("CJK", size=12)
        else:
            pdf.set_font("Helvetica", size=12)
        pages = [
            ["Python Programming Guide", "", "Python is a high-level language created by Guido van Rossum in 1991.",
             "It emphasizes code readability with significant indentation.", "",
             "Python is dynamically-typed and garbage-collected.", "It supports multiple programming paradigms."],
            ["Data Types", "", "Python has several built-in data types.",
             "Numeric: int, float, complex. Sequence: list, tuple, range.", "",
             "Text: str. Mapping: dict. Set: set, frozenset."],
            ["Control Flow", "", "Python supports standard control flow. if/elif/else for conditional logic.",
             "", "for loops for iterating over sequences.", "while loops for repeated execution."],
            ["Functions", "", "Functions are defined with def keyword.", "Default arguments: def power(base, exp=2)",
             "", "Lambda: lambda x: x**2 for anonymous functions."],
            ["File I/O", "", "File operations use the with statement.", "open for reading, writing, and appending.",
             "", "Exception handling with try/except/finally."],
            ["OOP", "", "Python supports OOP with classes.", "class Animal: def __init__(self, name)",
             "", "Inheritance for code reuse between classes."],
            ["Data Processing", "", "JSON: json.dumps and json.loads for data serialization.",
             "Regex: re.findall and re.match for pattern matching.", "",
             "Dates: datetime and timedelta for time manipulation."],
        ]
        for pg in pages:
            pdf.add_page()
            for line in pg:
                if not line:
                    pdf.ln(5)
                else:
                    pdf.cell(0, 8, line, new_x="LMARGIN", new_y="NEXT")
        pdf.output(str(pdf_path))
        created.append(f"PDF: {pdf_path.name}")

    # DOCX — Word 文档
    docx_path = DATA_DIR / "test_doc.docx"
    if not docx_path.exists():
        from docx import Document
        doc = Document()
        headings = ["Python 概述", "数据类型", "控制流", "函数", "文件 IO"]
        contents = [
            [
                "Python 是 Guido van Rossum 在 1991 年创建的高级语言。",
                "它强调代码可读性，使用缩进组织代码块。",
                "Python 是动态类型语言，支持多种编程范式。",
            ],
            [
                "Python 提供了多种内置数据类型。",
                "数字类型：int, float, complex。序列类型：list, tuple, range。",
                "映射类型：dict。集合类型：set, frozenset。",
            ],
            [
                "Python 支持 if/elif/else 条件判断。",
                "for 循环用于遍历序列，while 循环用于重复执行。",
                "列表推导式提供了简洁的列表创建方式。",
            ],
            [
                "函数用 def 关键字定义，支持默认参数。",
                "Lambda 表达式用于创建匿名函数。",
                "函数在 Python 中是一等公民。",
            ],
            [
                "文件操作推荐使用 with 语句。",
                "异常处理用 try/except/finally。",
                "finally 块无论是否异常都会执行。",
            ],
        ]
        for h, paragraphs in zip(headings, contents):
            doc.add_heading(h, level=1)
            for p in paragraphs:
                doc.add_paragraph(p)
            doc.add_paragraph("")
        doc.save(str(docx_path))
        created.append(f"DOCX: {docx_path.name}")

    # MD — Markdown 文档
    md_path = DATA_DIR / "test_doc.md"
    if not md_path.exists():
        md_content = """# Python 基础

## 概述

Python 是 Guido van Rossum 在 1991 年创建的高级语言。
它强调代码可读性，使用缩进组织代码块。

## 数据类型

Python 提供了多种内置数据类型。
数字类型：int, float, complex。
序列类型：list, tuple, range。

## 控制流

Python 支持 if/elif/else 条件判断。
for 循环用于遍历序列，while 循环用于重复执行。

## 函数

函数用 def 关键字定义。
Lambda 表达式用于创建匿名函数。

## 异常处理

异常处理用 try/except/finally。
finally 块无论是否异常都会执行。
"""
        md_path.write_text(md_content.strip(), encoding="utf-8")
        created.append(f"MD: {md_path.name}")

    # TXT — 纯文本文档
    txt_path = DATA_DIR / "test_doc.txt"
    if not txt_path.exists():
        txt_content = """Python 基础

Python 是 Guido van Rossum 在 1991 年创建的高级语言。
它强调代码可读性，使用缩进组织代码块。

数据类型
Python 提供了多种内置数据类型。
数字类型：int, float, complex。序列类型：list, tuple, range。

控制流
Python 支持 if/elif/else 条件判断。
for 循环用于遍历序列，while 循环用于重复执行。

函数
函数用 def 关键字定义，支持默认参数。
Lambda 表达式用于创建匿名函数。
"""
        txt_path.write_text(txt_content.strip(), encoding="utf-8")
        created.append(f"TXT: {txt_path.name}")

    return created


# ============ 各格式测试问题 ============

TEST_QUESTIONS = {
    "PDF": [
        "Python有哪些数据类型",
        "lambda函数是什么",
        "列表推导式是什么",
        "怎么处理JSON数据",
        "try/except/finally的用法",
        "Python的for循环怎么用",
        "range函数的作用",
        "Python的类怎么定义",
        "Python的正则表达式怎么用",
    ],
    "DOCX": [
        "Python有哪些数据类型",
        "lambda函数是什么",
        "Python支持哪些编程范式",
        "Python的异常处理怎么用",
        "Python的for循环怎么用",
        "Python用什么组织代码块",
        "Python的列表推导式怎么用",
        "Python的函数支持默认参数吗",
        "Python有哪些内置数字类型",
    ],
    "MD": [
        "Python的概述是什么",
        "Python有哪些数据类型",
        "Python的异常处理怎么用",
        "Python的for循环怎么用",
        "Python的函数怎么定义",
        "Python的Lambda是什么",
        "Python有哪些序列类型",
        "Python的if语句怎么用",
        "Python的while循环怎么用",
    ],
    "TXT": [
        "Python有哪些数据类型",
        "Python的异常处理怎么用",
        "Python的for循环怎么用",
        "Python的函数怎么定义",
        "Python的Lambda是什么",
        "Python有哪些序列类型",
        "Python支持哪些编程范式",
        "Python的if语句怎么用",
        "Python用什么组织代码块",
    ],
}


# ============ 测试逻辑 ============

def print_header(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}")


def print_chunks(chunks):
    for i, c in enumerate(chunks):
        meta = c.meta
        page = f"第{meta.page_num}页" if meta.page_num and meta.page_num > 0 else ""
        heading = meta.heading_number or ""
        label = f"[{page} {heading}]" if page else f"[{heading}]"
        preview = c.content[:55].replace("\n", " ")
        print(f"  {i+1:>2}. {label:20s} {preview}...")


def test_format(file_path, format_name):
    from app.index.chroma_repo import ChromaRepository
    from app.index.embedder import SentenceEmbedder
    from app.ingest.reader_factory import get_reader_factory

    questions = TEST_QUESTIONS.get(format_name, [])
    if not questions:
        print(f"  ⚠️  未配置 {format_name} 的测试问题，跳过")
        return 0, 0

    print_header(f"测试 {format_name} 格式")
    print(f"  文件: {file_path.name}")

    # 1. 读取并分块
    factory = get_reader_factory()
    reader = factory.get_reader(str(file_path))
    chunks = reader.read(str(file_path))
    print(f"  分块数: {len(chunks)}")
    print_chunks(chunks)

    # 2. 嵌入模型 + 索引
    print("\n  加载模型 + 入库...")
    embedder = SentenceEmbedder()
    repo = ChromaRepository(embedder)
    n = repo.upsert(chunks)
    print(f"  已入库 {n} 个分块")

    # 3. 检索测试
    print(f"\n  检索测试 ({len(questions)} 个问题):")
    passed = 0
    for i, q in enumerate(questions, 1):
        hits = repo.search(embedder.embed_query(q), top_k=3)
        if hits:
            top = hits[0]
            preview = top.content[:40].replace("\n", " ")
            heading = top.meta.heading_number or ""
            print(f"  [{i:>2}] {q:28s} → {heading:12s} | {preview}...")
            passed += 1
        else:
            print(f"  [{i:>2}] {q:28s} → ❌ 未命中")

    print(f"\n  ✅ 命中: {passed}/{len(questions)}")
    return passed, len(questions)


def main():
    print_header("全格式检索能力自测工具")
    print(f"  项目: {project_root.name}")
    print(f"  缓存: {DATA_DIR / 'models'}")

    # 1. 生成测试数据
    print("\n📦 生成测试数据...")
    created = ensure_test_data()
    for c in created:
        print(f"  ✅ {c}")

    # 2. 清理旧索引
    chroma_dir = DATA_DIR / "chroma_db"
    if chroma_dir.exists():
        shutil.rmtree(str(chroma_dir))
        print("\n🧹 已清理旧索引")

    # 3. 逐格式测试
    test_cases = [
        (DATA_DIR / "test_normal_pdf.pdf", "PDF"),
        (DATA_DIR / "test_doc.docx", "DOCX"),
        (DATA_DIR / "test_doc.md", "MD"),
        (DATA_DIR / "test_doc.txt", "TXT"),
    ]

    all_passed = 0
    all_total = 0

    for file_path, fmt in test_cases:
        if not file_path.exists():
            print(f"\n⚠️  文件不存在: {file_path.name}，跳过")
            continue
        p, t = test_format(file_path, fmt)
        all_passed += p
        all_total += t

    # 4. 汇总
    print_header("测试汇总")
    if all_total > 0:
        print(f"  总命中: {all_passed}/{all_total} ({all_passed/all_total*100:.1f}%)")
    print("  格式覆盖: PDF | DOCX | MD | TXT")
    print("\n💡  换自己的文件:")
    print("     修改 test_cases 列表，把路径换成你的文件即可")
    print("  换测试问题:")
    print("     修改 TEST_QUESTIONS 字典，按格式分类添加")


if __name__ == "__main__":
    main()
