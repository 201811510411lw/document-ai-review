from dataclasses import dataclass, field
from typing import Any

from app.models import ReviewInputContext


@dataclass(frozen=True)
class RuleContext:
    input_context: ReviewInputContext
    facts: dict[str, Any] = field(default_factory=dict)
