"""Persistence boundaries for review results."""

from app.repositories.review_result_repository import (
    MySQLReviewResultRepository,
    build_review_result_repository_from_env,
)

__all__ = ["MySQLReviewResultRepository", "build_review_result_repository_from_env"]
