# PRD: 营业执照工作台人工复核与验收闭环 V1

## Problem Statement

营业执照审核工作台已经具备审核结果查询、详情展示、人工复核后端写回和企微通知基础能力，但前端人工复核仍停留在禁用占位状态，详情页对验收所需字段、空状态、审计事件和通知跳转链路的表达还不完整。

这导致 QC 审核员无法在工作台内完成“查看审核结果 -> 判断风险 -> 人工复核 -> 追溯审计”的闭环，也不利于把 `business_license` 当前主线作为可演示、可验收的端到端样板。

## Solution

围绕 GitHub issue #79 和 #80，完成营业执照工作台的最小验收闭环：

- 人工复核页从占位页升级为真实可提交表单。
- 营业执照详情页展示原始文件、抽取字段、标准化字段、规则结果、待复核原因、复核结果和审计事件。
- 列表页继续通过现有筛选条件查询历史审核记录，并保持与后端 API 参数一致。
- 企微通知和登录跳转继续复用工作台路由，未登录用户登录后回到目标详情页。

## User Stories

1. As a QC 审核员, I want to open a pending manual review record, so that I can inspect the evidence before making a final decision.
2. As a QC 审核员, I want to choose approved or rejected, so that my manual decision is explicit and auditable.
3. As a QC 审核员, I want to enter a manual review comment, so that later reviewers understand my basis.
4. As a QC 审核员, I want to see validation errors before submission, so that incomplete review decisions are not written back.
5. As a QC 审核员, I want the page to show a submitting state, so that I know the write-back is in progress.
6. As a QC 审核员, I want failed submissions to show an actionable error, so that I can retry or report the issue.
7. As a QC 审核员, I want successful submission to refresh the page with the latest review status, so that I know the write-back succeeded.
8. As a QC 审核员, I want completed manual review records to be read-only, so that duplicate decisions are avoided.
9. As a QC 审核员, I want audit events to show after manual review, so that the action is traceable.
10. As a QC 审核员, I want to open the original source file from the detail page, so that I can compare AI results against the source material.
11. As a QC 审核员, I want to see extracted fields and normalized fields side by side, so that I can understand what OCR/vision recognized and what rules used.
12. As a QC 审核员, I want to see each rule result with state, message, and evidence, so that I can understand why the record passed, failed, or needs review.
13. As a QC 审核员, I want clear empty states when source file, fields, rules, or audit events are missing, so that the page remains stable for incomplete records.
14. As a QC 审核员, I want to filter the list by business name, credit code, risk level, review status, date range, and pagination, so that I can find historical records quickly.
15. As a QC 审核员, I want notification links to land on the correct review detail page, so that I can move from企微通知 to review action directly.
16. As an unauthenticated reviewer, I want login to preserve my intended destination, so that after login I return to the detail page I opened.
17. As a developer, I want the business-license detail and QC detail flows to use the correct manual review API, so that the same UI works in both workbench contexts.
18. As a developer, I want behavior tests around manual review and detail rendering, so that future UI refactors do not break the acceptance flow.

## Implementation Decisions

- The primary public UI surfaces are the review list, business license detail page, QC detail page, and manual review page.
- The manual review submission contract remains the existing client shape: decision, comment, and reviewer ID.
- Business license detail context writes to the business-license manual review endpoint.
- QC detail context writes to the QC manual review endpoint.
- Manual review pages must derive completed/read-only state from the mapped manual review status, not from local-only flags.
- Detail pages should render available data defensively. Missing source URL, fields, rules, reasons, audit events, or payload must not throw runtime errors.
- The work remains scoped to `business_license` and the existing QC unified workbench surface. It does not add new document types.
- No database schema change is planned for this PRD; existing persistence and repository contracts are reused.
- README/workbench documentation should describe the updated验收 path once implementation is complete.

## Testing Decisions

- Tests should verify behavior through public user-facing interfaces: routes, rendered text, form controls, fetch calls, and updated UI state.
- Frontend tests should cover manual review success, validation/failed submission, completed read-only state, and endpoint selection between business-license and QC contexts.
- Frontend tests should cover detail rendering for original file link, normalized fields, empty rule/audit states, and existing list filters.
- API client tests should cover the QC manual review endpoint if the client interface gains a QC-specific submission method.
- Existing tests in `web-console/src/App.test.tsx` and `web-console/src/api/httpClient.test.ts` are the closest prior art.
- Backend tests are not expected unless implementation reveals a server contract mismatch; existing API endpoints already have coverage.

## Out of Scope

- Contract review implementation.
- Tobacco license consistency workflow completion.
- New QC document types beyond the existing unified workbench surface.
- Batch download, PDF report generation, Excel export, and OA/ERP write-back.
- New authentication provider behavior beyond preserving existing login return routes.
- Database schema migrations.

## Further Notes

- Related implementation issues:
  - #79 `fix: 接通人工复核前端提交闭环`
  - #80 `feat: 完成营业执照工作台验收闭环`
- This PRD intentionally treats `business_license` as the current delivery trunk. Other registered use cases remain compatible but are not expanded here.
