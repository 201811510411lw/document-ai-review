import type {
  ListReviewsResponse,
  ReviewClient,
  ReviewDetail,
  ReviewFilters,
  ReviewRow
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

    return nameMatches && codeMatches && riskMatches && statusMatches;
  });
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
    await delay(160);
    const filtered = applyFilters(mockReviews, filters);

    return {
      items: filtered.map(({ payload, extractedFields, normalizedFields, ruleResults, manualReviewReasons, sourceUrl, summary, ...row }) => row as ReviewRow),
      metrics: metricsFrom(filtered)
    };
  },

  async getReview(taskId: string): Promise<ReviewDetail | null> {
    await delay(120);
    return mockReviews.find((item) => item.taskId === taskId) ?? null;
  }
};
