from scripts.review_one_srm_business_license import _debug_enabled, _summary_payload


def test_debug_enabled_follows_document_ai_review_debug_env(monkeypatch):
    monkeypatch.setenv("DOCUMENT_AI_REVIEW_DEBUG", "false")
    assert _debug_enabled() is False

    monkeypatch.setenv("DOCUMENT_AI_REVIEW_DEBUG", "true")
    assert _debug_enabled() is True


def test_summary_payload_keeps_compliance_signal_without_full_skill_result():
    payload = {
        "task_id": "review-task-000001",
        "document_type": "business_license",
        "status": "REVIEWED",
        "risk_level": "NONE",
        "needs_manual_review": False,
        "summary": "营业执照规则校验通过",
        "manual_review": {"reasons": []},
        "rule_results": [
            {
                "rule_code": "BUSINESS_LICENSE_VALIDITY_PERIOD",
                "rule_name": "营业执照有效期",
                "passed": True,
                "message": "营业执照未识别到有效期，按长期有效处理",
                "details": {"assumed_long_term": True},
            }
        ],
        "skill_result": {
            "document_input": {
                "file_name": "营业执照.jpg",
                "source_url": "https://files.example.test/license.jpg",
            },
            "extracted_fields": {
                "subject_name": "成都示例商贸有限公司",
                "credit_code": "91510100MA0000000X",
                "valid_from": "2018-04-10",
                "valid_to": None,
                "valid_to_evidence": "营业期限2018年4月10日至永久",
                "business_address": "不应出现在摘要输出里",
            },
            "normalized_fields": {
                "business_address": "不应出现在摘要输出里",
            },
        },
    }

    summary = _summary_payload(payload)

    assert summary == {
        "task_id": "review-task-000001",
        "document_type": "business_license",
        "status": "REVIEWED",
        "risk_level": "NONE",
        "needs_manual_review": False,
        "summary": "营业执照规则校验通过",
        "manual_review_reasons": [],
        "failed_rules": [],
        "extracted_fields": {
            "subject_name": "成都示例商贸有限公司",
            "credit_code": "91510100MA0000000X",
            "valid_from": "2018-04-10",
            "valid_to": None,
            "valid_to_evidence": "营业期限2018年4月10日至永久",
        },
        "document_input": {
            "file_name": "营业执照.jpg",
            "source_url": "https://files.example.test/license.jpg",
        },
    }
