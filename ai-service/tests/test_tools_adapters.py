from app.tools import (
    StubDocumentLoader,
    StubErpAdapter,
    StubFileAdapter,
    StubImageAdapter,
    StubImAdapter,
    StubLlmAdapter,
    StubOaAdapter,
    StubOcrAdapter,
    StubPdfAdapter,
)


def test_tools_adapter_stubs_do_not_require_external_services():
    assert StubOcrAdapter().extract_text({"file": "example.pdf"}) == ""
    assert StubPdfAdapter().extract_text(b"%PDF") == ""
    assert StubImageAdapter().normalize(b"image") == b""
    assert StubFileAdapter().read_bytes("/tmp/missing") == b""

    document_result = StubDocumentLoader().load({"source": "request"})
    llm_result = StubLlmAdapter().complete("prompt")
    erp_result = StubErpAdapter().fetch_context("supplier-001")
    oa_result = StubOaAdapter().write_back_review("review-task-001", {})
    im_result = StubImAdapter().notify("audit", {})

    for result in [document_result, llm_result, erp_result, oa_result, im_result]:
        assert result["implementation_status"] == "not_implemented"
