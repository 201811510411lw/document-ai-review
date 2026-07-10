from datetime import date

from app.capabilities.food_production_license.schemas import (
    FoodProductionLicenseDocumentClassification,
    FoodProductionLicenseDocumentInputResult,
    FoodProductionLicenseExtractedFields,
    FoodProductionLicenseNormalizedFields,
)
from app.models import ManualReview, ManualReviewStatus, RiskLevel, RuleResult
from app.tools.license_file_recognition import recognize_license_file
from app.tools.remote_document import RemoteDocumentDownloader
from app.tools.skill_rule_review import (
    build_food_production_license_skill_rule_review_adapter,
    load_skill_text,
)
from app.tools.vision_adapter import build_food_production_license_file_adapter
from app.workflows.food_production_license.state import FoodProductionLicenseWorkflowState


food_production_license_remote_downloader = RemoteDocumentDownloader()
food_production_license_file_adapter = build_food_production_license_file_adapter()
food_production_license_skill_rule_review_adapter = (
    build_food_production_license_skill_rule_review_adapter()
)


def _current_rule_date():
    from datetime import date

    return date.today()


def load_document(
    state: FoodProductionLicenseWorkflowState,
) -> FoodProductionLicenseWorkflowState:
    input_context = state["input_context"]
    review_input = input_context.input
    recognition_result = recognize_license_file(
        review_input,
        adapter=food_production_license_file_adapter,
        downloader=food_production_license_remote_downloader,
    )
    return {
        **state,
        "document_text": recognition_result.document_text,
        "llm_structured_fields": recognition_result.structured_fields,
        "document_input": FoodProductionLicenseDocumentInputResult(
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


def classify_document(
    state: FoodProductionLicenseWorkflowState,
) -> FoodProductionLicenseWorkflowState:
    structured_fields = state.get("llm_structured_fields") or {}
    if structured_fields.get("document_type"):
        document_type = _normalize_document_type(structured_fields.get("document_type"))
        return {
            **state,
            "document_classification": FoodProductionLicenseDocumentClassification(
                document_type=document_type,
                confidence=1.0 if document_type == "food_production_license" else 0.0,
                reasons=["大模型文件识别返回结构化证照类型"],
            ),
        }
    return {
        **state,
        "document_classification": FoodProductionLicenseDocumentClassification(
            document_type="unknown",
            confidence=0.0,
            reasons=["大模型文件识别未返回结构化证照类型"],
        ),
    }


def extract_fields(
    state: FoodProductionLicenseWorkflowState,
) -> FoodProductionLicenseWorkflowState:
    structured_fields = state.get("llm_structured_fields") or {}
    if structured_fields:
        extracted_fields = FoodProductionLicenseExtractedFields.model_validate(
            _sanitize_structured_fields(
                structured_fields,
                source_text=state.get("document_text") or "",
            )
        )
        return {
            **state,
            "extracted_fields": extracted_fields,
            "extraction_metadata": {
                **state.get("extraction_metadata", {}),
                "structured_extraction": {
                    "source": "llm_file_extractor",
                    "schema": "FoodProductionLicenseExtractedFields",
                },
            },
        }

    return {
        **state,
        "extracted_fields": FoodProductionLicenseExtractedFields(),
        "extraction_metadata": {
            **state.get("extraction_metadata", {}),
            "structured_extraction": {
                "source": "llm_file_extractor",
                "schema": "FoodProductionLicenseExtractedFields",
                "status": "missing_structured_fields",
            },
        },
    }


def normalize_fields(
    state: FoodProductionLicenseWorkflowState,
) -> FoodProductionLicenseWorkflowState:
    extracted_fields = (
        state.get("extracted_fields") or FoodProductionLicenseExtractedFields()
    )
    normalized_fields = FoodProductionLicenseNormalizedFields(
        document_type=_normalize_document_type(extracted_fields.document_type),
        producer_name=extracted_fields.producer_name,
        credit_code=extracted_fields.credit_code,
        license_no=extracted_fields.license_no,
        production_address=extracted_fields.production_address,
        legal_person=extracted_fields.legal_person,
        food_categories=list(extracted_fields.food_categories),
        valid_from=_normalize_date_text(extracted_fields.valid_from),
        valid_to=_normalize_date_text(extracted_fields.valid_to),
        issue_authority=extracted_fields.issue_authority,
        issue_date=_normalize_date_text(extracted_fields.issue_date),
    )
    return {
        **state,
        "normalized_fields": normalized_fields,
    }


def run_rules(
    state: FoodProductionLicenseWorkflowState,
) -> FoodProductionLicenseWorkflowState:
    input_context = state["input_context"]
    document_classification = state.get("document_classification")
    normalized_fields = state.get("normalized_fields")
    skill_name = "food-production-license-review"
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
    rules_result = food_production_license_skill_rule_review_adapter.review(
        skill_name=skill_name,
        skill_text=load_skill_text(skill_name),
        review_payload=review_payload,
    )
    return {
        **state,
        "rule_results": rules_result.get("rule_results", []),
        "risk_level": rules_result.get("risk_level", RiskLevel.MEDIUM),
        "needs_manual_review": rules_result.get("needs_manual_review", True),
        "summary": rules_result.get("summary", "食品生产许可证 Skill 规则审核完成。"),
        "manual_review_reasons": rules_result.get("manual_review_reasons", []),
        "skill_rule_review_metadata": {
            **dict(rules_result.get("metadata") or {}),
            "skill_name": skill_name,
        },
    }


def summarize_risk(
    state: FoodProductionLicenseWorkflowState,
) -> FoodProductionLicenseWorkflowState:
    guarded = _apply_deterministic_review_guards(state)
    return {
        **guarded,
        "risk_level": guarded.get("risk_level", RiskLevel.MEDIUM),
        "needs_manual_review": guarded.get("needs_manual_review", True),
        "summary": guarded.get("summary", "食品生产许可证 Skill 规则审核完成。"),
    }


def _apply_deterministic_review_guards(
    state: FoodProductionLicenseWorkflowState,
) -> FoodProductionLicenseWorkflowState:
    normalized_fields = state.get("normalized_fields") or FoodProductionLicenseNormalizedFields()
    input_context = state["input_context"]
    reasons = list(state.get("manual_review_reasons", []))
    rule_results = list(state.get("rule_results", []))
    risk_level = state.get("risk_level", RiskLevel.MEDIUM)

    recognized_credit = _normalize_credit_code(normalized_fields.credit_code)
    expected_credit = _normalize_credit_code(input_context.input.supplier_credit_code)
    if not recognized_credit:
        reasons.append("证照统一社会信用代码缺失")
        rule_results = _upsert_rule_result(
            rule_results,
            RuleResult(
                rule_code="FOOD_PRODUCTION_LICENSE_CREDIT_CODE_MATCH",
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
                rule_code="FOOD_PRODUCTION_LICENSE_CREDIT_CODE_MATCH",
                rule_name="统一社会信用代码是否与供应商一致",
                passed=False,
                risk_level_on_failure=RiskLevel.HIGH,
                message="来源系统统一社会信用代码缺失，无法与证照识别值比对。",
                details={"recognized_credit_code": recognized_credit},
            ),
        )
        risk_level = RiskLevel.HIGH
    elif expected_credit and recognized_credit != expected_credit:
        reasons.append("统一社会信用代码与来源信息不一致")
        rule_results = _upsert_rule_result(
            rule_results,
            RuleResult(
                rule_code="FOOD_PRODUCTION_LICENSE_CREDIT_CODE_MATCH",
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

    if not _text(normalized_fields.legal_person):
        reasons.append("负责人/法定代表人缺失")
        risk_level = _max_risk(risk_level, RiskLevel.MEDIUM)

    if not _text(normalized_fields.valid_to):
        reasons.append("有效期截止日期缺失")
        rule_results = _upsert_rule_result(
            rule_results,
            RuleResult(
                rule_code="FOOD_PRODUCTION_LICENSE_VALIDITY_PERIOD",
                rule_name="有效期是否合规",
                passed=False,
                risk_level_on_failure=RiskLevel.HIGH,
                message="食品生产许可证有效期截止日期缺失，需要人工复核。",
                details={},
            ),
        )
        risk_level = RiskLevel.HIGH

    deduped_reasons = list(dict.fromkeys(reason for reason in reasons if reason))
    needs_manual_review = state.get("needs_manual_review", True) or bool(deduped_reasons)
    summary = state.get("summary", "食品生产许可证 Skill 规则审核完成。")
    if deduped_reasons:
        summary = "食品生产许可证关键字段校验未通过，需要人工复核。"
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


def _text(value) -> str:
    return str(value or "").strip()


def _max_risk(current: RiskLevel, candidate: RiskLevel) -> RiskLevel:
    order = {
        RiskLevel.NONE: 0,
        RiskLevel.LOW: 1,
        RiskLevel.MEDIUM: 2,
        RiskLevel.HIGH: 3,
    }
    return candidate if order[candidate] > order.get(current, 0) else current


def route_review(
    state: FoodProductionLicenseWorkflowState,
) -> FoodProductionLicenseWorkflowState:
    risk_level = state.get("risk_level", RiskLevel.NONE)
    document_classification = state.get("document_classification")
    unknown_document_type = (
        document_classification is None
        or document_classification.document_type != "food_production_license"
    )
    rule_execution_needs_manual_review = state.get("needs_manual_review", False)
    needs_manual_review = (
        rule_execution_needs_manual_review
        or unknown_document_type
        or risk_level in {RiskLevel.HIGH, RiskLevel.MEDIUM}
    )
    reasons = []
    if state.get("extraction_metadata", {}).get("input_error", {}).get("code") == (
        "UNSUPPORTED_TEXT_DOCUMENT_INPUT"
    ):
        reasons.append("食品生产许可证审核不支持文本输入，请提供 PDF/JPG/JPEG/PNG 文件")
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


def _sanitize_structured_fields(fields: dict, *, source_text: str = "") -> dict:
    sanitized = dict(fields)
    sanitized["food_categories"] = _string_list(sanitized.get("food_categories"))
    if not sanitized["food_categories"]:
        sanitized["food_categories"] = _extract_food_categories_from_text(source_text)
    if not _optional_text(sanitized.get("legal_person")):
        sanitized["legal_person"] = _first_optional_text(
            sanitized,
            (
                "法定代表人",
                "负责人",
                "法定代表人/负责人",
                "法定代表人（负责人）",
                "负责人姓名",
                "legalRepresentative",
                "legal_representative",
                "responsible_person",
                "person_in_charge",
            ),
        )
    if not _optional_text(sanitized.get("legal_person")):
        sanitized["legal_person"] = _extract_legal_person_from_text(source_text)
    if not _optional_text(sanitized.get("issue_date")):
        sanitized["issue_date"] = _first_optional_text(
            sanitized,
            (
                "签发日期",
                "发证日期",
                "核发日期",
                "issueDate",
                "issue_date",
            ),
        )
    if not _optional_text(sanitized.get("valid_to")):
        sanitized["valid_to"] = _first_optional_text(
            sanitized,
            (
                "有效日期至",
                "有效期至",
                "有效期止",
                "有效期限至",
                "截止日期",
                "到期日期",
                "valid_until",
                "valid_end",
                "expiry_date",
                "expiration_date",
                "expire_date",
            ),
        )
    issue_date = _optional_text(sanitized.get("issue_date"))
    if issue_date:
        valid_from = _optional_text(sanitized.get("valid_from"))
        valid_to = _optional_text(sanitized.get("valid_to"))
        if _should_move_valid_from_to_valid_to(valid_from, valid_to, issue_date):
            sanitized["valid_to"] = valid_from
        sanitized["valid_from"] = issue_date
    for key in (
        "document_type",
        "producer_name",
        "credit_code",
        "license_no",
        "production_address",
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
        for key in ("食品类别", "类别", "品种明细", "生产范围", "名称", "内容", "food_category", "category", "name", "text", "value"):
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


def _first_optional_text(fields: dict, keys: tuple[str, ...]) -> str | None:
    for key in keys:
        text = _optional_text(fields.get(key))
        if text:
            return text
    return None


def _extract_legal_person_from_text(source_text: str) -> str | None:
    if not source_text:
        return None
    import re
    import unicodedata

    compact = unicodedata.normalize("NFKC", source_text)
    compact = re.sub(r"[ \t\r\f\v]+", "", compact)
    compact = re.sub(r"\n+", "", compact)
    label_pattern = r"(?:法定代表人|法定代表人/负责人|法定代表人负责人|负责人)"
    stop_pattern = (
        r"住[所址]|住所|生产地址|生产地|食品类别|许可证编号|统一社会信用代码|"
        r"发证机关|发证日期|签发日期|有效日期至|有效期至|说明"
    )
    patterns = (
        rf"{label_pattern}[(:：)]{{0,2}}(.{{1,24}}?)(?={stop_pattern}|$)",
        rf"{label_pattern}[(:：)]{{0,2}}(.{{1,24}})",
    )
    for pattern in patterns:
        match = re.search(pattern, compact)
        if not match:
            continue
        text = unicodedata.normalize("NFKC", match.group(1))
        text = re.sub(r"[（(]负责人[）)]", "", text)
        text = text.strip(" ：:;；,，。|/\\")
        text = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff·.-]", "", text)
        text = re.sub(
            r"(住所|住址|生产地址|食品类别|许可证编号|统一社会信用代码|发证机关|发证日期|签发日期|有效日期至|有效期至|说明).*$",
            "",
            text,
        )
        if text and text not in {"负责人", "法定代表人"} and len(text) <= 12:
            return text
    return None


def _extract_food_categories_from_text(source_text: str) -> list[str]:
    if not source_text:
        return []
    import re
    import unicodedata

    compact = unicodedata.normalize("NFKC", source_text)
    compact = re.sub(r"[ \t\r\f\v]+", "", compact)
    compact = re.sub(r"\n+", "", compact)
    label_pattern = r"(?:食品类别|食品生产类别|类别名称|生产范围|品种明细)"
    stop_pattern = (
        r"发证机关|发证日期|签发日期|有效日期至|有效期至|许可证编号|"
        r"统一社会信用代码|说明|备注|二维码"
    )
    patterns = (
        rf"{label_pattern}[(:：)]{{0,2}}(.{{1,80}}?)(?={stop_pattern}|$)",
        rf"{label_pattern}[(:：)]{{0,2}}(.{{1,40}})",
    )
    for pattern in patterns:
        match = re.search(pattern, compact)
        if not match:
            continue
        text = unicodedata.normalize("NFKC", match.group(1))
        text = re.sub(
            r"(发证机关|发证日期|签发日期|有效日期至|有效期至|许可证编号|统一社会信用代码|说明|备注|二维码).*$",
            "",
            text,
        )
        text = re.sub(r"\s+", "", text).strip(" ：:;；,，。|/\\")
        if not text:
            continue
        text = re.sub(r"[()（）【】\[\]{}]", "", text)
        items = []
        for item in re.split(r"[、,，;；/|]+", text):
            cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff·.-]", "", item).strip()
            if cleaned and cleaned not in {"食品类别", "类别名称", "生产范围", "品种明细"}:
                items.append(cleaned)
        if items:
            return list(dict.fromkeys(items))
    return []


def _should_move_valid_from_to_valid_to(
    valid_from,
    valid_to,
    issue_date,
) -> bool:
    normalized_valid_from = _normalize_date_text(_optional_text(valid_from))
    normalized_issue_date = _normalize_date_text(_optional_text(issue_date))
    if not normalized_valid_from or not normalized_issue_date:
        return False
    valid_to_text = _optional_text(valid_to) or ""
    if valid_to_text and "长期" not in valid_to_text:
        return False
    try:
        from_date = date.fromisoformat(normalized_valid_from)
        issue = date.fromisoformat(normalized_issue_date)
    except ValueError:
        return False
    return from_date > issue
