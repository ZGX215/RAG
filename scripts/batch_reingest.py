"""重新批量入库：清除旧库，加载新测试数据"""

import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import logging

from app.index.chroma_repo import ChromaRepository
from app.index.embedder import SentenceEmbedder
from config.settings import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    print("=== 重新批量入库 ===\n")

    # 初始化嵌入模型
    print("1. 初始化嵌入模型...")
    embedder = SentenceEmbedder()

    # 清空 ChromaDB 并重建
    import chromadb
    print("2. 清空旧数据库...")
    persist_dir = settings.index.persist_dir
    from pathlib import Path
    _path = Path(persist_dir)
    if not _path.is_absolute():
        from app.cross.paths import get_project_root
        _path = get_project_root() / _path
    _client = chromadb.PersistentClient(path=str(_path.resolve()))
    try:
        _client.delete_collection(settings.index.collection_name)
        print(f"   已删除旧 collection: {settings.index.collection_name}")
    except Exception:
        print("   旧 collection 不存在，跳过删除")
    repo = ChromaRepository(
        embedder=embedder,
        persist_dir=settings.index.persist_dir,
        collection_name=settings.index.collection_name,
    )
    print(f"   ChromaDB 重建完成，当前文档数: {repo.count()}\n")

    # 读取批量测试文件
    batch_dir = os.path.join(_PROJECT_ROOT, "data", "batch_test")
    files = sorted([f for f in os.listdir(batch_dir) if f.endswith('.txt')])
    print(f"3. 找到 {len(files)} 个文件")

    from app.ingest.name_classifier import parse_classification_from_filename

    # 跳过格式错误的文件
    valid_files = []
    for fname in files:
        file_path = os.path.join(batch_dir, fname)
        result = parse_classification_from_filename(file_path)
        if result.is_valid:
            valid_files.append((fname, result.classification, result.clean_name))
        else:
            print(f"   跳过格式错误: {fname} ({result.error})")

    print(f"   有效文件: {len(valid_files)} 个\n")

    # 逐文件读取、分块、入库
    all_chunks = 0
    for fname, classification, name in valid_files:
        file_path = os.path.join(batch_dir, fname)
        print(f"4. 处理 {fname} → classification={classification}")

        # 用工厂获取正确的 reader（TxtReader 已经注册）
        from app.ingest.reader_factory import get_reader_factory
        factory = get_reader_factory()
        reader = factory.get_reader(file_path)
        chunks = reader.read(file_path)

        # 设置正确的密级（reader 默认是 PUBLIC，需要修正）
        for chunk in chunks:
            chunk.meta.classification = classification
            chunk.meta.doc_name = name

        print(f"   分块: {len(chunks)} 个 chunks")

        # 批量写入数据库
        written = repo.upsert(chunks)
        all_chunks += written

        print(f"   写入完成: {written} 个 chunks")

    print(f"\n5. 全部完成: 总计 {all_chunks} 个 chunks 写入")
    print(f"   数据库文档数: {repo.count()}")
    print("\n=== 完成 ===")

if __name__ == "__main__":
    main()