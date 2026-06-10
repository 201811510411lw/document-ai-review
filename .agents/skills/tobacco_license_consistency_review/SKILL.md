---
name: tobacco_license_consistency_review
description: 营业执照与烟草证一致性校验的 Agent Skill 描述层。
---

# tobacco_license_consistency_review

## 能力边界

用于描述营业执照与烟草专卖零售许可证之间的一致性校验能力。重点关注企业名称、经营场所、负责人和有效期字段比对，并为 OA 回写和 IM 告警提供结构化结果摘要。

本 Skill 描述层不执行字段比对规则。确定性一致性校验由 Python Runtime 的 rules 目录执行。

## 支持的输入

- 营业执照 OCR 文本或文件引用。
- 烟草专卖零售许可证 OCR 文本或文件引用。
- 企业名称、经营场所、负责人、有效期等业务字段。
- OA 流程单号或外部业务引用。

## 输出结构摘要

- 营业执照字段抽取摘要。
- 烟草证字段抽取摘要。
- 企业名称、经营场所、负责人、有效期比对结果摘要。
- 风险等级。
- 是否需要人工复核。
- OA 回写 payload 摘要。
- IM 告警摘要。

## 规则摘要

- 双证主体名称是否一致或可解释近似一致。
- 经营场所是否一致或存在可接受差异。
- 负责人是否一致。
- 烟草证是否在有效期内。
- 营业执照状态和有效期是否满足审核要求。
- 不一致项是否需要阻断流程或进入人工复核。

## 人工复核边界

当任一证照无法识别、关键字段缺失、字段比对不一致、有效期异常或业务流程需要人工确认时，应进入人工复核。

## 禁止事项

- 不在 `SKILL.md` 中编写字段比对执行逻辑。
- 不直接调用真实 OA、飞书或企微。
- 不声明公有云 OCR 或 LLM 为必需依赖。
- 不绕过 ReviewService 和 use case registry。
- 不直接调用 workflow 内部节点。

## 与 Python Runtime 的关系

Python Runtime facade 对应 `ai-service/app/use_cases/tobacco_license_consistency_review/skill.py`。平台通过 use case 入口调用 Runtime。后续 workflow 位于 `ai-service/app/workflows/tobacco_license/`；如需要可执行能力拆分，应落在 `ai-service/app/capabilities/`。
