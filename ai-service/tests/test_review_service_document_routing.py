from types import SimpleNamespace

from app.services.review_service import _reroute_document_type


def _input(document_type: str):
    return SimpleNamespace(declared_document_type=document_type)


def _result(document_type: str, **skill_result):
    return SimpleNamespace(document_type=document_type, skill_result=skill_result)


def test_reroutes_between_license_workflows_when_content_type_conflicts():
    target = _reroute_document_type(
        review_input=_input("business_license"),
        result=_result("food_production_license"),
    )

    assert target == "food_production_license"


def test_reroutes_to_qc_workflow_for_recognized_product_report_title():
    target = _reroute_document_type(
        review_input=_input("food_license"),
        result=_result(
            "food_license",
            extracted_fields={"document_type_raw": "第三方检验报告"},
        ),
    )

    assert target == "product_report"


def test_does_not_reroute_when_content_type_matches_source_declaration():
    target = _reroute_document_type(
        review_input=_input("tobacco_license"),
        result=_result("tobacco_license"),
    )

    assert target is None
