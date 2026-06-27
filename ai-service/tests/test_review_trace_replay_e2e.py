from app.models import ReviewDocumentInput, ReviewInput
from app.services.review_service import ReviewService
from app.workflows.runtime.trace import build_review_graph_trace
from app.workflows.tobacco_license import workflow as tobacco_license_workflow
from tests.pdf_helpers import write_minimal_pdf


BUSINESS_FIELDS = {
    "document_type": "business_license",
    "subject_name": "成都示例商贸有限公司",
    "credit_code": "91510100MA0000000X",
    "business_address": "成都市高新区天府大道 1 号",
    "legal_person": "张三",
    "valid_to": "长期有效",
    "subject_name_evidence": "名称：成都示例商贸有限公司",
    "credit_code_evidence": "统一社会信用代码：91510100MA0000000X",
    "valid_to_evidence": "营业期限：长期有效",
}

TOBACCO_FIELDS = {
    "document_type": "tobacco_license",
    "subject_name": "成都示例烟草商行",
    "business_address": "成都市高新区天府大道 1 号",
    "legal_person": "张三",
    "license_no": "烟专零售许第510100000001号",
    "valid_to": "2099-12-31",
}


class StubFileAdapter:
    def __init__(self, fields):
        self.fields = fields

    def extract_text(self, source):
        return {
            "text": "",
            "structured_fields": self.fields,
            "metadata": {"implementation_status": "stub"},
        }


def test_business_license_success_trace_replay(tmp_path, monkeypatch):
    monkeypatch.setenv("BUSINESS_LICENSE_FAKE_VISION_JSON", _json_like(BUSINESS_FIELDS))

    result = ReviewService().review(
        _business_input(tmp_path),
        use_case_name="business_license",
    )
    trace = _trace_from_result(
        result,
        events=[
            {"step": "classify_document", "kind": "route", "route": "extract_fields"},
            {"step": "summarize_risk", "kind": "route", "route": "reviewed"},
        ],
    )

    assert trace["final"]["status"] == "REVIEWED"
    assert trace["final"]["risk_level"] == "NONE"
    assert trace["events"][-1]["route"] == "reviewed"


def test_business_license_invalid_document_trace_replay(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "BUSINESS_LICENSE_FAKE_VISION_JSON",
        _json_like({**BUSINESS_FIELDS, "document_type": "food_license"}),
    )

    result = ReviewService().review(
        _business_input(tmp_path),
        use_case_name="business_license",
    )
    trace = _trace_from_result(
        result,
        events=[
            {"step": "classify_document", "kind": "route", "route": "reject"},
        ],
    )

    assert trace["final"]["status"] == "FAILED"
    assert trace["events"][0]["route"] == "reject"


def test_tobacco_license_manual_review_trace_replay(tmp_path, monkeypatch):
    monkeypatch.setattr(
        tobacco_license_workflow,
        "tobacco_license_file_adapter",
        StubFileAdapter({"document_type": "tobacco_license", "license_no": "烟专零售许第1号"}),
    )

    result = ReviewService().review(
        _tobacco_input(tmp_path),
        use_case_name="tobacco_license",
    )
    trace = _trace_from_result(
        result,
        events=[
            {"step": "summarize_risk", "kind": "route", "route": "manual_review"},
        ],
    )

    assert trace["final"]["status"] == "PENDING_MANUAL_REVIEW"
    assert trace["final"]["risk_level"] == "MEDIUM"
    assert "subject_name 缺失" in trace["final"]["manual_review_reasons"]


def _trace_from_result(result, events):
    return build_review_graph_trace(
        graph_name=result.use_case_name,
        graph_version=result.use_case_version,
        ruleset_version=result.ruleset_version,
        task_id=result.task_id,
        events=events,
        document_type=result.document_type,
        status=result.status,
        risk_level=result.risk_level,
        needs_manual_review=result.needs_manual_review,
        rule_results=result.rule_results,
        manual_review=result.manual_review,
    )


def _business_input(tmp_path):
    image_path = tmp_path / "business-license.png"
    image_path.write_bytes(b"fake-image-bytes")
    return ReviewInput(
        file=ReviewDocumentInput(
            local_path=str(image_path),
            file_name="business-license.png",
            mime_type="image/png",
            document_format="image",
        ),
        supplier_name="成都示例商贸有限公司",
        supplier_credit_code="91510100MA0000000X",
        declared_document_type="business_license",
    )


def _tobacco_input(tmp_path):
    pdf_path = tmp_path / "tobacco-license.pdf"
    write_minimal_pdf(pdf_path, "embedded text should not be used")
    return ReviewInput(
        file=ReviewDocumentInput(
            local_path=str(pdf_path),
            file_name="tobacco-license.pdf",
            mime_type="application/pdf",
            document_format="pdf",
        ),
        supplier_name="成都示例烟草商行",
        supplier_credit_code="91510100MA0000000X",
        declared_document_type="tobacco_license",
    )


def _json_like(fields):
    import json

    return json.dumps(fields, ensure_ascii=False)
