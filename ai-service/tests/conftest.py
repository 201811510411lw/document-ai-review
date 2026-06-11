import pytest

from app.tools.vision_adapter import FakeVisionAdapter
from app.workflows.business_license import nodes as business_license_nodes


@pytest.fixture(autouse=True)
def use_fake_business_license_vision_adapter(monkeypatch):
    monkeypatch.setattr(
        business_license_nodes,
        "business_license_vision_adapter",
        FakeVisionAdapter(),
    )
