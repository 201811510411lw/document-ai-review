import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

function setPath(path: string) {
  window.history.pushState({}, "", path);
}

function setSession() {
  window.localStorage.setItem(
    "document-ai-review.web-console.session",
    JSON.stringify({
      accessToken: "test-token",
      expiresAt: Math.floor(Date.now() / 1000) + 3600,
      user: {username: "reviewer", displayName: "审核员"}
    })
  );
}

function clearSession() {
  window.localStorage.removeItem("document-ai-review.web-console.session");
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  clearSession();
  setPath("/reviews");
});

describe("business license review workbench", () => {
  it("renders the review list with metrics and rows", async () => {
    setSession();
    setPath("/reviews");
    render(<App />);

    expect(screen.getByText("审核结果列表")).toBeInTheDocument();
    expect(screen.getByText("今日审核")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getAllByText("上海云岚供应链管理有限公司").length).toBeGreaterThan(0);
    }, { timeout: 2000 });

    expect(screen.getAllByText("高风险").length).toBeGreaterThan(0);
    expect(screen.getAllByText("详情").length).toBeGreaterThan(0);
  });

  it("filters reviews by date range and supports pagination", async () => {
    const user = userEvent.setup();
    setSession();
    setPath("/reviews");
    render(<App />);

    await waitFor(() => {
      expect(screen.getAllByText("上海云岚供应链管理有限公司").length).toBeGreaterThan(0);
    });

    await user.selectOptions(screen.getByLabelText("时间范围"), "today");

    await waitFor(() => {
      expect(screen.getByText(/共 2 条/)).toBeInTheDocument();
    });

    expect(screen.queryByText("杭州简禾食品科技有限公司")).not.toBeInTheDocument();
    expect(screen.getAllByText("上海云岚供应链管理有限公司").length).toBeGreaterThan(0);

    await user.selectOptions(screen.getByLabelText("时间范围"), "all");

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "下一页" })).toBeEnabled();
    });

    await user.click(screen.getByRole("button", { name: "下一页" }));

    await waitFor(() => {
      expect(screen.getAllByText("深圳岭南电子商务有限公司").length).toBeGreaterThan(0);
    });
  });

  it("resets immediate filters back to defaults and the first page", async () => {
    const user = userEvent.setup();
    setSession();
    setPath("/reviews");
    render(<App />);

    await waitFor(() => {
      expect(screen.getAllByText("上海云岚供应链管理有限公司").length).toBeGreaterThan(0);
    });

    await user.selectOptions(screen.getByLabelText("时间范围"), "all");
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "下一页" })).toBeEnabled();
    });
    await user.click(screen.getByRole("button", { name: "下一页" }));
    await waitFor(() => {
      expect(screen.getAllByText("深圳岭南电子商务有限公司").length).toBeGreaterThan(0);
    });

    await user.selectOptions(screen.getByLabelText("风险等级"), "HIGH");
    await user.click(screen.getByRole("button", { name: "重置" }));

    await waitFor(() => {
      expect(screen.getByText(/当前第 1 \/ 2 页/)).toBeInTheDocument();
    });
    expect(screen.getByLabelText("时间范围")).toHaveValue("week");
    expect(screen.getByLabelText("风险等级")).toHaveValue("ALL");
    expect(screen.getAllByText("上海云岚供应链管理有限公司").length).toBeGreaterThan(0);
  });

  it("refreshes the review list through the review client boundary", async () => {
    const user = userEvent.setup();
    setSession();
    setPath("/reviews");
    render(<App />);

    await waitFor(() => {
      expect(screen.getAllByText("上海云岚供应链管理有限公司").length).toBeGreaterThan(0);
    });

    await user.click(screen.getByRole("button", { name: /刷新数据/ }));

    await waitFor(() => {
      expect(screen.getAllByText("上海云岚供应链管理有限公司").length).toBeGreaterThan(0);
    });
  });

  it("renders the detail page with extracted fields and failed rules", async () => {
    setSession();
    setPath("/reviews/blr-20260615-0002");
    render(<App />);

    await waitFor(() => {
      expect(screen.getAllByText("上海云岚供应链管理有限公司").length).toBeGreaterThan(0);
    });

    expect(screen.getByText("字段抽取结果")).toBeInTheDocument();
    expect(screen.getByText("规则校验结果")).toBeInTheDocument();
    expect(screen.getByText("统一社会信用代码不一致")).toBeInTheDocument();
    expect(screen.getByText("审核详情")).toHaveAttribute("href", "/reviews");
    expect(screen.getByText("查看复核预留页")).toBeInTheDocument();
  });

  it("renders the manual review placeholder without enabling submit actions", async () => {
    setSession();
    setPath("/reviews/blr-20260615-0002/manual-review");
    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("人工复核动作预留")).toBeInTheDocument();
    });

    expect(screen.getByText("后续 API 契约预留")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "确认通过" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "驳回" })).toBeDisabled();
  });

  it("renders real mobile bottom navigation entries", async () => {
    setSession();
    setPath("/reviews");
    render(<App />);

    const mobileNav = screen.getByRole("navigation", { name: "移动端底部导航" });
    expect(mobileNav).toBeInTheDocument();
    expect(within(mobileNav).getByText("筛选")).toBeInTheDocument();
    expect(within(mobileNav).getByText("我的")).toBeInTheDocument();
    expect(within(mobileNav).getByText("暂未开放")).toBeInTheDocument();
    expect(within(mobileNav).getByTitle("占位功能，暂未开放")).toHaveAttribute(
      "aria-disabled",
      "true"
    );
  });

  it("redirects anonymous users to the login page", async () => {
    setPath("/reviews");
    render(<App />);

    expect(screen.getByText("营业执照审核工作台")).toBeInTheDocument();
    expect(window.location.pathname).toBe("/login");
    expect(window.location.search).toBe("?next=%2Freviews");
  });

  it("logs in and returns to the requested route", async () => {
    const user = userEvent.setup();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          access_token: "login-token",
          token_type: "bearer",
          expires_at: Math.floor(Date.now() / 1000) + 3600,
          user: {username: "reviewer", display_name: "审核员"}
        }),
        {status: 200}
      )
    );
    setPath("/login?next=/reviews");
    render(<App />);

    await user.click(screen.getByRole("button", {name: "登录"}));

    await waitFor(() => {
      expect(window.localStorage.getItem("document-ai-review.web-console.session")).toContain(
        "login-token"
      );
    });
    expect(window.location.pathname).toBe("/reviews");
  });

  it("shows a login error for invalid credentials", async () => {
    const user = userEvent.setup();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("", {status: 401}));
    setPath("/login");
    render(<App />);

    await user.clear(screen.getByLabelText("密码"));
    await user.type(screen.getByLabelText("密码"), "wrong");
    await user.click(screen.getByRole("button", {name: "登录"}));

    await waitFor(() => {
      expect(screen.getByText("账号或密码不正确。")).toBeInTheDocument();
    });
  });
});
