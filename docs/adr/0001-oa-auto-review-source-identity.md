# OA auto review is scoped by OA request identity

An OA Auto Review is identified and made idempotent by `workflow_id + requestid`, and its Source Task must contain evidence from that exact OA request. The current StarRocks adapter may supply the evidence only by exact `requestid` match; it must never infer the request from a store name, title, or the latest record. A future live OA adapter can replace the source without changing the review contract. Request-provided callback URLs are not trusted source configuration and are outside the initial synchronous and polling contract.
