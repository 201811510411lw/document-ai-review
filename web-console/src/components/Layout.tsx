import { ClipboardCheck, FileSearch, ListFilter, Menu, ShieldCheck, UserRound } from "lucide-react";
import type { ReactNode } from "react";

export function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="工作台导航">
        <div className="brand">
          <ShieldCheck size={22} aria-hidden="true" />
          <span>Document AI</span>
        </div>
        <nav>
          <a className="nav-item nav-item-active" href="/reviews">
            <ClipboardCheck size={18} aria-hidden="true" />
            <span>营业执照审核</span>
          </a>
          <span className="nav-item nav-item-muted">
            <FileSearch size={18} aria-hidden="true" />
            <span>其他单证</span>
          </span>
        </nav>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <button className="icon-button" aria-label="打开导航">
            <Menu size={20} />
          </button>
          <div>
            <strong>营业执照审核结果工作台</strong>
            <span>浏览器预览版</span>
          </div>
        </header>
        <main className="content">{children}</main>
      </div>
      <nav className="mobile-bottom-nav" aria-label="移动端底部导航">
        <a className="mobile-bottom-nav-active" href="/reviews">
          <ClipboardCheck size={18} aria-hidden="true" />
          <span>列表</span>
        </a>
        <a href="/reviews#filters">
          <ListFilter size={18} aria-hidden="true" />
          <span>筛选</span>
        </a>
        <span className="mobile-bottom-nav-disabled" aria-disabled="true" title="占位功能，暂未开放">
          <UserRound size={18} aria-hidden="true" />
          <span>我的</span>
          <small>暂未开放</small>
        </span>
      </nav>
    </div>
  );
}
