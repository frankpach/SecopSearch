from datetime import date, timedelta

import pytest

import app_secop
from search import Filtros, identificar_fila

# La fixture `app` sustituye _aviso_inicio en la clase: se guarda el real al importar
AVISO_INICIO_REAL = app_secop.AppSECOP._aviso_inicio


def test_la_app_arranca_con_directorio_y_paneles(app):
    assert app.directorio is not None
    assert app.entry_texto is not None and app.var_busqueda is not None


def test_rango_por_defecto_es_el_ultimo_anio_y_se_rellena_en_los_campos(app):
    hoy = date.today()
    assert app.var_rango.get() == "Último año"
    assert app.ent_desde.get() == (hoy - timedelta(days=365)).isoformat()
    assert app.ent_hasta.get() == hoy.isoformat()


def test_leer_filtros_incluye_el_rango_calculado(app):
    app.entry_texto.insert(0, "x")
    f = app._leer_filtros()
    assert f.fecha_desde == app.ent_desde.get() and f.fecha_hasta == app.ent_hasta.get()


def test_todo_el_historial_vacia_las_fechas(app):
    app.var_rango.set("Todo el historial")
    app._on_rango()
    assert app.ent_desde.get() == "" and app.ent_hasta.get() == ""
    assert app._leer_filtros().fecha_desde == ""


def test_editar_una_fecha_pasa_a_personalizado(app):
    app.ent_desde.delete(0, "end")
    app.ent_desde.insert(0, "2024-01-01")
    app._on_fecha_editada()
    assert app.var_rango.get() == "Personalizado"
    assert app._leer_rango() == {"modo": "personalizado", "desde": "2024-01-01",
                                 "hasta": app.ent_hasta.get()}


def test_cambiar_de_rango_predefinido_recalcula_los_campos(app):
    app.var_rango.set("Últimos 30 días")
    app._on_rango()
    hoy = date.today()
    assert app.ent_desde.get() == (hoy - timedelta(days=30)).isoformat()
    assert app._leer_rango() == {"modo": "30_dias"}


def test_leer_y_cargar_filtros_ida_y_vuelta(app):
    f = Filtros(texto="logistico", valor_min="1000000", modalidad="Contratación directa",
                estado="activo", departamento="Antioquia", unspsc="80111600",
                entidad_nombre="Alcaldia")
    rango = {"modo": "personalizado", "desde": "2024-01-01", "hasta": "2024-12-31"}
    app._cargar_filtros_en_widgets(f, rango)
    leido = app._leer_filtros()
    for campo in ("texto", "valor_min", "modalidad", "estado", "departamento",
                  "unspsc", "entidad_nombre"):
        assert getattr(leido, campo) == getattr(f, campo)
    assert (leido.fecha_desde, leido.fecha_hasta) == ("2024-01-01", "2024-12-31")
    assert app.var_avanzado.get() is True               # hay filtros avanzados: se despliegan


def test_filtros_invalidos_no_inician_consulta(app, monkeypatch):
    avisos = []
    monkeypatch.setattr("app_secop.messagebox.showwarning", lambda *a, **k: avisos.append(a))
    app.entry_texto.insert(0, "logistico")
    app.ent_desde.delete(0, "end")
    app.ent_desde.insert(0, "2024-99-99")
    app._on_fecha_editada()
    app._iniciar_consulta()
    assert avisos and app._consultando is False


def test_sin_criterios_no_consulta_aunque_haya_rango_por_defecto(app, monkeypatch):
    avisos = []
    monkeypatch.setattr("app_secop.messagebox.showwarning", lambda *a, **k: avisos.append(a))
    app._iniciar_consulta()
    assert avisos and app._consultando is False


def test_guardar_busqueda_conserva_el_modo_de_rango_no_las_fechas(app, monkeypatch):
    monkeypatch.setattr("app_secop.simpledialog.askstring", lambda *a, **k: "Reciente")
    app.entry_texto.insert(0, "operador logistico")
    app._guardar_busqueda()
    b = app.directorio.buscar_busqueda_por_nombre("Reciente")
    assert b["filtros"] == {"texto": "operador logistico"}
    assert b["rango"] == {"modo": "ultimo_anio"}
    assert "Reciente" in app.combo_busqueda["values"]


def test_guardar_busqueda_con_fechas_personalizadas(app, monkeypatch):
    monkeypatch.setattr("app_secop.simpledialog.askstring", lambda *a, **k: "Fijo")
    app.entry_texto.insert(0, "x")
    app.ent_desde.delete(0, "end")
    app.ent_desde.insert(0, "2024-01-01")
    app._on_fecha_editada()
    app._guardar_busqueda()
    b = app.directorio.buscar_busqueda_por_nombre("Fijo")
    assert b["rango"]["modo"] == "personalizado" and b["rango"]["desde"] == "2024-01-01"


def test_ejecutar_busqueda_guardada_restaura_filtros_rango_y_tamano(app, monkeypatch):
    lanzados = []
    monkeypatch.setattr("app_secop.threading.Thread",
                        lambda target=None, args=(), daemon=None, **k:
                        type("H", (), {"start": lambda s: lanzados.append(args)})())
    app.directorio.guardar_busqueda("B", {"texto": "x", "estado": "activo"}, {"modo": "6_meses"})
    app._refrescar_combo_busquedas()
    app.var_tamano.set("200")
    app.var_busqueda.set("B")
    app._ejecutar_busqueda_guardada()
    assert app.entry_texto.get() == "x" and app.var_rango.get() == "Últimos 6 meses"
    assert app.var_tamano.get() == "100"                 # fijo para comparar novedades
    assert lanzados and lanzados[0][1].estado == "activo"


def test_busqueda_guardada_danada_avisa_sin_lanzar_la_consulta(app, monkeypatch):
    import app_secop
    lanzados, avisos = [], []
    monkeypatch.setattr("app_secop.threading.Thread",
                        lambda target=None, args=(), daemon=None, **k:
                        type("H", (), {"start": lambda s: lanzados.append(args)})())
    monkeypatch.setattr("app_secop.messagebox.showwarning", lambda *a, **k: avisos.append(a))

    def desde_dict_roto(d):
        raise ValueError("dato inesperado")
    monkeypatch.setattr(app_secop.Filtros, "desde_dict", staticmethod(desde_dict_roto))
    app.directorio.guardar_busqueda("Rota", {"texto": "x"})
    app._refrescar_combo_busquedas()
    app.var_busqueda.set("Rota")
    app._ejecutar_busqueda_guardada()
    assert lanzados == [] and app._consultando is False
    assert len(avisos) == 1 and "danada" in avisos[0][1]


def test_filas_nuevas_se_marcan_solo_desde_la_segunda_ejecucion(app):
    fila = {"fuente": "SECOP II", "id_contrato": "C1", "referencia": "", "entidad_nit": "",
            "entidad": "E", "fecha_firma": "2024-01-01"}
    nueva = dict(fila, id_contrato="C2")
    b = app.directorio.guardar_busqueda("X", {"texto": "a"})
    app._busqueda_activa = b["id"]
    app._procesar_busqueda_guardada([fila])             # primera vez: nada se marca
    assert app._nuevos == set()
    app._busqueda_activa = b["id"]
    app._procesar_busqueda_guardada([fila, nueva])
    assert app._nuevos == {identificar_fila(nueva)}


def test_volver_a_la_pagina_1_no_borra_las_marcas_de_nuevas(app):
    fila = {"fuente": "SECOP II", "id_contrato": "C1", "referencia": "", "entidad_nit": "",
            "entidad": "E", "fecha_firma": "2024-01-01"}
    app._nuevos = {identificar_fila(fila)}
    app._busqueda_activa = None                         # ya procesada al cargar la pagina 1
    assert app._procesar_busqueda_guardada([fila]) == 1
    assert app._nuevos == {identificar_fila(fila)}


def test_limpiar_restaura_el_rango_por_defecto(app):
    app.var_rango.set("Todo el historial")
    app._on_rango()
    app._limpiar()
    assert app.var_rango.get() == "Último año" and app.ent_desde.get() != ""


# ---- robustez: validacion, tokens y fallos de disco ---------------------------------

def _fila(id_contrato):
    return {"fuente": "SECOP II", "id_contrato": id_contrato, "empresa": "E", "nit": "",
            "entidad": "X", "entidad_nit": "", "referencia": "", "objeto": "o", "valor": "$1",
            "pagado": "", "pendiente": "", "estado": "Activo", "fecha_firma": "2025-01-01",
            "fecha_fin": "", "sancion": "No", "url": ""}


class QueryFalsa:
    """Sustituye SECOPQuery en "Ejecutar todas": registra (nombre, nit, filtros)."""
    llamadas = []
    errores = []          # errores de dataset que devuelve cada pagina
    al_consultar = None   # gancho opcional (p. ej. pulsar Cancelar a mitad)

    def __init__(self, client):
        pass

    def consultar_pagina(self, nombre, nit=None, filtros=None, offset=0, page_size=100,
                         on_progress=None):
        QueryFalsa.llamadas.append((nombre, nit, filtros))
        if QueryFalsa.al_consultar:
            QueryFalsa.al_consultar()
        return [_fila("C1")], {}, list(QueryFalsa.errores), False


@pytest.fixture
def query_falsa(monkeypatch):
    import app_secop
    QueryFalsa.llamadas, QueryFalsa.errores, QueryFalsa.al_consultar = [], [], None
    monkeypatch.setattr(app_secop, "SECOPQuery", QueryFalsa)
    infos = []
    monkeypatch.setattr("app_secop.messagebox.showinfo", lambda *a, **k: infos.append(a))
    return infos


def test_ejecutar_todas_no_consulta_busquedas_con_fechas_guardadas_invalidas(app, query_falsa):
    infos = query_falsa
    app.directorio.guardar_busqueda("Mala", {"texto": "a"},
                                    {"modo": "personalizado", "desde": "2024-99-99", "hasta": ""})
    app.directorio.guardar_busqueda("Buena", {"texto": "b"}, {"modo": "30_dias"})
    app._set_consultando(True)
    app._hilo_ejecutar_todas(app.directorio.listar_busquedas(), app._consulta_id)
    app.update()
    assert [c[2].texto for c in QueryFalsa.llamadas] == ["b"]   # la invalida no se consulta
    assert QueryFalsa.llamadas[0][2].fecha_desde != ""           # rango recalculado a hoy
    resumen = infos[0][1]
    assert "Mala" in resumen and "invalid" in resumen.lower() and "Buena" in resumen
    assert app._consultando is False


def test_ejecutar_todas_cancelada_no_toca_la_ui(app, monkeypatch):
    lanzados = []
    monkeypatch.setattr("app_secop.threading.Thread",
                        lambda target=None, args=(), daemon=None, **k:
                        type("H", (), {"start": lambda s: lanzados.append(args)})())
    infos = []
    monkeypatch.setattr("app_secop.messagebox.showinfo", lambda *a, **k: infos.append(a))
    app.directorio.guardar_busqueda("B", {"texto": "x"})
    app._ejecutar_todas()
    assert app._consultando is True and lanzados
    token = lanzados[0][1]
    app._cancelar_operacion()
    assert app._consultando is False
    app._fin_ejecutar_todas(["B: 1 nuevo(s)"], token)        # llega tarde: se descarta
    assert infos == [] and app.lbl_estado.cget("text") == "Operacion cancelada."


def test_fallo_de_disco_al_registrar_la_ejecucion_no_rompe_la_pagina(app, monkeypatch):
    import app_secop
    monkeypatch.setattr(app_secop.AppSECOP, "_iniciar_conteo", lambda self: None)

    def falla(*a, **k):
        raise OSError("disco lleno")
    b = app.directorio.guardar_busqueda("X", {"texto": "a"})
    monkeypatch.setattr(app.directorio, "registrar_ejecucion", falla)
    app._filtros_activos = {"empresas": {None: None}, "filtros": Filtros(texto="a")}
    app._busqueda_activa = b["id"]
    app._mostrar_resultados_pagina([_fila("C1")], {}, [], False, 0, [], [])
    assert len(app.tree.get_children()) == 1
    assert "disco lleno" in app.lbl_estado.cget("text")


def test_guardar_busqueda_con_disco_lleno_avisa(app, monkeypatch):
    import app_secop
    errores = []
    monkeypatch.setattr(app_secop, "error_guardado", lambda e, *a, **k: errores.append(e))
    monkeypatch.setattr("app_secop.simpledialog.askstring", lambda *a, **k: "Z")

    def falla(*a, **k):
        raise OSError("sin permiso")
    monkeypatch.setattr(app.directorio, "guardar_busqueda", falla)
    app.entry_texto.insert(0, "x")
    app._guardar_busqueda()
    assert errores and "Z" not in app.combo_busqueda["values"]


def test_las_filas_nuevas_se_pintan_y_el_pie_muestra_el_rango(app, monkeypatch):
    import app_secop
    monkeypatch.setattr(app_secop.AppSECOP, "_iniciar_conteo", lambda self: None)
    b = app.directorio.guardar_busqueda("X", {"texto": "a"})
    app.directorio.registrar_ejecucion(b["id"], [identificar_fila(_fila("C1"))])
    app._filtros_activos = {"empresas": {None: None},
                            "filtros": Filtros(texto="a", fecha_desde="2025-01-01",
                                               fecha_hasta="2025-12-31")}
    app._busqueda_activa = b["id"]
    app._mostrar_resultados_pagina([_fila("C1"), _fila("C2")], {}, [], False, 0, [], [])
    tags = [app.tree.item(i, "tags") for i in app.tree.get_children()]
    assert "nuevo" not in tags[0] and "nuevo" in tags[1]
    texto = app.lbl_estado.cget("text")
    assert "1 NUEVO(S)" in texto and "Fechas: 2025-01-01 a 2025-12-31" in texto


# ---- correcciones de la revision ----------------------------------------------------

def test_las_fechas_no_dependen_de_eventos_de_teclado(app):
    # Tab, flechas, Ctrl+C...: ninguna tecla por si sola cambia el modo; solo el texto
    for entry in (app.ent_desde, app.ent_hasta):
        assert not entry.bind("<KeyRelease>") and not entry.bind("<Key>")


def test_sin_cambio_de_texto_no_pasa_a_personalizado(app):
    app._on_fecha_editada()                              # p. ej. tras Tab o una flecha
    assert app.var_rango.get() == "Último año"
    assert app._leer_rango() == {"modo": "ultimo_anio"}


def test_escribir_de_verdad_en_una_fecha_pasa_a_personalizado(app):
    app.ent_hasta.insert("end", "x")                     # sin llamar a nada mas
    assert app.var_rango.get() == "Personalizado"


def test_reescribir_la_misma_fecha_no_cuenta_como_edicion_si_es_programatica(app):
    app.var_rango.set("Últimos 30 días")
    app._on_rango()
    app._on_fecha_editada()
    assert app._leer_rango() == {"modo": "30_dias"}
    app._aplicar_rango_a_widgets({"modo": "6_meses"})
    app._on_fecha_editada()
    assert app._leer_rango() == {"modo": "6_meses"}
    app._limpiar()
    assert app._leer_rango() == {"modo": "ultimo_anio"}


def test_guardar_tras_navegar_por_las_fechas_conserva_el_rango_movil(app, monkeypatch):
    monkeypatch.setattr("app_secop.simpledialog.askstring", lambda *a, **k: "Movil")
    app.entry_texto.insert(0, "x")
    app.ent_desde.icursor(3)                             # moverse sin escribir
    app._on_fecha_editada()
    app._guardar_busqueda()
    assert app.directorio.buscar_busqueda_por_nombre("Movil")["rango"] == {"modo": "ultimo_anio"}


def test_guardar_con_nombre_existente_pide_confirmacion(app, monkeypatch):
    preguntas = []
    respuesta = [False]
    monkeypatch.setattr("app_secop.simpledialog.askstring", lambda *a, **k: "rEPETIDA")
    monkeypatch.setattr("app_secop.messagebox.askyesno",
                        lambda *a, **k: preguntas.append(a) or respuesta[0])
    b = app.directorio.guardar_busqueda("Repetida", {"texto": "viejo"})
    app.directorio.registrar_ejecucion(b["id"], ["a"])
    app.entry_texto.insert(0, "nuevo")
    app._guardar_busqueda()                              # No: no se toca nada
    assert preguntas and "nuev" in preguntas[0][1].lower()
    assert app.directorio.buscar_busqueda_por_nombre("Repetida")["filtros"] == {"texto": "viejo"}
    respuesta[0] = True
    app._guardar_busqueda()                              # Si: se sobrescribe
    assert app.directorio.buscar_busqueda_por_nombre("Repetida")["filtros"] == {"texto": "nuevo"}


def test_guardar_nombre_nuevo_no_pide_confirmacion(app, monkeypatch):
    monkeypatch.setattr("app_secop.simpledialog.askstring", lambda *a, **k: "Nueva")
    monkeypatch.setattr("app_secop.messagebox.askyesno",
                        lambda *a, **k: pytest.fail("no debia preguntar"))
    app.entry_texto.insert(0, "x")
    app._guardar_busqueda()
    assert app.directorio.buscar_busqueda_por_nombre("Nueva") is not None


@pytest.mark.parametrize("activa", ["consultando", "exportando"])
def test_botones_de_busquedas_y_empresa_se_desactivan_durante_operaciones(app, activa):
    botones = list(app._btns_busqueda.values()) + [app.btn_buscar_empresa]
    getattr(app, f"_set_{activa}")(True)
    assert all(str(b.cget("state")) == "disabled" for b in botones)
    getattr(app, f"_set_{activa}")(False)
    assert all(str(b.cget("state")) == "normal" for b in botones)


def test_ejecutar_todas_desactiva_los_botones(app, monkeypatch):
    monkeypatch.setattr("app_secop.threading.Thread",
                        lambda target=None, args=(), daemon=None, **k:
                        type("H", (), {"start": lambda s: None})())
    app.directorio.guardar_busqueda("B", {"texto": "x"})
    app._ejecutar_todas()
    assert str(app._btns_busqueda["guardar"].cget("state")) == "disabled"
    assert str(app.btn_buscar_empresa.cget("state")) == "disabled"


def test_una_sancion_nueva_conserva_el_resaltado_rojo(app):
    sancion = dict(_fila("S1"), sancion="SI", fuente="Sancion SECOP II")
    normal = _fila("C1")
    app._nuevos = {identificar_fila(sancion), identificar_fila(normal)}
    app._renderizar_tabla_lazy([sancion, normal], 0)
    t_sancion, t_normal = [app.tree.item(i, "tags") for i in app.tree.get_children()]
    assert list(t_sancion[:2]) == ["sancion", "nuevo"]
    assert "nuevo" in t_normal
    # prioridad de tags: el creado primero gana (sancion antes que nuevo)
    nombres = list(app.tree.tk.splitlist(app.tree.tk.call(app.tree._w, "tag", "names")))
    assert nombres.index("sancion") < nombres.index("nuevo")


def test_ejecutar_todas_cancelada_antes_de_registrar_no_registra(app, query_falsa):
    b = app.directorio.guardar_busqueda("B", {"texto": "x"})
    app._set_consultando(True)
    token = app._consulta_id
    QueryFalsa.al_consultar = app._cancelar_operacion    # Cancelar mientras consulta
    app._hilo_ejecutar_todas([dict(b)], token)
    app.update()
    assert app.directorio.obtener_busqueda(b["id"])["ultima_ejecucion"] == ""
    assert query_falsa == [] and app._consultando is False


@pytest.mark.parametrize("dato", [{"filtros": ["no", "dict"]}, {"rango": "6_meses"},
                                  {"filtros": None, "rango": 7}])
def test_ejecutar_todas_con_datos_corruptos_informa_y_libera_la_ui(app, query_falsa, dato):
    infos = query_falsa
    mala = dict({"id": "m", "nombre": "Corrupta", "filtros": {"texto": "a"},
                 "rango": {"modo": "ultimo_anio"}, "ultimos_ids": [], "ultima_ejecucion": ""},
                **dato)
    buena = app.directorio.guardar_busqueda("Buena", {"texto": "b"})
    app._set_consultando(True)
    app._hilo_ejecutar_todas([mala, dict(buena)], app._consulta_id)
    app.update()
    assert app._consultando is False and infos
    assert "Corrupta" in infos[0][1] and "Buena" in infos[0][1]


def test_ejecutar_todas_si_falla_crear_la_consulta_libera_la_ui(app, query_falsa, monkeypatch):
    def falla(*a, **k):
        raise RuntimeError("sin cliente")
    monkeypatch.setattr(app_secop, "SECOPClient", falla)
    b = app.directorio.guardar_busqueda("B", {"texto": "x"})
    app._set_consultando(True)
    app._hilo_ejecutar_todas([dict(b)], app._consulta_id)
    app.update()
    assert app._consultando is False and "sin cliente" in query_falsa[0][1]


def test_guardar_busqueda_con_nit_manual_invalido_avisa(app, monkeypatch):
    avisos = []
    monkeypatch.setattr("app_secop.messagebox.showwarning", lambda *a, **k: avisos.append(a))
    monkeypatch.setattr("app_secop.simpledialog.askstring", lambda *a, **k: "N")
    app.entry_nit.insert(0, "12")
    app._guardar_busqueda()
    assert avisos and app.directorio.buscar_busqueda_por_nombre("N") is None


def test_guardar_busqueda_con_nit_de_entidad_invalido_avisa(app, monkeypatch):
    avisos = []
    monkeypatch.setattr("app_secop.messagebox.showwarning", lambda *a, **k: avisos.append(a))
    monkeypatch.setattr("app_secop.simpledialog.askstring", lambda *a, **k: "N")
    app.entry_texto.insert(0, "x")
    app.entry_entidad_nit.insert(0, "abc")
    app._guardar_busqueda()
    assert avisos and app.directorio.buscar_busqueda_por_nombre("N") is None


def test_ejecutar_todas_omite_busquedas_con_nit_invalido(app, query_falsa):
    app.directorio.guardar_busqueda("MalNit", {"nit_proveedor": "12"})
    app.directorio.guardar_busqueda("MalEnt", {"texto": "a", "entidad_nit": "xyz"})
    app._set_consultando(True)
    app._hilo_ejecutar_todas(app.directorio.listar_busquedas(), app._consulta_id)
    app.update()
    assert QueryFalsa.llamadas == []
    resumen = query_falsa[0][1]
    assert "MalNit" in resumen and "MalEnt" in resumen and "invalid" in resumen.lower()


def test_ejecutar_todas_pasa_el_nit_como_nombre_y_nit(app, query_falsa):
    app.directorio.guardar_busqueda("ConNit", {"nit_proveedor": "900123456"})
    app.directorio.guardar_busqueda("SinNit", {"texto": "a"})
    app._set_consultando(True)
    app._hilo_ejecutar_todas(app.directorio.listar_busquedas(), app._consulta_id)
    app.update()
    assert [(c[0], c[1]) for c in QueryFalsa.llamadas] == [("900123456", "900123456"),
                                                           (None, None)]


def test_ejecutar_todas_no_registra_si_la_pagina_tiene_errores(app, query_falsa):
    b = app.directorio.guardar_busqueda("B", {"texto": "x"})
    QueryFalsa.errores = ["Contratos: 503"]
    app._set_consultando(True)
    app._hilo_ejecutar_todas([dict(b)], app._consulta_id)
    app.update()
    assert app.directorio.obtener_busqueda(b["id"])["ultima_ejecucion"] == ""
    assert "503" in query_falsa[0][1]


def test_ejecutar_no_compara_ni_registra_si_la_pagina_1_tiene_errores(app, monkeypatch):
    monkeypatch.setattr(app_secop.AppSECOP, "_iniciar_conteo", lambda self: None)
    monkeypatch.setattr(app_secop.AppSECOP, "_mostrar_errores", lambda self: None)
    b = app.directorio.guardar_busqueda("X", {"texto": "a"})
    app.directorio.registrar_ejecucion(b["id"], ["previo"])
    antes = app.directorio.obtener_busqueda(b["id"])["ultima_ejecucion"]
    app._filtros_activos = {"empresas": {None: None}, "filtros": Filtros(texto="a")}
    app._busqueda_activa = b["id"]
    app._mostrar_resultados_pagina([_fila("C1")], {}, ["Procesos: 503"], False, 0, [], [])
    guardada = app.directorio.obtener_busqueda(b["id"])
    assert guardada["ultimos_ids"] == ["previo"] and guardada["ultima_ejecucion"] == antes
    assert app._nuevos == set() and app._busqueda_activa is None
    assert "sin registrar" in app.lbl_estado.cget("text")


def test_consulta_solo_por_nit_usa_el_ultimo_anio(app, monkeypatch):
    lanzados = []
    monkeypatch.setattr("app_secop.threading.Thread",
                        lambda target=None, args=(), daemon=None, **k:
                        type("H", (), {"start": lambda s: lanzados.append(args)})())
    app.entry_nit.insert(0, "900123456")
    app._iniciar_consulta()
    empresas, filtros = lanzados[0][0], lanzados[0][1]
    hoy = date.today()
    assert empresas == {"900123456": "900123456"}
    assert filtros.nit_proveedor == "900123456"
    assert (filtros.fecha_desde, filtros.fecha_hasta) == (
        (hoy - timedelta(days=365)).isoformat(), hoy.isoformat())


def test_aviso_inicio_muestra_el_aviso_una_vez_y_ofrece_ejecutar(app, monkeypatch):
    avisos, preguntas, ejecutadas = [], [], []
    monkeypatch.setattr("app_secop.messagebox.showwarning", lambda *a, **k: avisos.append(a))
    monkeypatch.setattr("app_secop.messagebox.askyesno",
                        lambda *a, **k: preguntas.append(a) or True)
    monkeypatch.setattr(app_secop.AppSECOP, "_ejecutar_todas",
                        lambda self: ejecutadas.append(1))
    app.directorio.aviso = "El directorio estaba danado; se respaldo en X"
    app.directorio.guardar_busqueda("B", {"texto": "x"})
    AVISO_INICIO_REAL(app)
    assert len(avisos) == 1 and "danado" in avisos[0][1]
    assert app.directorio.aviso == ""
    assert preguntas and "1 busqueda" in preguntas[0][1] and ejecutadas == [1]
    AVISO_INICIO_REAL(app)                                  # el aviso no se repite
    assert len(avisos) == 1


def test_aviso_inicio_sin_busquedas_no_pregunta(app, monkeypatch):
    monkeypatch.setattr("app_secop.messagebox.askyesno",
                        lambda *a, **k: pytest.fail("no debia preguntar"))
    monkeypatch.setattr("app_secop.messagebox.showwarning",
                        lambda *a, **k: pytest.fail("no hay aviso"))
    AVISO_INICIO_REAL(app)


# ---- revision final: avanzados ocultos visibles; fallo al pintar no bloquea la UI -------

def test_filtros_avanzados_ocultos_pero_activos_se_indican(app, monkeypatch):
    monkeypatch.setattr("app_secop.threading.Thread",
                        lambda target=None, args=(), daemon=None, **k:
                        type("H", (), {"start": lambda s: None})())
    app.var_avanzado.set(True)
    app._toggle_avanzado()
    app.ent_av["estado"].insert(0, "activo")
    assert app.chk_avanzado.cget("text") == "Filtros avanzados"     # a la vista: sin aviso
    app.var_avanzado.set(False)
    app._toggle_avanzado()
    assert app.chk_avanzado.cget("text") == "Filtros avanzados activos (1)"
    app.entry_texto.insert(0, "x")
    app._iniciar_consulta()
    assert "Filtros avanzados: Estado: activo" in app.lbl_rango.cget("text")
    app._consultando = False
    app._limpiar()
    assert app.chk_avanzado.cget("text") == "Filtros avanzados"


def test_error_al_pintar_los_resultados_termina_la_consulta_y_se_informa(app, monkeypatch):
    def falla(*a, **k):
        raise RuntimeError("fallo al pintar")
    monkeypatch.setattr(app, "_renderizar_tabla_lazy", falla)
    app._set_consultando(True)
    app._mostrar_resultados_pagina([_fila("C1")], {}, [], False, 0, [], [])
    assert app._consultando is False
    assert str(app.btn_consultar.cget("state")) == "normal"
    assert "fallo al pintar" in app.lbl_estado.cget("text")
