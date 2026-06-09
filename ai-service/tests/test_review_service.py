from datetime import datetime, timezone

from app.models import ReviewInput, ReviewInputContext, ReviewResult
from app.services import review_service as review_service_module
from app.services.review_service import ReviewService


def test_review_service_gets_food_license_skill_from_registry_and_calls_review(monkeypatch):
    calls = []

    class StubSkill:
        name = "food_license"
        version = "v1"
        ruleset_version = "food-license-rules-v1"
        supported_document_types = ("food_license",)

        def supports(self, input_context: ReviewInputContext) -> bool:
            return True

        def review(self, input_context: ReviewInputContext) -> ReviewResult:
            calls.append(input_context)
            now = datetime(2026, 6, 8, 14, 30, tzinfo=timezone.utc)
            return ReviewResult.model_validate(
                {
                    "task_id": input_context.task_id,
                    "skill_name": self.name,
                    "skill_version": self.version,
                    "ruleset_version": self.ruleset_version,
                    "document_type": "food_license",
                    "status": "REVIEWED",
                    "risk_level": "NONE",
                    "needs_manual_review": False,
                    "rule_results": [],
                    "summary": "stub",
                    "manual_review": {"status": "NOT_REQUIRED"},
                    "audit_events": [],
                    "created_at": now,
                    "updated_at": now,
                    "skill_result": {},
                }
            )

    class StubRegistry:
        def __init__(self) -> None:
            self.requested_skill_names = []

        def get(self, skill_name: str):
            self.requested_skill_names.append(skill_name)
            return StubSkill()

    registry = StubRegistry()
    monkeypatch.setattr(review_service_module, "skill_registry", registry)

    result = ReviewService().review_food_license(
        ReviewInput(
            ocr_text="食品经营许可证",
            supplier_name="成都示例食品有限公司",
            supplier_credit_code="91510100MA00000000",
        )
    )

    assert registry.requested_skill_names == ["food_license"]
    assert len(calls) == 1
    assert calls[0].skill_name == "food_license"
    assert calls[0].input.supplier_credit_code == "91510100MA00000000"
    assert result.skill_name == "food_license"


def test_review_service_review_can_call_skill_by_name(monkeypatch):
    calls = []

    class StubSkill:
        name = "contract_review"
        version = "v1"
        ruleset_version = "contract-rules-v1-placeholder"
        supported_document_types = ("contract_review",)

        def supports(self, input_context: ReviewInputContext) -> bool:
            return True

        def review(self, input_context: ReviewInputContext) -> ReviewResult:
            calls.append(input_context)
            now = datetime(2026, 6, 8, 14, 30, tzinfo=timezone.utc)
            return ReviewResult.model_validate(
                {
                    "task_id": input_context.task_id,
                    "skill_name": self.name,
                    "skill_version": self.version,
                    "ruleset_version": self.ruleset_version,
                    "document_type": "contract_review",
                    "status": "PENDING_MANUAL_REVIEW",
                    "risk_level": "MEDIUM",
                    "needs_manual_review": True,
                    "rule_results": [],
                    "summary": "stub",
                    "manual_review": {
                        "status": "PENDING",
                        "reasons": ["stub not implemented"],
                    },
                    "audit_events": [],
                    "created_at": now,
                    "updated_at": now,
                    "skill_result": {"implementation_status": "not_implemented"},
                }
            )

    class StubRegistry:
        def __init__(self) -> None:
            self.requested_skill_names = []

        def get(self, skill_name: str):
            self.requested_skill_names.append(skill_name)
            return StubSkill()

    registry = StubRegistry()
    monkeypatch.setattr(review_service_module, "skill_registry", registry)

    result = ReviewService().review(
        ReviewInput(
            ocr_text="合同文本",
            supplier_name="成都示例食品有限公司",
            supplier_credit_code="91510100MA00000000",
            declared_document_type="contract_review",
        ),
        skill_name="contract_review",
    )

    assert registry.requested_skill_names == ["contract_review"]
    assert len(calls) == 1
    assert calls[0].skill_name == "contract_review"
    assert result.skill_name == "contract_review"


def test_review_service_review_can_select_skill(monkeypatch):
    calls = []

    class StubSkill:
        name = "contract_review"
        version = "v1"
        ruleset_version = "contract-rules-v1-placeholder"
        supported_document_types = ("contract_review",)

        def supports(self, input_context: ReviewInputContext) -> bool:
            return input_context.input.declared_document_type == "contract_review"

        def review(self, input_context: ReviewInputContext) -> ReviewResult:
            calls.append(input_context)
            now = datetime(2026, 6, 8, 14, 30, tzinfo=timezone.utc)
            return ReviewResult.model_validate(
                {
                    "task_id": input_context.task_id,
                    "skill_name": self.name,
                    "skill_version": self.version,
                    "ruleset_version": self.ruleset_version,
                    "document_type": "contract_review",
                    "status": "PENDING_MANUAL_REVIEW",
                    "risk_level": "MEDIUM",
                    "needs_manual_review": True,
                    "rule_results": [],
                    "summary": "stub",
                    "manual_review": {"status": "PENDING"},
                    "audit_events": [],
                    "created_at": now,
                    "updated_at": now,
                    "skill_result": {"implementation_status": "not_implemented"},
                }
            )

    class StubRegistry:
        def __init__(self) -> None:
            self.select_calls = []

        def select(self, input_context: ReviewInputContext):
            self.select_calls.append(input_context)
            return StubSkill()

    registry = StubRegistry()
    monkeypatch.setattr(review_service_module, "skill_registry", registry)

    result = ReviewService().review(
        ReviewInput(
            ocr_text="合同文本",
            supplier_name="成都示例食品有限公司",
            supplier_credit_code="91510100MA00000000",
            declared_document_type="contract_review",
        )
    )

    assert len(registry.select_calls) == 1
    assert registry.select_calls[0].skill_name == ""
    assert len(calls) == 1
    assert calls[0].skill_name == "contract_review"
    assert result.skill_name == "contract_review"
