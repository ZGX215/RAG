# ============================================================
# 多阶段构建：builder 阶段装依赖，final 阶段只留运行时
# 镜像更小，构建更快，安全面更小
# ============================================================

FROM python:3.11-slim AS builder

WORKDIR /build

# 装编译依赖（sentence-transformers / numpy 需要）
# 构建完就扔，不进最终镜像
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# 先拷 requirements，利用 Docker 缓存
COPY requirements.txt .

# 先单独装 CPU 版 torch —— 必须排在 requirements 之前。
# Linux 上 PyPI 的 torch 默认是 CUDA 构建（wheel 529MB），并会额外拉
# nvidia-cudnn / nccl / cusparselt / nvshmem 共 4 个包，合计 1.5~2GB+，
# 而本服务配置是 EMBEDDING_DEVICE=cpu，根本用不到 GPU，纯属白占体积。
# 先装 CPU 版把依赖提前满足，后面 pip 就不会再拉 CUDA 版。
# 该命令已在 CI（Linux + Python 3.11）实测通过；本镜像同为 Debian 系、同 Python 版本。
RUN pip install --no-cache-dir --prefix=/install \
    torch --index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ============================================================
# final 阶段：运行时镜像
# ============================================================

FROM python:3.11-slim AS final

WORKDIR /app

# 运行时只需要最小系统依赖
# - libgomp1: sentence-transformers 需要
# - curl: 健康检查用
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 从 builder 阶段拷贝已装好的 Python 包
COPY --from=builder /install /usr/local

# 拷项目源码（除了 .dockerignore 里排除的）
COPY . .

# 数据目录挂载点：embedding 模型、ChromaDB、SQLite 都放这里
# 用 volume 挂载，数据不进镜像，容器删了数据还在
VOLUME ["/app/data"]

# 暴露 API 端口
EXPOSE 8000

# 默认启动 web 服务
# 也可以通过 docker-compose 覆盖 command 来启动 celery worker
CMD ["python", "main.py"]
