import json
import re
from typing import Any

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel, Field

from app.core.config import settings
from app.skills.food_license.models import FoodLicenseExtractedFields


class FoodLicenseExtractionResult(BaseModel):
    fields: FoodLicenseExtractedFields
    metadata: dict[str, Any] = Field(default_factory=dict)


def build_structured_extraction_chain():
    parser = PydanticOutputParser(pydantic_object=FoodLicenseExtractedFields)
    prompt = _build_extraction_prompt(parser)
    deterministic_extractor = RunnableLambda(
        lambda prompt_value: _deterministic_extract_to_json(prompt_value.to_string())
    )
    return prompt | deterministic_extractor | parser


def build_llm_structured_extraction_chain(llm):
    parser = PydanticOutputParser(pydantic_object=FoodLicenseExtractedFields)
    return _build_extraction_prompt(parser) | llm | parser


def extract_food_license_fields(
    document_text: str,
    regex_fields: FoodLicenseExtractedFields | None = None,
    structured_extractor=None,
    llm_enabled: bool | None = None,
    llm_chain=None,
) -> FoodLicenseExtractionResult:
    regex_fields = regex_fields or regex_extract_food_license_fields(document_text)
    if _has_required_fields(regex_fields):
        return FoodLicenseExtractionResult(
            fields=regex_fields,
            metadata={
                "extraction_mode": "regex_only",
                "llm_used": False,
                "llm_reason": "required_fields_present",
            },
        )

    llm_should_run = (
        settings.food_license_llm_enabled if llm_enabled is None else llm_enabled
    )
    metadata: dict[str, Any] = {
        "extraction_mode": "regex_only",
        "llm_used": False,
        "llm_reason": "llm_disabled",
    }

    if llm_should_run:
        try:
            extractor = llm_chain or structured_extractor or build_configured_llm_chain()
            if extractor is None:
                metadata["extraction_mode"] = "regex_fallback_after_llm_failed"
                metadata["llm_reason"] = "llm_not_configured"
            else:
                llm_fields = extractor.invoke({"document_text": document_text})
                supplemented_fields = _supplement_missing_fields(regex_fields, llm_fields)
                return FoodLicenseExtractionResult(
                    fields=supplemented_fields,
                    metadata={
                        "extraction_mode": "regex_with_llm_supplement",
                        "llm_used": True,
                        "llm_reason": "missing_required_fields",
                    },
                )
        except Exception:
            metadata["extraction_mode"] = "regex_fallback_after_llm_failed"
            metadata["llm_reason"] = "llm_error"

    return FoodLicenseExtractionResult(fields=regex_fields, metadata=metadata)


def build_configured_llm_chain():
    if not settings.food_license_llm_api_key or not settings.food_license_llm_model:
        return None

    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        return None

    provider = settings.food_license_llm_provider
    base_url = settings.food_license_llm_base_url or None
    llm = ChatOpenAI(
        model=settings.food_license_llm_model,
        api_key=settings.food_license_llm_api_key,
        base_url=base_url if provider in {"compatible", "openai"} else None,
        temperature=0,
    )
    return build_llm_structured_extraction_chain(llm)


def regex_extract_food_license_fields(document_text: str) -> FoodLicenseExtractedFields:
    return FoodLicenseExtractedFields(
        subject_name=_extract_line_value(document_text, ("经营者名称", "名称", "主体名称")),
        credit_code=_extract_line_value(document_text, ("统一社会信用代码", "社会信用代码")),
        license_no=_extract_line_value(document_text, ("许可证编号", "编号")),
        business_address=_extract_line_value(document_text, ("经营场所", "经营地址", "住所")),
        business_items=_extract_business_items(document_text),
        valid_to=_extract_line_value(document_text, ("有效期至", "有效期截止日期", "有效期限至")),
    )


def _deterministic_extract_to_json(prompt_text: str) -> str:
    fields = regex_extract_food_license_fields(prompt_text)
    return json.dumps(fields.model_dump(mode="json"), ensure_ascii=False)


def _build_extraction_prompt(parser: PydanticOutputParser) -> PromptTemplate:
    return PromptTemplate(
        template=(
            "你是食品安全证照审核系统的字段抽取器。\n"
            "从 OCR 文本中抽取食品经营许可证字段，只输出符合格式说明的 JSON。\n"
            "{format_instructions}\n"
            "OCR 文本：\n{document_text}"
        ),
        input_variables=["document_text"],
        partial_variables={"format_instructions": parser.get_format_instructions()},
    )


def _supplement_missing_fields(
    regex_fields: FoodLicenseExtractedFields,
    llm_fields: FoodLicenseExtractedFields,
) -> FoodLicenseExtractedFields:
    merged = regex_fields.model_dump()
    supplement = llm_fields.model_dump()
    for key, value in supplement.items():
        if merged.get(key) in (None, [], "") and value not in (None, [], ""):
            merged[key] = value
    return FoodLicenseExtractedFields.model_validate(merged)


def _has_required_fields(fields: FoodLicenseExtractedFields) -> bool:
    return bool(fields.credit_code and fields.license_no)


def _extract_line_value(document_text: str, labels: tuple[str, ...]) -> str | None:
    for label in labels:
        pattern = rf"{re.escape(label)}\s*[:：]\s*([^\n]+)"
        match = re.search(pattern, document_text)
        if match:
            return match.group(1).strip()
    return None


def _extract_business_items(document_text: str) -> list[str]:
    value = _extract_line_value(document_text, ("经营项目", "经营范围"))
    if not value:
        return []
    return [item.strip() for item in re.split(r"[、,，;；]", value) if item.strip()]
