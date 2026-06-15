import { httpReviewClient } from "./httpClient";
import { mockReviewClient } from "./mockClient";
import type { ReviewClient } from "./reviews";

export const reviewClient: ReviewClient =
  import.meta.env.VITE_USE_MOCK_API === "true" || import.meta.env.MODE === "test"
    ? mockReviewClient
    : httpReviewClient;
