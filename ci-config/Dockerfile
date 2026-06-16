# Single-image production build for document-ai-review.
# Build context: repository root.

ARG BASE_IMAGE=prod-mirror-cn-beijing.cr.volces.com/metadata/document-ai-review-deps:node22-python311-v1

FROM ${BASE_IMAGE} AS web-builder
WORKDIR /app/web-console
ENV npm_config_registry=https://registry.npmmirror.com \
    npm_config_disturl=https://npmmirror.com/mirrors/node
COPY web-console/package*.json ./
RUN npm ci
COPY web-console ./
RUN npm run test -- --run && npm run build

FROM ${BASE_IMAGE} AS runtime
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai \
    PORT=8000 \
    PATH=/opt/document-ai-review/venv/bin:$PATH

COPY ai-service /app/ai-service
COPY .agents /app/.agents
COPY --from=web-builder /app/web-console/dist /app/web-console/dist

WORKDIR /app/ai-service
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
