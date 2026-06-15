import { useEffect, useState } from "react";
import { Layout } from "./components/Layout";
import { loadSession } from "./api/auth";
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
  const manualMatch = path.match(/^\/reviews\/([^/]+)\/manual-review$/);
  const detailMatch = path.match(/^\/reviews\/([^/]+)$/);

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

  useEffect(() => {
    const refreshRoute = () => setNavigationVersion((version) => version + 1);
    window.addEventListener(NAVIGATION_EVENT, refreshRoute);
    window.addEventListener("popstate", refreshRoute);
    return () => {
      window.removeEventListener(NAVIGATION_EVENT, refreshRoute);
      window.removeEventListener("popstate", refreshRoute);
    };
  }, []);

  const route = currentRoute();
  const session = loadSession();

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
      ) : route.page === "detail" ? (
        <ReviewDetailPage taskId={route.taskId} />
      ) : (
        <ReviewsPage />
      )}
    </Layout>
  );
}
