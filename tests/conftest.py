import os

import pytest


@pytest.fixture(autouse=True)
def datos_aislados(tmp_path, monkeypatch):
    """Ninguna prueba toca %APPDATA% real."""
    monkeypatch.setenv("SECOP_DATA_DIR", str(tmp_path / "datos"))
    yield


def pytest_collection_modifyitems(config, items):
    if os.environ.get("SECOP_LIVE") == "1":
        return
    saltar = pytest.mark.skip(reason="usa la API real; ejecutar con SECOP_LIVE=1")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(saltar)
