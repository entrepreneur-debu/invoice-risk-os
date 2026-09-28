import pytest

from app.core.config import Settings


@pytest.fixture(autouse=True)
def _isolate_from_process_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit tests must not depend on variables exported in the developer's shell or CI."""
    for field_name in Settings.model_fields:
        monkeypatch.delenv(field_name.upper(), raising=False)
