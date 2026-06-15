import type {
  ListReviewsResponse,
  ReviewClient,
  ReviewDetail,
  ReviewFilters,
  ReviewRow,
  RuleResult,
  ManualReviewRequest
} from "./reviews";
import { authHeaders, clearSession } from "./auth";
import { navigateTo } from "../navigation";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");
const nowProvider = () => new Date();

export const httpReviewClient: ReviewClient = {
  async listReviews(filters: ReviewFilters): Promise<ListReviewsResponse> {
    const response = await fetch(
      `${API_BASE_URL}/api/v1/business-license/reviews?${queryString(filters)}`,
      {headers: authHeaders()}
    );
    handleUnauthorized(response);
    if (!response.ok) {
      throw new Error(`Failed to list business license reviews: ${response.status}`);
    }
    return mapListResponse(await response.json());
  },

  async getReview(taskId: string): Promise<ReviewDetail | null> {
    const response = await fetch(
      `${API_BASE_URL}/api/v1/business-license/reviews/${encodeURIComponent(taskId)}`,
      {headers: authHeaders()}
    );
    handleUnauthorized(response);
    if (response.status === 404) {
      return null;
    }
    if (!response.ok) {
      throw new Error(`Failed to get business license review: ${response.status}`);
    }
    return mapDetailResponse(await response.json());
  },

  async submitManualReview(
    taskId: string,
    request: ManualReviewRequest
  ): Promise<ReviewDetail> {
    const response = await fetch(
      `${API_BASE_URL}/api/v1/business-license/reviews/${encodeURIComponent(taskId)}/manual-review`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders()
        },
        body: JSON.stringify({
          decision: request.decision,
          comment: request.comment,
          reviewer_id: request.reviewerId
        })
      }
    );
    handleUnauthorized(response);
    if (!response.ok) {
      throw new Error(`Failed to submit business license manual review: ${response.status}`);
    }
    return mapDetailResponse(await response.json());
  }
};

function handleUnauthorized(response: Response) {
  if (response.status === 401) {
    clearSession();
    navigateTo("/login", { replace: true });
  }
}

function queryString(filters: ReviewFilters) {
  const params = new URLSearchParams();
  if (filters.businessName.trim()) {
    params.set("business_name", filters.businessName.trim());
  }
  if (filters.creditCode.trim()) {
    params.set("credit_code", filters.creditCode.trim().toUpperCase());
  }
  if (filters.riskLevel !== "ALL") {
    params.set("risk_level", filters.riskLevel);
  }
  if (filters.reviewStatus !== "ALL") {
    params.set("review_status", filters.reviewStatus);
  }
  const range = dateRange(filters.dateRange);
  if (range.createdFrom) {
    params.set("created_from", range.createdFrom);
  }
  if (range.createdTo) {
    params.set("created_to", range.createdTo);
  }
  params.set("page", String(filters.page));
  params.set("page_size", String(filters.pageSize));
  return params.toString();
}

function dateRange(dateRangeValue: ReviewFilters["dateRange"]) {
  if (dateRangeValue === "all") {
    return {};
  }
  const now = nowProvider();
  const start = new Date(now);
  if (dateRangeValue === "week") {
    start.setDate(now.getDate() - 6);
  }
  if (dateRangeValue === "month") {
    start.setDate(now.getDate() - 29);
  }
  return {
    createdFrom: formatLocalDate(start),
    createdTo: formatLocalDate(now)
  };
}

function formatLocalDate(value: Date) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function mapListResponse(payload: ApiListResponse): ListReviewsResponse {
  return {
    items: payload.items.map(mapRow),
    metrics: {
      todayReviewed: payload.metrics.today_reviewed,
      pendingManualReview: payload.metrics.pending_manual_review,
      highRisk: payload.metrics.high_risk,
      passRate: payload.metrics.pass_rate
    },
    page: payload.page,
    pageSize: payload.page_size,
    total: payload.total,
    totalPages: payload.total_pages
  };
}

function mapDetailResponse(payload: ApiReviewDetail): ReviewDetail {
  return {
    ...mapRow(payload),
    sourceUrl: payload.source_url ?? "#",
    summary: payload.summary ?? "",
    extractedFields: mapFields(payload.extracted_fields, payload),
    normalizedFields: mapFields(payload.normalized_fields, payload),
    ruleResults: (payload.rule_results ?? []).map(mapRule),
    manualReviewReasons: payload.manual_review_reasons ?? [],
    manualReview: mapManualReview(payload.manual_review, payload.manual_review_reasons),
    auditEvents: (payload.audit_events ?? []).map(mapAuditEvent),
    payload: payload.payload ?? { ...payload }
  };
}

function mapRow(payload: ApiReviewRow): ReviewRow {
  return {
    taskId: payload.task_id,
    businessName: payload.business_name ?? "未识别主体名称",
    creditCode: payload.credit_code ?? "未识别",
    reviewStatus: payload.review_status,
    reviewStatusLabel: payload.review_status_label,
    riskLevel: payload.risk_level,
    riskLevelLabel: payload.risk_level_label,
    needsManualReview: payload.needs_manual_review,
    reviewedAt: payload.created_at ?? payload.updated_at ?? "",
    sourceRecordId: payload.source_record_id ?? "-",
    attachmentId: payload.source_attachment_ref_id ?? "-"
  };
}

function mapFields(fields: ApiFieldSet | undefined, detail: ApiReviewDetail) {
  return {
    subjectName: fields?.subject_name ?? detail.business_name ?? "",
    creditCode: fields?.credit_code ?? detail.credit_code ?? "",
    legalPerson: fields?.legal_person ?? detail.legal_person ?? "",
    establishedDate: fields?.established_date ?? fields?.valid_from ?? detail.valid_from ?? "",
    validFrom: fields?.valid_from ?? detail.valid_from ?? "",
    validTo: fields?.valid_to ?? detail.valid_to ?? "",
    businessAddress: fields?.business_address ?? detail.business_address ?? "",
    confidence: numericConfidence(fields?.confidence)
  };
}

function mapRule(rule: ApiRuleResult): RuleResult {
  return {
    ruleCode: rule.rule_code,
    ruleName: rule.rule_name,
    state: rule.passed ? "passed" : "failed",
    riskLevelOnFailure: rule.risk_level_on_failure,
    message: rule.message,
    evidence: rule.details ? JSON.stringify(rule.details) : undefined
  };
}

function numericConfidence(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function mapManualReview(
  payload: ApiManualReview | undefined,
  fallbackReasons: string[] | undefined
) {
  return {
    status: payload?.status ?? "PENDING",
    decision: payload?.decision,
    comment: payload?.comment,
    reviewerId: payload?.reviewer_id,
    reviewerUsername: payload?.reviewer_username,
    reviewedAt: payload?.reviewed_at,
    reasons: payload?.reasons ?? fallbackReasons ?? []
  };
}

function mapAuditEvent(payload: ApiAuditEvent) {
  return {
    eventType: payload.event_type,
    message: payload.message,
    occurredAt: payload.occurred_at,
    actorId: payload.actor_id,
    actorUsername: payload.actor_username,
    details: payload.details ?? {}
  };
}

interface ApiListResponse {
  items: ApiReviewRow[];
  metrics: {
    today_reviewed: number;
    pending_manual_review: number;
    high_risk: number;
    pass_rate: number;
  };
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

interface ApiReviewRow {
  task_id: string;
  source_record_id?: string | null;
  source_attachment_ref_id?: string | null;
  business_name?: string | null;
  credit_code?: string | null;
  review_status: ReviewRow["reviewStatus"];
  review_status_label: string;
  risk_level: ReviewRow["riskLevel"];
  risk_level_label: string;
  needs_manual_review: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

interface ApiReviewDetail extends ApiReviewRow {
  source_url?: string | null;
  summary?: string | null;
  business_address?: string | null;
  legal_person?: string | null;
  valid_from?: string | null;
  valid_to?: string | null;
  rule_results?: ApiRuleResult[];
  extracted_fields?: ApiFieldSet;
  normalized_fields?: ApiFieldSet;
  manual_review_reasons?: string[];
  manual_review?: ApiManualReview;
  audit_events?: ApiAuditEvent[];
  payload?: Record<string, unknown>;
}

interface ApiManualReview {
  status: "NOT_REQUIRED" | "PENDING" | "COMPLETED";
  decision?: "approved" | "rejected";
  comment?: string;
  reviewer_id?: string;
  reviewer_username?: string;
  reviewed_at?: string;
  reasons?: string[];
}

interface ApiAuditEvent {
  event_type: string;
  message: string;
  occurred_at: string;
  actor_id?: string;
  actor_username?: string;
  details?: Record<string, unknown>;
}

interface ApiFieldSet {
  subject_name?: string;
  credit_code?: string;
  legal_person?: string;
  established_date?: string;
  valid_from?: string;
  valid_to?: string;
  business_address?: string;
  confidence?: unknown;
}

interface ApiRuleResult {
  rule_code: string;
  rule_name: string;
  passed: boolean;
  risk_level_on_failure: RuleResult["riskLevelOnFailure"];
  message: string;
  details?: Record<string, unknown>;
}
