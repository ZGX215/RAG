#!/usr/bin/env python
"""诊断第三十九条检索排名"""

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from app.index.chroma_repo import ChromaRepository
from app.index.embedder import SentenceEmbedder
from config.settings import settings


def main():
    embedder = SentenceEmbedder()
    repo = ChromaRepository(embedder, settings.index.persist_dir, 'mcu_qa')

    # 查全部 75 条，看第三十九条排第几
    query = '第三十九条是什么'
    vec = embedder.embed_query(query)
    hits = repo.search(vec, top_k=75)
    for i, h in enumerate(hits):
        if h.meta.heading_number == '第三十九条':
            print(f'第三十九条排在第 {i+1} 名, score={h.dense_score:.3f}')
            break
    else:
        print('第三十九条不在全部 75 条结果中')

    # 用语义相关的问题
    query2 = '向境外提供个人信息需要什么条件'
    vec2 = embedder.embed_query(query2)
    hits2 = repo.search(vec2, top_k=5)
    print('\n--- 用语义问题 "向境外提供个人信息需要什么条件" ---')
    for h in hits2:
        print(f'  [{h.meta.heading_number}] score={h.dense_score:.3f}  {h.content[:60]}')


if __name__ == '__main__':
    main()
