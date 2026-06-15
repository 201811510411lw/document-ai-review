import { useEffect, useState } from "react";
import { ArrowLeft } from "lucide-react";
import { mockReviewClient } from "../api/mockClient";
import type { ReviewDetail } from "../api/reviews";
import { RiskBadge, StatusBadge } from "../components/Badge";
import { EmptyState, ErrorState, LoadingState } from "../components/EmptyState";

export function ManualReviewPlaceholderPage({ taskId }: { taskId: string }) {
  const [detail, setDetail] = useState<ReviewDetail | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "empty" | "error">("loading");

  useEffect(() => {
    let mounted = true;
    setStatus("loading");

    mockReviewClient
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
    return <ErrorState message="mock client 返回异常，请检查本地前端状态。" />;
  }

  if (status === "empty" || !detail) {
    return <EmptyState title="未找到审核记录" message="该任务 ID 不存在于 mock 数据中。" />;
  }

  return (
    <div className="page-stack manual-page">
      <a className="back-link" href={`/reviews/${detail.taskId}`}>
        <ArrowLeft size={16} aria-hidden="true" />
        返回详情
      </a>

      <section className="page-heading">
        <div>
          <h1>人工复核动作预留</h1>
          <p>V1 只预留交互位置，不实现完整审批流和状态写回</p>
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
            <h3>复核操作区 V1 占位</h3>
            <label>
              <span>复核结论</span>
              <input disabled placeholder="暂不提交，仅展示未来入口" />
            </label>
            <label>
              <span>复核备注</span>
              <input disabled placeholder="请输入人工判断依据，V1 可禁用或隐藏提交" />
            </label>
            <label>
              <span>附件 / 证据</span>
              <input disabled placeholder="未来可追加截图、说明或二次校验证据" />
            </label>
            <div className="review-actions">
              <button disabled type="button">
                确认通过
              </button>
              <button disabled type="button">
                驳回
              </button>
              <button disabled type="button">
                保存复核备注
              </button>
              <span>按钮在 V1 可置灰，避免误以为已支持完整工作流</span>
            </div>
          </form>

          <aside className="contract-card">
            <h3>后续 API 契约预留</h3>
            <code>
              POST /api/business-license/reviews/{"{task_id}"}/manual-review
              {"\n"}{"{"}
              {"\n"}  "decision": "approved | rejected",
              {"\n"}  "comment": "人工复核备注",
              {"\n"}  "reviewer_id": "企业微信用户 ID"
              {"\n"}{"}"}
            </code>
          </aside>
        </div>
      </section>
    </div>
  );
}
