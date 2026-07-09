from app.models import ReviewInput
from app.services.review_service import ReviewService


def test_qc_document_review_reviews_batch_report_from_ocr_text():
    result = ReviewService().review(
        ReviewInput(
            supplier_name="广州市秀雅秀贸易有限公司（常温）",
            supplier_credit_code="",
            declared_document_type="batch_report",
            ocr_text="""
            商品批次报告
            厂名：广州市秀雅秀贸易有限公司（常温）
            产品名称：游世佳族金唱片面包
            生产日期：2026年05月08日
            """,
            source={
                "sku_name": "游世佳族金唱片面包",
                "production_date": "2026-05-08",
            },
        ),
        use_case_name="qc_document_review",
    )

    assert result.document_type == "batch_report"
    assert result.status == "REVIEWED"
    assert result.needs_manual_review is False
    assert result.skill_result["extracted_fields"]["product_name"] == "游世佳族金唱片面包"
    assert result.skill_result["extracted_fields"]["production_date"] == "2026-05-08"


def test_qc_document_review_routes_blank_batch_report_to_manual_review():
    result = ReviewService().review(
        ReviewInput(
            supplier_name="广州市秀雅秀贸易有限公司（常温）",
            supplier_credit_code="",
            declared_document_type="batch_report",
            source={
                "sku_name": "游世佳族金唱片面包",
                "production_date": "2026-05-08",
            },
        ),
        use_case_name="qc_document_review",
    )

    assert result.document_type == "batch_report"
    assert result.status == "PENDING_MANUAL_REVIEW"
    assert result.needs_manual_review is True
    assert "批次报告附件未获取到可审核文本" in result.manual_review.reasons[0]


def test_qc_document_review_extracts_multiline_sample_name_and_title_producer():
    result = ReviewService().review(
        ReviewInput(
            supplier_name="内蒙古伊利实业集团股份有限公司",
            supplier_credit_code="",
            declared_document_type="batch_report",
            ocr_text="""
            液态奶事业部
            湖北黄冈伊利乳业有限责任公司产品检验报告
            编号：2025050719829-YLHG-2025050033
            样品名称
            伊刻活泉现泡茶茉莉花茶固体
            饮料
            生产日期 20250506
            检验结论 检测结果符合标准要求，产品合格。
            """,
            source={
                "vendor_name": "内蒙古伊利实业集团股份有限公司",
                "sku_name": "伊利伊刻活泉现泡茶茉莉花茶",
                "production_date": "2026-04-07",
            },
        ),
        use_case_name="qc_document_review",
    )

    fields = result.skill_result["extracted_fields"]
    assert fields["producer_name"] == "湖北黄冈伊利乳业有限责任公司"
    assert fields["product_name"] == "伊刻活泉现泡茶茉莉花茶固体"
    assert fields["production_date"] == "2025-05-06"
    assert result.status == "PENDING_MANUAL_REVIEW"
    assert "生产日期" in result.manual_review.reasons[-1]
