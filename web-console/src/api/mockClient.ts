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

    const dateMatches = inDateRange(item.reviewedAt, filters.dateRange);

    return nameMatches && codeMatches && riskMatches && statusMatches && dateMatches;
  });
}

function inDateRange(
  value: string,
  dateRange: ReviewFilters["dateRange"],
  now = new Date("2026-06-15T12:00:00+08:00")
) {
  if (dateRange === "all") {
    return true;
  }

  const reviewedAt = new Date(value);
  const current = new Date(now);

  if (dateRange === "today") {
    return reviewedAt.toISOString().slice(0, 10) === current.toISOString().slice(0, 10);
  }

  const start = new Date(current);
  if (dateRange === "week") {
    start.setDate(current.getDate() - 6);
  }
  if (dateRange === "month") {
    start.setDate(current.getDate() - 29);
  }

  start.setHours(0, 0, 0, 0);
  return reviewedAt >= start && reviewedAt <= current;
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

  async getReview(taskId: string): Promise<ReviewDetail | null> {
    await delay(20);
    return mockReviews.find((item) => item.taskId === taskId) ?? null;
  }
};
