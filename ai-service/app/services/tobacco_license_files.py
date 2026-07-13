import mimetypes
import re
import shutil
import zipfile
from pathlib import Path

from pydantic import BaseModel

from app.integrations.starrocks.tobacco_license_sources import TobaccoLicenseSourceFile


DEFAULT_TOBACCO_LICENSE_DATA_DIR = (
    Path(__file__).resolve().parents[2] / "data" / "tobacco_license"
)
DEFAULT_NAS_ROOT = Path("/data")


class TobaccoLicenseStoredFile(BaseModel):
    file_name: str
    relative_path: str
    local_path: str
    content_type: str | None = None
    file_size: int


class TobaccoLicenseStoredDocument(BaseModel):
    source: TobaccoLicenseSourceFile
    output_dir: str
    files: list[TobaccoLicenseStoredFile]


class TobaccoLicenseFileStoreError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        source_path: str | None = None,
    ):
        self.code = code
        self.source_path = source_path
        super().__init__(message)


class TobaccoLicenseFileStore:
    def __init__(
        self,
        *,
        base_data_dir: Path | str = DEFAULT_TOBACCO_LICENSE_DATA_DIR,
        nas_root: Path | str = DEFAULT_NAS_ROOT,
    ) -> None:
        self.base_data_dir = Path(base_data_dir)
        self.nas_root = Path(nas_root)

    def store_source_files(
        self,
        source_files: list[TobaccoLicenseSourceFile],
    ) -> list[TobaccoLicenseStoredDocument]:
        return [self.store_source_file(source_file) for source_file in source_files]

    def store_source_file(
        self,
        source_file: TobaccoLicenseSourceFile,
    ) -> TobaccoLicenseStoredDocument:
        if _is_encrypted(source_file):
            raise TobaccoLicenseFileStoreError(
                "TOBACCO_LICENSE_FILE_ENCRYPTED",
                "OA 附件已加密，当前暂不支持本地解密",
                source_path=source_file.file_real_path,
            )

        source_path = self.resolve_nas_path(source_file.file_real_path)
        output_dir = self._output_dir(source_file)
        if output_dir.exists():
            shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if _truthy_flag(source_file.is_zip):
            stored_files = self._extract_zip(source_path, output_dir, source_file)
        else:
            stored_files = [self._copy_plain_file(source_path, output_dir, source_file)]

        if not stored_files:
            raise TobaccoLicenseFileStoreError(
                "TOBACCO_LICENSE_ZIP_EMPTY",
                "OA 附件压缩包内没有可保存的文件",
                source_path=str(source_path),
            )

        return TobaccoLicenseStoredDocument(
            source=source_file,
            output_dir=str(output_dir),
            files=stored_files,
        )

    def resolve_nas_path(self, file_real_path: str) -> Path:
        text = str(file_real_path or "").strip()
        if not text:
            raise TobaccoLicenseFileStoreError(
                "TOBACCO_LICENSE_FILE_PATH_EMPTY",
                "OA 附件存储路径为空",
            )

        candidate = Path(text)
        if not candidate.is_absolute():
            candidate = self.nas_root / text.lstrip("/")

        root = self.nas_root.resolve(strict=False)
        resolved = candidate.resolve(strict=False)
        try:
            resolved.relative_to(root)
        except ValueError as error:
            raise TobaccoLicenseFileStoreError(
                "TOBACCO_LICENSE_FILE_PATH_OUTSIDE_NAS",
                "OA 附件存储路径不在允许的 NAS 根目录下",
                source_path=text,
            ) from error

        if not resolved.is_file():
            raise TobaccoLicenseFileStoreError(
                "TOBACCO_LICENSE_FILE_NOT_FOUND",
                "本地 NAS 未找到 OA 附件文件",
                source_path=str(resolved),
            )
        return resolved

    def resolve_local_file(self, relative_path: str) -> Path:
        text = str(relative_path or "").strip()
        if not text:
            raise TobaccoLicenseFileStoreError(
                "TOBACCO_LICENSE_LOCAL_PATH_EMPTY",
                "本地文件路径为空",
            )

        root = self.base_data_dir.resolve(strict=False)
        resolved = (self.base_data_dir / text).resolve(strict=False)
        try:
            resolved.relative_to(root)
        except ValueError as error:
            raise TobaccoLicenseFileStoreError(
                "TOBACCO_LICENSE_LOCAL_PATH_OUTSIDE_DATA_DIR",
                "本地文件路径不在烟草证数据目录下",
                source_path=text,
            ) from error

        if not resolved.is_file():
            raise TobaccoLicenseFileStoreError(
                "TOBACCO_LICENSE_LOCAL_FILE_NOT_FOUND",
                "本地烟草证文件不存在",
                source_path=str(resolved),
            )
        return resolved

    def _extract_zip(
        self,
        source_path: Path,
        output_dir: Path,
        source_file: TobaccoLicenseSourceFile,
    ) -> list[TobaccoLicenseStoredFile]:
        try:
            archive = zipfile.ZipFile(source_path)
        except zipfile.BadZipFile as error:
            raise TobaccoLicenseFileStoreError(
                "TOBACCO_LICENSE_BAD_ZIP",
                "OA 附件不是有效 zip 文件",
                source_path=str(source_path),
            ) from error

        stored_files: list[TobaccoLicenseStoredFile] = []
        with archive:
            members = [member for member in archive.infolist() if not member.is_dir()]
            for index, member in enumerate(members, start=1):
                target_name = _safe_file_name(
                    member.filename,
                    fallback=_fallback_file_name(source_file, index=index),
                )
                target_name = _source_name_when_missing_suffix(
                    target_name,
                    source_file,
                    index=index,
                    total=len(members),
                )
                target_path = _dedupe_path(output_dir / target_name)
                with archive.open(member) as source, target_path.open("wb") as target:
                    shutil.copyfileobj(source, target)
                stored_files.append(self._stored_file(target_path))
        return stored_files

    def _copy_plain_file(
        self,
        source_path: Path,
        output_dir: Path,
        source_file: TobaccoLicenseSourceFile,
    ) -> TobaccoLicenseStoredFile:
        target_name = _safe_file_name(
            source_file.real_filename
            or source_file.docimage_filename
            or source_path.name,
            fallback=_fallback_file_name(source_file, index=1),
        )
        target_path = _dedupe_path(output_dir / target_name)
        shutil.copy2(source_path, target_path)
        return self._stored_file(target_path)

    def _stored_file(self, path: Path) -> TobaccoLicenseStoredFile:
        relative_path = path.resolve(strict=False).relative_to(
            self.base_data_dir.resolve(strict=False)
        )
        return TobaccoLicenseStoredFile(
            file_name=path.name,
            relative_path=relative_path.as_posix(),
            local_path=str(path),
            content_type=mimetypes.guess_type(path.name)[0],
            file_size=path.stat().st_size,
        )

    def _output_dir(self, source_file: TobaccoLicenseSourceFile) -> Path:
        store_part = _safe_path_part(
            source_file.store_code or source_file.store_name or "unknown_store"
        )
        request_part = _safe_path_part(str(source_file.requestid or "unknown_request"))
        doc_part = _safe_path_part(str(source_file.docid or "unknown_doc"))
        image_part = _safe_path_part(str(source_file.imagefile_id or "unknown_image"))
        return self.base_data_dir / store_part / f"{request_part}_{doc_part}_{image_part}"


def _is_encrypted(source_file: TobaccoLicenseSourceFile) -> bool:
    return _truthy_flag(source_file.is_encrypt) or bool(source_file.is_aes_encrypt)


def _truthy_flag(value: object) -> bool:
    return str(value or "").strip() in {"1", "true", "True", "Y", "y"}


def _safe_file_name(value: str | None, *, fallback: str) -> str:
    raw = str(value or "").replace("\\", "/").split("/")[-1].strip()
    raw = raw.replace("\x00", "")
    for char in '<>:"|?*':
        raw = raw.replace(char, "_")
    return raw or fallback


def _fallback_file_name(source_file: TobaccoLicenseSourceFile, *, index: int) -> str:
    base = source_file.real_filename or source_file.docimage_filename
    suffix = Path(base or "").suffix or ".bin"
    docid = source_file.docid or "unknown_doc"
    imagefile_id = source_file.imagefile_id or "unknown_image"
    return f"tobacco_license_{docid}_{imagefile_id}_{index}{suffix}"


def _source_name_when_missing_suffix(
    target_name: str,
    source_file: TobaccoLicenseSourceFile,
    *,
    index: int,
    total: int,
) -> str:
    if Path(target_name).suffix:
        return target_name
    source_name = _safe_file_name(
        source_file.real_filename or source_file.docimage_filename,
        fallback="",
    )
    suffix = Path(source_name).suffix
    if not suffix:
        return target_name
    if total == 1:
        return source_name
    return f"{Path(source_name).stem}_{index}{suffix}"


def _safe_path_part(value: str) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[^0-9A-Za-z._-]+", "_", text)
    text = text.strip("._-")
    return text or "unknown"


def _dedupe_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    index = 2
    while True:
        candidate = parent / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1
