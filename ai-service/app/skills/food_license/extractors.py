import json
import re

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda

from app.skills.food_license.models import FoodLicenseExtractedFields


def build_structured_extraction_chain():
    parser = PydanticOutputParser(pydantic_object=FoodLicenseExtractedFields)
    prompt = PromptTemplate(
        template=(
            "从食品安全证照 OCR 文本中抽取结构化字段。\n"
            "{format_instructions}\n"
            "OCR 文本：\n{document_text}"
        ),
        input_variables=["document_text"],
        partial_variables={"format_instructions": parser.get_format_instructions()},
    )
    deterministic_extractor = RunnableLambda(
        lambda prompt_value: _deterministic_extract_to_json(prompt_value.to_string())
    )
    return prompt | deterministic_extractor | parser


def extract_food_license_fields(
    document_text: str,
    structured_extractor=None,
) -> FoodLicenseExtractedFields:
    extractor = structured_extractor or build_structured_extraction_chain()
    structured_fields = extractor.invoke({"document_text": document_text})
    fallback_fields = regex_extract_food_license_fields(document_text)
    return _merge_fields(structured_fields, fallback_fields)


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


def _merge_fields(
    structured_fields: FoodLicenseExtractedFields,
    fallback_fields: FoodLicenseExtractedFields,
) -> FoodLicenseExtractedFields:
    merged = structured_fields.model_dump()
    fallback = fallback_fields.model_dump()
    for key, value in fallback.items():
        if merged.get(key) in (None, [], "") and value not in (None, [], ""):
            merged[key] = value
    return FoodLicenseExtractedFields.model_validate(merged)


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
