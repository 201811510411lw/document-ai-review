from typing import Protocol

from app.models import ReviewInputContext, ReviewResult


class UseCase(Protocol):
    name: str
    version: str
    ruleset_version: str
    supported_document_types: tuple[str, ...]

    def supports(self, input_context: ReviewInputContext) -> bool:
        ...

    def review(self, input_context: ReviewInputContext) -> ReviewResult:
        ...
