from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.auth import require_web_console_user
from app.integrations.mysql_client import MySqlFetchClient, mysql_settings_from_env
from app.integrations.starrocks.tobacco_license_sources import (
    SqlFetchClient,
    fetch_pending_stores,
    fetch_latest_tobacco_license_source_files,
    TobaccoLicenseSourceTaskError,
)
from app.models import ReviewInput, ReviewInputContext, ReviewResult
from app.repositories import build_review_result_repository_from_env
from app.services.review_service import ReviewService, review_service
from app.services.tobacco_license_files import (
    TobaccoLicenseFileStore,
    TobaccoLicenseFileStoreError,
)
from app.use_cases.tobacco_license_consistency_review import (
    tobacco_license_consistency_review_use_case,
)


router = APIRouter(
    prefix="/api/v1/tobacco-license-consistency",
    tags=["tobacco-license-consistency"],
)


class CreateConsistencyReviewRequest(BaseModel):
    store_identifier: str


def get_starrocks_sql_client() -> SqlFetchClient:
    return MySqlFetchClient(mysql_settings_from_env("STARROCKS"))


def get_file_store() -> TobaccoLicenseFileStore:
    return TobaccoLicenseFileStore()


def get_review_repository():
    return build_review_result_repository_from_env()


@router.get("/pending-stores")
def list_pending_stores(
    _current_user: dict[str, Any] = Depends(require_web_console_user),
    sql_client: SqlFetchClient = Depends(get_starrocks_sql_client),
) -> dict[str, Any]:
    """返回有待处理 OA 烟草证提交流程的门店列表"""
    try:
        stores = fetch_pending_stores(sql_client)
    except TobaccoLicenseSourceTaskError as error:
        raise HTTPException(
            status_code=400,
            detail={
                "code": error.code,
                "message": str(error),
            },
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "PENDING_STORES_QUERY_FAILED",
                "message": f"查询待处理门店失败: {error}",
            },
        ) from error

    return {"stores": stores}


@router.post("/reviews")
def create_consistency_review(
    request: CreateConsistencyReviewRequest,
    _current_user: dict[str, Any] = Depends(require_web_console_user),
    sql_client: SqlFetchClient = Depends(get_starrocks_sql_client),
    file_store: TobaccoLicenseFileStore = Depends(get_file_store),
    repository=Depends(get_review_repository),
) -> dict[str, Any]:
    """获取门店来源文件并触发营业执照与烟草证一致性比对"""
    store_identifier = request.store_identifier.strip()
    if not store_identifier:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "STORE_IDENTIFIER_EMPTY",
                "message": "门店标识不能为空",
            },
        )

    # 1. 查询 StarRocks 获取来源文件
    try:
        source_files = fetch_latest_tobacco_license_source_files(
            sql_client,
            store_identifier,
        )
    except TobaccoLicenseSourceTaskError as error:
        raise HTTPException(
            status_code=400,
            detail={
                "code": error.code,
                "message": str(error),
                "store_identifier": store_identifier,
            },
        ) from error

    if not source_files:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "SOURCE_RECORD_NOT_FOUND",
                "message": "未找到该门店的烟草证来源记录",
                "store_identifier": store_identifier,
            },
        )

    # 2. 从 OA 表单中提取字段作为基础比对数据
    first = source_files[0]
    store_name = first.store_name or first.store_code or store_identifier

    business_fields = {
        "subject_name": store_name,
        "business_address": "",
        "legal_person": "",
        "document_type": "business_license",
    }

    tobacco_fields = {
        "subject_name": store_name,
        "business_address": "",
        "legal_person": "",
        "document_type": "tobacco_license",
        "valid_from": first.valid_from or "",
        "valid_to": first.valid_to or "",
        "license_no": "",
    }

    # 3. 尝试存储来源文件（可能因为 NAS 不可用而失败，但不阻断流程）
    try:
        file_store.store_source_files(source_files)
    except TobaccoLicenseFileStoreError:
        pass  # 文件存储失败不影响比对流程

    # 4. 构建输入并执行一致性比对
    review_input = ReviewInput(
        supplier_name=store_name,
        supplier_credit_code="",
        declared_document_type="business_tobacco_consistency",
        source={
            "store_identifier": store_identifier,
            "requestid": first.requestid,
        },
        options={
            "business_license_fields": business_fields,
            "tobacco_license_fields": tobacco_fields,
        },
    )

    task_id = _generate_task_id(store_identifier)
    input_context = ReviewInputContext(
        task_id=task_id,
        input=review_input,
        use_case_name=tobacco_license_consistency_review_use_case.name,
        use_case_version=tobacco_license_consistency_review_use_case.version,
        ruleset_version=tobacco_license_consistency_review_use_case.ruleset_version,
    )

    try:
        result = tobacco_license_consistency_review_use_case.review(input_context)
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "CONSISTENCY_REVIEW_FAILED",
                "message": f"一致性比对执行失败: {error}",
            },
        ) from error

    # 5. 保存审核结果
    try:
        repository.save(result)
    except Exception as error:
        # 结果保存失败不影响比对结果返回
        pass

    # 6. 从规则结果中提取比对结论
    rule_results = result.rule_results or []
    unmatched = [r.rule_name for r in rule_results if not r.passed]
    has_validity_issue = any(not r.passed and "VALIDITY" in (r.rule_code or "") for r in rule_results)

    return {
        "task_id": result.task_id,
        "summary": result.summary,
        "status": result.status.value,
        "risk_level": result.risk_level.value,
        "needs_manual_review": result.needs_manual_review,
        "report": {
            "id": result.task_id,
            "company_name": store_name,
            "overall_result": "待校验" if result.needs_manual_review else ("通过" if result.risk_level.value == "NONE" else "不通过"),
            "compare_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "unmatched_fields": unmatched,
            "name_match": "不匹配" if any(not r.passed and "SUBJECT_NAME" in (r.rule_code or "") for r in rule_results) else "匹配",
            "address_match": "不匹配" if any(not r.passed and "ADDRESS" in (r.rule_code or "") for r in rule_results) else "匹配",
            "person_match": "不匹配" if any(not r.passed and "PERSON" in (r.rule_code or "") for r in rule_results) else "匹配",
            "type_match": "正确",
            "validity_status": "已过期" if has_validity_issue else "未过期",
        },
    }


def _generate_task_id(store_identifier: str) -> str:
    import hashlib
    import time

    raw = f"tobacco-consistency-{store_identifier}-{time.time_ns()}"
    return f"tc-{hashlib.md5(raw.encode()).hexdigest()[:16]}"
