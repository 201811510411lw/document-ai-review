from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.api.auth import require_web_console_user
from app.integrations.mysql_client import MySqlFetchClient, mysql_settings_from_env
from app.integrations.starrocks.tobacco_license_sources import (
    SqlFetchClient,
    TobaccoLicenseSourceTaskError,
    fetch_latest_tobacco_license_source_files,
)
from app.services.tobacco_license_files import (
    TobaccoLicenseFileStore,
    TobaccoLicenseFileStoreError,
    TobaccoLicenseStoredDocument,
)


router = APIRouter(prefix="/api/v1/tobacco-license", tags=["tobacco-license"])
LOCAL_FILE_ROUTE_PREFIX = "/api/v1/tobacco-license/source-files/local"


class TobaccoLicenseSourceFetchRequest(BaseModel):
    store_identifier: str


def get_tobacco_license_starrocks_sql_client() -> SqlFetchClient:
    return MySqlFetchClient(mysql_settings_from_env("STARROCKS"))


def get_tobacco_license_file_store() -> TobaccoLicenseFileStore:
    return TobaccoLicenseFileStore()


@router.post("/source-files/from-starrocks")
def fetch_tobacco_license_source_files_from_starrocks(
    request: TobaccoLicenseSourceFetchRequest,
    _current_user: dict[str, Any] = Depends(require_web_console_user),
    sql_client: SqlFetchClient = Depends(get_tobacco_license_starrocks_sql_client),
    file_store: TobaccoLicenseFileStore = Depends(get_tobacco_license_file_store),
) -> dict[str, Any]:
    store_identifier = request.store_identifier.strip()
    if not store_identifier:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "TOBACCO_LICENSE_STORE_IDENTIFIER_EMPTY",
                "message": "门店标识不能为空",
            },
        )

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
                "code": "TOBACCO_LICENSE_SOURCE_RECORD_NOT_FOUND",
                "message": "未找到该门店的烟草证附件记录",
                "store_identifier": store_identifier,
            },
        )

    try:
        stored_documents = file_store.store_source_files(source_files)
    except TobaccoLicenseFileStoreError as error:
        status_code = 404 if error.code.endswith("_NOT_FOUND") else 400
        raise HTTPException(
            status_code=status_code,
            detail={
                "code": error.code,
                "message": str(error),
                "source_path": error.source_path,
                "store_identifier": store_identifier,
            },
        ) from error

    return {
        "store_identifier": store_identifier,
        "documents": [_stored_document_response(document) for document in stored_documents],
    }


@router.get("/source-files/local/{relative_path:path}")
def get_tobacco_license_local_file(
    relative_path: str,
    download: bool = Query(default=False),
    _current_user: dict[str, Any] = Depends(require_web_console_user),
    file_store: TobaccoLicenseFileStore = Depends(get_tobacco_license_file_store),
) -> FileResponse:
    try:
        path = file_store.resolve_local_file(relative_path)
    except TobaccoLicenseFileStoreError as error:
        raise HTTPException(
            status_code=404 if error.code.endswith("_NOT_FOUND") else 400,
            detail={
                "code": error.code,
                "message": str(error),
                "source_path": error.source_path,
            },
        ) from error

    return FileResponse(
        path,
        media_type=_content_type(path.name),
        filename=path.name if download else None,
    )


def _stored_document_response(document: TobaccoLicenseStoredDocument) -> dict[str, Any]:
    return {
        "source": document.source.model_dump(mode="json"),
        "output_dir": document.output_dir,
        "files": [
            {
                **stored_file.model_dump(mode="json"),
                "preview_url": _local_file_url(stored_file.relative_path),
                "download_url": _local_file_url(stored_file.relative_path, download=True),
            }
            for stored_file in document.files
        ],
    }


def _local_file_url(relative_path: str, *, download: bool = False) -> str:
    url = f"{LOCAL_FILE_ROUTE_PREFIX}/{relative_path}"
    return f"{url}?download=1" if download else url


def _content_type(file_name: str) -> str | None:
    import mimetypes

    return mimetypes.guess_type(file_name)[0]
