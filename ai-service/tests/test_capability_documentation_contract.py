from pathlib import Path

from app.workflows.registry import review_graph_registry


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_capability_matrix_covers_every_registered_review_use_case():
    capability_matrix = (REPO_ROOT / "docs/CAPABILITIES.md").read_text(
        encoding="utf-8"
    )

    for definition in review_graph_registry.list():
        assert f"`{definition['name']}`" in capability_matrix

    assert "`implemented`" in capability_matrix
    assert "`partial`" in capability_matrix
    assert "`placeholder`" in capability_matrix
    assert "`planned`" in capability_matrix


def test_core_docs_link_the_glossary_and_capability_matrix():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    spec = (REPO_ROOT / "docs/SPEC.md").read_text(encoding="utf-8")

    assert "[CONTEXT.md](CONTEXT.md)" in readme
    assert "[docs/CAPABILITIES.md](docs/CAPABILITIES.md)" in readme
    assert "Capability Status" in spec

    for definition in review_graph_registry.list():
        assert f"#### {definition['name']}" in spec
