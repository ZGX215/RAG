#!/usr/bin/env python
"""P1 薄切片端到端验证脚本。

一条命令跑通：PDF 提取 → 分块 → 索引 → 检索 → 生成。

用法:
    python scripts/p1_demo.py                          # 使用默认问题
    python scripts/p1_demo.py "你自定义的问题"          # 自己指定问题
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

# 确保项目根目录在 sys.path 中
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from app.cross.logging import setup_logging
from app.cross.paths import ensure_data_dirs
from app.generate.llm_client import DeepSeekClient
from app.index.chroma_repo import ChromaRepository
from app.index.embedder import SentenceEmbedder
from app.ingest.pdf_reader import PdfReader
from config.settings import settings

logger = setup_logging(log_level=settings.general.log_level)


async def main():
    pdf_path = r"C:\Users\Lenovo\Desktop\附件1：《中华人民共和国个人信息保护法》.pdf"

    # 从命令行参数读取问题，没有则用默认问题
    question = sys.argv[1] if len(sys.argv) > 1 else "个人信息保护法的适用范围是什么？"

    # === 1. 准备目录 ===
    ensure_data_dirs()
    logger.info("=" * 50)
    logger.info("P1 薄切片通路验证开始")

    # === 2. 初始化 Embedder + ChromaRepository ===
    embedder = SentenceEmbedder()
    repo = ChromaRepository(
        embedder=embedder,
        persist_dir=settings.index.persist_dir,
        collection_name=settings.index.collection_name,
    )

    # === 3. PDF 提取 + 分块 ===
    t0 = time.time()
    chunks = PdfReader().read(pdf_path)
    t1 = time.time()
    print(f"\n📄 提取: {len(chunks)} 个切片 ({t1 - t0:.1f}s)")

    # === 4. 索引 ===
    n = repo.upsert(chunks)
    t2 = time.time()
    print(f"📦 索引: {n} 条写入 ({t2 - t1:.1f}s)")

    # === 5. 提问 + 混合检索 ===
    from app.retrieve.hybrid import HybridRetriever
    from app.retrieve.query_understanding import QueryUnderstanding

    retriever = HybridRetriever(repo=repo, embedder=embedder)
    query_understanding = QueryUnderstanding()
    intent = query_understanding.analyze(question)
    hits = retriever.search(
        question,
        top_k=5,
        boost_sparse=intent.boost_sparse,
    )
    t3 = time.time()
    print(f"🔍 检索: 命中 {len(hits)} 条 ({t3 - t2:.1f}s)")
    for i, h in enumerate(hits):
        print(f"   [{i + 1}] {h.meta.heading_number} (score={h.final_score:.3f})")

    # === 6. 生成回答 ===
    context = "\n\n".join(f"[{h.meta.heading_number}]\n{h.content[:500]}" for h in hits)
    llm = DeepSeekClient(
        api_key=settings.llm.api_key,
        base_url=settings.llm.base_url,
        model=settings.llm.model,
    )
    system_prompt = "你是一个法律助手，基于以下法律条文回答用户问题。"
    user_prompt = f"法律条文：\n{context}\n\n问题：{question}"
    answer = await llm.generate(system_prompt, user_prompt)
    t4 = time.time()

    print(f"\n🤖 回答 ({t4 - t3:.1f}s):")
    print(f"   {answer}")
    print("\n来源:")
    for h in hits:
        print(f"   - {h.meta.heading_number} ({h.meta.doc_name})")
    print(f"\n⏱ 总耗时: {t4 - t0:.1f}s")
    print("✅ P1 薄切片通路验证完成")


if __name__ == "__main__":
    asyncio.run(main())