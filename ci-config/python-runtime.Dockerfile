# Python runtime base image for document-ai-review.
# Build context: repository root is not required; this file can be built alone.

ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}

ENV TZ=Asia/Shanghai \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

RUN set -eux; \
    . /etc/os-release; \
    rm -f /etc/apt/sources.list.d/*; \
    printf "deb https://mirrors.aliyun.com/debian/ %s main\n" "$VERSION_CODENAME" > /etc/apt/sources.list; \
    printf "deb https://mirrors.aliyun.com/debian/ %s-updates main\n" "$VERSION_CODENAME" >> /etc/apt/sources.list; \
    printf "deb https://mirrors.aliyun.com/debian-security %s-security main\n" "$VERSION_CODENAME" >> /etc/apt/sources.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        libglib2.0-0 \
        libjpeg62-turbo \
        libpng16-16 \
        poppler-utils; \
    rm -rf /var/lib/apt/lists/*
