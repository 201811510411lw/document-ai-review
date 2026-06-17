import { useEffect, useMemo, useState } from "react";
import { ArrowRight, DatabaseZap, RotateCcw } from "lucide-react";
import { reviewClient } from "../api/client";
import type { ListReviewsResponse, ReviewFilters, ReviewRow } from "../api/reviews";
import { EmptyState, ErrorState, LoadingState } from "../components/EmptyState";
import { MetricCard } from "../components/MetricCard";
import { RiskBadge, StatusBadge } from "../components/Badge";

const defaultFilters: ReviewFilters = {
  businessName: "",
  creditCode: "",
  documentType: "ALL",
  riskLevel: "ALL",
  reviewStatus: "ALL",
  dateRange: "week",
  page: 1,
  pageSize: 3
};

export function ReviewsPage({ qcView = false }: { qcView?: boolean }) {
  const [filters, setFilters] = useState<ReviewFilters>(defaultFilters);
  const [data, setData] = useState<ListReviewsResponse | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "empty" | "error">("loading");
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [srmStatus, setSrmStatus] = useState<"idle" | "submitting" | "success" | "error">("idle");

  useEffect(() => {
    let mounted = true;
    if (data) {
      setIsRefreshing(true);
    } else {
      setStatus("loading");
    }

    const listReviews = qcView ? reviewClient.listQcReviews : reviewClient.listReviews;
    listReviews(filters)
      .then((response) => {
        if (!mounted) {
          return;
        }
        setData(response);
        setStatus(response.items.length === 0 ? "empty" : "ready");
        setIsRefreshing(false);
      })
      .catch(() => {
        if (mounted) {
          setIsRefreshing(false);
          setStatus("error");
        }
      });

    return () => {
      mounted = false;
    };
  }, [filters, refreshKey, qcView]);

  const metrics = useMemo(
    () =>
      data?.metrics ?? {
        todayReviewed: 0,
        pendingManualReview: 0,
        highRisk: 0,
        passRate: 0
      },
    [data]
  );

  async function createFromSrm() {
    if (srmStatus === "submitting") {
      return;
    }
    setSrmStatus("submitting");
    try {
      const created = await reviewClient.createReviewFromSrm();
      setData((current) =>
        current
          ? {
              ...current,
              items: [created, ...current.items].slice(0, current.pageSize),
              total: current.total + 1,
              totalPages: Math.max(1, Math.ceil((current.total + 1) / current.pageSize)),
              metrics: {
                ...current.metrics,
                todayReviewed: current.metrics.todayReviewed + 1,
                passRate: Math.round(
                  ((current.items.filter((item) => item.reviewStatus === "REVIEWED").length +
                    (created.reviewStatus === "REVIEWED" ? 1 : 0)) /
                    (current.total + 1)) *
                    100
                )
              }
            }
          : current
      );
      setSrmStatus("success");
    } catch {
      setSrmStatus("error");
    }
  }

  return (
    <div className="page-stack">
      <section className="page-heading">
        <div>
          <p>营业执照</p>
          <h1>{qcView ? "QC 审核结果列表" : "审核结果列表"}</h1>
        </div>
        <div className="heading-actions">
          {!qcView && (
            <button
              className="primary-button"
              type="button"
              onClick={createFromSrm}
              disabled={srmStatus === "submitting"}
            >
              <DatabaseZap size={16} aria-hidden="true" />
              {srmStatus === "submitting" ? "拉取中" : "从 SRM 拉取审核"}
            </button>
          )}
          <button
            className="secondary-button"
            type="button"
            onClick={() => setRefreshKey((current) => current + 1)}
          >
            <RotateCcw size={16} aria-hidden="true" />
            刷新数据
          </button>
        </div>
      </section>

      {srmStatus === "success" && (
        <div className="inline-notice inline-notice-success">已从 SRM 来源记录创建审核任务。</div>
      )}
      {srmStatus === "error" && (
        <div className="inline-notice inline-notice-error">SRM 来源记录审核创建失败，请检查 API 服务状态。</div>
      )}

      <section className="metrics-grid" aria-label="审核统计">
        <MetricCard label="今日审核" value={metrics.todayReviewed} hint="mock 数据口径" />
        <MetricCard
          label="需人工复核"
          value={metrics.pendingManualReview}
          hint="包含待复核状态"
        />
        <MetricCard label="高风险" value={metrics.highRisk} hint="优先处理" />
        <MetricCard label="通过率" value={`${metrics.passRate}%`} hint="已审核 / 当前结果" />
      </section>

      <section className="filter-panel" aria-label="筛选审核结果" id="filters">
        <label>
          <span>主体名称</span>
          <input
            value={filters.businessName}
            onChange={(event) =>
              setFilters((current) => ({
                ...current,
                businessName: event.target.value,
                page: 1
              }))
            }
            placeholder="输入企业名称"
          />
        </label>
        <label>
          <span>统一社会信用代码</span>
          <input
            value={filters.creditCode}
            onChange={(event) =>
              setFilters((current) => ({
                ...current,
                creditCode: event.target.value,
                page: 1
              }))
            }
            placeholder="输入信用代码"
          />
        </label>
        {qcView && (
          <label>
            <span>证照类型</span>
            <select
              value={filters.documentType}
              onChange={(event) =>
                setFilters((current) => ({
                  ...current,
                  documentType: event.target.value as ReviewFilters["documentType"],
                  page: 1
                }))
              }
            >
              <option value="ALL">全部</option>
              <option value="business_license">营业执照</option>
              <option value="food_license">食品经营许可证</option>
              <option value="product_report">产品报告</option>
              <option value="tobacco_license">烟草证</option>
              <option value="business_tobacco_consistency">营业执照与烟草证一致性</option>
            </select>
          </label>
        )}
        <label>
          <span>风险等级</span>
          <select
            value={filters.riskLevel}
            onChange={(event) =>
              setFilters((current) => ({
                ...current,
                riskLevel: event.target.value as ReviewFilters["riskLevel"],
                page: 1
              }))
            }
          >
            <option value="ALL">全部</option>
            <option value="HIGH">高风险</option>
            <option value="MEDIUM">中风险</option>
            <option value="LOW">低风险</option>
            <option value="NONE">无风险</option>
          </select>
        </label>
        <label>
          <span>审核状态</span>
          <select
            value={filters.reviewStatus}
            onChange={(event) =>
              setFilters((current) => ({
                ...current,
                reviewStatus: event.target.value as ReviewFilters["reviewStatus"],
                page: 1
              }))
            }
          >
            <option value="ALL">全部</option>
            <option value="REVIEWED">已审核</option>
            <option value="PENDING_MANUAL_REVIEW">待人工复核</option>
            <option value="MANUAL_REVIEWED">人工已复核</option>
            <option value="FAILED">审核失败</option>
          </select>
        </label>
        <label>
          <span>时间范围</span>
          <select
            value={filters.dateRange}
            onChange={(event) =>
              setFilters((current) => ({
                ...current,
                dateRange: event.target.value as ReviewFilters["dateRange"],
                page: 1
              }))
            }
          >
            <option value="today">今日</option>
            <option value="week">本周</option>
            <option value="month">本月</option>
            <option value="all">全部</option>
          </select>
        </label>
        <button
          className="secondary-button"
          type="button"
          onClick={() => setFilters(defaultFilters)}
        >
          <RotateCcw size={16} aria-hidden="true" />
          重置
        </button>
      </section>

      {isRefreshing && (
        <div className="inline-notice">正在刷新审核结果，列表会自动更新。</div>
      )}
      {status === "loading" && <LoadingState />}
      {status === "error" && <ErrorState message="审核结果查询失败，请检查 API 服务状态。" />}
      {status === "empty" && (
        <EmptyState title="没有匹配的审核结果" message="调整筛选条件后再查看。" />
      )}
      {status === "ready" && data && (
        <ReviewTable
          rows={data.items}
          page={data.page}
          pageSize={data.pageSize}
          total={data.total}
          totalPages={data.totalPages}
          qcView={qcView}
          onPageChange={(page) => setFilters((current) => ({ ...current, page }))}
        />
      )}
    </div>
  );
}

function ReviewTable({
  rows,
  page,
  pageSize,
  total,
  totalPages,
  qcView,
  onPageChange
}: {
  rows: ReviewRow[];
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
  qcView: boolean;
  onPageChange: (page: number) => void;
}) {
  const detailPath = (taskId: string) =>
    qcView ? `/qc/reviews/${taskId}` : `/reviews/${taskId}`;

  return (
    <section className="table-panel">
      <div className="table-panel-header">
        <h2>审核结果列表</h2>
        <span>
          共 {total} 条，当前第 {page} / {totalPages} 页
        </span>
      </div>
      <table>
        <thead>
          <tr>
            <th>主体名称</th>
            <th>统一社会信用代码</th>
            <th>审核状态</th>
            <th>风险等级</th>
            <th>复核状态</th>
            <th>审核时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.taskId}>
              <td>
                <strong>{row.businessName}</strong>
                <small>{row.taskId}</small>
                <small>{row.sourceRecordId}</small>
              </td>
              <td>{row.creditCode}</td>
              <td>
                <StatusBadge status={row.reviewStatus} label={row.reviewStatusLabel} />
              </td>
              <td>
                <RiskBadge risk={row.riskLevel} label={row.riskLevelLabel} />
              </td>
              <td>{manualReviewStateLabel(row)}</td>
              <td>{formatTime(row.reviewedAt)}</td>
              <td>
                <a className="table-action" href={detailPath(row.taskId)}>
                  详情
                  <ArrowRight size={15} aria-hidden="true" />
                </a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="mobile-card-list">
        {rows.map((row) => (
          <article className="review-card" key={row.taskId}>
            <div className="review-card-header">
              <strong>{row.businessName}</strong>
              <RiskBadge risk={row.riskLevel} label={row.riskLevelLabel} />
            </div>
            <dl>
              <div>
                <dt>统一社会信用代码</dt>
                <dd>{row.creditCode}</dd>
              </div>
              <div>
                <dt>SRM 记录 ID</dt>
                <dd>{row.sourceRecordId}</dd>
              </div>
              <div>
                <dt>审核状态</dt>
                <dd>
                  <StatusBadge status={row.reviewStatus} label={row.reviewStatusLabel} />
                </dd>
              </div>
              <div>
                <dt>复核状态</dt>
                <dd>{manualReviewStateLabel(row)}</dd>
              </div>
              <div>
                <dt>审核时间</dt>
                <dd>{formatTime(row.reviewedAt)}</dd>
              </div>
            </dl>
            <a className="primary-link" href={detailPath(row.taskId)}>
              查看详情
              <ArrowRight size={15} aria-hidden="true" />
            </a>
          </article>
        ))}
      </div>

      <div className="pagination-bar" aria-label="审核结果分页">
        <span>
          每页 {pageSize} 条，当前展示 {rows.length} 条
        </span>
        <div>
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => onPageChange(page - 1)}
          >
            上一页
          </button>
          <button
            type="button"
            disabled={page >= totalPages}
            onClick={() => onPageChange(page + 1)}
          >
            下一页
          </button>
        </div>
      </div>
    </section>
  );
}

function manualReviewStateLabel(row: ReviewRow) {
  if (row.reviewStatus === "MANUAL_REVIEWED") {
    return "已复核";
  }
  if (row.needsManualReview || row.reviewStatus === "PENDING_MANUAL_REVIEW") {
    return "待复核";
  }
  return "不需要";
}

function formatTime(value: string) {
  return value.replace("T", " ").replace("+08:00", "");
}
