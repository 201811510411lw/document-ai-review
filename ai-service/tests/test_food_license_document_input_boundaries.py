from langchain_core.runnables import RunnableLambda

from app.models import ReviewInput, ReviewInputContext
from app.skills.food_license.extractors import (
    build_structured_extraction_chain,
    extract_food_license_fields,
)
from app.skills.food_license.models import FoodLicenseExtractedFields
from app.skills.food_license.loaders import StubFoodLicenseOcrAdapter, load_food_license_document
from app.skills.food_license.nodes import extract_fields, load_document
from app.skills.food_license.skill import food_license_skill


def _input_context(review_input: ReviewInput) -> ReviewInputContext:
    return ReviewInputContext(
        task_id="review-task-file-input",
        input=review_input,
        skill_name="food_license",
        skill_version="v1",
        ruleset_version="food-license-rules-v1",
    )


def test_review_input_accepts_pdf_file_input_boundary():
    review_input = ReviewInput(
        supplier_name="成都示例食品有限公司",
        supplier_credit_code="91510100MA00000000",
        declared_document_type="food_license",
        file={
            "filename": "food-license.pdf",
            "content_type": "application/pdf",
            "content_base64": "ZmFrZS1wZGY=",
        },
        source={"input_type": "pdf"},
    )

    payload = review_input.model_dump(mode="json")

    assert payload["ocr_text"] is None
    assert payload["file"]["content_type"] == "application/pdf"
    assert payload["file"]["filename"] == "food-license.pdf"


def test_stub_ocr_adapter_returns_fixed_text_for_pdf_or_image_input():
    adapter = StubFoodLicenseOcrAdapter(
        fixed_text="食品经营许可证\n经营者名称：成都示例食品有限公司\n许可证编号：JY15101000000000"
    )
    review_input = ReviewInput(
        supplier_name="成都示例食品有限公司",
        supplier_credit_code="91510100MA00000000",
        file={
            "filename": "food-license.png",
            "content_type": "image/png",
            "content_base64": "ZmFrZS1pbWFnZQ==",
        },
    )

    document = load_food_license_document(review_input, ocr_adapter=adapter)

    assert document.text.startswith("食品经营许可证")
    assert document.input_type == "image"
    assert document.metadata["filename"] == "food-license.png"


def test_load_document_uses_skill_internal_ocr_adapter_for_file_input():
    input_context = _input_context(
        ReviewInput(
            supplier_name="成都示例食品有限公司",
            supplier_credit_code="91510100MA00000000",
            file={
                "filename": "food-license.pdf",
                "content_type": "application/pdf",
                "content_base64": "ZmFrZS1wZGY=",
            },
            options={
                "stub_ocr_text": "食品经营许可证\n统一社会信用代码：91510100MA00000000\n许可证编号：JY15101000000000"
            },
        )
    )

    state = load_document({"input_context": input_context})

    assert state["document_text"].startswith("食品经营许可证")
    assert state["document_input_type"] == "pdf"
    assert state["document_metadata"]["filename"] == "food-license.pdf"


def test_langchain_structured_extraction_boundary_maps_to_food_license_fields():
    chain = build_structured_extraction_chain()
    fields = chain.invoke(
        {
            "document_text": "食品经营许可证\n经营者名称：成都示例食品有限公司\n统一社会信用代码：91510100MA00000000\n许可证编号：JY15101000000000\n经营项目：预包装食品销售\n有效期至：2099-01-01"
        }
    )

    assert fields.subject_name == "成都示例食品有限公司"
    assert fields.credit_code == "91510100MA00000000"
    assert fields.license_no == "JY15101000000000"
    assert fields.business_items == ["预包装食品销售"]


def test_extract_fields_falls_back_to_regex_when_structured_extraction_has_gaps():
    result = extract_food_license_fields(
        "食品经营许可证\n经营者名称：成都示例食品有限公司\n统一社会信用代码：91510100MA00000000\n许可证编号：JY15101000000000\n经营项目：预包装食品销售\n有效期至：2099-01-01",
        structured_extractor=RunnableLambda(lambda _: FoodLicenseExtractedFields()),
        llm_enabled=True,
    )

    fields = result.fields
    assert fields.subject_name == "成都示例食品有限公司"
    assert fields.credit_code == "91510100MA00000000"
    assert fields.license_no == "JY15101000000000"
    assert result.metadata["extraction_mode"] == "regex_only"


def test_extract_fields_node_uses_food_license_extractor_boundary():
    state = extract_fields(
        {
            "document_text": "食品经营许可证\n经营者名称：成都示例食品有限公司\n统一社会信用代码：91510100MA00000000\n许可证编号：JY15101000000000"
        }
    )

    assert state["extracted_fields"].license_no == "JY15101000000000"


def test_food_license_review_accepts_file_input_via_stub_ocr_boundary():
    result = food_license_skill.review(
        _input_context(
            ReviewInput(
                supplier_name="成都示例食品有限公司",
                supplier_credit_code="91510100MA00000000",
                file={
                    "filename": "food-license.pdf",
                    "content_type": "application/pdf",
                    "content_base64": "ZmFrZS1wZGY=",
                },
                options={
                    "stub_ocr_text": "食品经营许可证\n经营者名称：成都示例食品有限公司\n统一社会信用代码：91510100MA00000000\n许可证编号：JY15101000000000\n经营项目：预包装食品销售\n有效期至：2099-01-01"
                },
            )
        )
    )
    payload = result.model_dump(mode="json")

    assert result.needs_manual_review is False
    assert payload["skill_result"]["extracted_fields"]["license_no"] == "JY15101000000000"
    assert payload["skill_result"]["extraction_metadata"]["extraction_mode"] == "regex_only"
    assert "extraction_metadata" not in payload
    assert "extracted_fields" not in payload
