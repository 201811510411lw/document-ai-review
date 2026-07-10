from datetime import date

from app.models import ManualReview, ManualReviewStatus, RiskLevel, RuleResult
from app.capabilities.food_license.schemas import (
    FoodLicenseDocumentClassification,
    FoodLicenseDocumentInputResult,
    FoodLicenseExtractedFields,
    FoodLicenseNormalizedFields,
)
from app.tools.license_file_recognition import recognize_license_file
from app.tools.remote_document import RemoteDocumentDownloader
from app.tools.skill_rule_review import (
    build_food_license_skill_rule_review_adapter,
    load_skill_text,
)
from app.tools.vision_adapter import build_food_license_file_adapter
from app.workflows.food_license.state import FoodLicenseWorkflowState


food_license_remote_downloader = RemoteDocumentDownloader()
food_license_file_adapter = build_food_license_file_adapter()
food_license_skill_rule_review_adapter = build_food_license_skill_rule_review_adapter()


def _current_rule_date():
    from datetime import date

    return date.today()


def load_document(state: FoodLicenseWorkflowState) -> FoodLicenseWorkflowState:
    input_context = state["input_context"]
    review_input = input_context.input
    recognition_result = recognize_license_file(
        review_input,
        adapter=food_license_file_adapter,
        downloader=food_license_remote_downloader,
    )
    return {
        **state,
        "document_text": recognition_result.document_text,
        "llm_structured_fields": recognition_result.structured_fields,
        "document_input": FoodLicenseDocumentInputResult(
            **recognition_result.document_input.__dict__
        ),
        "extraction_metadata": {
            **state.get("extraction_metadata", {}),
            **recognition_result.extraction_metadata,
        },
        "source_evidence": {
            "supplier_name": review_input.supplier_name,
            "supplier_credit_code": review_input.supplier_credit_code,
            "declared_document_type": review_input.declared_document_type,
            "source": review_input.source,
            "options": review_input.options,
        },
    }


def classify_document(state: FoodLicenseWorkflowState) -> FoodLicenseWorkflowState:
    structured_fields = state.get("llm_structured_fields") or {}
    if structured_fields.get("document_type"):
        document_type = _normalize_document_type(structured_fields.get("document_type"))
        return {
            **state,
            "document_classification": FoodLicenseDocumentClassification(
                document_type=document_type,
                confidence=1.0 if document_type == "food_license" else 0.0,
                reasons=["大模型文件识别返回结构化证照类型"],
            ),
        }
    return {
        **state,
        "document_classification": FoodLicenseDocumentClassification(
            document_type="unknown",
            confidence=0.0,
            reasons=["大模型文件识别未返回结构化证照类型"],
        ),
    }


def extract_fields(state: FoodLicenseWorkflowState) -> FoodLicenseWorkflowState:
    structured_fields = state.get("llm_structured_fields") or {}
    if structured_fields:
        extracted_fields = FoodLicenseExtractedFields.model_validate(
            _sanitize_structured_fields(structured_fields)
        )
        return {
            **state,
            "extracted_fields": extracted_fields,
            "extraction_metadata": {
                **state.get("extraction_metadata", {}),
                "structured_extraction": {
                    "source": "llm_file_extractor",
                    "schema": "FoodLicenseExtractedFields",
                },
            },
        }

    return {
        **state,
        "extracted_fields": FoodLicenseExtractedFields(),
        "extraction_metadata": {
            **state.get("extraction_metadata", {}),
            "structured_extraction": {
                "source": "llm_file_extractor",
                "schema": "FoodLicenseExtractedFields",
                "status": "missing_structured_fields",
            },
        },
    }


def normalize_fields(state: FoodLicenseWorkflowState) -> FoodLicenseWorkflowState:
    extracted_fields = state.get("extracted_fields") or FoodLicenseExtractedFields()
    normalized_fields = FoodLicenseNormalizedFields(
        document_type=_normalize_document_type(extracted_fields.document_type),
        subject_name=extracted_fields.subject_name,
        credit_code=extracted_fields.credit_code,
        license_no=extracted_fields.license_no,
        business_address=extracted_fields.business_address,
        legal_person=extracted_fields.legal_person,
        business_items=list(extracted_fields.business_items),
        valid_from=_normalize_date_text(extracted_fields.valid_from),
        valid_to=_normalize_date_text(extracted_fields.valid_to),
        issue_authority=extracted_fields.issue_authority,
        issue_date=_normalize_date_text(extracted_fields.issue_date),
    )
    return {
        **state,
        "normalized_fields": normalized_fields,
    }


def run_rules(state: FoodLicenseWorkflowState) -> FoodLicenseWorkflowState:
    input_context = state["input_context"]
    document_classification = state.get("document_classification")
    normalized_fields = state.get("normalized_fields")
    skill_name = "food-license-review"
    review_payload = {
        "task_id": input_context.task_id,
        "declared_document_type": input_context.input.declared_document_type,
        "document_type": (
            document_classification.document_type
            if document_classification is not None
            else None
        ),
        "source_fields": {
            "supplier_name": input_context.input.supplier_name,
            "supplier_credit_code": input_context.input.supplier_credit_code,
            "supplier_address": input_context.input.supplier_address,
        },
        "extracted_fields": (
            normalized_fields.model_dump(mode="json") if normalized_fields else {}
        ),
        "current_date": _current_rule_date().isoformat(),
        "extraction_metadata": state.get("extraction_metadata", {}),
    }
    rules_result = food_license_skill_rule_review_adapter.review(
        skill_name=skill_name,
        skill_text=load_skill_text(skill_name),
        review_payload=review_payload,
    )
    return {
        **state,
        "rule_results": rules_result.get("rule_results", []),
        "risk_level": rules_result.get("risk_level", RiskLevel.MEDIUM),
        "needs_manual_review": rules_result.get("needs_manual_review", True),
        "summary": rules_result.get("summary", "食品许可证 Skill 规则审核完成。"),
        "manual_review_reasons": rules_result.get("manual_review_reasons", []),
        "skill_rule_review_metadata": {
            **dict(rules_result.get("metadata") or {}),
            "skill_name": skill_name,
        },
    }


def summarize_risk(state: FoodLicenseWorkflowState) -> FoodLicenseWorkflowState:
    guarded = _apply_deterministic_review_guards(state)
    return {
        **guarded,
        "risk_level": guarded.get("risk_level", RiskLevel.MEDIUM),
        "needs_manual_review": guarded.get("needs_manual_review", True),
        "summary": guarded.get("summary", "食品许可证 Skill 规则审核完成。"),
    }


def _apply_deterministic_review_guards(
    state: FoodLicenseWorkflowState,
) -> FoodLicenseWorkflowState:
    normalized_fields = state.get("normalized_fields") or FoodLicenseNormalizedFields()
    input_context = state["input_context"]
    reasons = list(state.get("manual_review_reasons", []))
    rule_results = list(state.get("rule_results", []))
    risk_level = state.get("risk_level", RiskLevel.MEDIUM)

    subject_guard = _subject_name_guard(
        normalized_fields.subject_name,
        input_context.input.supplier_name,
    )
    if subject_guard is not None:
        subject_passed, reason, rule_result = subject_guard
        rule_results = _upsert_rule_result(rule_results, rule_result)
        if subject_passed:
            reasons = [item for item in reasons if item != "主体名称与来源信息不一致"]
        else:
            if not any("主体名称缺失" in item for item in reasons):
                reasons.append(reason)
            risk_level = _max_risk(risk_level, RiskLevel.MEDIUM)

    recognized_credit = _normalize_credit_code(normalized_fields.credit_code)
    expected_credit = _normalize_credit_code(input_context.input.supplier_credit_code)
    if not recognized_credit:
        reasons.append("证照统一社会信用代码缺失")
        rule_results = _upsert_rule_result(
            rule_results,
            RuleResult(
                rule_code="FOOD_LICENSE_CREDIT_CODE_MATCH",
                rule_name="统一社会信用代码是否与供应商一致",
                passed=False,
                risk_level_on_failure=RiskLevel.HIGH,
                message="证照统一社会信用代码缺失，无法与来源系统比对。",
                details={},
            ),
        )
        risk_level = RiskLevel.HIGH
    elif not expected_credit:
        reasons.append("来源系统统一社会信用代码缺失")
        rule_results = _upsert_rule_result(
            rule_results,
            RuleResult(
                rule_code="FOOD_LICENSE_CREDIT_CODE_MATCH",
                rule_name="统一社会信用代码是否与供应商一致",
                passed=False,
                risk_level_on_failure=RiskLevel.HIGH,
                message="来源系统统一社会信用代码缺失，无法与证照识别值比对。",
                details={"recognized_credit_code": recognized_credit},
            ),
        )
        risk_level = RiskLevel.HIGH
    elif recognized_credit != expected_credit:
        reasons.append("统一社会信用代码与来源信息不一致")
        rule_results = _upsert_rule_result(
            rule_results,
            RuleResult(
                rule_code="FOOD_LICENSE_CREDIT_CODE_MATCH",
                rule_name="统一社会信用代码是否与供应商一致",
                passed=False,
                risk_level_on_failure=RiskLevel.HIGH,
                message="证照统一社会信用代码与供应商信用代码不一致。",
                details={
                    "recognized_credit_code": recognized_credit,
                    "expected_credit_code": expected_credit,
                },
            ),
        )
        risk_level = RiskLevel.HIGH

    validity_guard = _validity_period_guard(normalized_fields.valid_to)
    if validity_guard is not None:
        reason, rule_result, guard_risk = validity_guard
        reasons.append(reason)
        rule_results = _upsert_rule_result(rule_results, rule_result)
        risk_level = _max_risk(risk_level, guard_risk)

    deduped_reasons = list(dict.fromkeys(reason for reason in reasons if reason))
    risk_level = _risk_from_rule_results(rule_results, fallback=risk_level)
    needs_manual_review = bool(deduped_reasons) or risk_level in {
        RiskLevel.HIGH,
        RiskLevel.MEDIUM,
    }
    summary = state.get("summary", "食品许可证 Skill 规则审核完成。")
    if deduped_reasons:
        summary = "食品经营许可证关键字段校验未通过，需要人工复核。"
    return {
        **state,
        "rule_results": rule_results,
        "risk_level": risk_level,
        "needs_manual_review": needs_manual_review,
        "manual_review_reasons": deduped_reasons,
        "summary": summary,
    }


def _upsert_rule_result(rule_results: list, replacement: RuleResult) -> list:
    updated = []
    replaced = False
    for rule in rule_results:
        rule_code = rule.get("rule_code") if isinstance(rule, dict) else rule.rule_code
        if rule_code == replacement.rule_code:
            updated.append(replacement)
            replaced = True
        else:
            updated.append(rule)
    if not replaced:
        updated.append(replacement)
    return updated


def _normalize_credit_code(value) -> str:
    return "".join(str(value or "").split()).upper()


def _subject_name_guard(
    recognized: str | None,
    expected: str | None,
) -> tuple[bool, str, RuleResult] | None:
    recognized_text = str(recognized or "").strip()
    expected_text = str(expected or "").strip()
    if not recognized_text:
        return (
            False,
            "主体名称缺失",
            RuleResult(
                rule_code="FOOD_LICENSE_SUBJECT_NAME_MATCH",
                rule_name="主体名称是否与供应商名称一致",
                passed=False,
                risk_level_on_failure=RiskLevel.MEDIUM,
                message="证照主体名称缺失，无法与来源系统供应商名称比对。",
                details={},
            ),
        )
    if not expected_text:
        return None
    if _normalize_subject_name(recognized_text) == _normalize_subject_name(expected_text):
        return (
            True,
            "",
            RuleResult(
                rule_code="FOOD_LICENSE_SUBJECT_NAME_MATCH",
                rule_name="主体名称是否与供应商名称一致",
                passed=True,
                risk_level_on_failure=RiskLevel.MEDIUM,
                message="证照主体名称与供应商名称一致，仅存在括号或标点差异。",
                details={
                    "recognized_subject_name": recognized_text,
                    "expected_subject_name": expected_text,
                    "normalized_match": True,
                },
            ),
        )
    return (
        False,
        "主体名称与来源信息不一致",
        RuleResult(
            rule_code="FOOD_LICENSE_SUBJECT_NAME_MATCH",
            rule_name="主体名称是否与供应商名称一致",
            passed=False,
            risk_level_on_failure=RiskLevel.MEDIUM,
            message="证照主体名称与来源系统供应商名称不一致。",
            details={
                "recognized_subject_name": recognized_text,
                "expected_subject_name": expected_text,
            },
        ),
    )


def _normalize_subject_name(value: str | None) -> str:
    punctuation = set("()（）[]【】,，.。;；:：-—_·'\"“”‘’")
    return "".join(character for character in str(value or "").strip() if character not in punctuation and not character.isspace())


def _validity_period_guard(valid_to: str | None) -> tuple[str, RuleResult, RiskLevel] | None:
    text = str(valid_to or "").strip()
    if not text or "长期" in text:
        return None
    try:
        days_until_expiry = (date.fromisoformat(text) - _current_rule_date()).days
    except ValueError:
        return (
            "有效期截止日期无法解析",
            RuleResult(
                rule_code="FOOD_LICENSE_VALIDITY_PERIOD",
                rule_name="有效期是否有效",
                passed=False,
                risk_level_on_failure=RiskLevel.HIGH,
                message="食品经营许可证有效期截止日期无法解析，需要人工复核。",
                details={"valid_to": text},
            ),
            RiskLevel.HIGH,
        )
    if days_until_expiry < 0:
        return (
            "食品经营许可证已过期",
            RuleResult(
                rule_code="FOOD_LICENSE_VALIDITY_PERIOD",
                rule_name="有效期是否有效",
                passed=False,
                risk_level_on_failure=RiskLevel.HIGH,
                message=(
                    f"许可证有效期至{text}，当前日期为"
                    f"{_current_rule_date().isoformat()}，已过期。"
                ),
                details={
                    "valid_to": text,
                    "current_date": _current_rule_date().isoformat(),
                    "days_until_expiry": days_until_expiry,
                },
            ),
            RiskLevel.HIGH,
        )
    if days_until_expiry <= 30:
        return (
            "食品经营许可证有效期不足30天",
            RuleResult(
                rule_code="FOOD_LICENSE_VALIDITY_PERIOD",
                rule_name="有效期是否有效",
                passed=False,
                risk_level_on_failure=RiskLevel.MEDIUM,
                message=(
                    f"许可证有效期至{text}，当前日期为"
                    f"{_current_rule_date().isoformat()}，有效期不足30天。"
                ),
                details={
                    "valid_to": text,
                    "current_date": _current_rule_date().isoformat(),
                    "days_until_expiry": days_until_expiry,
                },
            ),
            RiskLevel.MEDIUM,
        )
    return None


def _max_risk(current: RiskLevel, candidate: RiskLevel) -> RiskLevel:
    order = {
        RiskLevel.NONE: 0,
        RiskLevel.LOW: 1,
        RiskLevel.MEDIUM: 2,
        RiskLevel.HIGH: 3,
    }
    return candidate if order[candidate] > order.get(current, 0) else current


def _risk_from_rule_results(rule_results: list, *, fallback: RiskLevel) -> RiskLevel:
    risk = RiskLevel.NONE
    for rule in rule_results:
        passed = rule.get("passed") if isinstance(rule, dict) else rule.passed
        if passed is not False:
            continue
        level = (
            rule.get("risk_level_on_failure")
            if isinstance(rule, dict)
            else rule.risk_level_on_failure
        )
        try:
            risk = _max_risk(risk, RiskLevel(level))
        except ValueError:
            risk = _max_risk(risk, fallback)
    return risk


def route_review(state: FoodLicenseWorkflowState) -> FoodLicenseWorkflowState:
    risk_level = state.get("risk_level", RiskLevel.NONE)
    document_classification = state.get("document_classification")
    unknown_document_type = (
        document_classification is None
        or document_classification.document_type != "food_license"
    )
    rule_execution_needs_manual_review = state.get("needs_manual_review", False)
    needs_manual_review = (
        rule_execution_needs_manual_review
        or unknown_document_type
        or risk_level in {RiskLevel.HIGH, RiskLevel.MEDIUM}
    )
    reasons = []
    if state.get("extraction_metadata", {}).get("input_error", {}).get("code") == "UNSUPPORTED_TEXT_DOCUMENT_INPUT":
        reasons.append("食品许可证审核不支持文本输入，请提供 PDF/JPG/JPEG/PNG 文件")
    if unknown_document_type:
        reasons.append("文档类型无法识别，需要人工复核")
    elif rule_execution_needs_manual_review:
        reasons.extend(state.get("manual_review_reasons", []))
    elif needs_manual_review:
        reasons.append("Skill 规则结果需要人工复核")

    manual_review = ManualReview(
        status=(
            ManualReviewStatus.PENDING
            if needs_manual_review
            else ManualReviewStatus.NOT_REQUIRED
        ),
        reasons=reasons,
    )
    return {
        **state,
        "needs_manual_review": needs_manual_review,
        "manual_review": manual_review,
    }


def _normalize_document_type(value) -> str:
    text = "" if value is None else str(value).strip()
    if text in {"food_license", "食品经营许可证"}:
        return "food_license"
    if text in {"food_production_license", "食品生产许可证"}:
        return "food_production_license"
    return text or ""


def _normalize_date_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if "长期" in text:
        return text
    import re

    match = re.fullmatch(r"(\d{4})年(\d{1,2})月(\d{1,2})日?", text)
    if match:
        year, month, day = match.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"
    return text


def _sanitize_structured_fields(fields: dict) -> dict:
    sanitized = dict(fields)
    if sanitized.get("document_type") == "食品经营许可证":
        sanitized["document_type"] = "food_license"
    elif sanitized.get("document_type") == "食品生产许可证":
        sanitized["document_type"] = "food_production_license"
    sanitized["business_items"] = _string_list(sanitized.get("business_items"))
    for key in (
        "document_type",
        "subject_name",
        "credit_code",
        "license_no",
        "business_address",
        "legal_person",
        "valid_from",
        "valid_to",
        "issue_authority",
        "issue_date",
    ):
        sanitized[key] = _optional_text(sanitized.get(key))
    return sanitized


def _string_list(value) -> list[str]:
    values = value if isinstance(value, list) else [value]
    items: list[str] = []
    for item in values:
        text = _item_to_text(item)
        if text:
            items.append(text)
    return items


def _item_to_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("经营项目", "项目", "名称", "内容", "business_item", "item", "name", "text", "value"):
            text = _item_to_text(value.get(key))
            if text:
                return text
        return " ".join(text for text in (_item_to_text(item) for item in value.values()) if text).strip()
    if isinstance(value, list):
        return " ".join(text for text in (_item_to_text(item) for item in value) if text).strip()
    return str(value).strip()


def _optional_text(value) -> str | None:
    text = _item_to_text(value)
    return text or None
