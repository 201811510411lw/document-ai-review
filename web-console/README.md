# web-console

营业执照审核结果工作台前端。

当前版本默认调用 `ai-service` 的营业执照审核结果查询 API，不接入企业微信 SDK、OAuth、权限系统或人工复核写回。

## API 与本地联调

默认使用真实 API client，并同源调用：

```text
/api/v1/business-license/reviews
```

本地开发时，Vite 已将 `/api` 代理到 `ai-service` 默认地址，避免 `5173 -> 8000` 直连触发 CORS：

```text
http://127.0.0.1:8000
```

本地联调步骤：

```bash
# 终端 1：启动 ai-service
cd ../ai-service
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 终端 2：启动 web-console
npm install
npm run dev
```

如需调用其他后端地址，配置：

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000
```

如需使用本地 mock 数据预览，不依赖后端服务：

```bash
VITE_USE_MOCK_API=true npm run dev
```

## 本地运行

```bash
npm install
npm run dev
```

可预览路由：

- `/reviews`
- `/reviews/blr-20260615-0002`
- `/reviews/blr-20260615-0002/manual-review`
