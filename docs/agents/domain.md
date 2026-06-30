# Domain Docs

This is a single-context repo.

## Read First

- `README.md` for the project overview and current boundaries.
- `docs/PRD.md` for product requirements.
- `docs/SPEC.md` for architecture, data model, workflow, repository, and API design constraints.
- `docs/API.md` for HTTP contract details.
- `.agents/skills/*/SKILL.md` for business rule vocabulary and rule output shape.
- `AGENTS.md` for Codex operating constraints.

## Vocabulary

Use the project's existing domain terms:

- `ReviewService`
- `ReviewInput`
- `ReviewInputContext`
- `ReviewResult`
- `RuleResult`
- `UseCase Thin Entry`
- `Workflow`
- `LangChain Tool / capability`
- `Domain Rules`
- `Agent Skill`
- `qc_document_review`
- `product_report`
- `product_report_reviews`
- `product_report_inspection_items`
- `manual_review`

## Current Product Report Scope

Product report work belongs to `qc_document_review`. The source data is current SRM MySQL SKU material where `category='sku'`, `typeName='产品报告'`, `deleted=0`, and attachment `removed=0`.

The first product report vertical slice should keep final compliance decisions in deterministic rules and use LLM/OCR only for extraction and structure.
