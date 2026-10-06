from datetime import date, timedelta

from search import Filtros, identificar_fila


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
    llamadas = []

    def __init__(self, client):
        pass

    def consultar_pagina(self, nombre, nit=None, filtros=None, offset=0, page_size=100,
                         on_progress=None):
        QueryFalsa.llamadas.append(filtros)
        return [_fila("C1")], {}, [], False


def test_ejecutar_todas_no_consulta_busquedas_con_fechas_guardadas_invalidas(app, monkeypatch):
    import app_secop
    QueryFalsa.llamadas = []
    monkeypatch.setattr(app_secop, "SECOPQuery", QueryFalsa)
    infos = []
    monkeypatch.setattr("app_secop.messagebox.showinfo", lambda *a, **k: infos.append(a))
    app.directorio.guardar_busqueda("Mala", {"texto": "a"},
                                    {"modo": "personalizado", "desde": "2024-99-99", "hasta": ""})
    app.directorio.guardar_busqueda("Buena", {"texto": "b"}, {"modo": "30_dias"})
    app._set_consultando(True)
    app._hilo_ejecutar_todas(app.directorio.listar_busquedas(), app._consulta_id)
    app.update()
    assert [f.texto for f in QueryFalsa.llamadas] == ["b"]   # la invalida no se consulta
    assert QueryFalsa.llamadas[0].fecha_desde != ""           # rango recalculado a hoy
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
