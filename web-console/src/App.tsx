import { Layout } from "./components/Layout";
import { ManualReviewPlaceholderPage } from "./pages/ManualReviewPlaceholderPage";
import { ReviewDetailPage } from "./pages/ReviewDetailPage";
import { ReviewsPage } from "./pages/ReviewsPage";

function currentRoute() {
  const path = window.location.pathname;
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
  const route = currentRoute();

  return (
    <Layout>
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
