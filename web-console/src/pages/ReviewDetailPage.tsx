import { useEffect, useState } from "react";
import { ArrowLeft, ExternalLink } from "lucide-react";
import { reviewClient } from "../api/client";
import type { ExtractedFieldSet, ReviewDetail } from "../api/reviews";
import { EmptyState, ErrorState, LoadingState } from "../components/EmptyState";
import { RiskBadge, RuleStateBadge, StatusBadge } from "../components/Badge";

export function ReviewDetailPage({ taskId, qcView = false }: { taskId: string; qcView?: boolean }) {
  const [detail, setDetail] = useState<ReviewDetail | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "empty" | "error">("loading");

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
    return <ErrorState message="审核详情查询失败，请检查 API 服务状态。" />;
  }

  if (status === "empty" || !detail) {
    return <EmptyState title="未找到审核详情" message="该任务 ID 不存在或已被清理。" />;
  }

  return (
    <div className="page-stack detail-page">
      <a className="back-link" href={qcView ? "/qc/reviews" : "/reviews"}>
        <ArrowLeft size={16} aria-hidden="true" />
        返回列表
      </a>
      <a className="mobile-back-link" href={qcView ? "/qc/reviews" : "/reviews"}>
        <ArrowLeft size={16} aria-hidden="true" />
        审核详情
      </a>

      <section className="detail-hero">
        <div>
          <p>营业执照审核详情</p>
          <h1>{detail.businessName}</h1>
          <div className="hero-badges">
            <StatusBadge status={detail.reviewStatus} label={detail.reviewStatusLabel} />
            <RiskBadge risk={detail.riskLevel} label={detail.riskLevelLabel} />
          </div>
        </div>
        <a className="primary-button" href={detail.sourceUrl} target="_blank" rel="noreferrer">
          <ExternalLink size={16} aria-hidden="true" />
          打开原文件
        </a>
      </section>

      <section className="info-strip" aria-label="任务追踪信息">
        <InfoItem label="任务 ID" value={detail.taskId} />
        <InfoItem label="SRM 记录 ID" value={detail.sourceRecordId} />
        <InfoItem label="附件 ID" value={detail.attachmentId} />
        <InfoItem label="审核时间" value={formatTime(detail.reviewedAt)} />
      </section>

      <section className="two-column">
        <div className="panel">
          <div className="panel-title">
            <h2>字段抽取结果</h2>
            <span>置信度 {Math.round(detail.extractedFields.confidence * 100)}%</span>
          </div>
          <FieldGrid fields={detail.extractedFields} />
        </div>

        <div className="panel">
          <div className="panel-title">
            <h2>标准化字段</h2>
            <span>规则使用值</span>
          </div>
          <FieldGrid fields={detail.normalizedFields} />
        </div>
      </section>

      <section className="two-column">
        <div className="panel">
          <div className="panel-title">
            <h2>规则校验结果</h2>
            <span>{detail.ruleResults.length} 条规则</span>
          </div>
          {detail.ruleResults.length > 0 ? (
            <div className="rule-list">
              {detail.ruleResults.map((rule) => (
              <article className="rule-item" key={rule.ruleCode}>
                <div>
                  <strong>{rule.ruleName}</strong>
                  <small>{rule.ruleCode}</small>
                </div>
                <RuleStateBadge state={rule.state} />
                <p>{rule.message}</p>
                {rule.evidence && <blockquote>{rule.evidence}</blockquote>}
              </article>
              ))}
            </div>
          ) : (
            <p className="muted-text">暂无规则校验结果。</p>
          )}
        </div>

        <div className="panel">
          <div className="panel-title">
            <h2>审核摘要</h2>
            <span>{detail.needsManualReview ? "需复核" : "自动审核"}</span>
          </div>
          <p className="muted-text">{detail.summary || "暂无审核摘要。"}</p>
        </div>
      </section>

      <section className="panel">
        <div className="panel-title">
          <h2>人工复核</h2>
          <span>{detail.manualReview.status}</span>
        </div>
        <ManualReviewSummary detail={detail} />
        <div className="review-actions">
          <a
            className="secondary-button"
            href={qcView ? `/qc/reviews/${detail.taskId}/manual-review` : `/reviews/${detail.taskId}/manual-review`}
          >
            进入人工复核
          </a>
        </div>
      </section>

      <section className="panel">
        <div className="panel-title">
          <h2>审计事件</h2>
          <span>{detail.auditEvents.length} 条</span>
        </div>
        {detail.auditEvents.length > 0 ? (
          <div className="audit-list">
            {detail.auditEvents.map((event) => (
              <article key={`${event.eventType}-${event.occurredAt}`}>
                <div>
                  <strong>{event.message}</strong>
                  <span>{formatTime(event.occurredAt)}</span>
                </div>
                <p>
                  操作人：{event.actorUsername || event.actorId || textFromDetails(event.details, "reviewer_username") || textFromDetails(event.details, "reviewer_id") || "-"}
                </p>
                {textFromDetails(event.details, "comment") && (
                  <p>备注：{textFromDetails(event.details, "comment")}</p>
                )}
              </article>
            ))}
          </div>
        ) : (
          <p className="muted-text">暂无审计事件。</p>
        )}
      </section>

      <details className="json-panel">
        <summary>完整 JSON 快照</summary>
        <pre>{JSON.stringify(detail.payload, null, 2)}</pre>
      </details>
    </div>
  );
}

function ManualReviewSummary({ detail }: { detail: ReviewDetail }) {
  const reasons =
    detail.manualReview.reasons.length > 0
      ? detail.manualReview.reasons
      : detail.manualReviewReasons;

  return (
    <div className="manual-review-summary">
      {reasons.length > 0 ? (
        <div>
          <h3>复核原因</h3>
          <ul className="reason-list">
            {reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="muted-text">当前记录没有人工复核原因。</p>
      )}

      {detail.manualReview.status === "COMPLETED" ? (
        <dl className="manual-review-grid">
          <div>
            <dt>复核结论</dt>
            <dd>{manualReviewDecisionLabel(detail.manualReview.decision)}</dd>
          </div>
          <div>
            <dt>复核人</dt>
            <dd>{detail.manualReview.reviewerUsername || detail.manualReview.reviewerId || "-"}</dd>
          </div>
          <div>
            <dt>复核时间</dt>
            <dd>{detail.manualReview.reviewedAt ? formatTime(detail.manualReview.reviewedAt) : "-"}</dd>
          </div>
          <div className="manual-review-comment">
            <dt>复核备注</dt>
            <dd>{detail.manualReview.comment || "-"}</dd>
          </div>
        </dl>
      ) : (
        <p className="muted-text">还没有人工复核结论。</p>
      )}
    </div>
  );
}

function FieldGrid({ fields }: { fields: ExtractedFieldSet }) {
  const rows = [
    ["主体名称", fields.subjectName],
    ["统一社会信用代码", fields.creditCode],
    ["法定代表人", fields.legalPerson],
    ["成立日期", fields.establishedDate],
    ["营业期限", `${fields.validFrom} 至 ${fields.validTo}`],
    ["住所", fields.businessAddress],
    ["置信度", `${Math.round(fields.confidence * 100)}%`]
  ];

  return (
    <dl className="field-grid">
      {rows.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function InfoItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function manualReviewDecisionLabel(decision: string | undefined) {
  if (decision === "approved") {
    return "通过";
  }
  if (decision === "rejected") {
    return "不通过";
  }
  return "-";
}

function textFromDetails(details: Record<string, unknown>, key: string) {
  const value = details[key];
  return typeof value === "string" && value.trim() ? value : "";
}

function formatTime(value: string) {
  return value.replace("T", " ").replace("+08:00", "");
}
