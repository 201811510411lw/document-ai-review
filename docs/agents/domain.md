# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Before exploring, read these

- `README.md` at the repo root. This is the primary project context for this repo.
- `docs/architecture.md` when the task touches service boundaries, architecture, or system flow.
- `docs/adr/` if it exists in the future. Read ADRs that touch the area you're about to work in.

This repo intentionally does not use `CONTEXT.md` or `CONTEXT-MAP.md` right now. Do not suggest creating them upfront; use `README.md` as the source of project terminology and domain context.

## Layout

Single-context repo:

```text
/
├── README.md
├── docs/
│   └── architecture.md
└── ai-service/
```

## Use the README vocabulary

When your output names a domain concept, issue title, refactor proposal, hypothesis, or test, use the terms from `README.md`.

Important current terms include:

- Document AI Review Agent / Skill 平台
- 食品安全证照检测
- backend-java
- ai-service
- 审核任务
- 字段抽取
- 规则校验
- 风险报告
- 人工复核
- 审计留痕

## Flag architecture conflicts

If your output contradicts `README.md`, `docs/architecture.md`, or a future ADR, surface it explicitly instead of silently overriding it.
