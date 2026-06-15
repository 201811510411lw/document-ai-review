# MySQL 审核结果持久化 V1 PRD

本文档定义 `document-ai-review` 使用独立 MySQL 审核库保存审核结果的 V1 产品范围、实现边界和测试决策。

`README.md` 仍然是项目唯一主上下文。本文档只补充审核结果持久化从 SQLite 测试实现迁移到 MySQL 生产实现的 PRD，不替代既有营业执照、食品许可证或多模态审核 PRD。

---

## Problem Statement

当前 `ai-service` 已经具备统一 `ReviewResult` 契约，并且营业执照链路已经可以从 SRM MySQL 来源记录获取文件、抽取字段、执行 Skill 规则审核并输出结构化结果。但审核结果持久化仍主要依赖 SQLite 仓库样式，脚本和 FastAPI 默认服务也没有把生产审核结果稳定写入独立审核库。

从用户视角看，这会造成几个问题：

- 营业执照脚本执行后只能看到控制台输出，缺少可追溯的生产结果存储；
- FastAPI 审核接口返回结果后，如果调用方没有另行保存，系统侧无法查询历史审核记录；
- 后续食品许可证、烟草证和双证一致性比对复用统一审核链路时，缺少一套生产级结果仓库；
- SQLite 不再作为审核结果存储目标，避免本地和生产两套持久化行为长期分叉；
- 审核人员后续要做查询、复核、导出和审计留痕时，需要稳定的 MySQL 表结构承接完整结果快照和单证投影。

## Solution

V1 使用独立 MySQL 审核库保存 `ReviewResult`。系统移除 SQLite 审核结果仓库实现，脚本入口和 FastAPI 默认服务统一通过 MySQL repository 持久化审核结果，并在审核完成后自动保存结果。

生产 MySQL 审核库采用“两层存储”：

- 完整结果快照表：保存完整 `ReviewResult` JSON，用于审计、回放和兼容未来字段扩展；
- 单证投影表：保存营业执照等常用查询字段，以及抽取字段、规则结果、来源证据等 JSON 快照，用于列表查询、人工复核和报表导出。

V1 首先确保营业执照链路通过脚本和 API 都能保存到 MySQL。食品许可证和商品报告可以复用同一个 repository 接口逐步接入，不要求一次完成所有生产查询接口。

## User Stories

1. As a QC reviewer, I want business license review results to be saved after a script run, so that I can audit what was reviewed later.
2. As a QC reviewer, I want API-created review results to be persisted automatically, so that successful API calls do not disappear after the response is returned.
3. As a compliance reviewer, I want each saved review result to keep the full `ReviewResult` payload, so that I can inspect the original rule outcome and evidence.
4. As a compliance reviewer, I want business license fields to be saved in queryable columns, so that I can search by supplier name, credit code, status, risk level and review time.
5. As a system integrator, I want the audit database to be separate from the source business database, so that review writes do not affect SRM or ERP source systems.
6. As a system integrator, I want source record identifiers and file URLs to be preserved, so that each review can be traced back to the upstream attachment.
7. As a platform maintainer, I want tests to mock the MySQL repository boundary, so that local development does not require a real cloud database.
8. As a platform maintainer, I want a MySQL repository behind the existing repository protocol, so that use cases do not know the SQL details.
9. As a platform maintainer, I want MySQL configuration to be explicit, so that deployments fail clearly when audit database credentials are missing.
10. As a platform maintainer, I want the script entrypoint to use the configured repository, so that manual smoke tests and scheduled jobs behave like production.
11. As a platform maintainer, I want FastAPI's default `ReviewService` to use the configured repository, so that HTTP requests are persisted without custom dependency wiring.
12. As a developer, I want the MySQL schema to mirror the existing SQLite projection shape where reasonable, so that implementation risk is low.
13. As a developer, I want JSON snapshots to be stored in JSON-capable columns, so that future extracted fields and rule details do not require immediate schema changes.
14. As a developer, I want idempotent upsert by `task_id`, so that retries do not duplicate review results.
15. As a developer, I want `get_by_task_id` behavior to match the SQLite repository, so that callers can retrieve a saved result consistently.
16. As a developer, I want MySQL save tests to run with a fake connection, so that CI does not depend on cloud database credentials.
17. As an operations owner, I want database connection settings to use a separate environment prefix from SRM source MySQL, so that read-only source credentials and read-write audit credentials are not mixed.
18. As an operations owner, I want missing MySQL configuration to fail clearly when MySQL persistence is selected, so that deployment mistakes are obvious.
19. As an operations owner, I want the service to keep no-persistence behavior available for isolated tests, so that old tests can remain focused on review logic.
20. As a future tobacco-license implementer, I want persistence to remain document-type extensible, so that tobacco license projections can be added without rewriting the repository interface.

## Implementation Decisions

- V1 chooses MySQL, not PostgreSQL, for production persistence because the current source integration already uses MySQL and the immediate workload is business-query-oriented review result storage.
- The production database is an independent MySQL audit database, not the SRM or ERP source business database.
- The existing repository protocol remains the use-case boundary. `ReviewService` continues to depend on a repository interface, not a concrete database implementation.
- SQLite review result persistence is removed from the runtime code path.
- A MySQL review result repository will implement at least `save` and `get_by_task_id` with behavior equivalent to the SQLite repository for full `ReviewResult` payloads.
- The repository will create required tables if they do not exist, matching the current SQLite repository ergonomics for V1.
- The repository will save a full payload table and business-license projection table in V1. Product report and future document projections can be added incrementally.
- The business-license projection will preserve source record identifiers, source attachment identifiers, source URL, document type, extracted business name, credit code, address, legal person, validity fields, status, risk level, manual-review flag, summary, rule results JSON, extracted fields JSON, normalized fields JSON, extraction metadata JSON and source evidence JSON.
- JSON snapshots should be serialized with UTF-8 Chinese content preserved.
- `task_id` is the idempotency and lookup key. Saving the same task again updates the existing row.
- Environment variables use a distinct audit prefix, `REVIEW_RESULT_MYSQL_*`, so they cannot be confused with `SRM_MYSQL_*`.
- A repository factory will centralize MySQL repository construction. This keeps scripts, API setup and future workers from each hand-rolling persistence configuration.
- Script summary output remains human-friendly and does not need to expose full persistence details unless debug mode is enabled.
- API response shape remains the existing `ReviewResult` JSON shape. Persistence is a side effect of `ReviewService`, not a new response contract.
- Missing or invalid MySQL configuration should fail during repository construction.
- V1 does not introduce database migration tooling. Schema creation can be embedded in the repository for the current lightweight deployment stage.

## Testing Decisions

- Good tests should verify external behavior: saving, retrieving, upserting, projection contents and service wiring. They should not assert private SQL formatting beyond essential schema and parameter behavior.
- MySQL repository tests should use a fake or monkeypatched PyMySQL connection so CI does not need real cloud credentials.
- Repository construction tests should verify that MySQL configuration is read from the `REVIEW_RESULT_MYSQL_*` prefix.
- Script tests should verify that the script constructs a review service with the configured repository without requiring a real database.
- FastAPI tests should verify that the default service can persist through the selected repository and that API response contracts are unchanged.
- Existing SQLite repository tests should be replaced by MySQL repository tests for `save`, `get_by_task_id`, projection snapshot behavior and injected repository service behavior.
- Existing business-license persistence tests remain prior art for projection field expectations.
- Existing MySQL fetch client tests remain prior art for monkeypatching PyMySQL connection behavior.
- Real MySQL smoke tests are optional and must be gated by explicit environment variables. They should not run by default.

## Out of Scope

- PostgreSQL implementation.
- Production database migration framework.
- Historical data migration from existing SQLite files.
- Admin UI, query page, export page or manual-review page.
- Multi-tenant row-level permission model.
- Full production reporting or BI schema.
- Implementing every future document-type projection in the same PRD.
- Changing business-license extraction or Skill rule semantics.
- Writing review results back into SRM, OA or ERP source systems.

## Further Notes

- The immediate implementation target is: business license script and FastAPI API both persist to MySQL when MySQL persistence is selected.
- Tests should mock MySQL connections rather than depend on SQLite.
- Future tobacco license and food license work should reuse the repository interface and add document-specific projection tables only when their query requirements are clear.
- If the team later adopts a formal migration tool, the repository's embedded schema creation can be replaced by managed migrations without changing the `ReviewService` boundary.
