"""日志基础设施（P1 最小可用版）

P1 只做：控制台输出 + 按天滚动文件。
P3 再升级：全链路追踪、结构化日志、日志采样。
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


def setup_logging(
    log_dir: str = "./data/logs",
    log_level: str = "INFO",
    app_name: str = "enterprise-rag",
) -> logging.Logger:
    """初始化应用日志。

    参数:
        log_dir: 日志文件目录（不存在则自动创建）
        log_level: 日志级别（DEBUG/INFO/WARNING/ERROR）
        app_name: 应用名，同时也是 logger 名和日志文件名前缀

    返回:
        应用根 logger
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(app_name)
    logger.setLevel(log_level.upper())

    # 避免重复添加 handler（多次调用 setup_logging 时）
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 控制台 handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 文件 handler（按天滚动，保留 30 天）
    file_handler = TimedRotatingFileHandler(
        filename=log_path / f"{app_name}.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """获取子模块 logger。

    用法::

        logger = get_logger(__name__)
        logger.info("embedding %d texts", len(texts))
    """
    return logging.getLogger(f"enterprise-rag.{name}")