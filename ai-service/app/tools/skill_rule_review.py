import json
import os
from pathlib import Path
from typing import Any, Protocol


class SkillRuleReviewAdapter(Protocol):
    def review(
        self,
        *,
        skill_name: str,
        skill_text: str,
        review_payload: dict[str, Any],
    ) -> dict[str, Any]:
        ...


class OpenAiSkillRuleReviewAdapter:
    implementation_status = "configured"

    def __init__(
        self,
        *,
        model: str | None = None,
        model_env_key: str = "BUSINESS_LICENSE_SKILL_REVIEW_MODEL",
        base_url: str | None = None,
        timeout: int = 60,
        max_attempts: int | None = None,
    ) -> None:
        self.model = model or os.environ.get(model_env_key, "")
        self.base_url = base_url or os.environ.get("OPENAI_BASE_URL")
        self.timeout = timeout
        self.max_attempts = max_attempts or int(os.environ.get("OPENAI_MAX_ATTEMPTS", "3"))

    def review(
        self,
        *,
        skill_name: str,
        skill_text: str,
        review_payload: dict[str, Any],
    ) -> dict[str, Any]:
        if not self.model:
            return _error_result("SKILL_RULE_REVIEW_MODEL_NOT_CONFIGURED", self.model)

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return _error_result("SKILL_RULE_REVIEW_NOT_CONFIGURED", self.model)
        try:
            from openai import OpenAI
        except Exception:
            return _error_result("SKILL_RULE_REVIEW_DEPENDENCY_MISSING", self.model)

        prompt = build_skill_rule_review_prompt(
            skill_name=skill_name,
            skill_text=skill_text,
            review_payload=review_payload,
        )
        client = OpenAI(api_key=api_key, base_url=self.base_url, timeout=self.timeout)
        try:
            content, attempts = _create_chat_completion_content(
                client=client,
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_attempts=self.max_attempts,
            )
        except Exception as error:
            result = _error_result("SKILL_RULE_REVIEW_MODEL_CALL_FAILED", self.model)
            result["metadata"]["error_type"] = type(error).__name__
            result["metadata"]["error_message"] = str(error)
            result["metadata"]["attempts"] = self.max_attempts
            return result

        parsed = parse_json_object(content)
        if parsed is None:
            result = _error_result("SKILL_RULE_REVIEW_JSON_MISSING", self.model)
            result["metadata"]["raw_response_preview"] = content[:500]
            return result
        parsed["metadata"] = {
            **dict(parsed.get("metadata") or {}),
            "implementation_status": self.implementation_status,
            "provider": "openai_compatible_chat_completions",
            "model": self.model,
            "skill_name": skill_name,
            "attempts": attempts,
        }
        return parsed


class FakeSkillRuleReviewAdapter:
    implementation_status = "fake"

    def __init__(self, result: dict[str, Any] | None = None) -> None:
        self.result = result

    def review(
        self,
        *,
        skill_name: str,
        skill_text: str,
        review_payload: dict[str, Any],
    ) -> dict[str, Any]:
        if self.result is not None:
            return self.result
        return {
            "status": "PENDING_MANUAL_REVIEW",
            "risk_level": "MEDIUM",
            "needs_manual_review": True,
            "summary": "fake skill rule review 未提供审核结果。",
            "manual_review_reasons": ["fake skill rule review 未提供审核结果"],
            "rule_results": [],
            "metadata": {
                "implementation_status": self.implementation_status,
                "skill_name": skill_name,
            },
        }


def build_business_license_skill_rule_review_adapter() -> SkillRuleReviewAdapter:
    return build_skill_rule_review_adapter("BUSINESS_LICENSE")


def build_food_license_skill_rule_review_adapter() -> SkillRuleReviewAdapter:
    return build_skill_rule_review_adapter("FOOD_LICENSE")


def build_food_production_license_skill_rule_review_adapter() -> SkillRuleReviewAdapter:
    return build_skill_rule_review_adapter("FOOD_PRODUCTION_LICENSE")


def build_qc_document_skill_rule_review_adapter() -> SkillRuleReviewAdapter:
    return build_skill_rule_review_adapter("QC_DOCUMENT")


def build_skill_rule_review_adapter(env_prefix: str) -> SkillRuleReviewAdapter:
    provider = os.environ.get(f"{env_prefix}_SKILL_REVIEW_PROVIDER", "openai").strip().lower()
    if provider in {"fake", "stub"}:
        fake_json = os.environ.get(f"{env_prefix}_SKILL_REVIEW_FAKE_JSON", "").strip()
        return FakeSkillRuleReviewAdapter(parse_json_object(fake_json) if fake_json else None)
    model = os.environ.get(f"{env_prefix}_SKILL_REVIEW_MODEL")
    if not model and env_prefix != "BUSINESS_LICENSE":
        model = os.environ.get("BUSINESS_LICENSE_SKILL_REVIEW_MODEL")
    return OpenAiSkillRuleReviewAdapter(
        model=model,
        model_env_key=f"{env_prefix}_SKILL_REVIEW_MODEL",
    )


def load_skill_text(skill_name: str) -> str:
    repo_root = Path(__file__).resolve().parents[3]
    skill_path = repo_root / ".agents" / "skills" / skill_name / "SKILL.md"
    return skill_path.read_text(encoding="utf-8")


def build_skill_rule_review_prompt(
    *,
    skill_name: str,
    skill_text: str,
    review_payload: dict[str, Any],
) -> str:
    return (
        "你是证照合规审核执行器。请严格根据 Skill 中的规则判断，不要使用未声明规则。\n"
        "只输出一个 JSON 对象，不要输出 Markdown。\n\n"
        f"# Skill: {skill_name}\n"
        f"{skill_text}\n\n"
        "# 审核输入\n"
        f"{json.dumps(review_payload, ensure_ascii=False, indent=2, default=str)}\n"
    )


def parse_json_object(content: str) -> dict[str, Any] | None:
    if not content:
        return None
    candidate = content.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if candidate.startswith("json"):
            candidate = candidate[4:].strip()
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        parsed = json.loads(candidate[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _error_result(code: str, model: str) -> dict[str, Any]:
    return {
        "status": "PENDING_MANUAL_REVIEW",
        "risk_level": "MEDIUM",
        "needs_manual_review": True,
        "summary": "Skill 规则审核未完成，需要人工复核。",
        "manual_review_reasons": ["Skill 规则审核未完成"],
        "rule_results": [],
        "metadata": {
            "implementation_status": "failed",
            "provider": "openai_compatible_chat_completions",
            "model": model,
            "error_code": code,
        },
    }


def _chat_completion_content(response: Any) -> str:
    choices = getattr(response, "choices", None) or []
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    return str(getattr(message, "content", "") or "").strip()


def _create_chat_completion_content(
    *,
    client: Any,
    model: str,
    messages: list[dict[str, Any]],
    max_attempts: int,
) -> tuple[str, int]:
    attempts = max(1, max_attempts)
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0,
            )
            return _chat_completion_content(response), attempt
        except Exception as error:
            last_error = error
    if last_error is not None:
        raise last_error
    return "", attempts
