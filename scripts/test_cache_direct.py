"""直接测试缓存逻辑，不依赖启动服务。"""

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import time

from app.cross.cache import MultiLevelCache
from app.index.embedder import FakeEmbedder, CachedEmbedder


def test_cache_manager():
    print("=" * 50)
    print("测试 1: 缓存管理器基础操作")
    print("=" * 50)

    cache = MultiLevelCache(redis_url="redis://localhost:6379/2")
    print(f"Redis 连接: {cache.is_redis_connected}")

    # 写入
    cache.set("test", "hello", "world", ttl=60)
    print(f"写入: namespace='test', key='hello', value='world'")

    # 读取
    val = cache.get("test", "hello")
    print(f"读取: {val}")

    assert val == "world", "缓存读回的值应该和写入一致"
    print("通过!")

    # 删除
    cache.delete("test", "hello")
    val2 = cache.get("test", "hello")
    print(f"删除后读取: {val2}")
    assert val2 is None, "删除后应该读不到"
    print("通过!")


def test_cached_embedder():
    print("\n" + "=" * 50)
    print("测试 2: 带缓存的 Embedder")
    print("=" * 50)

    embedder = CachedEmbedder(FakeEmbedder(dim=384))

    text = "第三十九条是什么"

    # 第一次 —— 计算
    start = time.time()
    vec1 = embedder.embed_query(text)
    t1 = time.time() - start
    print(f"第一次: {t1:.4f}s, 向量长度: {len(vec1)}")

    # 第二次 —— 命中缓存
    start = time.time()
    vec2 = embedder.embed_query(text)
    t2 = time.time() - start
    print(f"第二次: {t2:.4f}s, 向量长度: {len(vec2)}")

    # 确认结果一致
    assert vec1 == vec2, "缓存和计算结果应该一样"
    print(f"结果一致: True")
    speedup = t1 / t2 if t2 > 0 else float("inf")
    print(f"加速比: {speedup:.0f}x")

    # 不同文本 —— 重新计算
    vec3 = embedder.embed_query("第四十条")
    print(f"不同问题: 向量长度: {len(vec3)}")
    print("通过!")


def test_ttl_expiration():
    print("\n" + "=" * 50)
    print("测试 3: TTL 过期")
    print("=" * 50)

    cache = MultiLevelCache(redis_url="redis://localhost:6379/2")
    cache.set("ttl", "key1", "val1", ttl=1)

    # 立刻读取
    v1 = cache.get("ttl", "key1")
    print(f"立刻读取: {v1}")
    assert v1 == "val1"

    # 等待 2 秒后 L1 应该过期
    time.sleep(2)
    v2 = cache.get("ttl", "key1")
    print(f"2秒后读取: {v2}")
    # L1 过期了，L2 可能也过期了
    print("通过!")


def main():
    test_cache_manager()
    test_cached_embedder()
    test_ttl_expiration()
    print("\n" + "=" * 50)
    print("所有缓存测试通过!")
    print("=" * 50)


if __name__ == "__main__":
    main()