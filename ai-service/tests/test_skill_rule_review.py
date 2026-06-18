from datetime import datetime

from app.tools.skill_rule_review import (
    OpenAiSkillRuleReviewAdapter,
    build_food_license_skill_rule_review_adapter,
    build_skill_rule_review_prompt,
    load_skill_text,
    parse_json_object,
)


def test_load_skill_text_reads_business_license_review_skill():
    content = load_skill_text("business-license-review")

    assert "name: business-license-review" in content
    assert "## 审核规则" in content


def test_parse_json_object_accepts_markdown_wrapped_json():
    parsed = parse_json_object(
        """
        ```json
        {"status": "REVIEWED", "needs_manual_review": false}
        ```
        """
    )

    assert parsed == {"status": "REVIEWED", "needs_manual_review": False}


def test_build_skill_rule_review_prompt_contains_skill_and_payload():
    prompt = build_skill_rule_review_prompt(
        skill_name="business-license-review",
        skill_text="## 审核规则\n- 主体名称一致则通过",
        review_payload={"extracted_fields": {"subject_name": "示例公司"}},
    )

    assert "business-license-review" in prompt
    assert "主体名称一致则通过" in prompt
    assert '"subject_name": "示例公司"' in prompt


def test_build_skill_rule_review_prompt_serializes_datetime_values():
    prompt = build_skill_rule_review_prompt(
        skill_name="business-license-review",
        skill_text="## 审核规则",
        review_payload={
            "source_evidence": {
                "source": {
                    "created": datetime(2026, 4, 1, 10, 7, 12),
                },
            },
        },
    )

    assert '"created": "2026-04-01 10:07:12"' in prompt


def test_openai_skill_rule_review_adapter_requires_skill_review_model(monkeypatch):
    monkeypatch.delenv("BUSINESS_LICENSE_SKILL_REVIEW_MODEL", raising=False)

    adapter = OpenAiSkillRuleReviewAdapter(
        model_env_key="BUSINESS_LICENSE_SKILL_REVIEW_MODEL",
    )
    result = adapter.review(
        skill_name="business-license-review",
        skill_text="## 审核规则",
        review_payload={},
    )

    assert result["metadata"]["error_code"] == "SKILL_RULE_REVIEW_MODEL_NOT_CONFIGURED"


def test_openai_skill_rule_review_adapter_prefers_skill_review_model(monkeypatch):
    monkeypatch.setenv("BUSINESS_LICENSE_SKILL_REVIEW_MODEL", "review-model")

    adapter = OpenAiSkillRuleReviewAdapter(
        model_env_key="BUSINESS_LICENSE_SKILL_REVIEW_MODEL",
    )

    assert adapter.model == "review-model"


def test_food_license_skill_rule_adapter_reuses_business_license_model(monkeypatch):
    monkeypatch.delenv("FOOD_LICENSE_SKILL_REVIEW_MODEL", raising=False)
    monkeypatch.setenv("BUSINESS_LICENSE_SKILL_REVIEW_MODEL", "qwen-flash")

    adapter = build_food_license_skill_rule_review_adapter()

    assert isinstance(adapter, OpenAiSkillRuleReviewAdapter)
    assert adapter.model == "qwen-flash"


def test_skill_rule_adapter_ignores_removed_fake_provider_setting(monkeypatch):
    monkeypatch.setenv("FOOD_LICENSE_SKILL_REVIEW_PROVIDER", "fake")
    monkeypatch.delenv("FOOD_LICENSE_SKILL_REVIEW_MODEL", raising=False)
    monkeypatch.setenv("BUSINESS_LICENSE_SKILL_REVIEW_MODEL", "qwen-flash")

    adapter = build_food_license_skill_rule_review_adapter()

    assert isinstance(adapter, OpenAiSkillRuleReviewAdapter)
    assert adapter.model == "qwen-flash"


def test_openai_skill_rule_review_adapter_retries_connection_errors(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    calls = {"count": 0}

    class StubMessage:
        content = (
            '{"status":"REVIEWED","risk_level":"LOW",'
            '"needs_manual_review":false,"summary":"通过","rule_results":[]}'
        )

    class StubChoice:
        message = StubMessage()

    class StubResponse:
        choices = [StubChoice()]

    class StubCompletions:
        def create(self, **kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                raise ConnectionError("temporary connection error")
            return StubResponse()

    class StubChat:
        completions = StubCompletions()

    class StubOpenAI:
        def __init__(self, **kwargs):
            self.chat = StubChat()

    import sys
    import types

    monkeypatch.setitem(
        sys.modules,
        "openai",
        types.SimpleNamespace(OpenAI=StubOpenAI),
    )
    adapter = OpenAiSkillRuleReviewAdapter(model="gpt-5.4")

    result = adapter.review(
        skill_name="business-license-review",
        skill_text="## 审核规则",
        review_payload={},
    )

    assert calls["count"] == 2
    assert result["status"] == "REVIEWED"
    assert result["metadata"]["attempts"] == 2
