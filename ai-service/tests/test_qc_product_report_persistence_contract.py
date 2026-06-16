from app.models import ReviewInput
from app.integrations.mysql_client import MySqlSettings
from app.repositories import MySQLReviewResultRepository
from app.services.review_service import ReviewService
from tests.mysql_repository_stub import install_mysql_repository_stub


def test_mysql_repository_saves_product_report_projection_and_items(monkeypatch):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    service = ReviewService(repository=repository)

    result = service.review(
        ReviewInput(
            ocr_text="""
            产品检验报告
            报告编号：BG-20260610-001
            样品名称：麻辣牛肉
            受检单位：成都示例食品有限公司
            生产单位：成都示例食品厂
            批号：20260601-A
            生产日期：2026年06月01日
            签发日期：2026年06月10日
            检验结论：经检验，所检项目符合要求。
            检验项目：
            1. 菌落总数 120 CFU/g
            2. 大肠菌群 未检出
            """,
            supplier_name="成都示例食品有限公司",
            supplier_credit_code="91510100MA00000000",
            declared_document_type="product_report",
            source={
                "record_id": "cert-001",
                "attachment_ref_id": "att-001",
                "tenant": "8560",
            },
        ),
        use_case_name="qc_document_review",
    )

    snapshot = repository.get_product_report_snapshot(result.task_id)

    assert snapshot is not None
    assert snapshot["task_id"] == result.task_id
    assert snapshot["document_type"] == "product_report"
    assert snapshot["source_record_id"] == "cert-001"
    assert snapshot["source_attachment_ref_id"] == "att-001"
    assert snapshot["tenant"] == "8560"
    assert snapshot["product_name"] == "麻辣牛肉"
    assert snapshot["vendor_name"] == "成都示例食品有限公司"
    assert snapshot["vendor_name_extracted"] == "成都示例食品有限公司"
    assert snapshot["manufacturer_name"] == "成都示例食品厂"
    assert snapshot["batch_no"] == "20260601-A"
    assert snapshot["production_date"] == "2026-06-01"
    assert snapshot["issue_date"] == "2026-06-10"
    assert snapshot["review_status"] == "REVIEWED"
    assert snapshot["risk_level"] == "NONE"
    assert snapshot["needs_manual_review"] is False
    assert snapshot["inspection_items"] == [
        {"name": "菌落总数", "result": "120 CFU/g"},
        {"name": "大肠菌群", "result": "未检出"},
    ]
    assert snapshot["source_evidence"]["source"]["record_id"] == "cert-001"


def test_mysql_repository_replaces_product_report_item_rows_on_update(monkeypatch):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    service = ReviewService(repository=repository)

    result = service.review(
        ReviewInput(
            ocr_text="""
            产品检验报告
            样品名称：麻辣牛肉
            受检单位：成都示例食品有限公司
            批号：20260601-A
            签发日期：2026年06月10日
            检验结论：合格
            检验项目：
            1. 菌落总数 120 CFU/g
            """,
            supplier_name="成都示例食品有限公司",
            supplier_credit_code="91510100MA00000000",
            declared_document_type="product_report",
        ),
        use_case_name="qc_document_review",
    )

    updated = result.model_copy(
        update={
            "skill_result": {
                **result.skill_result,
                "extracted_fields": {
                    **result.skill_result["extracted_fields"],
                    "inspection_items": [
                        {"name": "大肠菌群", "result": "未检出"},
                        {"name": "沙门氏菌", "result": "未检出"},
                    ],
                },
            }
        }
    )
    repository.save(updated)

    snapshot = repository.get_product_report_snapshot(result.task_id)

    assert snapshot is not None
    assert snapshot["inspection_items"] == [
        {"name": "大肠菌群", "result": "未检出"},
        {"name": "沙门氏菌", "result": "未检出"},
    ]


def _repository() -> MySQLReviewResultRepository:
    return MySQLReviewResultRepository(
        MySqlSettings(
            host="127.0.0.1",
            port=3306,
            user="review",
            password="secret",
            database="document_ai_review",
        )
    )
