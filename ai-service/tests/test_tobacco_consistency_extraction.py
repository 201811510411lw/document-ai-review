from pathlib import Path
from types import SimpleNamespace

from app.integrations.starrocks.tobacco_license_sources import TobaccoLicenseSourceFile
from app.services.tobacco_consistency_extraction import (
    extract_consistency_document_results,
    resolved_consistency_fields,
)
from app.services.tobacco_license_files import (
    TobaccoLicenseStoredDocument,
    TobaccoLicenseStoredFile,
)


class StubReviewService:
    def __init__(self):
        self.calls = []

    def review(self, review_input, use_case_name=None):
        self.calls.append((review_input, use_case_name))
        return SimpleNamespace(
            skill_result={
                "normalized_fields": {
                    "document_type": use_case_name,
                    "subject_name": f"{use_case_name}-subject",
                }
            }
        )


class CandidateReviewService:
    def __init__(self, outcomes):
        self.outcomes = outcomes

    def review(self, review_input, use_case_name=None):
        outcome = self.outcomes[review_input.file.file_name]
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(skill_result={"normalized_fields": outcome})


def test_source_documents_are_reviewed_by_their_oa_document_role(tmp_path):
    service = StubReviewService()
    documents = [
        _stored_document(tmp_path, role="business_license", docid=1001),
        _stored_document(tmp_path, role="tobacco_license", docid=1002),
    ]

    results, errors = extract_consistency_document_results(
        documents,
        review_service=service,
        store_identifier="B65230024",
    )

    assert errors == {}
    assert set(results) == {"business_license", "tobacco_license"}
    assert [use_case_name for _, use_case_name in service.calls] == [
        "business_license",
        "tobacco_license",
    ]
    for review_input, use_case_name in service.calls:
        assert review_input.declared_document_type == use_case_name
        assert review_input.supplier_name == ""
        assert review_input.source["source_system"] == "oa_starrocks"
        assert review_input.source["attachment_ref_id"].startswith("oa:")
        assert Path(review_input.file.local_path).is_file()
        assert review_input.file.file_uri.startswith(
            "/api/v1/tobacco-license/source-files/local/"
        )
    inputs_by_use_case = {
        use_case_name: review_input
        for review_input, use_case_name in service.calls
    }
    assert inputs_by_use_case["business_license"].options == {}
    assert inputs_by_use_case["tobacco_license"].options == {
        "skip_rpa_verification": True,
    }


def test_manual_fields_override_only_non_empty_business_values():
    result = SimpleNamespace(
        skill_result={
            "normalized_fields": {
                "document_type": "tobacco_license",
                "subject_name": "证照主体",
                "business_address": "证照地址",
            }
        }
    )

    fields = resolved_consistency_fields(
        result,
        {
            "document_type": "business_license",
            "subject_name": "",
            "business_address": "人工修正地址",
        },
    )

    assert fields == {
        "document_type": "tobacco_license",
        "subject_name": "证照主体",
        "business_address": "人工修正地址",
    }


def test_conflicting_same_role_candidates_are_not_silently_selected(tmp_path):
    documents = [
        _stored_document(tmp_path, role="tobacco_license", docid=1001),
        _stored_document(tmp_path, role="tobacco_license", docid=1002),
    ]
    service = CandidateReviewService(
        {
            "tobacco_license-1001.jpg": {
                "document_type": "tobacco_license",
                "license_no": "A-001",
            },
            "tobacco_license-1002.jpg": {
                "document_type": "tobacco_license",
                "license_no": "B-002",
            },
        }
    )

    results, errors = extract_consistency_document_results(
        documents,
        review_service=service,
        store_identifier="B65230024",
    )

    assert "tobacco_license" not in results
    assert errors["tobacco_license"] == "MULTIPLE_CONFLICTING_CANDIDATES"


def test_usable_candidate_is_retained_when_another_attachment_fails(tmp_path):
    documents = [
        _stored_document(tmp_path, role="business_license", docid=1001),
        _stored_document(tmp_path, role="business_license", docid=1002),
    ]
    service = CandidateReviewService(
        {
            "business_license-1001.jpg": RuntimeError("unreadable image"),
            "business_license-1002.jpg": {
                "document_type": "business_license",
                "subject_name": "可用主体",
            },
        }
    )

    results, errors = extract_consistency_document_results(
        documents,
        review_service=service,
        store_identifier="B65230024",
    )

    assert results["business_license"].skill_result["normalized_fields"]["subject_name"] == "可用主体"
    assert "RuntimeError: unreadable image" in errors["business_license:business_license-1001.jpg"]


def _stored_document(tmp_path, *, role, docid):
    local_path = tmp_path / f"{role}-{docid}.jpg"
    local_path.write_bytes(b"image")
    source = TobaccoLicenseSourceFile(
        store_code="B65230024",
        requestid=2801287,
        docid=docid,
        imagefile_id=docid + 10,
        document_role=role,
        file_real_path="/data/oaec/example.jpg",
    )
    return TobaccoLicenseStoredDocument(
        source=source,
        output_dir=str(tmp_path),
        files=[
            TobaccoLicenseStoredFile(
                file_name=local_path.name,
                relative_path=local_path.name,
                local_path=str(local_path),
                content_type="image/jpeg",
                file_size=local_path.stat().st_size,
            )
        ],
    )
