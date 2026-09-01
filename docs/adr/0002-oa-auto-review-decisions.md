# OA auto review exposes four decisions

OA Auto Review keeps `pass`, `reject`, `manual_review`, and `exception` as distinct domain, persistence, and polling decisions. `reject` requires complete evidence and a deterministic business-negative rule; incomplete or contradictory evidence becomes `manual_review`, while database, NAS, OCR, LLM, and RPA technical failures become `exception` and must never be represented as a business rejection or automatic pass.

The deployed OA callback receiver supports only the transport decisions `pass`, `reject`, and `exception`. The callback projection therefore maps an internal `manual_review` to `exception` with `error.code=REVIEW_REQUIRES_MANUAL_REVIEW` and `retryable=false`, while preserving `manual_review_reasons` and `manual_review_reason_text`. This is a partner-protocol compatibility mapping only; it must not change the persisted domain decision or be reported as a retryable technical failure.
