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
    expect(screen.getByRole("button", { name: "从 SRM 拉取审核" })).toBeInTheDocument();
    expect(screen.getAllByText("详情")[0].closest("a")).toHaveAttribute(
      "href",
      "/reviews/blr-20260615-0001"
    );
    expect(screen.getAllByText("查看详情")[0].closest("a")).toHaveAttribute(
      "href",
      "/reviews/blr-20260615-0001"
    );
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
      expect(screen.getByText(/共 3 条/)).toBeInTheDocument();
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

  it("shows completed manual reviews as reviewed instead of not required", async () => {
    const user = userEvent.setup();
    setSession();
    setPath("/reviews");
    render(<App />);

    await waitFor(() => {
      expect(screen.getAllByText("上海云岚供应链管理有限公司").length).toBeGreaterThan(0);
    });

    await user.selectOptions(screen.getByLabelText("审核状态"), "MANUAL_REVIEWED");

    await waitFor(() => {
      expect(screen.getAllByText("苏州复核完成商贸有限公司").length).toBeGreaterThan(0);
    });

    const row = screen
      .getAllByText("苏州复核完成商贸有限公司")
      .map((element) => element.closest("tr"))
      .find((element): element is HTMLTableRowElement => element !== null);
    expect(row).not.toBeNull();
    expect(within(row as HTMLTableRowElement).getByText("已复核")).toBeInTheDocument();
    expect(within(row as HTMLTableRowElement).queryByText("不需要")).not.toBeInTheDocument();
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

  it("creates a business license review from an SRM source record", async () => {
    const user = userEvent.setup();
    setSession();
    setPath("/reviews");
    render(<App />);

    await waitFor(() => {
      expect(screen.getAllByText("上海云岚供应链管理有限公司").length).toBeGreaterThan(0);
    });

    await user.click(screen.getByRole("button", { name: "从 SRM 拉取审核" }));

    await waitFor(() => {
      expect(screen.getByText("已从 SRM 来源记录创建营业执照审核任务。")).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getAllByText("SRM-CERT-NEW").length).toBeGreaterThan(0);
    });
  });

  it("renders the QC review list with document type filtering", async () => {
    const user = userEvent.setup();
    setSession();
    setPath("/qc/reviews");
    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("QC 审核结果列表")).toBeInTheDocument();
      expect(screen.getAllByText("上海云岚供应链管理有限公司").length).toBeGreaterThan(0);
    });
    expect(screen.queryByRole("button", { name: "从 SRM 拉取审核" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "拉取营业执照" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "拉取食品经营许可证" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "拉取食品生产许可证" })).toBeInTheDocument();
    expect(screen.getAllByText("详情")[0].closest("a")?.getAttribute("href")).toMatch(
      /^\/qc\/reviews\//
    );
    expect(screen.getAllByText("查看详情")[0].closest("a")?.getAttribute("href")).toMatch(
      /^\/qc\/reviews\//
    );

    await user.selectOptions(screen.getByLabelText("证照类型"), "business_license");

    await waitFor(() => {
      expect(screen.getByLabelText("证照类型")).toHaveValue("business_license");
      expect(screen.getAllByText("上海云岚供应链管理有限公司").length).toBeGreaterThan(0);
    });

    await user.selectOptions(screen.getByLabelText("证照类型"), "food_production_license");
    expect(screen.getByLabelText("证照类型")).toHaveValue("food_production_license");
  });

  it("creates food license and food production license reviews from SRM on the QC page", async () => {
    const user = userEvent.setup();
    setSession();
    setPath("/qc/reviews");
    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("QC 审核结果列表")).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "拉取营业执照" }));

    await waitFor(() => {
      expect(screen.getByText("已从 SRM 来源记录创建营业执照审核任务。")).toBeInTheDocument();
    });
    expect(screen.getAllByText("SRM-CERT-NEW").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "拉取食品经营许可证" }));

    await waitFor(() => {
      expect(screen.getByText("已从 SRM 来源记录创建食品经营许可证审核任务。")).toBeInTheDocument();
    });
    expect(screen.getAllByText("SRM-FOOD-LICENSE-NEW").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "拉取食品生产许可证" }));

    await waitFor(() => {
      expect(screen.getByText("已从 SRM 来源记录创建食品生产许可证审核任务。")).toBeInTheDocument();
    });
    expect(screen.getAllByText("SRM-FOOD-PRODUCTION-LICENSE-NEW").length).toBeGreaterThan(0);
  });

  it("renders the detail page with extracted fields and failed rules", async () => {
    setSession();
    setPath("/reviews/blr-20260615-0002");
    render(<App />);

    await waitFor(() => {
      expect(screen.getAllByText("上海云岚供应链管理有限公司").length).toBeGreaterThan(0);
    });

    expect(screen.getByText("字段抽取结果")).toBeInTheDocument();
    expect(screen.getByText("校验期望值")).toBeInTheDocument();
    expect(screen.getByText("规则校验结果")).toBeInTheDocument();
    expect(screen.getByText("统一社会信用代码与来源系统不一致，需要人工核对原件。")).toBeInTheDocument();
    expect(screen.getByText("统一社会信用代码不一致")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "打开原文件" })).toHaveAttribute(
      "href",
      "https://files.example.test/business-license-0002.png"
    );
    expect(screen.getByText("审计事件")).toBeInTheDocument();
    expect(screen.getByText("暂无审计事件。")).toBeInTheDocument();
    expect(screen.getByText("审核详情")).toHaveAttribute("href", "/reviews");
    expect(screen.getByText("进入人工复核")).toHaveAttribute(
      "href",
      "/reviews/blr-20260615-0002/manual-review"
    );
  });

  it("renders food production license detail with production-specific fields", async () => {
    setSession();
    setPath("/qc/reviews/qc-food-production-1");
    render(<App />);

    await waitFor(() => {
      expect(screen.getAllByText("长沙波浪食品有限公司").length).toBeGreaterThan(0);
    });

    expect(screen.getByText("食品生产许可证审核详情")).toBeInTheDocument();
    expect(screen.getAllByText("生产者名称").length).toBeGreaterThan(0);
    expect(screen.getAllByText("许可证编号").length).toBeGreaterThan(0);
    expect(screen.getAllByText("SC12443010505553").length).toBeGreaterThan(0);
    expect(screen.getAllByText("生产地址").length).toBeGreaterThan(0);
    expect(screen.queryByText("营业期限")).not.toBeInTheDocument();
  });

  it("renders manual review decision, comment, reviewer and audit details", async () => {
    setSession();
    setPath("/reviews/blr-20260615-0003");
    render(<App />);

    await waitFor(() => {
      expect(screen.getAllByText("苏州复核完成商贸有限公司").length).toBeGreaterThan(0);
    });

    expect(screen.getByText("复核结论")).toBeInTheDocument();
    expect(screen.getByText("通过")).toBeInTheDocument();
    expect(screen.getByText("复核备注")).toBeInTheDocument();
    expect(screen.getByText("已核对原件，确认通过。")).toBeInTheDocument();
    expect(screen.getByText("reviewer")).toBeInTheDocument();
    expect(screen.getByText("人工复核确认通过")).toBeInTheDocument();
    expect(screen.getByText("备注：已核对原件，确认通过。")).toBeInTheDocument();
  });

  it("submits a business license manual review decision and shows the audit trail", async () => {
    const user = userEvent.setup();
    setSession();
    setPath("/reviews/blr-20260615-0002/manual-review");
    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("人工复核")).toBeInTheDocument();
    });

    await user.selectOptions(screen.getByLabelText("复核结论"), "rejected");
    await user.clear(screen.getByLabelText("复核备注"));
    await user.type(screen.getByLabelText("复核备注"), "统一社会信用代码与原件不一致");
    await user.clear(screen.getByLabelText("复核人 ID"));
    await user.type(screen.getByLabelText("复核人 ID"), "wecom-reviewer-001");
    await user.click(screen.getByRole("button", { name: "提交复核结论" }));

    await waitFor(() => {
      expect(screen.getByText(/人工复核驳回/)).toBeInTheDocument();
    });
    expect(screen.getByText(/status: COMPLETED/)).toBeInTheDocument();
    expect(screen.getByText(/decision: rejected/)).toBeInTheDocument();
    expect(screen.getByText(/reviewer: wecom-reviewer-001/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "提交复核结论" })).toBeDisabled();
  });

  it("submits a QC manual review through the QC endpoint", async () => {
    const user = userEvent.setup();
    setSession();
    setPath("/qc/reviews/qc-task-1/manual-review");
    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("人工复核")).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText("复核备注"), "确认原件信息一致");
    await user.clear(screen.getByLabelText("复核人 ID"));
    await user.type(screen.getByLabelText("复核人 ID"), "qc-reviewer-001");
    await user.click(screen.getByRole("button", { name: "提交复核结论" }));

    await waitFor(() => {
      expect(screen.getByText(/人工复核确认通过/)).toBeInTheDocument();
    });
    expect(screen.getByText(/status: COMPLETED/)).toBeInTheDocument();
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
    expect(screen.getByRole("button", { name: "企业微信登录" })).toBeInTheDocument();
    expect(window.location.pathname).toBe("/login");
    expect(window.location.search).toBe("?next=%2Freviews");
  });

  it("starts enterprise WeChat OAuth automatically inside WeCom", async () => {
    Object.defineProperty(window.navigator, "userAgent", {
      configurable: true,
      value: "Mozilla/5.0 wxwork/4.1.0"
    });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes("/api/v1/auth/me")) {
        return new Response("", {status: 401});
      }
      if (url.includes("/api/v1/auth/sso/start")) {
        return new Response(JSON.stringify({redirect_url: "/oauth-redirect"}), {
          status: 200
        });
      }
      return new Response("", {status: 404});
    });
    setPath("/reviews");

    render(<App />);

    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([input]) => String(input).includes("mode=work"))).toBe(true);
    });
  });

  it("logs in and returns to the requested route", async () => {
    const user = userEvent.setup();
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes("/api/v1/auth/login")) {
        return new Response(
          JSON.stringify({
            access_token: "login-token",
            token_type: "bearer",
            expires_at: Math.floor(Date.now() / 1000) + 3600,
            user: {username: "reviewer", display_name: "审核员"}
          }),
          {status: 200}
        );
      }
      if (url.includes("/api/v1/auth/providers")) {
        return new Response(JSON.stringify({providers: []}), {status: 200});
      }
      return new Response("", {status: 401});
    });
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
