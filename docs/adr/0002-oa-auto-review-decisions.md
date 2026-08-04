# OA auto review exposes four decisions

OA Auto Review exposes `pass`, `reject`, `manual_review`, and `exception` as distinct partner-facing decisions. `reject` requires complete evidence and a deterministic business-negative rule; incomplete or contradictory evidence becomes `manual_review`, while database, NAS, OCR, LLM, and RPA technical failures become `exception` and must never be represented as a business rejection or automatic pass.
