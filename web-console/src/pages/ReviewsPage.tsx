import { useEffect, useMemo, useState } from "react";
import { ArrowRight, RotateCcw, Search } from "lucide-react";
import { mockReviewClient } from "../api/mockClient";
import type { ListReviewsResponse, ReviewFilters, ReviewRow } from "../api/reviews";
import { EmptyState, ErrorState, LoadingState } from "../components/EmptyState";
import { MetricCard } from "../components/MetricCard";
import { RiskBadge, StatusBadge } from "../components/Badge";

const defaultFilters: ReviewFilters = {
  businessName: "",
  creditCode: "",
  riskLevel: "ALL",
  reviewStatus: "ALL",
  dateRange: "week",
  page: 1,
  pageSize: 3
};

export function ReviewsPage() {
  const [filters, setFilters] = useState<ReviewFilters>(defaultFilters);
  const [data, setData] = useState<ListReviewsResponse | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "empty" | "error">("loading");
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let mounted = true;
    setStatus("loading");

    mockReviewClient
      .listReviews(filters)
      .then((response) => {
        if (!mounted) {
          return;
        }
        setData(response);
        setStatus(response.items.length === 0 ? "empty" : "ready");
      })
      .catch(() => {
        if (mounted) {
          setStatus("error");
        }
      });

    return () => {
      mounted = false;
    };
  }, [filters, refreshKey]);

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

  return (
    <div className="page-stack">
      <section className="page-heading">
        <div>
          <p>营业执照</p>
          <h1>审核结果列表</h1>
        </div>
        <button
          className="secondary-button"
          type="button"
          onClick={() => setRefreshKey((current) => current + 1)}
        >
          <RotateCcw size={16} aria-hidden="true" />
          刷新 mock 数据
        </button>
      </section>

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
        <button className="primary-button" type="button">
          <Search size={16} aria-hidden="true" />
          筛选
        </button>
      </section>

      {status === "loading" && <LoadingState />}
      {status === "error" && <ErrorState message="mock client 返回异常，请检查本地前端状态。" />}
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
  onPageChange
}: {
  rows: ReviewRow[];
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}) {
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
            <th>人工复核</th>
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
              </td>
              <td>{row.creditCode}</td>
              <td>
                <StatusBadge status={row.reviewStatus} label={row.reviewStatusLabel} />
              </td>
              <td>
                <RiskBadge risk={row.riskLevel} label={row.riskLevelLabel} />
              </td>
              <td>{row.needsManualReview ? "需要" : "不需要"}</td>
              <td>{formatTime(row.reviewedAt)}</td>
              <td>
                <a className="table-action" href={`/reviews/${row.taskId}`}>
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
                <dt>审核状态</dt>
                <dd>
                  <StatusBadge status={row.reviewStatus} label={row.reviewStatusLabel} />
                </dd>
              </div>
              <div>
                <dt>人工复核</dt>
                <dd>{row.needsManualReview ? "需要" : "不需要"}</dd>
              </div>
              <div>
                <dt>审核时间</dt>
                <dd>{formatTime(row.reviewedAt)}</dd>
              </div>
            </dl>
            <a className="primary-link" href={`/reviews/${row.taskId}`}>
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

function formatTime(value: string) {
  return value.replace("T", " ").replace("+08:00", "");
}
