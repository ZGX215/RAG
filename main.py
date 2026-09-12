#!/usr/bin/env python3
"""RAG QA 服务启动入口。

初始化模型和 ChromaDB 后再启动 uvicorn，
避免在 uvicorn 事件循环中初始化 ChromaDB 导致数据库打开失败。
启动后自动预热，消除首次请求冷启动。
"""

import sys
import threading
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# 启动即校验配置：生产环境（APP_ENV=production）缺关键配置直接拒绝启动，
# 开发环境只告警。放在最前面，避免加载完模型才发现配置不可用。
from config.settings import settings, validate_runtime_config

validate_runtime_config()

# 先在 main 线程初始化模型 + ChromaDB
from app.access.app import app, init_repo

init_repo()

# 初始化关系型数据库表
from app.db.database import init_db

init_db()

# 预热：在后台线程中发送第一个请求，加载所有模型
def _warmup():
    """预热：发一个会走完整链路（检索 + 生成）的请求，让 embedding 模型
    首次推理、BM25 索引构建、向量库连接都提前完成。

    有两个坑会导致预热形同虚设，这里都已避开：
      1. 问题必须能真正触发检索。原先用的是"你好"，它会命中兜底规则直接返回，
         根本不进检索链路 —— 于是第一个真实请求仍要独自承担数秒冷启动
         （实测检索段 p90 高达 5.8s，而稳态仅 80ms）。
      2. 不再发送 X-User-Clearance 请求头 —— 该头已废弃，鉴权改由服务端
         签发的 token 决定，发它不会带来任何权限，反而容易让人误以为生效。
    """
    import logging
    import time

    import requests
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    time.sleep(3)  # 等 uvicorn 启动
    try:
        r = requests.post(
            f"http://localhost:{settings.api.port}/api/v1/qa",
            json={"question": "STM32F103 的系统时钟频率", "top_k": 3},
            timeout=300,
        )
        logging.getLogger("mcu-rag-qa").info("warmup done: status=%s", r.status_code)
    except Exception as e:
        logging.getLogger("mcu-rag-qa").warning("warmup failed: %s", e)

warmup_thread = threading.Thread(target=_warmup, daemon=True)
warmup_thread.start()

# 再启动 uvicorn（host/port 统一由 config.settings 提供，不再写死）
import uvicorn

uvicorn.run(
    app,
    host=settings.api.host,
    port=settings.api.port,
    log_level=settings.general.log_level.lower(),
)