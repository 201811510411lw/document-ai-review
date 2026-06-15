from app.capabilities.tobacco_license.schemas import TobaccoLicenseCapabilityResult


def build_tobacco_license_capability_result(workflow_state) -> TobaccoLicenseCapabilityResult:
    return TobaccoLicenseCapabilityResult(
        document_input=workflow_state.get("document_input"),
        document_classification=workflow_state.get("document_classification"),
        extracted_fields=workflow_state.get("extracted_fields"),
        normalized_fields=workflow_state.get("normalized_fields"),
        extraction_metadata=workflow_state.get("extraction_metadata", {}),
        source_evidence=workflow_state.get("source_evidence", {}),
    )
