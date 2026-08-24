# Capability Status

本文档回答“项目当前能做什么”。状态根据可运行代码、公共入口、结果保存和测试共同判断，
不根据目录名或原始 PRD 推断。

## 状态定义

| 状态 | 含义 |
| --- | --- |
| `implemented` | 当前范围内已有可调用入口、Review Workflow、Domain Rules、结果输出和回归测试 |
| `partial` | 核心 Workflow 已存在，但公共入口、结果查询、人工复核或运营闭环仍不完整 |
| `placeholder` | 为架构路由保留入口，但不会执行真实业务审核 |
| `planned` | 只有明确需求或设计，尚未注册为当前 Review Use Case |

`implemented` 不表示所有外部集成都默认可用。数据库、OCR、LLM、企业微信或 RPA 仍可能因
配置关闭、凭据缺失或网络不可用而失败。

## 总览

| Review Use Case | 状态 | 当前文档类型 | 主要入口 | 结果闭环 |
| --- | --- | --- | --- | --- |
| `business_license` | `implemented` | `business_license` | 文件创建、SRM 创建、列表、详情、人工复核 | 统一结果、营业执照投影、审计事件 |
| `food_license` | `partial` | `food_license` | 文件创建、SRM 创建 | 有审核与投影；无食品证专属查询和人工复核 API |
| `food_production_license` | `implemented` | `food_production_license` | QC SRM 创建、QC 查询和人工复核 | 统一结果和食品生产许可证投影 |
| `qc_document_review` | `implemented` | `product_report`、`batch_report` 等 | SRM/StarRocks 创建、QC 查询和人工复核 | 统一 QC 投影、产品报告及检验项目投影 |
| `tobacco_license` | `partial` | `tobacco_license` | 一致性审核内部的证照识别 Workflow | 有结构化审核结果；无独立烟草证创建和查询 API |
| `tobacco_license_consistency_review` | `implemented` | `business_tobacco_consistency` 等 | 待处理门店、单条/批量审核、人工复核、OA 结果、报告详情 | 统一结果、烟草报告、来源证据和 RPA 结果 |
| `contract_review` | `placeholder` | `contract`、`lease_contract` 等 | Review Registry 路由和前端占位列表 | 只返回未实现和人工复核状态，不执行合同规则 |

当前没有标记为 `planned` 的注册 Review Use Case。规划中的能力必须先形成需求和验收标准，
不能提前加入当前能力表。

## `business_license`

### 当前范围

- 接受 PDF、JPG、JPEG、PNG 的受信任本地路径或远程 URI。
- 可从 SRM/StarRocks 同步表准备一条供应商营业执照 Source Task。
- 执行文档获取、OCR/视觉抽取、字段标准化、Domain Rules 和人工复核路由。
- 保存完整 `ReviewResult`、营业执照查询投影和人工复核审计事件。

### 当前边界

- 不接受 `ocr_text` 或 `file.stub_text` 作为真实审核输入。
- 不负责烟草证字段和双证一致性规则。
- 不直接执行 OA 回写或企业微信通知。

业务规则口径见
[business-license-review](../.agents/skills/business-license-review/SKILL.md)。

## `food_license`

### 当前范围

- 接受真实 PDF 或图片文件，也可从 SRM 来源记录创建审核。
- 执行食品经营许可证字段抽取、基础规则和结果保存。

### 当前边界

- 不接受文本替身输入。
- 当前没有食品经营许可证专属的查询、详情和人工复核 HTTP 入口，因此状态为 `partial`。
- 工作台是否展示对应记录取决于当前结果投影和前端聚合范围。

业务规则口径见 [food-license-review](../.agents/skills/food-license-review/SKILL.md)。

## `food_production_license`

### 当前范围

- 从 SRM/StarRocks 同步数据准备食品生产许可证 Source Task。
- 执行文件获取、字段抽取、规则校验和统一结果保存。
- 通过 QC 共享接口查询详情和提交人工复核。

### 当前边界

- 当前没有直接上传或任意文件 URI 的专属创建接口。
- 结果读取和人工复核使用 QC 聚合路径，不新增第二套业务逻辑。

业务规则口径见
[food-production-license-review](../.agents/skills/food-production-license-review/SKILL.md)。

## `qc_document_review`

### 当前范围

- `product_report` 从 SRM SKU 材料准备专用 Source Task。
- `batch_report` 从 StarRocks 批次报告来源按审核日期准备 Source Task。
- PDF 优先读取文本层，缺少文本层时再使用 OCR 或视觉 adapter。
- 产品报告执行报告编号、产品名称、供应商/生产者、日期、结论和检验项目抽取。
- 第三方检验报告有效期按签发或批准日期加 180 天计算。
- 通过 QC 聚合入口完成列表、详情和人工复核。

### 当前边界

- LLM/OCR 只辅助抽取和结构化；最终风险和人工复核由 Domain Rules 决定。
- `product_report` 是 SKU 材料，不复用供应商证照 Source Task 语义。

业务规则口径见 [qc-document-review](../.agents/skills/qc-document-review/SKILL.md)。

## `tobacco_license`

### 当前范围

- 识别烟草专卖零售许可证并生成统一 Review Result。
- 作为烟草证一致性审核中的证照识别 Workflow 使用。
- OA 烟草来源文件由 ecology MySQL 实时查询后准备到受控本地目录；StarRocks ODS 仍可用于历史或分析查询。

### 当前边界

- 当前没有独立的烟草证审核创建、列表或人工复核 API，因此状态为 `partial`。
- 官网真伪核验属于一致性审核旁路的 RPA integration，不属于单证 Domain Rule。

业务规则口径见
[tobacco-license-review](../.agents/skills/tobacco-license-review/SKILL.md)。

## `tobacco_license_consistency_review`

### 当前范围

- 查询 OA 待处理门店，准备营业执照和烟草证附件并执行单条或批量一致性审核。
- 支持 OA 以 `workflow_id + requestid` 精确、幂等触发后台自动审核，将最终结果推送到固定回调地址，并使用专用 token 轮询结果。
- 支持 `standard` 和 `store_in_store` 两种审核模式。
- 对主体名称、经营地址、负责人、有效期和店中店证明执行确定性规则。
- 可在配置启用时执行影刀官网验真，将结果保存到同一 Review Result。
- 提供报告列表、详情、持久化人工复核和 OA 四态决策结果。

### 当前边界

- 当前有 OA 专用 token 的异步受理与轮询接口，并向服务端配置的固定地址主动回调；系统不替 OA 推进流程。
- RPA 的 `FAILED` 是业务负面结果；`ERROR` 是未可靠完成的技术异常，两者不能混用。

业务规则口径与单证来源约定共同维护在
[tobacco-license-review](../.agents/skills/tobacco-license-review/SKILL.md)。

## `contract_review`

### 当前范围

- 保留 Review Registry 路由和统一 Review Result 形状。
- 调用时明确返回 `implementation_status=not_implemented`，并进入人工复核。

### 当前边界

- 不执行合同字段抽取、条款审查、风险规则或修改建议生成。
- 前端合同报告列表是占位产品界面，不代表合同审核已交付。

## 横向平台能力

| 能力 | 当前状态 |
| --- | --- |
| 统一 Review Registry | 显式注册全部内置 Review Use Case，并按名称或文档类型路由 |
| 结果保存 | 完整 JSON 快照加业务投影表 |
| 人工复核 | 营业执照、QC 和烟草一致性已有 HTTP 入口；食品证能力不完全一致 |
| Web Console | 登录、看板、查询、审核、导入、记录管理、烟草报告和个人资料 |
| 企业微信 | SSO、通知队列和受独立 token 保护的 worker |
| 调度 | API 启动时尝试启动每日审核调度器；失败不阻断 API 启动 |
| 外部识别 | 本地/远程文件、PDF 文本层、RapidOCR、阿里云 OCR、Qwen/视觉 adapter |
| RPA 验真 | 影刀能力探测、同步触发、轮询、callback 兜底和状态查询 |
