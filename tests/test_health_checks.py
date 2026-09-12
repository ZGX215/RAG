"""健康检查分层与优雅关闭（app/access/app.py）。

为什么值得单独测：这两项是"运维契约"。探针语义错了后果很具体 ——
liveness 探了数据库，会让"依赖抖动"被误判成"进程死了"从而反复重启容器；
readiness 不返回 503，会让依赖已挂的实例继续接收流量。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import app.access.app as app_module


class TestHealthEndpoints:
    """liveness / readiness / 综合检查的语义差异。"""

    def test_liveness_does_not_touch_dependencies(self, monkeypatch):
        """liveness 只表示进程存活，必须不查任何依赖。

        若它去查数据库，"数据库不可用"会被编排误判为"进程死了"并重启容器 ——
        而重启对数据库故障毫无帮助，只会放大故障。
        """
        called = {"n": 0}

        def _record():
            called["n"] += 1
            return []

        monkeypatch.setattr(app_module, "_check_dependencies", _record)

        r = TestClient(app_module.app).get("/health/live")

        assert r.status_code == 200
        assert r.json()["status"] == "alive"
        assert called["n"] == 0, "liveness 不应触发任何依赖探测"

    def test_readiness_reports_checks_list(self):
        r = TestClient(app_module.app).get("/health/ready")

        assert r.status_code in (200, 503)
        body = r.json()
        assert body["status"] in ("ready", "not_ready")
        assert isinstance(body["checks"], list) and body["checks"]

    def test_readiness_returns_503_when_required_dependency_down(self, monkeypatch):
        """核心依赖不可用必须 503，否则上游不会摘流量。"""
        monkeypatch.setattr(
            app_module, "_check_dependencies",
            lambda: [{"name": "vector_store", "ok": False,
                      "detail": "not initialized", "required": True}],
        )

        r = TestClient(app_module.app).get("/health/ready")

        assert r.status_code == 503
        assert r.json()["status"] == "not_ready"

    def test_optional_dependency_failure_does_not_block_readiness(self, monkeypatch):
        """可选依赖（Redis）挂掉不应让 readiness 变 503 —— 服务会降级但仍可用，
        此时摘掉流量反而制造了可用性事故。"""
        monkeypatch.setattr(
            app_module, "_check_dependencies",
            lambda: [
                {"name": "vector_store", "ok": True, "detail": "661 chunks", "required": True},
                {"name": "redis", "ok": False, "detail": "ConnectionRefused", "required": False},
            ],
        )

        assert TestClient(app_module.app).get("/health/ready").status_code == 200

    def test_health_stays_200_and_exposes_detail(self):
        """综合检查不做状态码语义，始终 200 并给出明细，供人工排查。"""
        r = TestClient(app_module.app).get("/health")

        assert r.status_code == 200
        body = r.json()
        assert "total_chunks" in body
        assert isinstance(body["checks"], list)


class TestGracefulShutdown:
    """资源释放流程的健壮性。"""

    def test_safe_when_nothing_initialized(self):
        """未初始化任何资源时释放也不得抛异常。

        关闭流程抛异常会让容器看到非零退出码，掩盖真正的问题。
        """
        app_module._shutdown_resources()
        app_module._shutdown_resources()  # 重复调用同样安全

    def test_component_failure_does_not_abort_others(self, monkeypatch):
        """单项释放失败不能中断其余资源的释放（逐项 try/except 的意义）。"""
        class _Broken:
            def close(self):
                raise RuntimeError("simulated close failure")

        monkeypatch.setattr(app_module, "_repo", _Broken())

        app_module._shutdown_resources()  # 不应向外抛出

    def test_lifespan_invokes_release_on_exit(self, monkeypatch):
        """应用退出时 lifespan 必须真的调用资源释放。

        这条锁的是"接线正确"——释放函数写得再好，没挂到 lifespan 上就等于没有，
        容器停止时仍然是被硬杀。
        """
        calls = []
        monkeypatch.setattr(app_module, "_shutdown_resources", lambda: calls.append(1))

        with TestClient(app_module.app) as client:
            client.get("/health/live")

        assert calls == [1], "退出应用时必须触发且只触发一次资源释放"
