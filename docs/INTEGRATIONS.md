# 外部集成

本文只描述当前代码已经实现的集成边界。外部依赖未配置时，OpenAPI operation 仍可能存在，但对应业务链路不可用。

## 集成总览

| 集成 | 当前职责 | 主要失败边界 |
| --- | --- | --- |
| SRM | 提供供应商证照和 SKU 产品报告元数据 | 来源记录缺失、附件缺失或字段不满足筛选条件 |
| StarRocks | 承载同步后的 SRM、批次报告和 OA 来源表 | 连接或查询失败时返回明确错误，不伪造 demo 来源 |
| OA | 提供烟草证一致性审核的流程、门店和附件证据 | 提供专用 token 的同步触发与轮询，不主动调用任意 callback URL |
| 企业微信 | OAuth 登录、用户角色映射和审核通知 | 登录配置不完整或通知发送失败 |
| OCR / LLM | 文本获取、视觉识别、字段抽取和解释 | 只辅助抽取和结构化，不能替代 Domain Rule 作最终裁判 |
| 远程文件 | 下载 PDF/JPEG/PNG 并交给文本层、OCR 或视觉 adapter | 超时、HTTP 非 200、空文件、类型不支持或类型冲突 |
| 影刀 RPA | 烟草证官网验真触发、轮询、查询和 callback 兜底 | 业务负面 `FAILED` 与技术未完成 `ERROR` 必须分开 |

## 配置与鉴权映射

非敏感配置以 [`app-config/app.yaml.example`](../app-config/app.yaml.example) 为模板，Secret 以 [`.env.example`](../.env.example) 为模板。下表列出主要映射；完整键集合由 `app.core.config` 决定。

| 集成 | YAML / Shell 配置 | Secret / 鉴权 |
| --- | --- | --- |
| SRM / StarRocks 来源 | `starrocks.host/port/database`，对应 `STARROCKS_HOST/PORT/DATABASE` | `STARROCKS_USER`、`STARROCKS_PASSWORD` |
| Review Result MySQL | `review_result_mysql.host/port/database`，对应 `REVIEW_RESULT_MYSQL_HOST/PORT/DATABASE` | `REVIEW_RESULT_MYSQL_USER`、`REVIEW_RESULT_MYSQL_PASSWORD` |
| OA 来源字段 | `tobacco_consistency.oa_*`，对应 `TOBACCO_CONSISTENCY_OA_BUSINESS_LICENSE_FIELD`、`TOBACCO_CONSISTENCY_OA_RELATIONSHIP_EVIDENCE_FIELD`、`TOBACCO_CONSISTENCY_OA_MULTI_ADDRESS_EVIDENCE_FIELD` | 当前没有 OA 专用 HTTP token；来源库使用 StarRocks 账号 |
| 企业微信 | `wecom.corp_id/agent_id/notification_base_url` 及角色配置，对应 `WECOM_CORP_ID`、`WECOM_AGENT_ID` 等 | `WECOM_SECRET`；通知 worker 另用 `WECOM_WORKER_TOKEN` |
| OCR / LLM | provider、模型、超时等；例如 `BUSINESS_LICENSE_VISION_PROVIDER`、`ALIYUN_OCR_API_URL`、`OPENAI_BASE_URL` | `ALIYUN_OCR_APPCODE`、`OPENAI_API_KEY` |
| 影刀 RPA | `rpa_verification.tobacco_license.*`，对应启用开关、base URL、access key ID、`RPA_VERIFICATION_YINDAO_ROBOT_UUID`、精确账号和超时参数 | `RPA_YINDAO_ACCESS_KEY_SECRET` |
| 远程文件 | 当前支持类型和默认下载超时由 adapter 固定，没有独立 YAML 映射 | 只使用来源 URL 本身提供的访问能力 |

Shell 环境变量可覆盖 YAML；dotenv 文件只加载 Secret 白名单。精确优先级和部署方式见[运维手册](OPERATIONS.md)。

## 关键数据映射

| 来源字段或结果 | 应用内映射 |
| --- | --- |
| SRM `typeName='营业执照'` / `食品经营许可证` / `食品生产许可证` | 对应证照 `declared_document_type` 和供应商维度 Source Task |
| SRM `category='sku'`、`typeName='产品报告'` | `declared_document_type='product_report'` 和 SKU 专用 Source Task |
| StarRocks 批次报告行 | `declared_document_type='batch_report'` 的批次 Source Task |
| OA 流程、门店与三个附件字段 | 烟草一致性来源证据；附件识别结果进入双证 Workflow，OA 门店名不替代证照主体字段 |
| 企业微信用户 ID 与配置角色列表 | Web Console 的 reviewer/admin 访问角色；未匹配用户按配置策略处理 |
| 影刀 `parameter`、`responseId` 与任务状态 | 映射为 `AUTHENTIC`、`FAILED` 或 `ERROR`；缺少可判定证据时不得生成业务负面结论 |

## SRM 与 StarRocks

应用通过 MySQL 协议访问 StarRocks 同步表。营业执照、食品证照和产品报告 Source Task 从 SRM 同步数据构造；批次报告和 OA 烟草证来源也由 StarRocks 查询。建表脚本只定义应用消费的表，不负责把源系统数据同步进来，详见 [StarRocks 来源表](sql/README.md)。

产品报告使用 SKU 专用 Source Task：`category='sku'`、`typeName='产品报告'`，不能复用供应商证照 Source Task 的语义。审核结果不写回来源表，而是写入独立的 Review Result MySQL。

## OA 烟草证来源

OA 流程和附件元数据先同步到 StarRocks。应用查询待处理门店，从允许的 NAS 根目录准备附件，并将文件复制或安全解压到受控数据目录。路径必须位于允许目录内；加密附件、损坏压缩包、缺失文件和越界路径都会产生明确错误。

证照字段必须来自附件识别结果或人工确认，不能使用 OA 门店名称补造主体字段。
OA 自动审核按 `workflow_id=614` 和精确 `requestid` 获取 StarRocks/NAS 附件，
用 `X-OA-Token` 鉴权，并提供同步触发与结果轮询。系统不会主动推进 OA 流程，
也不会调用请求方传入的任意 callback URL。

## 企业微信

企业微信集成包含 OAuth 登录、用户角色映射和审核通知。OAuth 使用应用 `corp_id`、`agent_id` 与 `secret`；角色和未匹配用户策略由非敏感配置控制。

审核完成后可写入通知队列。通知 worker 是独立入口，必须使用 `WECOM_WORKER_TOKEN`，发送失败会按队列策略重试，最多 3 次。该 token 不等同于 Web Console 会话，也不应放入 YAML。

## OCR、LLM 与远程文件

真实 PDF 优先读取文本层；文本层缺失时再使用 OCR 或视觉解析 adapter。远程下载当前只接受 PDF、JPEG 和 PNG，通过 HTTP 状态、内容和文件类型校验后才进入识别流程。

OCR / LLM 可用于字段抽取、归一化、解释和结构化输出。最终通过、不通过、风险等级和是否进入人工复核由确定性的 Domain Rule 与 `RuleResult` 汇总。

## 影刀 RPA

影刀 RPA 是可选的烟草证官网验真集成。启用后，服务获取 token、启动机器人任务、使用 `data.jobUuid` 轮询结果，并将状态保存到同一 Review Result；callback 仅作为供应商回调兜底。

- `AUTHENTIC`：任务完成且官网证据通过。
- `FAILED`：任务完成后的业务负面结果；`parameter=false` 还必须有非空 `responseId`。
- `ERROR`：鉴权、配置、超时、协议或结果不完整等技术问题，不能表述为假证。

不要通过本地测试触发真实 RPA。测试和离线验证应设置 `RPA_VERIFICATION_TOBACCO_ENABLED=false` 或使用替身。

## 安全边界

- Secret 只放 Shell 环境、根 `.env` 或 `ai-service/.env`，不要写入 YAML、日志或文档。
- 不记录 access token、数据库密码、证书内容或完整外部账号信息。
- 远程文件和 OA/NAS 本地文件都必须经过类型与路径边界检查。
- 外部业务负面结果与技术失败分别建模，技术错误不得升级为业务结论。
