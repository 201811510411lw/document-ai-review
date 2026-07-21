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
