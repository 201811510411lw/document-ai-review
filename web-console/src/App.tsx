import { useEffect, useState } from "react";
import { Layout } from "./components/Layout";
import { loadCurrentSession, loadSession, type AuthSession } from "./api/auth";
import { navigateTo, NAVIGATION_EVENT } from "./navigation";
import { LoginPage } from "./pages/LoginPage";
import { ManualReviewPlaceholderPage } from "./pages/ManualReviewPlaceholderPage";
import { ReviewDetailPage } from "./pages/ReviewDetailPage";
import { ReviewsPage } from "./pages/ReviewsPage";

function currentRoute() {
  const path = window.location.pathname;
  if (path === "/login") {
    return { page: "login" as const };
  }
  const qcDetailMatch = path.match(/^\/qc\/reviews\/([^/]+)$/);
  const manualMatch = path.match(/^\/reviews\/([^/]+)\/manual-review$/);
  const detailMatch = path.match(/^\/reviews\/([^/]+)$/);

  if (path === "/qc/reviews") {
    return { page: "qc-list" as const };
  }

  if (qcDetailMatch) {
    return { page: "qc-detail" as const, taskId: qcDetailMatch[1] };
  }

  if (manualMatch) {
    return { page: "manual" as const, taskId: manualMatch[1] };
  }

  if (detailMatch) {
    return { page: "detail" as const, taskId: detailMatch[1] };
  }

  return { page: "list" as const };
}

export function App() {
  const [, setNavigationVersion] = useState(0);
  const [cookieSession, setCookieSession] = useState<AuthSession | null>(loadSession());
  const [sessionChecked, setSessionChecked] = useState(false);

  useEffect(() => {
    const refreshRoute = () => setNavigationVersion((version) => version + 1);
    window.addEventListener(NAVIGATION_EVENT, refreshRoute);
    window.addEventListener("popstate", refreshRoute);
    return () => {
      window.removeEventListener(NAVIGATION_EVENT, refreshRoute);
      window.removeEventListener("popstate", refreshRoute);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    loadCurrentSession().then((session) => {
      if (!cancelled) {
        setCookieSession(session);
        setSessionChecked(true);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const route = currentRoute();
  const session = cookieSession ?? loadSession();

  if (route.page === "login") {
    return <LoginPage />;
  }

  if (!session) {
    navigateTo(`/login?next=${encodeURIComponent(window.location.pathname)}`, { replace: true });
    return <LoginPage />;
  }

  return (
    <Layout session={session}>
      {route.page === "manual" ? (
        <ManualReviewPlaceholderPage taskId={route.taskId} />
      ) : route.page === "qc-detail" ? (
        <ReviewDetailPage taskId={route.taskId} qcView />
      ) : route.page === "detail" ? (
        <ReviewDetailPage taskId={route.taskId} />
      ) : route.page === "qc-list" ? (
        <ReviewsPage qcView />
      ) : (
        <ReviewsPage />
      )}
    </Layout>
  );
}
