# 运维手册

## 配置

应用导入 `app.core.config` 时加载配置。优先级从高到低为：

1. 进程启动前已经存在的 Shell 环境变量。
2. `ai-service/.env` 中 `SECRET_ENV_KEYS` 白名单内的 Secret。
3. 仓库根 `.env` 中白名单内的 Secret。
4. `DOCUMENT_AI_REVIEW_CONFIG_FILE` 指向的 YAML。
5. `app-config/app.local.yaml`。
6. `app-config/app.yaml`。

`.env` 文件只接收 `SECRET_ENV_KEYS`；数据库地址、模型名、开关等非敏感配置必须放在 YAML 或真实 Shell 环境。以 `.env.example` 和 `app-config/app.yaml.example` 为模板，不要提交实际 `.env`、`app.local.yaml` 或凭据。

OA 自动审核必须配置独立的 `OA_AUTO_REVIEW_TOKEN`。未配置或请求头
`X-OA-Token` 不匹配时，触发和轮询接口均返回 HTTP 401。
OA 结果回调地址通过 YAML 的 `oa_auto_review.callback_url` 配置。未配置时触发接口返回
HTTP 503 `OA_CALLBACK_NOT_CONFIGURED`；回调当前使用无认证 HTTP POST。修改 ConfigMap 后必须
确认 Deployment 已滚动，并在新 Pod 进程中核对实际加载地址，不能只检查 Git 或 ConfigMap。

## 数据库准备

StarRocks 保存同步后的 SRM 和批次报告来源数据；烟草 OA 自动审核直接查询 ecology MySQL。按 [SQL 指南](sql/README.md) 创建 StarRocks 来源表，并由外部同步作业持续装载 SRM、批次报告数据。

Review Result MySQL 保存统一结果、业务投影、人工复核、审计和通知队列。repository 首次使用时执行 `CREATE TABLE IF NOT EXISTS`，并为兼容字段执行必要的 `ALTER TABLE`；运行账号因此需要目标数据库的建表和变更权限。先创建 `REVIEW_RESULT_MYSQL_DATABASE` 对应数据库，再配置账号、密码和网络访问。

## 来源同步与调度器

FastAPI 启动时尝试创建后台线程 `daily-review-scheduler`，默认按服务器本地时间每日 `02:00` 执行 SRM 证照和产品报告、StarRocks 批次报告同步审核。数据库配置或连接失败只记录 warning，不阻断 API 启动；应通过启动日志确认线程实际运行。

`tobacco_consistency.daily_sync_enabled` 当前只有配置映射，`daily-review-scheduler` 不读取它。它不是已生效的 OA 烟草一致性自动同步开关，不能据此判断该任务已启用。

手动来源同步入口会访问真实来源库。执行前先确认租户、时间范围、去重条件和目标环境，避免重复创建 Review Task。

## 企业微信通知 worker

审核完成后通知记录进入 Review Result MySQL 队列。通过 `GET` 或 `POST /api/v1/wecom/notifications/worker` 消费到期记录，请求必须携带独立的 `WECOM_WORKER_TOKEN`。单条发送失败会记录错误并退避重试，达到 3 次后标记失败。

生产环境应由受控调度平台调用 worker，并限制 token 的读取范围。不要把 worker token 当作用户会话 token，也不要记录请求 Authorization header。

## 启动与验证

后端使用项目约定解释器：

```bash
cd ai-service
/home/lsym005226/project/starrocks-cleanup-audit/ai-env/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

日常快速验证在仓库根目录按改动范围执行，不默认运行全量测试：

```bash
make verify-oa-tobacco
make verify-frontend
```

后端服务启动后，可在 `ai-service` 目录执行接口与清单检查：

```bash
curl http://127.0.0.1:8000/health
/home/lsym005226/project/starrocks-cleanup-audit/ai-env/bin/python scripts/generate_api_operation_inventory.py --check
```

其他范围使用 `make verify-test TESTS='tests/test_file.py::test_name'`。`make verify-full` 仅用于显式要求的全量诊断，不作为提交、Jenkins 镜像构建或部署门禁。

OpenAPI 清单校验只证明路由契约未漂移，不证明 SRM、StarRocks、OCR、LLM、企业微信或影刀 RPA 已正确配置。镜像部署到 UAT 后应针对改动执行真实业务验收；OA 烟草流程使用新的 `workflow_id + requestid`，或对现有请求使用更高的 `submission_version`，核对运行镜像来源、持久化结果、实际 callback JSON、OA 业务接收状态和最终节点流转。

前端本地验证：

```bash
make verify-frontend
```

生产前端构建由 Jenkins 随镜像构建统一执行。本地仅在定位构建问题或用户明确要求时运行 `cd web-console && npm run build`。

构建后的 `web-console/dist` 存在时，FastAPI 会将其挂载为 SPA 静态站点；API 路径和带扩展名的静态资源不会回退到 `index.html`。

## 部署与安全

- 将非敏感 YAML 作为 ConfigMap 类配置，将 Secret 作为受控环境变量或 Secret 文件注入。
- 仅允许应用访问所需来源表、结果数据库、NAS 目录和外部 API。
- Review Result MySQL 账号当前需要 DDL 权限；若安全基线禁止运行时 DDL，应在发布流程预建完全兼容的表结构并单独验证。
- 默认关闭真实影刀调用，完成租户账号、机器人 UUID 和回调网络核对后再启用。
- 日志和故障工单中必须脱敏 token、密码、证书和账号信息。

## 故障排查

| 现象 | 检查项 |
| --- | --- |
| API 正常但每日任务未运行 | 检查启动日志中的 `daily-review-scheduler`、服务器本地时区、数据库配置；不要依赖 `daily_sync_enabled` |
| 来源接口返回不可用或记录不存在 | 按接口类型检查 OA ecology MySQL 或 StarRocks 连接、源表记录与业务筛选条件；不要回退为伪造数据 |
| Review Result 保存失败 | 检查数据库是否存在、账号 DDL/DML 权限及兼容列创建日志 |
| OA 附件无法准备 | 检查 NAS 挂载、允许根目录、文件是否加密、zip 是否有效及路径是否越界 |
| OA 调用连接超时 | 从 OA 服务器检查域名解析、443/目标端口、防火墙、反向代理和服务监听；连接超时发生在 HTTP 建连阶段，与 JSON 参数无关 |
| OA 返回 `SOURCE_RECORD_NOT_READY` | 检查 OA ecology MySQL 的连通性、源表中的精确 `workflow_id`/`requestid` 及 NAS 文件落盘；当前“烟草商品建档申请”流程应传 `614`，禁止改为门店模糊查询 |
| OA 长时间返回 `REVIEW_IN_PROGRESS` | 检查对应 `review_results` 是否为 `RUNNING` 以及执行实例日志；系统不会自动抢占运行态任务，只有确认原执行者已停止后才能人工清理占位并重试 |
| OA 没有收到结果回调 | 在详情页“OA 回调记录”核对实际目标、请求 JSON、HTTP 状态、响应正文和业务确认状态；HTTP 2xx 空响应只代表送达，不代表 OA 节点已推进；Pod 中途重启时使用 `oa-result` 轮询恢复 |
| OCR / LLM 失败 | 检查文件类型与内容、模型配置、API Secret、超时和 provider 日志 |
| 通知持续失败 | 检查 `WECOM_WORKER_TOKEN`、企业微信应用配置、队列 `attempts` 和最后错误 |
| RPA 返回 `ERROR` | 检查影刀鉴权、精确账号/机器人配置、超时和响应完整性；不要解释为业务不通过 |
| OpenAPI 检查失败 | 重新生成 operation 清单，审阅路由增删后再提交文档变化 |
