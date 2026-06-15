import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

function setPath(path: string) {
  window.history.pushState({}, "", path);
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  setPath("/reviews");
});

describe("business license review workbench", () => {
  it("renders the review list with metrics and rows", async () => {
    setPath("/reviews");
    render(<App />);

    expect(screen.getByText("审核结果列表")).toBeInTheDocument();
    expect(screen.getByText("今日审核")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getAllByText("上海云岚供应链管理有限公司").length).toBeGreaterThan(0);
    });

    expect(screen.getAllByText("高风险").length).toBeGreaterThan(0);
    expect(screen.getAllByText("详情").length).toBeGreaterThan(0);
  });

  it("renders the detail page with extracted fields and failed rules", async () => {
    setPath("/reviews/blr-20260615-0002");
    render(<App />);

    await waitFor(() => {
      expect(screen.getAllByText("上海云岚供应链管理有限公司").length).toBeGreaterThan(0);
    });

    expect(screen.getByText("字段抽取结果")).toBeInTheDocument();
    expect(screen.getByText("规则校验结果")).toBeInTheDocument();
    expect(screen.getByText("统一社会信用代码不一致")).toBeInTheDocument();
    expect(screen.getByText("查看复核预留页")).toBeInTheDocument();
  });

  it("renders the manual review placeholder without enabling submit actions", async () => {
    setPath("/reviews/blr-20260615-0002/manual-review");
    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("人工复核动作预留")).toBeInTheDocument();
    });

    expect(screen.getByText("后续 API 契约预留")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "确认通过" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "驳回" })).toBeDisabled();
  });
});
