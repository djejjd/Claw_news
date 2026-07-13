# syntax=docker/dockerfile:1.7
FROM python:3.12-slim@sha256:401f6e1a67dad31a1bd78e9ad22d0ee0a3b52154e6bd30e90be696bb6a3d7461

WORKDIR /app
ENV PIP_DEFAULT_TIMEOUT=120

# Install system dependencies for curl-cffi
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    libcurl4-openssl-dev \
    && rm -rf /var/lib/apt/lists/*

ARG PIP_INDEX_URL
ARG PIP_EXTRA_INDEX_URL

# 先只拷贝依赖文件，利用 Docker 缓存 — 业务代码变更不触发重装
COPY pyproject.toml .
# pip install . 需要包目录存在，建空壳让它通过，装完即删
RUN mkdir -p collectors aggregator infra pusher app \
    && touch collectors/__init__.py aggregator/__init__.py \
           infra/__init__.py pusher/__init__.py app/__init__.py
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    PIP_INDEX_URL="${PIP_INDEX_URL}" PIP_EXTRA_INDEX_URL="${PIP_EXTRA_INDEX_URL}" \
    pip install "setuptools>=68" wheel \
    && PIP_INDEX_URL="${PIP_INDEX_URL}" PIP_EXTRA_INDEX_URL="${PIP_EXTRA_INDEX_URL}" \
    pip install --no-build-isolation . \
    && rm -rf collectors aggregator infra pusher app

# 再拷贝源码 — 日常迭代只有这一层重建
COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
