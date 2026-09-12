"""问答耗时的真实记录（app/access/routes.py）。

背景：原先写查询日志时 `elapsed_ms=0` 是硬编码的，导致 /query-logs 返回的耗时
永远是 0、前端只能显示"?"，也没有任何可信的性能数据。改为实测后需要锁住行为，
避免以后又被改回常量。
"""

from __future__ import annotations

import time

from app.access.routes import _elapsed_ms


class TestElapsedMs:
    """_elapsed_ms：请求入口至当前的毫秒数。"""

    def test_none_returns_zero(self):
        """调用方未计时（None）时返回 0，而不是抛异常或给假值。

        早期返回路径（兜底规则命中、无命中）不经过计时，允许传 None。
        """
        assert _elapsed_ms(None) == 0

    def test_measures_elapsed_time(self):
        """确实反映经过的时间——这正是替代硬编码 0 的关键。"""
        start = time.perf_counter()
        time.sleep(0.05)

        ms = _elapsed_ms(start)

        assert 40 <= ms < 1000, f"睡 50ms 应测得约 50ms，实际 {ms}ms"

    def test_immediate_call_is_non_negative(self):
        """刚起计时就取值不得出现负数。"""
        assert _elapsed_ms(time.perf_counter()) >= 0

    def test_returns_int(self):
        """必须是整数毫秒，才能直接写入 QueryLog.elapsed_ms（Integer 列）。"""
        assert isinstance(_elapsed_ms(time.perf_counter()), int)
