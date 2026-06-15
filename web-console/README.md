# web-console

营业执照审核结果工作台前端。

当前版本默认调用 `ai-service` 的营业执照审核结果查询 API，不接入企业微信 SDK、OAuth、权限系统或人工复核写回。

## API 配置

默认同源调用：

```text
/api/v1/business-license/reviews
```

如前端和后端不同源，配置：

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000
```

如需使用本地 mock 数据预览：

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
