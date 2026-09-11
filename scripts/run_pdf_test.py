"""
PDF 检索能力自测脚本
====================

用法: python scripts/run_pdf_test.py

测试内容:
  1. 法律文档测试（个人信息保护法按条款分块检索）
  2. 普通文档测试（Python 编程指南按段落分块检索）

流程:
  - 自动选择 PDF 文件
  - 自动清理旧索引并重建
  - 输出分块详情和检索结果
"""

import os
import shutil
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

# 强制缓存到 E 盘
os.environ["HF_HOME"] = str(project_root / "data" / "models")
os.environ["HF_HUB_CACHE"] = str(project_root / "data" / "models")
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

# ============ 配置（按需修改）============

# 测试 PDF 路径（可改为自己的文件）
LEGAL_PDF = project_root / "data" / "个人信息保护法.pdf"
NORMAL_PDF = project_root / "data" / "test_normal_pdf.pdf"

# 法律文档测试问题
LEGAL_QUESTIONS = [
    "个人信息保护法第一条说了什么",
    "个人信息的定义是什么",
    "敏感个人信息有哪些",
    "个人信息处理的原则是什么",
    "个人在信息处理中的权利有哪些",
]

# 普通文档测试问题
NORMAL_QUESTIONS = [
    "Python有哪些数据类型",
    "lambda函数是什么",
    "列表推导式是什么",
    "怎么处理JSON数据",
    "try/except/finally的用法",
    "Python的for循环怎么用",
    "range函数的作用",
    "Python的类怎么定义",
    "Python的正则表达式怎么用",
]


# ============ 测试逻辑 ============

def print_header(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}")


def print_chunks(chunks):
    for i, c in enumerate(chunks):
        meta = c.meta
        page = f"第{meta.page_num}页" if meta.page_num else ""
        heading = meta.heading_number or ""
        label = f"[{page} {heading}]" if page else f"[{heading}]"
        preview = c.content[:60].replace("\n", " ")
        print(f"  {i+1:>2}. {label:20s} {preview}...")


def test_pdf(pdf_path, questions, mode_name):
    from app.index.chroma_repo import ChromaRepository
    from app.index.embedder import SentenceEmbedder
    from app.ingest.pdf_reader import PdfReader

    print_header(f"测试 {mode_name}")

    # 1. 读取并分块
    print(f"\n📄 文件: {pdf_path.name}")
    reader = PdfReader()
    chunks = reader.read(str(pdf_path))
    print(f"📦 分块数: {len(chunks)}")
    print_chunks(chunks)

    # 2. 初始化嵌入模型和索引
    print("\n🔧 加载模型...")
    embedder = SentenceEmbedder()
    print(f"   模型维度: {embedder.dimension}")

    # 3. 清理旧索引并重建
    repo = ChromaRepository(embedder)
    print("   入库中...")
    n = repo.upsert(chunks)
    print(f"   已入库: {n} 个分块")

    # 4. 检索测试
    print(f"\n🔍 检索测试 ({len(questions)} 个问题)")
    pass_count = 0
    for i, q in enumerate(questions, 1):
        hits = repo.search(embedder.embed_query(q), top_k=3)
        if hits:
            top = hits[0]
            preview = top.content[:50].replace("\n", " ")
            page = f"第{top.meta.page_num}页" if top.meta.page_num else top.meta.heading_number
            print(f"  [{i:>2}] {q:30s} → {page:10s} | {preview}...")
            pass_count += 1
        else:
            print(f"  [{i:>2}] {q:30s} → ❌ 未命中")

    print(f"\n✅ 命中率: {pass_count}/{len(questions)}")
    return pass_count


def main():
    print_header("PDF 检索能力自测工具")
    print(f"  项目: {project_root.name}")
    print(f"  缓存: {project_root}/data/models")

    # 清理旧索引
    chroma_dir = project_root / "data" / "chroma_db"
    if chroma_dir.exists():
        shutil.rmtree(str(chroma_dir))
        print("\n🧹 已清理旧索引")

    total = 0
    passed = 0

    # 测试法律文档
    if LEGAL_PDF.exists():
        p = test_pdf(LEGAL_PDF, LEGAL_QUESTIONS, "法律文档（按条款分块）")
        passed += p
        total += len(LEGAL_QUESTIONS)
    else:
        print(f"\n⚠️  法律文档未找到: {LEGAL_PDF}")
        print("   请将 PDF 放在 data/ 目录下")

    # 测试普通文档
    if NORMAL_PDF.exists():
        p = test_pdf(NORMAL_PDF, NORMAL_QUESTIONS, "普通文档（按段落分块）")
        passed += p
        total += len(NORMAL_QUESTIONS)
    else:
        print(f"\n⚠️  普通文档未找到: {NORMAL_PDF}")
        print("   请先运行以下命令生成测试 PDF：")
        print("   python scripts/gen_test_pdf.py")

    # 总览
    print_header("测试完成")
    if total > 0:
        print(f"  总命中: {passed}/{total} ({passed/total*100:.1f}%)")
    print("\n💡 提示：")
    print("  - 修改脚本顶部的 LEGAL_QUESTIONS / NORMAL_QUESTIONS 来换问题")
    print("  - 修改 LEGAL_PDF / NORMAL_PDF 路径来测试自己的 PDF 文件")
    print("  - 模型缓存位于 E 盘 data/models，首次测试自动加载无需联网")


if __name__ == "__main__":
    main()
