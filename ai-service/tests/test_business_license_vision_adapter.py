from app.tools.vision_adapter import (
    UnsupportedVisionProviderError,
    build_business_license_vision_adapter,
    build_food_license_file_adapter,
    build_food_production_license_file_adapter,
    parse_business_license_vision_json,
    reject_source_mismatched_fields,
)


def test_business_license_vision_adapter_defaults_to_aliyun(monkeypatch):
    monkeypatch.setenv("BUSINESS_LICENSE_VISION_PROVIDER", "")

    adapter = build_business_license_vision_adapter()

    assert adapter.__class__.__name__ == "AliyunCloudMarketOcrAdapter"


def test_business_license_vision_adapter_rejects_unknown_provider(monkeypatch):
    monkeypatch.setenv("BUSINESS_LICENSE_VISION_PROVIDER", "fake")

    import pytest

    with pytest.raises(UnsupportedVisionProviderError):
        build_business_license_vision_adapter()


def test_business_license_vision_adapter_can_build_qwen_ocr(monkeypatch):
    monkeypatch.setenv("BUSINESS_LICENSE_VISION_PROVIDER", "qwen_ocr")
    monkeypatch.setenv("BUSINESS_LICENSE_QWEN_OCR_MODEL", "qwen3.5-ocr")

    adapter = build_business_license_vision_adapter()

    assert adapter.__class__.__name__ == "QwenOcrBusinessLicenseAdapter"
    assert adapter.model == "qwen3.5-ocr"


def test_business_license_vision_adapter_can_build_qwen_ocr_with_aliyun_fallback(monkeypatch):
    monkeypatch.setenv("BUSINESS_LICENSE_VISION_PROVIDER", "qwen_ocr_with_aliyun_fallback")

    adapter = build_business_license_vision_adapter()

    assert adapter.__class__.__name__ == "QwenOcrWithAliyunFallbackBusinessLicenseAdapter"


def test_food_license_file_adapter_defaults_to_qwen_with_aliyun_fallback(monkeypatch):
    monkeypatch.delenv("FOOD_LICENSE_FILE_RECOGNITION_PROVIDER", raising=False)
    monkeypatch.setenv("BUSINESS_LICENSE_QWEN_OCR_MODEL", "qwen3.5-ocr")

    adapter = build_food_license_file_adapter()

    assert adapter.__class__.__name__ == "QwenOcrWithAliyunFallbackFoodLicenseAdapter"
    assert adapter.primary_adapter.model == "qwen3.5-ocr"
    assert adapter.fallback_adapter.__class__.__name__ == "AliyunOcrTextAdapter"


def test_food_license_file_adapter_can_build_qwen_only(monkeypatch):
    monkeypatch.setenv("FOOD_LICENSE_FILE_RECOGNITION_PROVIDER", "qwen_ocr")
    monkeypatch.setenv("FOOD_LICENSE_QWEN_OCR_MODEL", "qwen-vl-plus")
    monkeypatch.setenv("BUSINESS_LICENSE_QWEN_OCR_MODEL", "qwen3.5-ocr")

    adapter = build_food_license_file_adapter()

    assert adapter.__class__.__name__ == "QwenOcrFoodLicenseAdapter"
    assert adapter.model == "qwen-vl-plus"


def test_food_license_file_adapter_rejects_unknown_provider(monkeypatch):
    monkeypatch.setenv("FOOD_LICENSE_FILE_RECOGNITION_PROVIDER", "fake")

    import pytest

    with pytest.raises(UnsupportedVisionProviderError):
        build_food_license_file_adapter()


def test_food_license_file_recognition_instruction_prevents_license_number_as_credit_code():
    from app.tools.food_license_ocr_adapter import food_license_qwen_ocr_prompt

    prompt = food_license_qwen_ocr_prompt()
    assert "不要把许可证编号" in prompt
    assert "license_no" in prompt


def test_food_production_license_file_adapter_defaults_to_qwen_with_aliyun_fallback(
    monkeypatch,
):
    monkeypatch.delenv("FOOD_PRODUCTION_LICENSE_FILE_RECOGNITION_PROVIDER", raising=False)
    monkeypatch.setenv("BUSINESS_LICENSE_QWEN_OCR_MODEL", "qwen3.5-ocr")

    adapter = build_food_production_license_file_adapter()

    assert (
        adapter.__class__.__name__
        == "QwenOcrWithAliyunFallbackFoodProductionLicenseAdapter"
    )
    assert adapter.primary_adapter.model == "qwen3.5-ocr"
    assert adapter.fallback_adapter.__class__.__name__ == "AliyunOcrTextAdapter"


def test_food_production_license_file_adapter_can_build_qwen_only(monkeypatch):
    monkeypatch.setenv("FOOD_PRODUCTION_LICENSE_FILE_RECOGNITION_PROVIDER", "qwen_ocr")
    monkeypatch.setenv("FOOD_PRODUCTION_LICENSE_QWEN_OCR_MODEL", "qwen-vl-plus")
    monkeypatch.setenv("BUSINESS_LICENSE_QWEN_OCR_MODEL", "qwen3.5-ocr")

    adapter = build_food_production_license_file_adapter()

    assert adapter.__class__.__name__ == "QwenOcrFoodProductionLicenseAdapter"
    assert adapter.model == "qwen-vl-plus"


def test_food_production_license_file_adapter_rejects_unknown_provider(monkeypatch):
    monkeypatch.setenv("FOOD_PRODUCTION_LICENSE_FILE_RECOGNITION_PROVIDER", "fake")

    import pytest

    with pytest.raises(UnsupportedVisionProviderError):
        build_food_production_license_file_adapter()


def test_food_production_license_file_recognition_instruction_prevents_license_number_as_credit_code():
    from app.tools.food_production_license_ocr_adapter import (
        food_production_license_qwen_ocr_prompt,
    )

    prompt = food_production_license_qwen_ocr_prompt()
    assert "不要把许可证编号" in prompt
    assert "license_no" in prompt
    assert "SC" in prompt
    assert "开头" in prompt


def test_reject_source_mismatched_fields_records_mismatch_without_hiding_fields():
    result = reject_source_mismatched_fields(
        {
            "text": '{"document_type":"business_license"}',
            "structured_fields": {
                "document_type": "business_license",
                "subject_name": "广安市屈臣氏食品有限公司",
                "credit_code": "91510132MA6ALUL68M",
                "business_address": "广安市岳池县花园镇广场街",
                "issue_authority": "广安市市场监督管理局",
                "subject_name_evidence": "名称：广安市屈臣氏食品有限公司",
                "credit_code_evidence": "统一社会信用代码：91510132MA6ALUL68M",
            },
            "metadata": {"implementation_status": "configured"},
        },
        expected_subject_name="廖记食品有限责任公司",
        expected_credit_code="91510132 MA6AULU68M",
    )

    assert result["structured_fields"]["subject_name"] == "广安市屈臣氏食品有限公司"
    assert result["structured_fields"]["credit_code"] == "91510132MA6ALUL68M"
    assert result["structured_fields"]["business_address"] == "广安市岳池县花园镇广场街"
    assert result["structured_fields"]["issue_authority"] == "广安市市场监督管理局"
    assert result["structured_fields"]["subject_name_evidence"] == "名称：广安市屈臣氏食品有限公司"
    assert result["structured_fields"]["credit_code_evidence"] == "统一社会信用代码：91510132MA6ALUL68M"
    assert result["metadata"]["mismatched_fields"] == {
        "subject_name": {
            "expected": "廖记食品有限责任公司",
            "actual": "广安市屈臣氏食品有限公司",
            "reason": "source_mismatch",
        },
        "credit_code": {
            "expected": "91510132 MA6AULU68M",
            "actual": "91510132MA6ALUL68M",
            "reason": "source_mismatch",
        },
    }
    assert result["metadata"]["rejected_fields"] == result["metadata"]["mismatched_fields"]


def test_reject_source_mismatched_fields_ignores_credit_code_format_noise():
    result = reject_source_mismatched_fields(
        {
            "structured_fields": {
                "document_type": "business_license",
                "subject_name": "廖记食品有限责任公司",
                "credit_code": "统一社会信用代码：９１５１０１３２-MA6AULU68M",
            },
            "metadata": {"implementation_status": "configured"},
        },
        expected_subject_name="廖记食品有限责任公司",
        expected_credit_code="91510132 MA6AULU68M",
    )

    assert "mismatched_fields" not in result["metadata"]


def test_parse_business_license_vision_json_accepts_markdown_json_block():
    parsed = parse_business_license_vision_json(
        """
        ```json
        {
          "document_type": "business_license",
          "subject_name": "成都示例商贸有限公司"
        }
        ```
        """
    )

    assert parsed == {
        "document_type": "business_license",
        "subject_name": "成都示例商贸有限公司",
    }
