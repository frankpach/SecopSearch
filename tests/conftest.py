import gc
import os
import tkinter

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


@pytest.fixture
def app(monkeypatch, tmp_path):
    """AppSECOP real, oculta y aislada (cwd, datos y sin red al arrancar)."""
    # cwd aislado: la app busca el .env y los JSON antiguos en el directorio de trabajo
    monkeypatch.chdir(tmp_path)
    import app_secop
    monkeypatch.setattr(app_secop.AppSECOP, "_cargar_metadatos_async", lambda self: None)
    monkeypatch.setattr(app_secop.AppSECOP, "_aviso_inicio", lambda self: None, raising=False)
    # En Windows, crear un Tk falla de vez en cuando con TclError (init.tcl "no encontrado")
    # aunque haya display: se reintenta y solo se salta si falla siempre.
    error = None
    for _ in range(5):
        try:
            a = app_secop.AppSECOP()
            break
        except tkinter.TclError as e:
            error = e
    else:
        pytest.skip("sin display: %s" % error)
    a.withdraw()
    a.update()
    yield a
    a.destroy()
    # Liberar aqui (hilo principal) los objetos Tk ciclicos: si el GC los recogiera luego
    # desde un hilo de trabajo, Variable.__del__ falla con 'main thread is not in main loop'.
    del a
    gc.collect()
