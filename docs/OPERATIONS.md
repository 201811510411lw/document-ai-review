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

## 数据库准备

StarRocks 保存同步后的来源数据。按 [SQL 指南](sql/README.md) 创建来源表，并由外部同步作业持续装载 SRM、批次报告和 OA 数据。

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

基础检查：

```bash
curl http://127.0.0.1:8000/health
/home/lsym005226/project/starrocks-cleanup-audit/ai-env/bin/python scripts/generate_api_operation_inventory.py --check
/home/lsym005226/project/starrocks-cleanup-audit/ai-env/bin/pytest
```

OpenAPI 清单校验只证明路由契约未漂移，不证明 SRM、StarRocks、OCR、LLM、企业微信或影刀 RPA 已正确配置。上线前还应对目标环境执行只读连接和现有记录查询。

前端验证：

```bash
cd web-console
npm test
npm run build
```

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
| 来源接口返回不可用或记录不存在 | 检查 StarRocks 连接、同步延迟、租户与业务筛选条件；不要回退为伪造数据 |
| Review Result 保存失败 | 检查数据库是否存在、账号 DDL/DML 权限及兼容列创建日志 |
| OA 附件无法准备 | 检查 NAS 挂载、允许根目录、文件是否加密、zip 是否有效及路径是否越界 |
| OCR / LLM 失败 | 检查文件类型与内容、模型配置、API Secret、超时和 provider 日志 |
| 通知持续失败 | 检查 `WECOM_WORKER_TOKEN`、企业微信应用配置、队列 `attempts` 和最后错误 |
| RPA 返回 `ERROR` | 检查影刀鉴权、精确账号/机器人配置、超时和响应完整性；不要解释为业务不通过 |
| OpenAPI 检查失败 | 重新生成 operation 清单，审阅路由增删后再提交文档变化 |
