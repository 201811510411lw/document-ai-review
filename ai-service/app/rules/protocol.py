from typing import Any, Protocol

from app.models import RiskLevel


class Rule(Protocol):
    code: str
    name: str
    risk_level_on_failure: RiskLevel

    def evaluate(self, context: Any):
        ...
