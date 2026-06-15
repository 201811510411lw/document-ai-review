import { afterEach, describe, expect, it, vi } from "vitest";
import { httpReviewClient } from "./httpClient";

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("httpReviewClient", () => {
  it("maps list response from the business-license review query API", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          items: [
            {
              task_id: "review-task-1",
              source_record_id: "SRM-CERT-001",
              source_attachment_ref_id: "ATT-001",
              business_name: "成都示例商贸有限公司",
              credit_code: "91510100MA0000000X",
              review_status: "REVIEWED",
              review_status_label: "已审核",
              risk_level: "NONE",
              risk_level_label: "无风险",
              needs_manual_review: false,
              created_at: "2026-06-15T09:18:00+08:00",
              updated_at: "2026-06-15T09:18:00+08:00"
            }
          ],
          metrics: {
            today_reviewed: 1,
            pending_manual_review: 0,
            high_risk: 0,
            pass_rate: 100
          },
          page: 1,
          page_size: 20,
          total: 1,
          total_pages: 1
        }),
        { status: 200 }
      )
    );

    const response = await httpReviewClient.listReviews({
      businessName: "成都",
      creditCode: "",
      riskLevel: "NONE",
      reviewStatus: "ALL",
      dateRange: "all",
      page: 1,
      pageSize: 20
    });

    expect(fetchMock.mock.calls[0][0]).toContain("/api/v1/business-license/reviews?");
    expect(fetchMock.mock.calls[0][0]).toContain("business_name=%E6%88%90%E9%83%BD");
    expect(fetchMock.mock.calls[0][0]).toContain("risk_level=NONE");
    expect(response.items[0]).toMatchObject({
      taskId: "review-task-1",
      businessName: "成都示例商贸有限公司",
      reviewStatusLabel: "已审核",
      riskLevelLabel: "无风险",
      sourceRecordId: "SRM-CERT-001",
      attachmentId: "ATT-001"
    });
    expect(response.metrics.passRate).toBe(100);
  });

  it("maps detail response and treats 404 as empty detail", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            task_id: "review-task-2",
            source_record_id: "SRM-CERT-002",
            source_attachment_ref_id: "ATT-002",
            source_url: "https://files.example.test/business-license.pdf",
            business_name: "上海云岚供应链管理有限公司",
            credit_code: "91310115MA1K00002R",
            review_status: "PENDING_MANUAL_REVIEW",
            review_status_label: "待人工复核",
            risk_level: "HIGH",
            risk_level_label: "高风险",
            needs_manual_review: true,
            created_at: "2026-06-15T10:36:00+08:00",
            summary: "统一社会信用代码与来源系统不一致，需要人工核对原件。",
            extracted_fields: {
              subject_name: "上海云岚供应链管理有限公司",
              credit_code: "91310115MA1K00002R",
              legal_person: "李四",
              valid_from: "2019-07-11",
              valid_to: "2029-07-10",
              business_address: "上海市浦东新区张江路 88 号",
              confidence: 0.91
            },
            normalized_fields: {
              subject_name: "上海云岚供应链管理有限公司",
              credit_code: "91310115MA1K00002R"
            },
            rule_results: [
              {
                rule_code: "BUSINESS_LICENSE_CREDIT_CODE_MATCH",
                rule_name: "统一社会信用代码匹配",
                passed: false,
                risk_level_on_failure: "HIGH",
                message: "信用代码不一致",
                details: { actual: "91310115MA1K00002R" }
              }
            ],
            manual_review_reasons: ["统一社会信用代码不一致"],
            payload: { task_id: "review-task-2" }
          }),
          { status: 200 }
        )
      )
      .mockResolvedValueOnce(new Response("", { status: 404 }));

    const detail = await httpReviewClient.getReview("review-task-2");
    const missing = await httpReviewClient.getReview("missing");

    expect(fetchMock.mock.calls[0][0]).toContain(
      "/api/v1/business-license/reviews/review-task-2"
    );
    expect(detail?.businessName).toBe("上海云岚供应链管理有限公司");
    expect(detail?.extractedFields.confidence).toBe(0.91);
    expect(detail?.ruleResults[0].state).toBe("failed");
    expect(detail?.manualReviewReasons).toEqual(["统一社会信用代码不一致"]);
    expect(missing).toBeNull();
  });

  it("sends local business dates for the today filter without UTC conversion", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 5, 15, 0, 30, 0));
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          items: [],
          metrics: {
            today_reviewed: 0,
            pending_manual_review: 0,
            high_risk: 0,
            pass_rate: 0
          },
          page: 1,
          page_size: 20,
          total: 0,
          total_pages: 1
        }),
        { status: 200 }
      )
    );

    await httpReviewClient.listReviews({
      businessName: "",
      creditCode: "",
      riskLevel: "ALL",
      reviewStatus: "ALL",
      dateRange: "today",
      page: 1,
      pageSize: 20
    });

    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toContain("created_from=2026-06-15");
    expect(url).toContain("created_to=2026-06-15");
    expect(url).not.toContain("2026-06-14");
    expect(url).not.toContain("T16%3A");
  });
});
