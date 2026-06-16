from app.tools.vision_adapter import (
    build_business_license_vision_adapter,
    parse_business_license_vision_json,
    reject_source_mismatched_fields,
)


def test_business_license_vision_adapter_defaults_to_aliyun(monkeypatch):
    monkeypatch.delenv("BUSINESS_LICENSE_VISION_PROVIDER", raising=False)

    adapter = build_business_license_vision_adapter()

    assert adapter.__class__.__name__ == "AliyunCloudMarketOcrAdapter"


def test_business_license_vision_adapter_unknown_provider_falls_back_to_fake(monkeypatch):
    monkeypatch.setenv("BUSINESS_LICENSE_VISION_PROVIDER", "fake")

    adapter = build_business_license_vision_adapter()

    assert adapter.implementation_status == "fake"


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
