import type {
  ListReviewsResponse,
  ReviewClient,
  ReviewDetail,
  ReviewFilters,
  ReviewRow,
  ManualReviewRequest
} from "./reviews";
import { mockReviews } from "../mocks/reviews";

const delay = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));

function applyFilters(items: ReviewDetail[], filters: ReviewFilters): ReviewDetail[] {
  return items.filter((item) => {
    const nameMatches = item.businessName.includes(filters.businessName.trim());
    const codeMatches = item.creditCode.includes(filters.creditCode.trim().toUpperCase());
    const riskMatches =
      filters.riskLevel === "ALL" || item.riskLevel === filters.riskLevel;
    const statusMatches =
      filters.reviewStatus === "ALL" || item.reviewStatus === filters.reviewStatus;
    const itemDocumentType =
      typeof item.payload.document_type === "string"
        ? item.payload.document_type
        : typeof item.payload.documentType === "string"
          ? item.payload.documentType
          : "business_license";
    const documentTypeMatches =
      filters.documentType === "ALL" || itemDocumentType === filters.documentType;

    const dateMatches = inDateRange(item.reviewedAt, filters.dateRange);

    return nameMatches && codeMatches && documentTypeMatches && riskMatches && statusMatches && dateMatches;
  });
}

function inDateRange(
  value: string,
  dateRange: ReviewFilters["dateRange"],
  today = "2026-06-15"
) {
  if (dateRange === "all") {
    return true;
  }

  const businessDate = value.slice(0, 10);

  if (dateRange === "today") {
    return businessDate === today;
  }

  const current = parseBusinessDate(today);
  const reviewedAt = parseBusinessDate(businessDate);
  const start = parseBusinessDate(today);
  if (dateRange === "week") {
    start.setDate(current.getDate() - 6);
  }
  if (dateRange === "month") {
    start.setDate(current.getDate() - 29);
  }

  return reviewedAt >= start && reviewedAt <= current;
}

function parseBusinessDate(value: string) {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day);
}

function metricsFrom(items: ReviewDetail[]) {
  const todayReviewed = items.filter((item) =>
    item.reviewedAt.startsWith("2026-06-15")
  ).length;
  const pendingManualReview = items.filter((item) => item.needsManualReview).length;
  const highRisk = items.filter((item) => item.riskLevel === "HIGH").length;
  const reviewed = items.filter((item) => item.reviewStatus === "REVIEWED").length;

  return {
    todayReviewed,
    pendingManualReview,
    highRisk,
    passRate: items.length === 0 ? 0 : Math.round((reviewed / items.length) * 100)
  };
}

export const mockReviewClient: ReviewClient = {
  async listReviews(filters: ReviewFilters): Promise<ListReviewsResponse> {
    await delay(20);
    const filtered = applyFilters(mockReviews, filters);
    const pageSize = Math.max(1, filters.pageSize);
    const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
    const page = Math.min(Math.max(1, filters.page), totalPages);
    const offset = (page - 1) * pageSize;
    const pageItems = filtered.slice(offset, offset + pageSize);

    return {
      items: pageItems.map(({ payload, extractedFields, normalizedFields, ruleResults, manualReviewReasons, sourceUrl, summary, ...row }) => row as ReviewRow),
      metrics: metricsFrom(filtered),
      page,
      pageSize,
      total: filtered.length,
      totalPages
    };
  },

  async listQcReviews(filters: ReviewFilters): Promise<ListReviewsResponse> {
    await delay(20);
    const filtered = applyFilters(mockReviews, filters);
    const pageSize = Math.max(1, filters.pageSize);
    const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
    const page = Math.min(Math.max(1, filters.page), totalPages);
    const offset = (page - 1) * pageSize;
    const pageItems = filtered.slice(offset, offset + pageSize);

    return {
      items: pageItems.map(({ payload, extractedFields, normalizedFields, ruleResults, manualReviewReasons, sourceUrl, summary, ...row }) => row as ReviewRow),
      metrics: metricsFrom(filtered),
      page,
      pageSize,
      total: filtered.length,
      totalPages
    };
  },

  async getReview(taskId: string): Promise<ReviewDetail | null> {
    await delay(20);
    return mockReviews.find((item) => item.taskId === taskId) ?? null;
  },

  async getQcReview(taskId: string): Promise<ReviewDetail | null> {
    await delay(20);
    return mockReviews.find((item) => item.taskId === taskId) ?? null;
  },

  async createReviewFromSrm(): Promise<ReviewDetail> {
    await delay(20);
    const createdAt = "2026-06-15T12:00:00+08:00";
    const taskId = `blr-srm-${mockReviews.length + 1}`;
    const created: ReviewDetail = {
      taskId,
      businessName: "成都示例商贸有限公司",
      creditCode: "91510100MA0000000X",
      reviewStatus: "REVIEWED",
      reviewStatusLabel: "已审核",
      riskLevel: "NONE",
      riskLevelLabel: "无风险",
      needsManualReview: false,
      reviewedAt: createdAt,
      sourceRecordId: "SRM-CERT-NEW",
      attachmentId: "ATT-BL-NEW",
      sourceUrl: "https://files.example.test/business-license-new.png",
      summary: "从 SRM 来源记录创建审核任务，营业执照规则校验通过。",
      extractedFields: {
        subjectName: "成都示例商贸有限公司",
        creditCode: "91510100MA0000000X",
        legalPerson: "张三",
        establishedDate: "2020-01-02",
        validFrom: "2020-01-02",
        validTo: "2030-01-01",
        businessAddress: "成都市高新区天府大道 1 号",
        confidence: 0.96
      },
      normalizedFields: {
        subjectName: "成都示例商贸有限公司",
        creditCode: "91510100MA0000000X",
        legalPerson: "张三",
        establishedDate: "2020-01-02",
        validFrom: "2020-01-02",
        validTo: "2030-01-01",
        businessAddress: "成都市高新区天府大道1号",
        confidence: 0.96
      },
      ruleResults: [
        {
          ruleCode: "BUSINESS_LICENSE_TYPE_MATCH",
          ruleName: "营业执照类型匹配",
          state: "passed",
          riskLevelOnFailure: "HIGH",
          message: "已确认文件为营业执照"
        }
      ],
      manualReviewReasons: [],
      manualReview: {
        status: "NOT_REQUIRED",
        reasons: []
      },
      auditEvents: [],
      payload: {
        task_id: taskId,
        status: "REVIEWED",
        risk_level: "NONE",
        source: {
          record_id: "SRM-CERT-NEW",
          attachment_ref_id: "ATT-BL-NEW"
        }
      }
    };
    mockReviews.unshift(created);
    return created;
  },

  async submitManualReview(
    taskId: string,
    request: ManualReviewRequest
  ): Promise<ReviewDetail> {
    await delay(20);
    const index = mockReviews.findIndex((item) => item.taskId === taskId);
    if (index < 0) {
      throw new Error("Review not found");
    }
    const reviewedAt = new Date().toISOString();
    const updated = {
      ...mockReviews[index],
      reviewStatus: "MANUAL_REVIEWED" as const,
      reviewStatusLabel: "人工已复核",
      needsManualReview: false,
      manualReview: {
        status: "COMPLETED" as const,
        decision: request.decision,
        comment: request.comment,
        reviewerId: request.reviewerId,
        reviewerUsername: "reviewer",
        reviewedAt,
        reasons: mockReviews[index].manualReviewReasons
      },
      auditEvents: [
        ...mockReviews[index].auditEvents,
        {
          eventType: "BUSINESS_LICENSE_MANUAL_REVIEW",
          message: request.decision === "approved" ? "人工复核确认通过" : "人工复核驳回",
          occurredAt: reviewedAt,
          actorId: request.reviewerId,
          actorUsername: "reviewer",
          details: {
            decision: request.decision,
            comment: request.comment,
            reviewer_id: request.reviewerId,
            reviewer_username: "reviewer"
          }
        }
      ]
    };
    mockReviews[index] = updated;
    return updated;
  }
};
