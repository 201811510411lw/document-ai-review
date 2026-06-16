# Single-image production build for document-ai-review.
# Build context: repository root.

ARG PYTHON_IMAGE=python:3.12-slim
ARG NODE_IMAGE=node:22-bookworm-slim

FROM ${NODE_IMAGE} AS web-builder
WORKDIR /build/web-console
ENV npm_config_registry=https://registry.npmmirror.com \
    npm_config_disturl=https://npmmirror.com/mirrors/node
COPY web-console/package*.json ./
RUN npm ci
COPY web-console ./
RUN npm run test -- --run && npm run build

FROM ${PYTHON_IMAGE} AS runtime
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai \
    PORT=8000

RUN apt-get update \
    && apt-get install -y --no-install-recommends poppler-utils libjpeg62-turbo libpng16-16 \
    && rm -rf /var/lib/apt/lists/*

COPY ai-service/requirements.txt /app/ai-service/requirements.txt
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r /app/ai-service/requirements.txt

COPY ai-service /app/ai-service
COPY .agents /app/.agents
COPY --from=web-builder /build/web-console/dist /app/web-console/dist

WORKDIR /app/ai-service
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
