import pytest

import app_secop
from search import Filtros


def _filas(n, desde=0):
    return [{"fuente": "SECOP II", "id_contrato": f"C{desde + i}", "empresa": "E", "nit": "",
             "entidad": "X", "entidad_nit": "", "referencia": "", "objeto": "o", "valor": "$1",
             "pagado": "", "pendiente": "", "estado": "Activo", "fecha_firma": "2025-01-01",
             "fecha_fin": "", "sancion": "No", "url": ""} for i in range(n)]


class HiloFalso:
    """Sustituye threading.Thread: registra lo que se lanzaria, sin red ni hilos."""
    lanzados = []

    def __init__(self, target=None, args=(), daemon=None, **k):
        self.target, self.args = target, args

    def start(self):
        HiloFalso.lanzados.append((self.target, self.args))


@pytest.fixture
def activa(app, monkeypatch):
    """App con una consulta activa; sin conteo real ni hilos."""
    HiloFalso.lanzados = []
    monkeypatch.setattr(app_secop.AppSECOP, "_iniciar_conteo", lambda self: None)
    monkeypatch.setattr(app_secop.threading, "Thread", HiloFalso)
    app._filtros_activos = {"empresas": {None: None}, "filtros": Filtros(texto="x")}
    app._filas_por_pagina = 100
    return app


def test_iniciar_consulta_conserva_los_filtros_activos(app, monkeypatch):
    HiloFalso.lanzados = []
    monkeypatch.setattr(app_secop.threading, "Thread", HiloFalso)
    app.entry_unspsc.insert(0, "80111600")
    app._iniciar_consulta()
    assert app._filtros_activos is not None
    assert app._filtros_activos["filtros"].unspsc == "80111600"
    assert len(HiloFalso.lanzados) == 1 and HiloFalso.lanzados[0][1][2] == 0


def test_barra_muestra_total_real_y_habilita_ultima(activa):
    activa._pagina_actual = 1
    activa._mostrar_resultados_pagina(_filas(3), {}, [], True, 0, [], [])
    activa._aplicar_conteos({"SECOP II - Contratos": 250, "SECOP II - Procesos": 90,
                             "SECOP Integrado": 0}, activa._consulta_id)
    assert activa._total_paginas == 3
    texto = activa.lbl_pag.cget("text")
    assert "de 3" in texto and "340" in texto and "100 por dataset" in texto
    assert str(activa.btn_last.cget("state")) == "normal"
    assert str(activa.btn_prev.cget("state")) == "disabled"


def test_conteo_de_una_consulta_vieja_se_descarta(activa):
    activa._aplicar_conteos({"a": 999}, activa._consulta_id - 1)
    assert activa._total_paginas is None and activa._conteos is None


def test_volver_a_una_pagina_en_cache_no_consulta_la_api(activa):
    activa._pagina_actual = 1
    activa._mostrar_resultados_pagina(_filas(2), {}, [], True, 0, [], [])
    activa._pagina_actual = 2
    activa._mostrar_resultados_pagina(_filas(5, 100), {}, [], True, 100, [], [])
    activa._cambiar_pagina(1)
    assert len(activa.tree.get_children()) == 2 and activa._pagina_actual == 1
    activa._cambiar_pagina(2)
    assert len(activa.tree.get_children()) == 5
    assert HiloFalso.lanzados == []
    activa._cambiar_pagina(3)                       # no esta en cache: consulta
    assert len(HiloFalso.lanzados) == 1 and activa._consultando is True
    assert HiloFalso.lanzados[0][1][2] == 200       # offset = (3 - 1) * 100


def test_la_cache_se_limita_a_cinco_paginas(activa):
    for p in range(1, 9):
        activa._pagina_actual = p
        activa._mostrar_resultados_pagina(_filas(1, p), {}, [], True, (p - 1) * 100, [], [])
    assert len(activa._cache) == 5
    assert activa._cache.obtener(1) is None and activa._cache.obtener(8) is not None


def test_no_hay_pagina_mas_alla_del_total(activa):
    activa._pagina_actual = 1
    activa._mostrar_resultados_pagina(_filas(1), {}, [], True, 0, [], [])
    activa._aplicar_conteos({"SECOP II - Contratos": 150}, activa._consulta_id)
    activa._cambiar_pagina(9)
    assert HiloFalso.lanzados == [] and activa._pagina_actual == 1


def test_ultima_pagina_e_ir_a_pagina(activa, monkeypatch):
    activa._pagina_actual = 1
    activa._mostrar_resultados_pagina(_filas(1), {}, [], True, 0, [], [])
    activa._aplicar_conteos({"SECOP II - Contratos": 450}, activa._consulta_id)
    activa._ultima_pagina()
    assert HiloFalso.lanzados[-1][1][2] == 400      # pagina 5 de 5
    activa._consultando = False
    activa._pagina_actual = 1
    n = len(HiloFalso.lanzados)
    activa.ent_ir.delete(0, "end")
    activa.ent_ir.insert(0, "99")                   # se ajusta al total (5)
    activa._ir_a_pagina()
    assert len(HiloFalso.lanzados) == n + 1 and HiloFalso.lanzados[-1][1][2] == 400
    activa._consultando = False
    monkeypatch.setattr("app_secop.messagebox.showwarning", lambda *a, **k: None)
    activa.ent_ir.delete(0, "end")
    activa.ent_ir.insert(0, "abc")
    n = len(HiloFalso.lanzados)
    activa._ir_a_pagina()                           # texto no numerico: avisa y no consulta
    assert len(HiloFalso.lanzados) == n


def test_cambiar_tamano_invalida_la_cache_y_recalcula_paginas(activa):
    activa._pagina_actual = 1
    activa._mostrar_resultados_pagina(_filas(1), {}, [], True, 0, [], [])
    activa._aplicar_conteos({"SECOP II - Contratos": 250}, activa._consulta_id)
    activa.var_tamano.set("50")
    activa._on_tamano()
    assert activa._filas_por_pagina == 50 and activa._total_paginas == 5
    assert len(activa._cache) == 0
    assert HiloFalso.lanzados and HiloFalso.lanzados[-1][1][2] == 0     # recarga la pagina 1


def test_el_detalle_no_se_acumula_y_las_pestanas_se_reconstruyen(activa):
    d1 = {"Contratos SECOP II": [{"id_contrato": "A"}]}
    d2 = {"Contratos SECOP II": [{"id_contrato": "B"}, {"id_contrato": "C"}]}
    activa._pagina_actual = 1
    activa._mostrar_resultados_pagina(_filas(1), d1, [], True, 0, [], [])
    viejo = activa._tabs_detalle["Contratos SECOP II"]
    activa._pagina_actual = 2
    activa._mostrar_resultados_pagina(_filas(1, 100), d2, [], True, 100, [], [])
    nuevo = activa._tabs_detalle["Contratos SECOP II"]
    assert nuevo is not viejo and not viejo.winfo_exists()      # destruida, no solo oculta
    assert activa._pagina_detalle == d2


def test_limpiar_destruye_las_pestanas_y_vacia_la_cache(activa):
    activa._pagina_actual = 1
    activa._mostrar_resultados_pagina(_filas(1), {"Contratos SECOP II": [{"a": 1}]}, [], True, 0, [], [])
    frm = activa._tabs_detalle["Contratos SECOP II"]
    activa._limpiar_tabla()
    assert not frm.winfo_exists() and len(activa._cache) == 0 and activa._tabs_detalle == {}


def test_cancelar_restaura_la_pagina_anterior(activa):
    activa._pagina_actual = 2
    activa._cambiar_pagina(3)
    assert activa._consultando is True and activa._pagina_actual == 3
    token = activa._consulta_id
    activa._cancelar_operacion()
    assert activa._consultando is False and activa._pagina_actual == 2
    assert activa._consulta_id == token + 1 and activa._cancelar.is_set()


def test_el_hilo_descarta_resultados_de_una_consulta_cancelada(activa, monkeypatch):
    class QueryFalsa:
        def __init__(self, client):
            self.omitidos = []

        def consultar_pagina(self, *a, **k):
            return [], {}, [], False
    monkeypatch.setattr(app_secop, "SECOPQuery", QueryFalsa)
    recibidos = []
    monkeypatch.setattr(activa, "_mostrar_resultados_pagina", lambda *a: recibidos.append(a))
    activa._hilo_consulta({None: None}, Filtros(texto="x"), 0, activa._consulta_id - 1)
    activa.update()
    assert recibidos == []                          # token viejo: se descarta
    activa._hilo_consulta({None: None}, Filtros(texto="x"), 0, activa._consulta_id)
    activa.update()
    assert len(recibidos) == 1


def test_boton_cancelar_solo_activo_mientras_se_consulta(activa):
    assert str(activa.btn_cancelar.cget("state")) == "disabled"
    activa._set_consultando(True)
    assert str(activa.btn_cancelar.cget("state")) == "normal"
    assert str(activa.combo_tamano.cget("state")) == "disabled"
    activa._set_consultando(False)
    assert str(activa.btn_cancelar.cget("state")) == "disabled"


class QueryOmitidos:
    def __init__(self, client):
        self.omitidos = ["SECOP Integrado"]

    def consultar_pagina(self, *a, **k):
        return _filas(1), {}, [], False


def test_omitidos_llegan_por_el_callback_y_no_desde_el_hilo(activa, monkeypatch):
    monkeypatch.setattr(app_secop, "SECOPQuery", QueryOmitidos)
    activa._omitidos = []
    activa._hilo_consulta({None: None}, Filtros(texto="x"), 0, activa._consulta_id)
    assert activa._omitidos == []                   # el hilo no toca el estado de la UI
    activa.update()
    assert activa._omitidos == ["SECOP Integrado"]
    assert "Omitidos" in activa.lbl_estado.cget("text")


def test_cancelar_despues_de_que_el_hilo_termina_tambien_descarta(activa, monkeypatch):
    monkeypatch.setattr(app_secop, "SECOPQuery", QueryOmitidos)
    recibidos = []
    monkeypatch.setattr(activa, "_mostrar_resultados_pagina", lambda *a: recibidos.append(a))
    activa._hilo_consulta({None: None}, Filtros(texto="x"), 0, activa._consulta_id)
    activa._cancelar_operacion()                    # llega antes de que la UI procese el after
    activa.update()
    assert recibidos == []
