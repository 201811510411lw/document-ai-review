# 文档导航

本文档集描述仓库当前已经实现的行为。代码和测试是运行时事实源；Agent Skill 是业务规则口径；`PRD.md` 保留原始需求，不代表所有需求均已实现。

## 开发与架构

- [能力矩阵](CAPABILITIES.md)：各 Review Use Case 的实现状态、入口、输出和边界。
- [技术规范](SPEC.md)：架构、领域模型、数据模型、目录和技术约束。
- [原始需求](PRD.md)：产品需求基线；阅读时应与能力矩阵核对。
- [项目领域语言](../CONTEXT.md)：Review Use Case、Workflow、Capability、Domain Rule 等统一术语。

## 接口对接

- [API 契约](API.md)：认证方式、业务接口、响应语义和当前限制。
- [OpenAPI operation 清单](api/openapi-operations.md)：从 FastAPI 应用生成的 HTTP operation 索引。
- [OA 烟草证一致性审核](api/oa-tobacco-consistency-auto-review.md)：OA/StarRocks 来源审核与影刀验真的现行接口。
- [外部集成](INTEGRATIONS.md)：SRM、StarRocks、OA、企业微信、OCR/LLM、远程文件和影刀 RPA 的职责边界。

## 业务规则

- [营业执照规则](../.agents/skills/business-license-review/SKILL.md)
- [食品经营许可证规则](../.agents/skills/food-license-review/SKILL.md)
- [食品生产许可证规则](../.agents/skills/food-production-license-review/SKILL.md)
- [烟草专卖零售许可证规则](../.agents/skills/tobacco-license-review/SKILL.md)
- [QC 文档规则](../.agents/skills/qc-document-review/SKILL.md)

## 数据与运维

- [运维手册](OPERATIONS.md)：配置优先级、数据库准备、调度、通知、部署验证和故障排查。
- [StarRocks 来源表](sql/README.md)：SRM、批次报告和 OA 同步表 DDL 及准备顺序。
