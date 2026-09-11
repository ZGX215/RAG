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

# ─────────────────────────────────────────────────────────────
# 关键一行：让 pip 的"已安装"检查能看到 --prefix 目标目录。
#
# 为什么必须加（CI 里的镜像内容断言实测抓到的真问题）：
#   pip 的"已满足"检查基于**当前解释器 sys.path**，而 `--prefix=/install` 把包
#   装到了 sys.path 之外。于是下面第二步 `pip install -r requirements.txt`
#   看不到已装好的 CPU 版 torch，判定 `torch>=2.2` 未满足 → 重新从 PyPI 解析 →
#   把 554MB 的 CUDA 版 torch 连同 nvidia-cudnn / nccl / cusparselt / nvshmem、
#   cuda-toolkit、triton 一起装回来。表象是"构建成功"，实际 CPU 版被静默替换，
#   白白多占 1.5~2GB —— 只验证"构建成功"是发现不了的。
#   把 /install 的 site-packages 放进 PYTHONPATH 后，pip 就能看到它并跳过重装。
#   （该目录在第一次 pip 时还不存在，不受影响。）
# 注：ENV 只在 builder 阶段生效，不会带入 final 阶段（多阶段构建各阶段独立）。
# ─────────────────────────────────────────────────────────────
ENV PYTHONPATH=/install/lib/python3.11/site-packages

# 先单独装 CPU 版 torch —— 必须排在 requirements 之前。
# Linux 上 PyPI 的 torch 默认是 CUDA 构建（wheel 500MB+），并会额外拉
# nvidia-cudnn / nccl / cusparselt / nvshmem、cuda-toolkit、triton 等一大批包，
# 合计 1.5~2GB+，而本服务配置是 EMBEDDING_DEVICE=cpu，根本用不到 GPU，纯属白占体积。
RUN pip install --no-cache-dir --prefix=/install \
    torch --index-url https://download.pytorch.org/whl/cpu

# 再装其余依赖。此时 pip 能看到上面装好的 torch（靠上面那行 PYTHONPATH），
# 判定 torch>=2.2 已满足 → 不会重装成 CUDA 版。
# 额外加 --extra-index-url 作第二道保险：万一日后版本约束变化导致 torch 仍需
# 重新解析，也会优先取到 CPU 版（PEP 440 里 2.x.y+cpu 高于 2.x.y）。
RUN pip install --no-cache-dir --prefix=/install \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -r requirements.txt

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
