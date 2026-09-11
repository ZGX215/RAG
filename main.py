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
from app.access.app import init_repo, app
init_repo()

# 初始化关系型数据库表
from app.db.database import init_db
init_db()

# 预热：在后台线程中发送第一个请求，加载所有模型
def _warmup():
    import time
    import requests
    import logging
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    time.sleep(3)  # 等 uvicorn 启动
    try:
        r = requests.post(
            f"http://localhost:{settings.api.port}/api/v1/qa",
            json={"question": "你好", "top_k": 1},
            headers={"X-User-Clearance": "public"},
            timeout=120,
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