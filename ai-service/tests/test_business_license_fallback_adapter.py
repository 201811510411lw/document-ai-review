from app.tools.business_license_fallback_adapter import (
    QwenOcrWithAliyunFallbackBusinessLicenseAdapter,
    validate_business_license_ocr_result,
)


class StubAdapter:
    implementation_status = "configured"

    def __init__(self, result):
        self.result = result
        self.calls = []

    def extract_text(self, source):
        self.calls.append(source)
        return self.result


def test_validate_business_license_ocr_result_ignores_credit_code_symbols():
    validation = validate_business_license_ocr_result(
        {
            "structured_fields": {
                "document_type": "business_license",
                "subject_name": "廖记食品有限责任公司",
                "credit_code": "统一社会信用代码：９１５１０１３２-MA6AULU68M",
                "valid_to": "长期",
                "subject_name_evidence": "名称 廖记食品有限责任公司",
                "credit_code_evidence": "统一社会信用代码 ９１５１０１３２-MA6AULU68M",
            },
            "metadata": {},
        },
        expected_subject_name="廖记食品有限责任公司",
        expected_credit_code="91510132 MA6AULU68M",
    )

    assert validation == {"passed": True, "failure_reasons": []}


def test_fallback_adapter_uses_qwen_result_when_validation_passes():
    primary = StubAdapter(
        {
            "text": "qwen text",
            "structured_fields": {
                "document_type": "business_license",
                "subject_name": "廖记食品有限责任公司",
                "credit_code": "91510132MA6AULU68M",
                "valid_to": "长期",
                "subject_name_evidence": "名称 廖记食品有限责任公司",
                "credit_code_evidence": "统一社会信用代码 91510132MA6AULU68M",
            },
            "metadata": {"provider": "qwen_ocr"},
        }
    )
    fallback = StubAdapter({"text": "fallback should not be called", "metadata": {}})

    result = QwenOcrWithAliyunFallbackBusinessLicenseAdapter(
        primary_adapter=primary,
        fallback_adapter=fallback,
    ).extract_text(
        {
            "expected_subject_name": "廖记食品有限责任公司",
            "expected_credit_code": "91510132 MA6AULU68M",
        }
    )

    assert result["text"] == "qwen text"
    assert fallback.calls == []
    assert result["metadata"]["fallback_used"] is False
    assert result["metadata"]["final_provider"] == "qwen_ocr"


def test_fallback_adapter_uses_aliyun_when_qwen_missing_key_field_evidence():
    primary = StubAdapter(
        {
            "text": "qwen text",
            "structured_fields": {
                "document_type": "business_license",
                "subject_name": "廖记食品有限责任公司",
                "credit_code": "91510132MA6AULU68M",
                "valid_to": "长期",
            },
            "metadata": {"provider": "qwen_ocr"},
        }
    )
    fallback = StubAdapter(
        {
            "text": "aliyun text",
            "structured_fields": {
                "document_type": "business_license",
                "subject_name": "廖记食品有限责任公司",
                "credit_code": "91510132MA6AULU68M",
                "valid_to": "长期",
                "subject_name_evidence": "名称 廖记食品有限责任公司",
                "credit_code_evidence": "统一社会信用代码 91510132MA6AULU68M",
            },
            "metadata": {"provider": "aliyun_cloud_market_ocr"},
        }
    )

    result = QwenOcrWithAliyunFallbackBusinessLicenseAdapter(
        primary_adapter=primary,
        fallback_adapter=fallback,
    ).extract_text(
        {
            "expected_subject_name": "廖记食品有限责任公司",
            "expected_credit_code": "91510132MA6AULU68M",
        }
    )

    assert result["text"] == "aliyun text"
    assert result["metadata"]["fallback_used"] is True
    assert result["metadata"]["fallback_trigger"] == "subject_name_evidence_missing"
    assert result["metadata"]["primary_validation"] == {
        "passed": False,
        "failure_reasons": [
            "subject_name_evidence_missing",
            "credit_code_evidence_missing",
        ],
    }


def test_fallback_adapter_uses_aliyun_when_qwen_missing_secondary_fields():
    primary = StubAdapter(
        {
            "text": "qwen text",
            "structured_fields": {
                "document_type": "business_license",
                "subject_name": "四川不俗供应链管理有限公司",
                "credit_code": "91510100MACJ2J6A94",
                "legal_person": None,
                "valid_from": None,
                "valid_to": None,
                "subject_name_evidence": "名称 四川不俗供应链管理有限公司",
                "credit_code_evidence": "统一社会信用代码 91510100MACJ2J6A94",
            },
            "metadata": {"provider": "qwen_ocr"},
        }
    )
    fallback = StubAdapter(
        {
            "text": "aliyun text",
            "structured_fields": {
                "document_type": "business_license",
                "subject_name": "四川不俗供应链管理有限公司",
                "credit_code": "91510100MACJ2J6A94",
                "legal_person": "陈胜",
                "established_date": "2023-05-04",
                "valid_from": "2023-05-04",
                "valid_to": "长期",
                "subject_name_evidence": "名称 四川不俗供应链管理有限公司",
                "credit_code_evidence": "统一社会信用代码 91510100MACJ2J6A94",
            },
            "metadata": {"provider": "aliyun_cloud_market_ocr"},
        }
    )

    result = QwenOcrWithAliyunFallbackBusinessLicenseAdapter(
        primary_adapter=primary,
        fallback_adapter=fallback,
    ).extract_text(
        {
            "expected_subject_name": "四川不俗供应链管理有限公司",
            "expected_credit_code": "91510100MACJ2J6A94",
        }
    )

    assert result["text"] == "aliyun text"
    assert len(fallback.calls) == 1
    assert result["structured_fields"]["legal_person"] == "陈胜"
    assert result["structured_fields"]["valid_to"] == "长期"
    assert result["metadata"]["fallback_used"] is True
    assert result["metadata"]["fallback_trigger"] == "secondary_fields_missing"


def test_fallback_adapter_uses_aliyun_when_qwen_subject_mismatches():
    primary = StubAdapter(
        {
            "text": "qwen text",
            "structured_fields": {
                "document_type": "business_license",
                "subject_name": "成都迅成食品有限责任公司",
                "credit_code": "91510132MA6AULU68M",
                "subject_name_evidence": "名称 成都迅成食品有限责任公司",
                "credit_code_evidence": "统一社会信用代码 91510132MA6AULU68M",
            },
            "metadata": {
                "provider": "qwen_ocr",
                "structured_extraction": "qwen_ocr_page_filter",
                "mismatched_fields": {
                    "subject_name": {
                        "expected": "廖记食品有限责任公司",
                        "actual": "成都迅成食品有限责任公司",
                    }
                },
            },
        }
    )
    fallback = StubAdapter(
        {
            "text": "aliyun text",
            "structured_fields": {
                "document_type": "business_license",
                "subject_name": "廖记食品有限责任公司",
                "credit_code": "91510132MA6AULU68M",
                "valid_to": "长期",
                "subject_name_evidence": "名称 廖记食品有限责任公司",
                "credit_code_evidence": "统一社会信用代码 91510132MA6AULU68M",
            },
            "metadata": {"provider": "aliyun_cloud_market_ocr"},
        }
    )

    result = QwenOcrWithAliyunFallbackBusinessLicenseAdapter(
        primary_adapter=primary,
        fallback_adapter=fallback,
    ).extract_text(
        {
            "expected_subject_name": "廖记食品有限责任公司",
            "expected_credit_code": "91510132 MA6AULU68M",
        }
    )

    assert result["text"] == "aliyun text"
    assert len(fallback.calls) == 1
    assert result["structured_fields"]["subject_name"] == "廖记食品有限责任公司"
    assert result["metadata"]["provider"] == "qwen_ocr_with_aliyun_fallback"
    assert result["metadata"]["final_provider"] == "aliyun_cloud_market_ocr"
    assert result["metadata"]["fallback_used"] is True
    assert result["metadata"]["fallback_trigger"] == "subject_name_mismatch"
    assert result["metadata"]["primary_validation"] == {
        "passed": False,
        "failure_reasons": ["subject_name_mismatch", "secondary_fields_missing"],
    }
    assert result["metadata"]["fallback_validation"] == {
        "passed": True,
        "failure_reasons": [],
    }
