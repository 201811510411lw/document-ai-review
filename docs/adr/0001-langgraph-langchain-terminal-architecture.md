# ADR 0001: LangGraph + LangChain Terminal Architecture

Status: Accepted

## Context

The project started with a hand-written `UseCase + Workflow + Capability`
runtime shape. That shape helped the first business license tracer bullet move
quickly, but it is no longer the target architecture for a multi-document AI
review platform.

The next architecture must support multiple document workflows, including
business license, tobacco license, QC documents, contracts, and future
assistant-style capabilities. The runtime must also keep deterministic audit
and compliance behavior explicit: LLM calls can extract, classify, and explain,
but they must not own the final business decision.

## Decision

We will move the runtime to the following terminal architecture:

```text
API Layer
  -> UseCase = Thin Entry
  -> Workflow = LangGraph StateGraph
  -> Capability = LangChain Tools
  -> Skill = Prompt / Policy Layer
  -> Domain Rules = Final Compliance Decision
```

This is a breaking change. We do not preserve the old
capability-as-workflow-layer architecture as a compatibility target. In short:
do not preserve the old capability-as-workflow-layer architecture.

The long-term meaning of each layer is:

- UseCase = Thin Entry. It performs input assembly, authorization and parameter
  validation where needed, invokes the selected graph, and returns the review
  result. It does not orchestrate business review steps.
- Workflow = LangGraph StateGraph. Each business process is a graph with typed
  state, explicit nodes, explicit edges, conditional routing, and human-in-loop
  nodes where needed.
- Capability = LangChain Tools. Document loading, OCR or vision parsing, field
  extraction, normalization, risk scoring helpers, and classification are
  exposed as stateless tools with structured inputs and outputs.
- Skill = Prompt / Policy Layer. Agent Skill documents and prompt templates
  define language, guardrails, schema constraints, and policy context. They do
  not control workflow execution.
- Domain Rules = Final Compliance Decision. Deterministic domain rule modules
  evaluate structured facts and produce final compliance decisions, risk, manual
  review requirements, and audit-friendly rule results.

## Guardrails

- LLM must not make the final compliance decision.
- LangChain agent must not replace deterministic workflow control.
- Capability tools must not contain workflow orchestration.
- Do not mix multiple tool systems for the same runtime extension point.
- Prompt and Skill text must not become hidden control flow.
- Graph routing decisions must be testable from typed state and domain rule
  outputs.

## Consequences

Business license becomes the first migration target. It should be rewritten as
standard StateGraph code whose nodes call LangChain tools and domain rules. The
current capability modules may temporarily provide implementation code during
the migration, but they are not the public workflow layer.

Tobacco license becomes the second tracer bullet. It must use the same graph
runtime contract to prove the multi-document extension model.

Old compatibility entry points, tests, and documentation that encode
`UseCase + Workflow + Capability` as the target architecture should be deleted
or rewritten as part of the migration.
