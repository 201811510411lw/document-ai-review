import { AlertCircle, Inbox } from "lucide-react";

export function EmptyState({ title, message }: { title: string; message: string }) {
  return (
    <div className="state-panel">
      <Inbox size={28} aria-hidden="true" />
      <strong>{title}</strong>
      <span>{message}</span>
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="state-panel state-panel-error" role="alert">
      <AlertCircle size={28} aria-hidden="true" />
      <strong>数据加载失败</strong>
      <span>{message}</span>
    </div>
  );
}

export function LoadingState() {
  return (
    <div className="state-panel" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <strong>正在加载审核结果</strong>
    </div>
  );
}
