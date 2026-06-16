# web-console

营业执照审核结果工作台前端。

当前版本默认调用 `ai-service` 的营业执照审核结果 API，并提供轻量登录验证和人工复核写回，便于本地打开前台页面做真实 API 联调。

当前版本已接入企业微信 OAuth 登录和审核通知 worker。企微内打开时复用同一套 `/reviews` 与 `/reviews/{task_id}` 页面；本地账号登录仍作为开发和应急 fallback 保留。

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

登录成功后，前端会把本地 bearer token 保存在 `localStorage`，并在查询营业执照审核结果列表和详情时自动带上 `Authorization` 请求头。企业微信 OAuth 回调由后端写入 `HttpOnly` cookie，前端启动时通过 `/api/v1/auth/me` 恢复会话。未登录或 token 失效时会回到 `/login`。

## 企业微信接入

后端配置：

```bash
WECOM_CORP_ID=<企业 ID>
WECOM_AGENT_ID=<自建应用 AgentId>
WECOM_SECRET=<自建应用 Secret>
WECOM_REDIRECT_URI=https://your-domain.example.com/api/v1/auth/sso/callback?provider=wecom
WECOM_REVIEWER_USER_IDS=
WECOM_ADMIN_USER_IDS=
WECOM_WORKER_TOKEN=<worker bearer token>
WECOM_NOTIFICATION_BASE_URL=https://your-domain.example.com
WEB_CONSOLE_BASE_URL=https://your-domain.example.com
```

企微后台需要配置：

- 自建应用 OAuth2.0 网页授权回调域名，需匹配 `WECOM_REDIRECT_URI` 的域名；
- 自建应用可信 IP，需包含 `ai-service` 出口 IP；
- 应用可见范围，需包含审核员；登录准入由企微应用可见范围控制，系统侧不再维护登录白名单；
- 企微工作台入口可配置为 `https://your-domain.example.com/reviews`。

接口：

```text
GET /api/v1/auth/providers
GET /api/v1/auth/sso/start?provider=wecom
GET /api/v1/auth/sso/callback?provider=wecom
GET|POST /api/v1/wecom/notifications/worker
```

营业执照审核保存后，若结果为高风险、审核失败或待人工复核，会写入持久化企微通知队列。`WECOM_REVIEWER_USER_IDS` 可选；不配置时默认发送给企微应用可见范围内的 `@all`。worker 使用如下方式触发发送：

```bash
curl -H "Authorization: Bearer $WECOM_WORKER_TOKEN" \
  https://your-domain.example.com/api/v1/wecom/notifications/worker
```

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
