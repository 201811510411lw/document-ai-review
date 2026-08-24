# OA auto review is scoped by OA request identity

An OA Auto Review is identified and made idempotent by `workflow_id + requestid`, and its Source Task must contain evidence from that exact OA request. The live OA ecology MySQL adapter supplies the evidence by exact `requestid` match; it must never infer the request from a store name, title, or the latest record. The source adapter can be replaced without changing the review contract. Request-provided callback URLs are not trusted source configuration; outbound result delivery uses only the server-managed callback URL.
