import { useEffect, useState } from "react";
import { ArrowLeft } from "lucide-react";
import { reviewClient } from "../api/client";
import type { ManualReviewDecision, ReviewDetail } from "../api/reviews";
import { RiskBadge, StatusBadge } from "../components/Badge";
import { EmptyState, ErrorState, LoadingState } from "../components/EmptyState";

export function ManualReviewPlaceholderPage({
  taskId,
  qcView = false
}: {
  taskId: string;
  qcView?: boolean;
}) {
  const [detail, setDetail] = useState<ReviewDetail | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "empty" | "error">("loading");
  const [decision, setDecision] = useState<ManualReviewDecision>("approved");
  const [comment, setComment] = useState("");
  const [reviewerId, setReviewerId] = useState("wecom-reviewer-local");
  const [submitStatus, setSubmitStatus] = useState<"idle" | "submitting" | "error">("idle");
  const [submitError, setSubmitError] = useState("");

  useEffect(() => {
    let mounted = true;
    setStatus("loading");

    const getReview = qcView ? reviewClient.getQcReview : reviewClient.getReview;
    getReview(taskId)
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
  }, [taskId, qcView]);

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
  const canSubmit = !isCompleted && submitStatus !== "submitting";

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit || !detail) {
      return;
    }
    const taskIdForSubmit = detail.taskId;

    const trimmedComment = comment.trim();
    const trimmedReviewerId = reviewerId.trim();
    if (!trimmedComment || !trimmedReviewerId) {
      setSubmitError("请填写复核备注和复核人 ID。");
      setSubmitStatus("error");
      return;
    }

    setSubmitStatus("submitting");
    setSubmitError("");
    try {
      const submitManualReview = qcView
        ? reviewClient.submitQcManualReview
        : reviewClient.submitManualReview;
      const updated = await submitManualReview(taskIdForSubmit, {
        decision,
        comment: trimmedComment,
        reviewerId: trimmedReviewerId
      });
      setDetail(updated);
      setSubmitStatus("idle");
    } catch {
      setSubmitStatus("error");
      setSubmitError("人工复核提交失败，请稍后重试。");
    }
  }

  return (
    <div className="page-stack manual-page">
      <a className="back-link" href={qcView ? `/qc/reviews/${detail.taskId}` : `/reviews/${detail.taskId}`}>
        <ArrowLeft size={16} aria-hidden="true" />
        返回详情
      </a>
      <a className="mobile-back-link" href={qcView ? `/qc/reviews/${detail.taskId}` : `/reviews/${detail.taskId}`}>
        <ArrowLeft size={16} aria-hidden="true" />
        复核预留
      </a>

      <section className="page-heading">
        <div>
          <h1>人工复核</h1>
          <p>提交复核结论后将写回审核记录并生成审计事件</p>
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
          <form className="manual-form" onSubmit={handleSubmit}>
            <h3>复核操作区</h3>
            <label>
              <span>复核结论</span>
              <select
                value={decision}
                disabled={!canSubmit}
                onChange={(event) => setDecision(event.target.value as ManualReviewDecision)}
              >
                <option value="approved">确认通过</option>
                <option value="rejected">驳回</option>
              </select>
            </label>
            <label>
              <span>复核备注</span>
              <textarea
                placeholder="请输入人工判断依据"
                rows={4}
                value={comment}
                disabled={!canSubmit}
                onChange={(event) => setComment(event.target.value)}
              />
            </label>
            <label>
              <span>复核人 ID</span>
              <input
                value={reviewerId}
                placeholder="企业微信用户 ID"
                disabled={!canSubmit}
                onChange={(event) => setReviewerId(event.target.value)}
              />
            </label>
            {submitError ? <p className="form-error">{submitError}</p> : null}
            <div className="review-actions">
              <button disabled={!canSubmit} type="submit">
                {submitStatus === "submitting" ? "提交中" : "提交复核结论"}
              </button>
              <span>
                {isCompleted
                  ? "该记录已有人工复核结果"
                  : "提交后将更新审核状态并写入审计事件"}
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
