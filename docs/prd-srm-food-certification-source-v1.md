# PRD: SRM 食品类证照来源接入 V1

本文档定义从 SRM `certification` / `attachment` 表拉取食品类证照来源记录，并接入 Document AI Review Agent / Skill 平台审核链路的 V1 范围。

`README.md` 仍然是项目唯一主上下文。本文档补充 SRM 食品类证照来源接入，不替代既有食品经营许可证、营业执照或平台架构文档。

## Problem Statement

当前 SRM 来源取数链路已经支持营业执照，默认 SQL 通过 `typeName = '营业执照'` 限定来源记录，并将 SRM 行映射为 `business_license` 审核输入。

QC 证照审核场景还需要处理食品经营许可证和食品生产许可证。用户已经验证以下 SRM 条件可以查到食品经营许可证记录：

```sql
t1.typeName = '食品经营许可证'
```

用户也提出食品生产许可证可以通过类似条件查询：

```sql
t1.typeName = '食品生产许可证'
```

如果继续只保留营业执照专用取数入口，食品类证照无法从 SRM 自动进入审核任务，审核人员仍需要手工整理文件 URL、供应商名称、统一社会信用代码等输入，无法形成可追溯、可复核的来源闭环。

## Solution

V1 建设一条 SRM 食品类证照来源接入能力：

- 支持从 SRM 拉取 `食品经营许可证` 来源记录，并转为 `food_license` 审核输入；
- 支持从 SRM 拉取 `食品生产许可证` 来源记录，并转为独立的 `food_production_license` 审核输入；
- 保留营业执照现有入口和行为不变；
- 将 SRM `typeName` 到平台 `declared_document_type` 的映射显式化；
- 复用现有 `ReviewService`、UseCase Thin Entry、Workflow Registry、LangGraph workflow、文件识别 Adapter 和 `ReviewResult` 契约；
- 为后续 QC 证照统一来源接入沉淀可复用 SRM 证照任务查询边界。

食品经营许可证和食品生产许可证都属于 QC 供应商证照审核范围，但二者不能混成同一个证照类型。食品生产许可证应使用独立文档类型、字段抽取 schema、规则口径和人工复核边界。

## User Stories

1. As a QC 审核员, I want 系统从 SRM 自动拉取食品经营许可证记录, so that 我不需要手工复制文件 URL 和供应商信息。
2. As a QC 审核员, I want 系统从 SRM 自动拉取食品生产许可证记录, so that 食品生产资质也能进入自动审核闭环。
3. As a QC 审核员, I want 食品经营许可证和食品生产许可证被识别为不同证照类型, so that 审核规则不会混用。
4. As a QC 审核员, I want 来源记录中的供应商名称进入审核输入, so that 证照主体名称可以和主数据比对。
5. As a QC 审核员, I want 来源记录中的统一社会信用代码进入审核输入, so that 证照信用代码可以和主数据比对。
6. As a QC 审核员, I want 来源记录中的附件 URL 进入文件识别链路, so that 系统可以直接读取 PDF/JPG/PNG 材料。
7. As a QC 审核员, I want 缺少 URL 的来源记录返回稳定错误, so that 我能定位 SRM 数据问题。
8. As a QC 审核员, I want 重复附件记录被去重, so that 同一证照不会重复创建审核任务。
9. As a QC 审核员, I want 未找到 SRM 来源记录时得到明确提示, so that 我能区分没有数据和系统异常。
10. As a QC 审核员, I want 审核结果保留 SRM record id 和 attachment ref id, so that 后续可以追溯到原始来源。
11. As a QC 审核员, I want 审核结果保留 SRM 原始行快照, so that 异常复核时可以还原输入证据。
12. As a 业务系统调用方, I want 一个食品经营许可证 SRM 快捷入口, so that 可以触发单条来源记录审核。
13. As a 业务系统调用方, I want 一个食品生产许可证 SRM 快捷入口, so that 可以触发单条来源记录审核。
14. As a 业务系统调用方, I want 食品类证照入口复用 `ReviewService`, so that 平台审核行为和其他证照一致。
15. As a 开发人员, I want SRM 证照类型映射集中维护, so that 新增证照类型时不需要复制大量代码。
16. As a 开发人员, I want 营业执照 SRM 入口继续通过现有测试, so that 食品类接入不会回归已验收能力。
17. As a 开发人员, I want 食品生产许可证先有清晰边界, so that 后续实现字段抽取和规则时不误用食品经营许可证能力。
18. As a 复核管理人员, I want 食品类证照审核输出统一 `ReviewResult`, so that 查询、人工复核和审计留痕可以复用平台能力。
19. As a 运维人员, I want SRM SQL 条件清晰固定, so that 生产排查时可以直接复现取数范围。
20. As a 测试人员, I want 使用 Stub SQL client 验证 SRM 映射和错误语义, so that 测试不依赖真实 SRM 数据库。

## Implementation Decisions

- SRM 来源接入继续以 `srm.certification` 左连接 `srm.attachment` 为基础，过滤 `category = 'vendor'`、`tenant = '8560'`、`refType = 'certification'`、URL 非空和目标 `typeName`。
- 食品经营许可证默认 SRM 条件使用 `t1.typeName = '食品经营许可证'`，平台文档类型映射为 `food_license`。
- 食品生产许可证默认 SRM 条件使用 `t1.typeName = '食品生产许可证'`，平台文档类型映射为 `food_production_license`。
- SRM 行标准化模块负责把 `typeName` 映射为 `declared_document_type`，未知 `typeName` 必须显式拒绝，不能静默映射。
- 食品经营许可证可以复用现有 `food_license` UseCase Thin Entry 和 workflow。
- 食品生产许可证不应复用 `food_license` 规则结论。若运行时能力尚未实现，应先接入来源映射和稳定错误/占位 use_case，再单独补字段抽取、规则审核和 Skill。
- 来源任务对象需要包含标准化 `DocumentRecord` 和平台 `ReviewInput`，`ReviewInput` 至少包含供应商名称、统一社会信用代码、声明文档类型、文件 URI、文件名和来源证据。
- 来源证据应保留 source system、tenant、record id、attachment ref id、document category、document type code、file store key 和原始 source payload。
- URL 缺失应返回证照类型专属稳定错误码，避免不同证照错误混淆。
- `POST /api/v1/food-license/reviews/from-srm` 作为食品经营许可证 SRM 快捷入口，调用 `ReviewService.review(..., use_case_name="food_license")`。
- 食品生产许可证入口应独立命名，避免放入食品经营许可证路径造成 API 语义混乱。
- 长期方向可以抽象通用 SRM certification source task builder，但 V1 可以先通过薄封装保持最小变更；抽象必须以测试覆盖营业执照、食品经营许可证和食品生产许可证后再收口。

## Testing Decisions

- 测试应验证外部行为，而不是内部实现细节：给定 SRM 行，输出正确 `ReviewInput`；给定缺 URL 行，输出稳定错误；给定重复行，只生成一个任务。
- SRM 行标准化测试应覆盖 `营业执照`、`食品经营许可证`、`食品生产许可证`、`产品报告` 和未知 `typeName`。
- 食品经营许可证来源任务测试应覆盖默认 SQL 包含 `t1.typeName = '食品经营许可证'`、URL 非空条件、limit、字段映射、去重和空结果。
- 食品生产许可证来源任务测试应覆盖默认 SQL 包含 `t1.typeName = '食品生产许可证'`、字段映射、URL 缺失错误、去重和空结果。
- API 测试应覆盖 from-SRM 快捷入口调用 ReviewService 边界、未找到来源记录、来源 URL 缺失和审核执行错误映射。
- 回归测试必须继续覆盖营业执照来源任务，确保 `typeName = '营业执照'` 的既有链路不被破坏。
- 不在单元测试中连接真实 SRM MySQL；真实数据库只用于人工或集成验收。
- 使用项目约定的 Python 环境执行 pytest，并在验证说明中记录实际 Python 可执行文件。

## Out of Scope

- 不实现食品生产许可证完整字段抽取和规则审核，除非另开专门实现任务。
- 不实现批量拉取和批量审核调度。
- 不实现 SRM 回写、OA 回写、IM 通知或任务编排。
- 不实现前端食品类证照工作台。
- 不修改营业执照审核结果工作台。
- 不引入 Java / Spring Boot 服务。
- 不让 LLM 直接决定最终规则结论。
- 不把食品生产许可证伪装成 `food_license`。

## Further Notes

- 用户已通过真实 SQL 验证 `食品经营许可证` 可以在 SRM 中查询到记录。
- 食品生产许可证 SQL 形态与食品经营许可证一致，但仍建议在实现前用真实 SRM 数据确认字段完整性、附件 URL 可访问性和 `typeName` 是否稳定。
- 既有 `docs/prd-food-license-v1.md` 仍描述较早 OCR 文本优先阶段；当前代码主线已经切换为文件输入优先，后续文档应逐步修正这一差异。
- 该 PRD 的核心是 SRM 来源接入，不是食品类证照完整合规规则建设。规则建设应分别由食品经营许可证和食品生产许可证各自的 Skill / workflow / Domain Rules 承担。
