# OA auto review pushes results to a server-managed callback

The OA trigger returns an accepted task identity before review completion. The application executes the existing idempotent review service as a FastAPI background task and POSTs the final four-state response as JSON to the server-managed `oa_auto_review.callback_url`. The callback payload includes the original `workflow_id`, `requestid`, and `store_code`; the result remains the existing `code / message / data` envelope.

The callback endpoint currently requires no authentication. Delivery accepts any HTTP 2xx response and retries network errors, HTTP 408/429, and 5xx responses up to three attempts. Client-provided callback URLs remain rejected. The callback does not advance OA itself; OA maps the returned decision to its own routing rules.

The background task is process-local rather than a durable job queue. A Pod restart during review can interrupt execution or delivery, so the persisted result and `GET .../oa-result` polling endpoint remain the recovery path. A future durable worker may replace the in-process task without changing the callback payload.
