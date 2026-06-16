from app.capabilities.business_license.schemas import BusinessLicenseCapabilityResult


def build_business_license_capability_result(workflow_state) -> BusinessLicenseCapabilityResult:
    return BusinessLicenseCapabilityResult(
        document_input=workflow_state.get("document_input"),
        document_classification=workflow_state.get("document_classification"),
        extracted_fields=workflow_state.get("extracted_fields"),
        normalized_fields=workflow_state.get("normalized_fields"),
        extraction_metadata=workflow_state.get("extraction_metadata", {}),
        source_evidence={
            **workflow_state.get("source_evidence", {}),
            "skill_rule_review_metadata": workflow_state.get(
                "skill_rule_review_metadata",
                {},
            ),
        },
    )
