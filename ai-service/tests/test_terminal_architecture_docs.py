from pathlib import Path


def test_core_architecture_docs_do_not_reintroduce_old_compatibility_language():
    repo_root = Path(__file__).resolve().parents[2]
    docs = [
        repo_root / "README.md",
        repo_root / "docs/SPEC.md",
        repo_root / "docs/API.md",
    ]
    forbidden_phrases = [
        "这条兼容链路必须继续保留",
        "不删除 `food_license` 兼容入口",
        "runtime capability 位于",
        "capability 专属结果",
        "作为兼容目标。当前保留",
    ]

    for doc in docs:
        content = doc.read_text(encoding="utf-8")
        for phrase in forbidden_phrases:
            assert phrase not in content, f"{phrase!r} found in {doc}"


def test_core_architecture_docs_point_to_terminal_architecture():
    repo_root = Path(__file__).resolve().parents[2]
    readme = (repo_root / "README.md").read_text(encoding="utf-8")
    spec = (repo_root / "docs/SPEC.md").read_text(
        encoding="utf-8"
    )

    assert "LangGraph + LangChain 驱动的 AI Workflow / Agent Platform" in readme
    assert "UseCase Thin Entry" in spec
    assert "Workflow Registry / Graph Runtime" in spec
    assert "Capability 不再是流程层对象" in spec
