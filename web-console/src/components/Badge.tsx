import type { RiskLevel, ReviewStatus, RuleState } from "../api/reviews";
import type { ReactNode } from "react";

interface BadgeProps {
  tone: "neutral" | "success" | "warning" | "danger" | "info";
  children: ReactNode;
}

export function Badge({ tone, children }: BadgeProps) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

export function StatusBadge({ status, label }: { status: ReviewStatus; label: string }) {
  const toneByStatus: Record<ReviewStatus, BadgeProps["tone"]> = {
    REVIEWED: "success",
    PENDING_MANUAL_REVIEW: "warning",
    MANUAL_REVIEWED: "info",
    FAILED: "danger"
  };

  return <Badge tone={toneByStatus[status]}>{label}</Badge>;
}

export function RiskBadge({ risk, label }: { risk: RiskLevel; label: string }) {
  const toneByRisk: Record<RiskLevel, BadgeProps["tone"]> = {
    NONE: "success",
    LOW: "info",
    MEDIUM: "warning",
    HIGH: "danger"
  };

  return <Badge tone={toneByRisk[risk]}>{label}</Badge>;
}

export function RuleStateBadge({ state }: { state: RuleState }) {
  const config: Record<RuleState, { tone: BadgeProps["tone"]; label: string }> = {
    passed: { tone: "success", label: "通过" },
    failed: { tone: "danger", label: "失败" },
    manual_review: { tone: "warning", label: "需复核" }
  };

  return <Badge tone={config[state].tone}>{config[state].label}</Badge>;
}
