# Dependency base image for document-ai-review.
# Build context: repository root.

ARG BASE_IMAGE=prod-mirror-cn-beijing.cr.volces.com/metadata/node:22-bookworm-slim-pnpm11.5.1
FROM ${BASE_IMAGE}

ENV TZ=Asia/Shanghai \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    npm_config_registry=https://registry.npmmirror.com \
    npm_config_disturl=https://npmmirror.com/mirrors/node \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    PATH=/opt/document-ai-review/venv/bin:$PATH

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        libglib2.0-0 \
        libgl1 \
        libjpeg62-turbo \
        libpng16-16 \
        poppler-utils \
        python3 \
        python3-dev \
        python3-pip \
        python3-venv \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /deps
COPY ai-service/requirements.txt /deps/requirements.txt
RUN python3 -m venv /opt/document-ai-review/venv \
    && pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r /deps/requirements.txt \
    && ln -sf /opt/document-ai-review/venv/bin/python3 /usr/local/bin/python \
    && ln -sf /opt/document-ai-review/venv/bin/pip3 /usr/local/bin/pip \
    && ln -sf /opt/document-ai-review/venv/bin/uvicorn /usr/local/bin/uvicorn \
    && ln -sf /opt/document-ai-review/venv/bin/pytest /usr/local/bin/pytest
