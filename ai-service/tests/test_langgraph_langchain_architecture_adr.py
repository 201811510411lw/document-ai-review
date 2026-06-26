from pathlib import Path


def test_langgraph_langchain_terminal_architecture_adr_documents_breaking_change():
    repo_root = Path(__file__).resolve().parents[2]
    adr = repo_root / "docs/SPEC.md"

    content = adr.read_text(encoding="utf-8")

    assert "Status: Accepted" in content
    assert "UseCase = Thin Entry" in content
    assert "Workflow = LangGraph StateGraph" in content
    assert "Capability = LangChain Tools" in content
    assert "Skill = Prompt / Policy Layer" in content
    assert "Domain Rules = Final Compliance Decision" in content
    assert "breaking change" in content
    assert "do not preserve the old capability-as-workflow-layer architecture" in content


def test_langgraph_langchain_terminal_architecture_adr_records_guardrails():
    repo_root = Path(__file__).resolve().parents[2]
    adr = repo_root / "docs/SPEC.md"

    content = adr.read_text(encoding="utf-8")

    assert "LLM must not make the final compliance decision" in content
    assert "LangChain agent must not replace deterministic workflow control" in content
    assert "Capability tools must not contain workflow orchestration" in content
    assert "Do not mix multiple tool systems" in content
