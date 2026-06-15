# 营业执照审核结果工作台 V1 PRD

本文档定义 `document-ai-review` 营业执照审核结果查询 API 与前端工作台 MVP 的产品范围、实现边界和测试决策。

`README.md` 仍然是项目唯一主上下文。本文档只补充审核人员查看、筛选、复核营业执照审核结果的工作台能力，不替代营业执照单证审核 PRD，也不替代 MySQL 审核结果持久化 PRD。

---

## Problem Statement

当前营业执照审核链路已经完成单条 SRM 来源记录审核，并且审核结果已经写入独立 MySQL 审核结果库。系统可以输出结构化 `ReviewResult`，也可以在 `business_license_reviews` 投影表中保存主体名称、统一社会信用代码、风险等级、审核状态、来源文件 URL、规则结果 JSON、抽取字段 JSON 和来源证据 JSON。

但从审核人员视角看，目前仍然缺少可用的审核工作台：

- 审核人员无法在浏览器中查看历史营业执照审核结果；
- 审核人员无法按主体名称、统一社会信用代码、风险等级、审核状态和审核时间筛选记录；
- 审核人员无法快速打开某条审核结果，查看字段抽取、规则校验、人工复核原因和原文件链接；
- 审核人员无法在一个统一界面中判断哪些记录需要人工处理；
- 后续企业微信应用缺少可承载的 Web 页面，只能依赖脚本和数据库查询，不适合交给业务审核人员使用。

因此，下一阶段需要建设一个面向审核人员的营业执照审核结果工作台 MVP，让当前已经落库的审核结果可以被查看、筛选和复核，并为后续企业微信应用集成预留边界。

## Solution

V1 建设“营业执照审核结果查询 API + 前端工作台 MVP”。

后端继续由 `ai-service` 承担 API 边界，新增营业执照审核结果查询接口，从 MySQL 审核结果库读取 `review_results` 和 `business_license_reviews`。接口应返回适合前端列表和详情展示的结构化 JSON，不要求前端直接解析数据库结构。

前端作为独立 Web 应用放在仓库根目录下，与 `ai-service` 同级。推荐目录名为 `web-console/`。这样它和 Python 后端服务边界清晰，后续可以独立构建、部署，也更容易作为企业微信应用入口页面接入。

V1 前端先做普通浏览器工作台，不直接深度绑定企业微信。企业微信应用在 V1 只作为后续部署形态预留：页面布局、路由和 API 调用方式应适配企业微信内置浏览器，但不实现企业微信 OAuth、通讯录权限、消息卡片和应用菜单配置。

V1 页面范围：

- 审核结果列表页；
- 审核结果详情页；
- 基础人工复核动作入口的 UI 和 API 契约预留。

V1 API 范围：

- 查询营业执照审核结果列表；
- 查询单条营业执照审核详情；
- 可选预留人工复核提交接口契约，但不要求完成完整权限和审批流。

## User Stories

1. As a QC reviewer, I want to open a web workbench, so that I can view business license review results without running scripts or SQL.
2. As a QC reviewer, I want to see recent business license reviews in a list, so that I can quickly understand today's review status.
3. As a QC reviewer, I want to see supplier or business name in the list, so that I can identify which company each result belongs to.
4. As a QC reviewer, I want to see unified social credit code in the list, so that I can distinguish companies with similar names.
5. As a QC reviewer, I want to see review status in the list, so that I can separate reviewed records from pending manual review records.
6. As a QC reviewer, I want to see risk level in the list, so that I can prioritize high-risk and medium-risk records.
7. As a QC reviewer, I want to see whether manual review is required, so that I can focus on records requiring human action.
8. As a QC reviewer, I want to see review time in the list, so that I can understand when the record was processed.
9. As a QC reviewer, I want to filter by business name, so that I can find all review results for a specific supplier.
10. As a QC reviewer, I want to filter by credit code, so that I can locate a company precisely.
11. As a QC reviewer, I want to filter by risk level, so that I can review risky results first.
12. As a QC reviewer, I want to filter by review status, so that I can focus on pending manual review records.
13. As a QC reviewer, I want to filter by review time range, so that I can check today's, this week's or a custom range of reviews.
14. As a QC reviewer, I want pagination, so that large result sets do not make the page slow or hard to use.
15. As a QC reviewer, I want to open a review detail page, so that I can inspect the complete audit context.
16. As a QC reviewer, I want to see extracted business license fields, so that I can verify whether the model read the document correctly.
17. As a QC reviewer, I want to see normalized fields, so that I can understand what values were used by rules.
18. As a QC reviewer, I want to see each rule result, so that I can understand why the review passed or needs manual review.
19. As a QC reviewer, I want failed rules to be visually distinguishable, so that I can focus on the exact problems.
20. As a QC reviewer, I want to see manual review reasons, so that I can decide the next action quickly.
21. As a QC reviewer, I want to open the original file URL, so that I can compare the original certificate with extracted fields.
22. As a QC reviewer, I want to see source record ID and attachment ID, so that I can trace the result back to SRM.
23. As a QC reviewer, I want to inspect the full JSON snapshot when needed, so that I can troubleshoot edge cases without database access.
24. As a QC reviewer, I want a basic manual review action area, so that I know where final human decisions will be recorded later.
25. As a compliance manager, I want list metrics such as total count, reviewed count, pending manual review count and risk distribution, so that I can assess workload.
26. As a compliance manager, I want the interface to be work-focused and compact, so that reviewers can scan many records efficiently.
27. As a business stakeholder, I want the workbench to be accessible from a browser first, so that it can be validated before enterprise WeChat integration.
28. As an enterprise WeChat user, I want the future enterprise WeChat app to open the same workbench page, so that the web implementation can be reused.
29. As a platform maintainer, I want frontend code to live beside `ai-service`, so that the Python service and web workbench are independent deployable modules.
30. As a platform maintainer, I want backend APIs to shield frontend from database tables, so that future schema changes do not require broad UI rewrites.
31. As a platform maintainer, I want query parameters to be explicit and stable, so that frontend state can be represented in URLs.
32. As a platform maintainer, I want API response schemas to include runtime codes and Chinese labels, so that frontend can display Chinese values while preserving machine-readable values.
33. As a developer, I want repository query methods to be tested independently, so that SQL filtering and pagination can be validated without a real cloud database.
34. As a developer, I want API tests for list and detail endpoints, so that frontend integration has stable contracts.
35. As a developer, I want frontend tests or component-level checks for list/detail rendering, so that future UI changes do not break core reviewer workflows.
36. As a future tobacco-license developer, I want the workbench layout to allow more document types later, so that tobacco license and food license results can reuse the same navigation pattern.
37. As a future batch-review developer, I want list pages to support many records and batch status fields, so that batch SRM review can plug into the same workbench later.
38. As an operations owner, I want the frontend to call configurable API base URLs, so that local, test and production deployments can point to different `ai-service` instances.
39. As an operations owner, I want enterprise WeChat integration to remain out of the first MVP, so that the team can validate data and UI before adding identity and permission complexity.
40. As an auditor, I want saved review evidence to remain traceable from the UI, so that audit trails do not depend on developer-only tooling.

## Implementation Decisions

- V1 builds a browser-based审核结果工作台 MVP before enterprise WeChat application integration.
- The frontend should be placed at repository root level beside `ai-service`, not inside `ai-service`.
- Recommended frontend directory name is `web-console/`.
- `ai-service` remains the backend API boundary. The frontend should not connect directly to MySQL.
- Backend query APIs should be added under the existing business-license API namespace.
- The list API should support filters for business name, credit code, review status, risk level, manual-review flag and created-at time range.
- The list API should support pagination with stable `page`/`page_size` or `limit`/`offset` semantics. V1 should choose one convention and document it.
- The list API should return a compact row shape for table rendering, not the entire full `ReviewResult` JSON.
- The detail API should return projection fields plus parsed JSON snapshots for rule results, extracted fields, normalized fields, extraction metadata, source evidence and full payload JSON.
- The backend repository should gain read-side methods for listing business license reviews and retrieving business license review detail by task ID.
- Repository read methods should remain deep modules: API handlers pass query parameters, repository returns stable dictionaries or Pydantic response models.
- Existing MySQL audit tables remain the source of truth for V1.
- V1 should not introduce a separate backend service for frontend. FastAPI continues to serve the API.
- Frontend should use a modern SPA setup. A conservative default is React + TypeScript + Vite.
- Frontend should use a quiet operational layout: table-first, compact filters, status/risk badges, detail panels, no marketing landing page.
- Frontend first screen should be the review result list, not a hero page.
- UI should be designed for enterprise reviewer workflow: dense but readable table, clear filters, predictable detail navigation and stable loading/error states.
- Risk level display should use restrained color semantics: high risk, medium risk, low risk and none should be distinguishable without dominating the whole page.
- Manual review status should be visible in both list and detail views.
- Original file link should open in a new browser tab.
- Full JSON payload should be hidden behind an expandable section in detail view.
- Artificial intelligence explanations should not be treated as final legal or compliance truth; the UI should present rule results and evidence as review support.
- Enterprise WeChat V1 integration is deferred, but frontend routing and responsive layout should work in enterprise WeChat's embedded browser.
- Authentication and authorization are not part of this PRD unless already available in deployment. The MVP may run behind internal network controls.
- API responses should keep runtime fields such as `review_status` and `risk_level`, and optionally provide Chinese labels for display.
- Manual review writeback can be represented as a reserved UI/API boundary, but full workflow state transition may be deferred to a later PRD if needed.
- Documentation should state that future enterprise WeChat work will add identity, permission, menu entry and notification card integration.

## Testing Decisions

- Good backend tests should verify API behavior and repository query results, not internal SQL formatting unless the SQL affects externally visible filtering or pagination.
- MySQL read-side repository tests should use the existing mock PyMySQL pattern instead of a real cloud database.
- API tests should cover list success, empty list, filtering by business name, filtering by credit code, filtering by risk level, filtering by status, pagination and detail not found.
- API tests should cover parsed JSON fields in detail responses, especially rule results and extracted fields.
- Frontend tests should focus on reviewer workflows: rendering rows, applying filters, opening details, showing failed rules and handling empty/error states.
- Frontend should have a local API mock or fixture layer so UI development does not require production MySQL data.
- Existing prior art includes business-license API tests, MySQL repository tests, MySQL repository stub tests and persistence contract tests.
- Visual verification should include desktop and narrow embedded-browser widths because future enterprise WeChat use is expected.
- Tests should not call real OCR, real LLM or real enterprise WeChat APIs.
- Real browser smoke tests are useful once frontend exists, but the PRD does not require them before API contracts are stable.

## UI Acceptance Criteria

V1 前端工作台必须先提供可预览的静态 UI，不依赖真实后端查询接口。实现应使用 mock 数据展示完整审核人员工作流，并保留后续替换真实 API 的客户端边界。

列表页验收标准：

- 默认路由 `/reviews` 展示营业执照审核结果列表。
- 桌面端采用企业后台风格，包含左侧导航、顶部栏、统计卡片、筛选区和审核结果表格。
- 统计卡片至少展示今日审核、需人工复核、高风险和通过率。
- 筛选区至少包含主体名称、统一社会信用代码、风险等级、审核状态和时间范围。
- 表格列至少包含主体名称、统一社会信用代码、审核状态、风险等级、人工复核、审核时间和操作。
- 审核状态和风险等级必须使用克制 badge 展示，避免大面积警示色。
- 操作列可以进入 `/reviews/{task_id}` 详情页。
- 页面必须提供基础 loading、empty 和 error 状态。

详情页验收标准：

- 路由 `/reviews/{task_id}` 展示单条营业执照审核详情。
- 顶部必须展示企业名称、任务 ID、SRM 记录 ID、附件 ID、审核时间和打开原文件按钮。
- 中间必须展示字段抽取结果和规则校验结果。
- 字段抽取结果至少包含主体名称、统一社会信用代码、法定代表人、成立日期、营业期限、住所和置信度。
- 规则结果必须能区分通过、失败和需复核三类状态。
- 底部必须展示人工复核原因和完整 JSON 快照折叠区。
- 人工复核动作 V1 只做 UI 占位，按钮必须禁用，不提交真实请求。

企业微信内嵌窄屏验收标准：

- 390px 和 430px 宽度下页面必须可用。
- 列表页在窄屏下切换为卡片列表，不能依赖横向滚动才能识别核心信息。
- 详情页在窄屏下切换为纵向分区卡片。
- V1 不接入企业微信 SDK、OAuth、菜单配置、消息通知或通讯录权限。

## Out of Scope

- Enterprise WeChat OAuth, SSO or user identity binding.
- Enterprise WeChat menu configuration.
- Enterprise WeChat message notifications or cards.
- Batch SRM business license review.
- Tobacco license review.
- Food license workbench pages.
- Contract review pages.
- Full role-based access control.
- Production BI dashboard.
- Export to Excel or PDF.
- Editing extracted fields.
- Re-running OCR or LLM from the UI.
- Full manual review state machine and approval workflow, unless handled by a later dedicated PRD.
- Replacing FastAPI or splitting a new backend service.
- Direct frontend access to MySQL.

## Further Notes

- This PRD follows the current repository architecture where `ai-service` is the Python backend. The frontend should be a sibling project at repo root, for example `web-console/`.
- The first implementation should start with backend query API contracts, then build the frontend against those contracts.
- The workbench should remain document-type extensible, but V1 should focus only on营业执照审核结果.
- The current MySQL audit tables already contain enough data for the first list and detail pages.
- A future PRD should cover enterprise WeChat application integration after the browser MVP is accepted by reviewers.

## Implemented Query API Contract

本 PRD 的后续实现已新增营业执照审核结果查询接口，并将 `web-console` 默认切换到真实 API client。

列表接口：

```text
GET /api/v1/business-license/reviews
```

支持查询参数：

- `business_name`
- `credit_code`
- `risk_level`
- `review_status`
- `needs_manual_review`
- `created_from`
- `created_to`
- `page`
- `page_size`

列表响应返回：

- `items`：适合前端列表渲染的营业执照审核结果行；
- `metrics`：`today_reviewed`、`pending_manual_review`、`high_risk`、`pass_rate`；
- `page`、`page_size`、`total`、`total_pages`。

详情接口：

```text
GET /api/v1/business-license/reviews/{task_id}
```

详情响应返回投影字段、解析后的 `rule_results`、`extracted_fields`、`normalized_fields`、`extraction_metadata`、`source_evidence`、人工复核原因和完整 `ReviewResult` payload。

前端配置：

- 默认同源调用 `/api/v1/business-license/reviews`；
- 可通过 `VITE_API_BASE_URL` 指向独立部署的 `ai-service`；
- 可通过 `VITE_USE_MOCK_API=true` 回退到本地 mock 数据预览。
