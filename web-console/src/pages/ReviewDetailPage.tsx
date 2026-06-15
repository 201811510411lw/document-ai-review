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
            <h2>规则校验结果</h2>
            <span>{detail.ruleResults.length} 条规则</span>
          </div>
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
        </div>
      </section>

      <section className="panel">
        <div className="panel-title">
          <h2>人工复核预留区</h2>
          <span>V1 不提交写回</span>
        </div>
        {detail.manualReviewReasons.length > 0 ? (
          <ul className="reason-list">
            {detail.manualReviewReasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        ) : (
          <p className="muted-text">当前记录没有人工复核原因。</p>
        )}
        <div className="review-actions">
          <button disabled type="button">
            人工通过
          </button>
          <button disabled type="button">
            人工驳回
          </button>
          <a className="secondary-button" href={`/reviews/${detail.taskId}/manual-review`}>
            查看复核预留页
          </a>
        </div>
      </section>

      <details className="json-panel">
        <summary>完整 JSON 快照</summary>
        <pre>{JSON.stringify(detail.payload, null, 2)}</pre>
      </details>
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

function formatTime(value: string) {
  return value.replace("T", " ").replace("+08:00", "");
}
