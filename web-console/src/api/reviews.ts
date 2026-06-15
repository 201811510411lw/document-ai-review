export type ReviewStatus =
  | "REVIEWED"
  | "PENDING_MANUAL_REVIEW"
  | "MANUAL_REVIEWED"
  | "FAILED";

export type RiskLevel = "NONE" | "LOW" | "MEDIUM" | "HIGH";

export type RuleState = "passed" | "failed" | "manual_review";

export interface ReviewRow {
  taskId: string;
  businessName: string;
  creditCode: string;
  reviewStatus: ReviewStatus;
  reviewStatusLabel: string;
  riskLevel: RiskLevel;
  riskLevelLabel: string;
  needsManualReview: boolean;
  reviewedAt: string;
  sourceRecordId: string;
  attachmentId: string;
}

export interface ExtractedFieldSet {
  subjectName: string;
  creditCode: string;
  legalPerson: string;
  establishedDate: string;
  validFrom: string;
  validTo: string;
  businessAddress: string;
  confidence: number;
}

export interface RuleResult {
  ruleCode: string;
  ruleName: string;
  state: RuleState;
  riskLevelOnFailure: RiskLevel;
  message: string;
  evidence?: string;
}

export interface ReviewDetail extends ReviewRow {
  sourceUrl: string;
  summary: string;
  extractedFields: ExtractedFieldSet;
  normalizedFields: ExtractedFieldSet;
  ruleResults: RuleResult[];
  manualReviewReasons: string[];
  payload: Record<string, unknown>;
}

export interface ReviewFilters {
  businessName: string;
  creditCode: string;
  riskLevel: "ALL" | RiskLevel;
  reviewStatus: "ALL" | ReviewStatus;
  dateRange: "today" | "week" | "month" | "all";
  page: number;
  pageSize: number;
}

export interface ReviewMetrics {
  todayReviewed: number;
  pendingManualReview: number;
  highRisk: number;
  passRate: number;
}

export interface ListReviewsResponse {
  items: ReviewRow[];
  metrics: ReviewMetrics;
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
}

export interface ReviewClient {
  listReviews(filters: ReviewFilters): Promise<ListReviewsResponse>;
  getReview(taskId: string): Promise<ReviewDetail | null>;
}
