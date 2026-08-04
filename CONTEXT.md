# Document AI Review

This context covers the language used to acquire business documents, review them, and preserve results for later inspection or manual handling.

## Language

**Review Use Case**:
A named business review capability that accepts a review input and returns one unified review result. It is the public business entry point for one review purpose.
_Avoid_: Skill, scene, review type

**Review Workflow**:
The ordered review process that acquires evidence, extracts fields, applies domain rules, and determines whether manual review is needed.
_Avoid_: Agent, pipeline

**Capability**:
A stateless extraction, normalization, classification, or document-processing ability used by a review workflow.
_Avoid_: Use Case, workflow

**Domain Rule**:
A deterministic business rule that produces a rule result and contributes to the final compliance decision.
_Avoid_: Prompt rule, LLM judgement

**Agent Skill**:
The maintained policy and prompt guidance for one document domain. It defines review vocabulary and rule intent but does not execute a review workflow.
_Avoid_: Review Use Case, runtime skill

**Source Task**:
A normalized unit of source-system evidence prepared for a specific review use case. Product-report source tasks remain distinct from supplier-certificate source tasks because they represent SKU materials.
_Avoid_: Generic source record

**Review Task**:
One traceable execution of a review use case against a review input.
_Avoid_: Source Task, job

**Review Result**:
The unified, traceable outcome of a review task, including status, risk, rule results, manual-review state, audit events, and the document-specific result.
_Avoid_: Skill result, response payload

**Rule Result**:
The outcome and evidence for one domain rule, including whether it passed and the risk attached to failure.
_Avoid_: Validation message

**Manual Review**:
The explicit human decision stage used when automated evidence is insufficient, contradictory, or requires an accountable business decision.
_Avoid_: Retry, technical failure

**Business-Negative Verification**:
A completed external verification whose evidence says the document did not pass verification.
_Avoid_: Technical error, incomplete verification

**Technical Verification Error**:
An external verification that did not complete reliably enough to make a business claim and may be retried.
_Avoid_: Verification failed, counterfeit result

**OA Auto Review**:
One idempotent review request initiated by an OA workflow for a specific OA request and its submitted evidence.
_Avoid_: Store review, latest store review

**Auto Review Decision**:
The partner-facing outcome of an OA Auto Review: `pass`, `reject`, `manual_review`, or `exception`.
_Avoid_: Status, result

**Manual-Review Decision**:
An Auto Review Decision used when evidence is incomplete, contradictory, or requires an accountable human judgement.
_Avoid_: Exception, retry

**Exception Decision**:
An Auto Review Decision used when a technical dependency did not complete reliably enough to form a business conclusion.
_Avoid_: Reject, verification failed
