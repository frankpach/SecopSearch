"""Logo de la app: rutas de recursos (normal y PyInstaller) y tolerancia a fallos."""
import os
import sys

import pytest

from recursos import aplicar_icono, ruta_recurso

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_ruta_recurso_junto_al_codigo(monkeypatch):
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    assert ruta_recurso("assets", "logo.png") == os.path.join(RAIZ, "assets", "logo.png")


def test_ruta_recurso_dentro_del_exe(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert ruta_recurso("assets", "logo.ico") == os.path.join(str(tmp_path), "assets", "logo.ico")


def test_los_recursos_existen_en_el_repositorio(monkeypatch):
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    assert os.path.isfile(ruta_recurso("assets", "logo.png"))
    assert os.path.isfile(ruta_recurso("assets", "logo.ico"))


def test_el_spec_empaqueta_los_recursos_y_el_icono():
    with open(os.path.join(RAIZ, "SECOP_Diligencia.spec"), encoding="utf-8") as f:
        spec = f.read()
    assert "('assets', 'assets')" in spec and "icon='assets/logo.ico'" in spec
    assert "('.env', '.')" in spec                         # lo existente se conserva


def test_icono_valido_devuelve_logo_pequeno(app, monkeypatch):
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    icono, logo = aplicar_icono(app, ruta_recurso("assets", "logo.png"))
    assert icono is not None and 28 <= logo.width() <= 40 and 28 <= logo.height() <= 40


@pytest.mark.parametrize("contenido", [None, b"esto no es un png"])
def test_logo_ausente_o_danado_no_falla(app, tmp_path, contenido):
    ruta = tmp_path / "logo.png"
    if contenido is not None:
        ruta.write_bytes(contenido)
    assert aplicar_icono(app, str(ruta), str(tmp_path / "logo.ico")) == (None, None)


def test_ico_danado_no_impide_el_icono_png(app, monkeypatch, tmp_path):
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    ico = tmp_path / "logo.ico"
    ico.write_bytes(b"no es un ico")
    icono, logo = aplicar_icono(app, ruta_recurso("assets", "logo.png"), str(ico))
    assert icono is not None and logo is not None


def test_la_app_muestra_el_logo_en_el_encabezado(app):
    assert app._logo is not None
    assert app.lbl_logo.cget("image")


def test_la_app_arranca_sin_logo(monkeypatch, tmp_path, request):
    import app_secop
    monkeypatch.setattr(app_secop, "ruta_recurso",
                        lambda *partes: str(tmp_path / "no_existe" / partes[-1]))
    a = request.getfixturevalue("app")
    assert a._icono is None and a._logo is None and a.lbl_logo is None
    assert a.tree is not None and a.lbl_estado is not None


@pytest.mark.skipif(sys.platform != "win32", reason="icono de ventana de Windows")
def test_el_ico_se_aplica_a_la_ventana_y_no_como_icono_por_defecto(app, monkeypatch):
    """Con iconbitmap(default=...) la barra de titulo mostraba el icono generico."""
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    llamadas = []
    original = app.iconbitmap
    monkeypatch.setattr(app, "iconbitmap",
                        lambda *a, **k: (llamadas.append((a, k)), original(*a, **k))[1])
    aplicar_icono(app, ruta_recurso("assets", "logo.png"), ruta_recurso("assets", "logo.ico"))
    assert llamadas and "default" not in llamadas[0][1]
    assert llamadas[0][0] and llamadas[0][0][0].endswith("logo.ico")
