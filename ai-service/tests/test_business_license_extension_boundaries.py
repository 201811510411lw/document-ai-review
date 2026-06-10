from pathlib import Path


def test_business_license_prd_documents_single_certificate_extension_boundaries():
    prd = Path("../docs/prd-business-license-review-v1.md").read_text(encoding="utf-8")

    assert "## Extension Boundaries for #34" in prd
    assert "business_license capability 只负责营业执照单证" in prd
    assert "来源记录标准化、远程文档获取、规则执行、ReviewResult 映射、SQLite 投影" in prd
    assert "不实现烟草证字段模型" in prd
    assert "不实现双证一致性规则" in prd
    assert "不实现 OA 回写" in prd
    assert "不实现企微通知" in prd
    assert "证照专属内容放入 skill_result 和对应投影表" in prd
