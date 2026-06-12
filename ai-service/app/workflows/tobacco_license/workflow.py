from typing import Any

from app.models import ReviewInputContext
from app.tools.license_file_recognition import recognize_license_file
from app.tools.vision_adapter import FakeVisionAdapter


tobacco_license_file_adapter = FakeVisionAdapter(
    structured_json_env="TOBACCO_LICENSE_FAKE_LLM_FILE_JSON",
    text_env="TOBACCO_LICENSE_FAKE_LLM_FILE_TEXT",
    model="fake-tobacco-license-file-recognition",
)


def run_tobacco_license_workflow(input_context: ReviewInputContext) -> dict[str, Any]:
    recognition_result = recognize_license_file(
        input_context.input,
        adapter=tobacco_license_file_adapter,
    )
    return {
        "implementation_status": "not_implemented",
        "use_case_name": input_context.use_case_name,
        "message": "tobacco_license workflow boundary is present but not implemented.",
        "document_input": recognition_result.document_input.__dict__,
        "structured_fields": recognition_result.structured_fields,
        "extraction_metadata": recognition_result.extraction_metadata,
    }
