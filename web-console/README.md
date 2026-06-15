# web-console

营业执照审核结果工作台前端。

当前版本默认调用 `ai-service` 的营业执照审核结果 API，并提供轻量登录验证和人工复核写回，便于本地打开前台页面做真实 API 联调。

当前版本不接入企业微信 SDK、OAuth、权限系统或完整审批流。

## 登录验证

本地默认账号：

```text
账号：reviewer
密码：reviewer123
```

后端可通过环境变量覆盖默认账号和 token 配置：

```bash
WEB_CONSOLE_AUTH_USERNAME=reviewer
WEB_CONSOLE_AUTH_PASSWORD=reviewer123
WEB_CONSOLE_AUTH_SECRET=change-me
WEB_CONSOLE_AUTH_TOKEN_TTL_SECONDS=28800
```

登录成功后，前端会把 bearer token 保存在 `localStorage`，并在查询营业执照审核结果列表和详情时自动带上 `Authorization` 请求头。未登录或 token 失效时会回到 `/login`。

## API 与本地联调

默认使用真实 API client，并同源调用：

```text
/api/v1/business-license/reviews
```

人工复核页会调用：

```text
POST /api/v1/business-license/reviews/{task_id}/manual-review
```

提交后后端会将记录状态更新为 `MANUAL_REVIEWED`，并写入人工复核审计事件。

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

打开 `http://127.0.0.1:5173/reviews`，使用默认账号登录后即可验证前台页面调用真实后端查询 API，并可在详情页进入人工复核页提交复核结论。

如需调用其他后端地址，配置：

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000
```

如需使用本地 mock 数据预览，不依赖后端服务：

```bash
VITE_USE_MOCK_API=true npm run dev
```

mock 预览仍会经过前端登录页；登录请求如果没有后端服务会失败。如只看静态 mock 页面，可先启动 `ai-service` 完成登录，或在浏览器 `localStorage` 写入测试 session 后刷新页面。

## 本地运行

```bash
npm install
npm run dev
```

可预览路由：

- `/reviews`
- `/reviews/blr-20260615-0002`
- `/reviews/blr-20260615-0002/manual-review`
