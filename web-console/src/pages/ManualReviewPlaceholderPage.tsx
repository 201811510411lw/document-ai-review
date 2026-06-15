import { useEffect, useState } from "react";
import { ArrowLeft } from "lucide-react";
import { reviewClient } from "../api/client";
import type { ManualReviewDecision, ReviewDetail } from "../api/reviews";
import { RiskBadge, StatusBadge } from "../components/Badge";
import { EmptyState, ErrorState, LoadingState } from "../components/EmptyState";

export function ManualReviewPlaceholderPage({ taskId }: { taskId: string }) {
  const [detail, setDetail] = useState<ReviewDetail | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "empty" | "error">("loading");
  const [decision, setDecision] = useState<ManualReviewDecision>("approved");
  const [comment, setComment] = useState("");
  const [reviewerId, setReviewerId] = useState("wecom-reviewer-local");
  const [submitStatus, setSubmitStatus] = useState<"idle" | "submitting" | "success" | "error">("idle");

  useEffect(() => {
    let mounted = true;
    setStatus("loading");

    reviewClient
      .getReview(taskId)
      .then((response) => {
        if (!mounted) {
          return;
        }
        setDetail(response);
        setStatus(response ? "ready" : "empty");
      })
      .catch(() => {
        if (mounted) {
          setStatus("error");
        }
      });

    return () => {
      mounted = false;
    };
  }, [taskId]);

  if (status === "loading") {
    return <LoadingState />;
  }

  if (status === "error") {
    return <ErrorState message="审核记录查询失败，请检查 API 服务状态。" />;
  }

  if (status === "empty" || !detail) {
    return <EmptyState title="未找到审核记录" message="该任务 ID 不存在或已被清理。" />;
  }

  const isCompleted = detail.manualReview.status === "COMPLETED";
  const canSubmit =
    !isCompleted &&
    submitStatus !== "success" &&
    submitStatus !== "submitting" &&
    comment.trim().length > 0 &&
    reviewerId.trim().length > 0;

  async function submitManualReview() {
    if (!detail || !canSubmit) {
      return;
    }
    setSubmitStatus("submitting");
    try {
      const updated = await reviewClient.submitManualReview(detail.taskId, {
        decision,
        comment: comment.trim(),
        reviewerId: reviewerId.trim()
      });
      setDetail(updated);
      setSubmitStatus("success");
    } catch {
      setSubmitStatus("error");
    }
  }

  return (
    <div className="page-stack manual-page">
      <a className="back-link" href={`/reviews/${detail.taskId}`}>
        <ArrowLeft size={16} aria-hidden="true" />
        返回详情
      </a>
      <a className="mobile-back-link" href={`/reviews/${detail.taskId}`}>
        <ArrowLeft size={16} aria-hidden="true" />
        复核预留
      </a>

      <section className="page-heading">
        <div>
          <h1>人工复核</h1>
          <p>提交人工复核结论，写回审核状态并记录审计事件</p>
        </div>
      </section>

      <section className="panel manual-panel">
        <div className="manual-record">
          <span>当前记录</span>
          <h2>{detail.businessName}</h2>
          <div className="hero-badges">
            <StatusBadge status={detail.reviewStatus} label={detail.reviewStatusLabel} />
            <RiskBadge risk={detail.riskLevel} label={detail.riskLevelLabel} />
          </div>
        </div>

        <div className="review-advice">
          <strong>复核建议</strong>
          <p>
            系统建议：请人工核对营业期限、主体信息和原始证照图片清晰度。AI 规则结果仅作为审核辅助，不作为最终合规结论。
          </p>
        </div>

        <div className="manual-workspace">
          <form className="manual-form">
            <h3>复核操作区</h3>
            <label>
              <span>复核结论</span>
              <select
                value={decision}
                onChange={(event) => setDecision(event.target.value as ManualReviewDecision)}
              >
                <option value="approved">确认通过</option>
                <option value="rejected">驳回</option>
              </select>
            </label>
            <label>
              <span>复核备注</span>
              <textarea
                value={comment}
                onChange={(event) => setComment(event.target.value)}
                placeholder="请输入人工判断依据"
                rows={4}
              />
            </label>
            <label>
              <span>复核人 ID</span>
              <input
                value={reviewerId}
                onChange={(event) => setReviewerId(event.target.value)}
                placeholder="企业微信用户 ID"
              />
            </label>
            <div className="review-actions">
              <button disabled={!canSubmit} type="button" onClick={submitManualReview}>
                {submitStatus === "submitting" ? "提交中" : "提交复核结论"}
              </button>
              <span>
                {isCompleted && "已写回人工复核结论"}
                {submitStatus === "error" && "提交失败，请检查 API 服务状态"}
                {submitStatus === "idle" && !isCompleted && "提交后状态将变为人工已复核"}
              </span>
            </div>
          </form>

          <aside className="contract-card">
            <h3>复核写回状态</h3>
            <code>
              status: {detail.manualReview.status}
              {"\n"}decision: {detail.manualReview.decision ?? "-"}
              {"\n"}reviewer: {detail.manualReview.reviewerId ?? "-"}
              {"\n"}reviewed_at: {detail.manualReview.reviewedAt ?? "-"}
            </code>
            {detail.auditEvents.length > 0 ? (
              <div className="audit-list">
                {detail.auditEvents.map((event) => (
                  <p key={`${event.eventType}-${event.occurredAt}`}>
                    {event.occurredAt} · {event.message}
                  </p>
                ))}
              </div>
            ) : null}
          </aside>
        </div>
      </section>
    </div>
  );
}
