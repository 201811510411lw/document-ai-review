---
name: contract_review
description: 法务合同内容审核的 Agent Skill 描述层。
---

# contract_review

## 能力边界

用于描述法务合同内容审核能力。覆盖通用合同、房屋租赁合同、常温食品供货合同的风险条款识别、修改建议生成和 OA 合同流程回写摘要。

本 Skill 描述层只定义审核能力和提示边界。合同风险规则、条款识别和复核策略由 Python Runtime、workflow 和 rules 层实现。

## 支持的输入

- 合同 OCR 文本。
- PDF、Word 转换文本或文件引用。
- 合同类型。
- 相对方、金额、期限、业务部门等上下文。
- OA 合同流程信息。

## 输出结构摘要

- 合同类型识别结果。
- 关键条款抽取摘要。
- 风险条款识别摘要。
- 修改建议摘要。
- 风险等级。
- 是否需要人工复核或法务复核。
- OA 合同流程回写 payload 摘要。

## 规则摘要

- 合同主体、金额、期限、签署方是否完整。
- 付款、违约、解除、保密、争议解决等关键条款是否缺失或异常。
- 房屋租赁合同是否包含租期、租金、押金、房屋用途、产权或授权证明等必要信息。
- 常温食品供货合同是否覆盖质量责任、资质要求、批次报告、召回责任和赔付边界。
- 高风险条款是否需要法务人工复核。

## 人工复核边界

当合同类型不明确、关键条款缺失、风险条款涉及重大责任、修改建议需要法务判断或 OA 流程要求人工确认时，应进入人工复核。

## 禁止事项

- 不在 `SKILL.md` 中编写合同规则执行逻辑。
- 不直接调用真实 LLM、OA 或外部合同系统。
- 不声明公有云大模型 API 为必需依赖。
- 不绕过 ReviewService 和 SkillRegistry。
- 不直接调用 workflow 内部节点。

## 与 Python Runtime 的关系

Python Runtime facade 对应 `ai-service/app/skills/contract_review/skill.py`。平台只通过 `Skill.review(input_context)` 调用该 Runtime。后续 workflow 应位于 `ai-service/app/workflows/contract/`，确定性规则应位于 `ai-service/app/skills/contract_review/rules/`。
