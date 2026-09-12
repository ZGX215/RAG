"""Celery 应用实例（P3 异步任务基座）。

所有 Celery 任务都注册在此 app 上，通过 config.settings 读取配置。
"""

from __future__ import annotations

from celery import Celery

from config.settings import settings

celery_app = Celery(
    "enterprise_rag",
    broker=settings.celery.broker_url,
    backend=settings.celery.result_backend,
)

celery_app.conf.update(
    task_serializer=settings.celery.task_serializer,
    result_serializer=settings.celery.result_serializer,
    accept_content=settings.celery.accept_content,
    task_track_started=settings.celery.task_track_started,
    task_time_limit=settings.celery.task_time_limit,
    task_soft_time_limit=settings.celery.task_soft_time_limit,
    imports=("app.ingest.tasks",),
)


@celery_app.task(bind=True)
def debug_task(self) -> str:
    """调试任务：验证 Celery 能正常投递和接收任务。"""
    return f"celery ready: request={self.request!r}"