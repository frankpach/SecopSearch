"""Lanzador hibrido: el exe sin consola no tiene stdout/stderr y uvicorn lo necesita."""
import sys

import secop_hibrido


def test_streams_nulos_se_reemplazan_y_soportan_isatty(monkeypatch):
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    secop_hibrido._asegurar_streams()
    assert sys.stdout.isatty() is False and sys.stderr.isatty() is False
    sys.stdout.write("x")           # no debe fallar


def test_streams_existentes_no_se_tocan(monkeypatch):
    class Falso:
        def isatty(self):
            return True
    f = Falso()
    monkeypatch.setattr(sys, "stdout", f)
    secop_hibrido._asegurar_streams()
    assert sys.stdout is f


def test_uvicorn_configura_logs_sin_stdout(monkeypatch):
    """Reproduce el traceback del exe: dictConfig de uvicorn con stdout=None."""
    import logging.config
    from uvicorn.config import LOGGING_CONFIG
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    secop_hibrido._asegurar_streams()
    logging.config.dictConfig(LOGGING_CONFIG)
