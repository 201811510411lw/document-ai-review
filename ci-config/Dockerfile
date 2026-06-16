# Single-image production build for document-ai-review.
# Build context: repository root.

ARG PYTHON_IMAGE=prod-mirror-cn-beijing.cr.volces.com/metadata/document-ai-review-python-runtime:3.12-slim
ARG NODE_IMAGE=prod-mirror-cn-beijing.cr.volces.com/metadata/node:22-bookworm-slim-pnpm11.5.1

FROM ${NODE_IMAGE} AS web-builder
WORKDIR /app/web-console
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
    PORT=8000 \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

COPY ai-service/requirements.txt /app/ai-service/requirements.txt
RUN pip install --no-cache-dir -r /app/ai-service/requirements.txt
COPY ai-service /app/ai-service
COPY .agents /app/.agents
COPY --from=web-builder /app/web-console/dist /app/web-console/dist

WORKDIR /app/ai-service
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
