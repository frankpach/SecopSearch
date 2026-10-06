import gc
import json
import os
import tkinter as tk

import pytest

from storage import Directorio
from ui_directorio import DialogoEdicion, VentanaDirectorio


@pytest.fixture
def raiz():
    # Con reintentos: en Windows crear un Tk falla a veces con TclError aunque haya
    # display; solo se salta si falla siempre.
    error = None
    for _ in range(5):
        try:
            r = tk.Tk()
            break
        except tk.TclError as e:
            error = e
    else:
        pytest.skip("sin display: %s" % error)
    r.withdraw()
    yield r
    r.destroy()
    del r
    gc.collect()        # objetos Tk ciclicos se liberan aqui, en el hilo principal


class HiloInmediato:
    """Sustituye threading.Thread: ejecuta el trabajo al instante en este hilo."""

    def __init__(self, target=None, args=(), daemon=None, **k):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


class HiloMudo:
    """Sustituye threading.Thread: no ejecuta nada."""

    def __init__(self, *a, **k):
        pass

    def start(self):
        pass


def _procesar(w):
    for _ in range(3):
        w.update()


def test_dialogo_edicion_devuelve_campos_normalizados(raiz):
    d = DialogoEdicion(raiz, "Editar", {"nombre": "ACME", "nit": "900123456",
                                         "alias": "a", "etiquetas": ["x", "y"], "notas": "n"})
    assert d.ent_nombre.get() == "ACME" and d.ent_etiquetas.get() == "x, y"
    d.ent_nombre.delete(0, "end")
    d.ent_nombre.insert(0, "  ACME SAS ")
    d._aceptar()
    assert d.resultado == {"nombre": "ACME SAS", "nit": "900123456", "alias": "a",
                           "etiquetas": "x, y", "notas": "n"}


def test_dialogo_edicion_exige_nombre_o_nit(raiz, monkeypatch):
    monkeypatch.setattr("ui_directorio.messagebox.showwarning", lambda *a, **k: None)
    d = DialogoEdicion(raiz, "Nuevo", {})
    d._aceptar()
    assert d.resultado is None


def test_ventana_lista_filtra_y_refresca(raiz, tmp_path):
    dir_ = Directorio(str(tmp_path / "d.json"))
    dir_.agregar("empresas", "ACME", "111111111", etiquetas=["vigilancia"])
    dir_.agregar("empresas", "Beta", "222222222")
    dir_.agregar("entidades", "Alcaldia", "800000001")
    cambios = []
    v = VentanaDirectorio(raiz, dir_, lambda: None, lambda: cambios.append(1))
    panel = v.paneles["empresas"]
    assert len(panel.tree.get_children()) == 2
    panel.var_filtro.set("vigil")
    assert len(panel.tree.get_children()) == 1
    assert len(v.paneles["entidades"].tree.get_children()) == 1
    v.destroy()


def test_eliminar_y_notificar(raiz, tmp_path, monkeypatch):
    dir_ = Directorio(str(tmp_path / "d.json"))
    e = dir_.agregar("empresas", "ACME", "111111111")
    cambios = []
    v = VentanaDirectorio(raiz, dir_, lambda: None, lambda: cambios.append(1))
    panel = v.paneles["empresas"]
    panel.tree.selection_set(e["id"])
    monkeypatch.setattr("ui_directorio.messagebox.askyesno", lambda *a, **k: True)
    panel.eliminar()
    assert dir_.listar("empresas") == [] and cambios
    v.destroy()


def test_fusionar_dos_seleccionados(raiz, tmp_path, monkeypatch):
    dir_ = Directorio(str(tmp_path / "d.json"))
    a = dir_.agregar("empresas", "A", "111111111", etiquetas=["x"])
    b = dir_.agregar("empresas", "A bis", "", etiquetas=["y"])
    v = VentanaDirectorio(raiz, dir_, lambda: None, lambda: None)
    panel = v.paneles["empresas"]
    panel.tree.selection_set((a["id"], b["id"]))
    monkeypatch.setattr("ui_directorio.messagebox.askyesno", lambda *a, **k: True)
    panel.fusionar()
    restantes = dir_.listar("empresas")
    assert len(restantes) == 1 and restantes[0]["etiquetas"] == ["x", "y"]
    v.destroy()


# ---- resolucion del nombre oficial en segundo plano -----------------------------

def test_dialogo_resuelve_el_nombre_oficial_sin_bloquear(raiz, monkeypatch):
    monkeypatch.setattr("ui_directorio.threading.Thread", HiloInmediato)
    d = DialogoEdicion(raiz, "Nuevo", {"nit": "900123456"}, resolver=lambda nit: "OFICIAL SAS")
    d._resolver_nombre()
    _procesar(raiz)
    assert d.ent_nombre.get() == "OFICIAL SAS"


def test_dialogo_descarta_el_nombre_si_cambio_el_nit_o_se_cerro(raiz, monkeypatch):
    monkeypatch.setattr("ui_directorio.threading.Thread", HiloInmediato)
    errores = []
    raiz.report_callback_exception = lambda *a: errores.append(a)
    d = DialogoEdicion(raiz, "Nuevo", {"nit": "900123456"}, resolver=lambda nit: "OFICIAL SAS")
    d._resolver_nombre()
    d.ent_nit.insert("end", "9")                    # el NIT cambio antes de llegar la respuesta
    _procesar(raiz)
    assert d.ent_nombre.get() == ""
    d2 = DialogoEdicion(raiz, "Nuevo", {"nit": "900123456"}, resolver=lambda nit: "OFICIAL SAS")
    d2._resolver_nombre()
    d2.destroy()                                    # cerrado antes de llegar la respuesta
    _procesar(raiz)
    assert errores == []


def test_editar_sin_cambiar_el_nombre_conserva_el_nombre_pendiente(raiz, tmp_path, monkeypatch):
    monkeypatch.setattr("ui_directorio.threading.Thread", HiloMudo)
    dir_ = Directorio(str(tmp_path / "d.json"))
    e = dir_.agregar("empresas", "", "900123456")   # nombre pendiente (= NIT)

    class DialogoFalso:
        def __init__(self, master, titulo, datos, resolver=None):
            self.resultado = {"nombre": datos["nombre"], "nit": datos["nit"], "alias": "al",
                              "etiquetas": "", "notas": ""}

        def wait_window(self):
            pass
    monkeypatch.setattr("ui_directorio.DialogoEdicion", DialogoFalso)
    v = VentanaDirectorio(raiz, dir_, lambda: None, lambda: None)
    panel = v.paneles["empresas"]
    panel.tree.selection_set(e["id"])
    panel.editar()
    item = dir_.obtener("empresas", e["id"])
    assert item["alias"] == "al" and item["nombre_resuelto"] is False
    v.destroy()


def test_ventana_resuelve_pendientes_y_notifica(raiz, tmp_path, monkeypatch):
    monkeypatch.setattr("ui_directorio.threading.Thread", HiloInmediato)
    monkeypatch.setattr("ui_directorio.resolver_nombre_oficial", lambda client, nit: "OFICIAL SAS")
    dir_ = Directorio(str(tmp_path / "d.json"))
    e = dir_.agregar("empresas", "", "900123456")
    cambios = []
    v = VentanaDirectorio(raiz, dir_, lambda: None, lambda: cambios.append(1))
    _procesar(raiz)
    assert dir_.obtener("empresas", e["id"])["nombre"] == "OFICIAL SAS" and cambios
    assert v.paneles["empresas"].tree.item(e["id"], "values")[0] == "OFICIAL SAS"
    v.destroy()


# ---- integracion con AppSECOP ---------------------------------------------------

@pytest.fixture
def legado(tmp_path, monkeypatch):
    """JSON antiguos en el directorio de trabajo (aislado) antes de crear la app."""
    monkeypatch.chdir(tmp_path)
    with open(tmp_path / "empresas_historial.json", "w", encoding="utf-8") as f:
        json.dump([{"nombre": "ACME SAS", "nit": "900123456", "ultima_consulta": "2025-01-01"}], f)
    with open(tmp_path / "entidades_historial.json", "w", encoding="utf-8") as f:
        json.dump([{"nombre": "Alcaldia", "nit": "800000001"}], f)
    return tmp_path


@pytest.fixture
def app_migrada(legado, app):
    return app


def test_app_migra_los_historiales_antiguos(app_migrada, legado):
    assert "ACME SAS" in app_migrada.combo_empresa["values"]
    assert "Alcaldia" in app_migrada.combo_entidad["values"]
    assert app_migrada.empresas == {"ACME SAS": "900123456"}
    assert os.path.exists(legado / "empresas_historial.json.bak")
    assert os.path.exists(legado / "entidades_historial.json.bak")
    assert app_migrada.directorio.ruta.startswith(os.environ["SECOP_DATA_DIR"])


def test_empresas_y_entidades_son_de_solo_lectura(app):
    with pytest.raises(AttributeError):
        app.empresas = {}
    with pytest.raises(AttributeError):
        app.entidades = {}


def test_guardar_nit_manual_y_resolver_el_nombre_oficial(app, monkeypatch):
    import app_secop
    monkeypatch.setattr(app_secop.threading, "Thread", HiloInmediato)
    monkeypatch.setattr(app_secop, "resolver_nombre_oficial", lambda client, nit: "OFICIAL SAS")
    app.entry_nit.insert(0, "900123456")
    app._guardar_empresa_manual()
    _procesar(app)
    item = app.directorio.buscar_por_nit("empresas", "900123456")
    assert item["nombre"] == "OFICIAL SAS" and item["nombre_resuelto"] is True
    assert app.var_empresa.get() == "OFICIAL SAS"           # la seleccion sigue al registro
    assert "OFICIAL SAS" in app.combo_empresa["values"]


def test_actualizar_historiales_agrega_al_directorio_sin_duplicar(app):
    app._actualizar_historiales([("ACME", "111111111")], [("Alcaldia", "800000001")])
    app._actualizar_historiales([("ACME", "111111111")], [("Alcaldia", "800000001")])
    assert app.empresas == {"ACME": "111111111"} and app.entidades == {"Alcaldia": "800000001"}
    assert "ACME" in app.combo_empresa["values"] and "Alcaldia" in app.combo_entidad["values"]


def test_consulta_marca_ultima_consulta_y_completa_el_nombre(app, monkeypatch):
    import app_secop
    from search import Filtros
    e = app.directorio.agregar("empresas", "", "900123456")
    app._refrescar_combos()
    app.var_empresa.set("900123456")

    class QueryFalsa:
        def __init__(self, client):
            self.omitidos = []

        def consultar_pagina(self, *a, **k):
            return [{"empresa": "ACME SAS", "estado": "Activo"}], {}, [], False
    monkeypatch.setattr(app_secop, "SECOPQuery", QueryFalsa)
    monkeypatch.setattr(app, "_mostrar_resultados_pagina", lambda *a: None)
    app._hilo_consulta({"900123456": "900123456"}, Filtros(nit_proveedor="900123456"), 0,
                       app._consulta_id)
    _procesar(app)
    item = app.directorio.obtener("empresas", e["id"])
    assert item["nombre"] == "ACME SAS" and item["ultima_consulta"]
    assert app.var_empresa.get() == "ACME SAS"


def test_eliminar_empresa_del_combo(app, monkeypatch):
    import app_secop
    app.directorio.agregar("empresas", "ACME", "111111111")
    app._refrescar_combos()
    app.var_empresa.set("ACME")
    monkeypatch.setattr(app_secop.messagebox, "askyesno", lambda *a, **k: True)
    app._eliminar_empresa()
    assert app.empresas == {} and app.var_empresa.get() == "TODAS"


def test_editar_seleccion_abre_una_sola_ventana_con_el_registro(app):
    e = app.directorio.agregar("entidades", "Alcaldia", "800000001")
    app._refrescar_combos()
    app.var_entidad.set("Alcaldia")
    v = app._editar_seleccion("entidades")
    assert v.paneles["entidades"].tree.selection() == (e["id"],)
    assert app._abrir_directorio() is v                     # no abre otra ventana


def test_exportar_recuerda_la_ultima_eleccion(app, monkeypatch):
    import app_secop
    from search import Filtros
    opc = {"alcance": "pagina", "formato": "csv", "columnas": ["valor"], "delimitador": ";"}
    previos = []

    class DialogoFalso:
        def __init__(self, master, columnas, n_pagina, n_sel, previo=None, total_estimado=None):
            previos.append(previo)
            self.resultado = opc

        def wait_window(self):
            pass
    monkeypatch.setattr(app_secop, "DialogoExportar", DialogoFalso)
    monkeypatch.setattr(app_secop.filedialog, "asksaveasfilename", lambda **k: "")
    app._filtros_activos = {"empresas": {None: None}, "filtros": Filtros(texto="x")}
    app._exportar()
    app._exportar()
    assert previos == [{}, opc]
    assert Directorio(app.directorio.ruta).preferencia("exportar") == opc


def test_consultar_una_empresa_sin_nit_avisa_y_no_consulta(app, monkeypatch):
    import app_secop
    lanzados, avisos = [], []
    monkeypatch.setattr(app_secop.threading, "Thread", lambda *a, **k: lanzados.append(k))
    monkeypatch.setattr(app_secop.messagebox, "showwarning", lambda *a, **k: avisos.append(a))
    app.directorio.agregar("empresas", "Sin NIT SAS", "")
    app._refrescar_combos()
    app.var_empresa.set("Sin NIT SAS")
    app._iniciar_consulta()
    assert lanzados == [] and avisos and "NIT" in avisos[0][0]


# ---- correcciones de la revision ------------------------------------------------

class HiloDiferido:
    """Sustituye threading.Thread: guarda el trabajo para ejecutarlo cuando la prueba quiera."""
    pendientes = []

    def __init__(self, target=None, args=(), daemon=None, **k):
        self.target, self.args = target, args

    def start(self):
        HiloDiferido.pendientes.append(self)

    @classmethod
    def correr_todos(cls):
        while cls.pendientes:
            h = cls.pendientes.pop(0)
            h.target(*h.args)


def _fila(empresa="ACME SAS", nit="900123456"):
    return {"fuente": "SECOP II", "id_contrato": "C1", "empresa": empresa, "nit": nit,
            "entidad": "X", "entidad_nit": "", "referencia": "", "objeto": "o", "valor": "$1",
            "pagado": "", "pendiente": "", "estado": "Activo", "fecha_firma": "2025-01-01",
            "fecha_fin": "", "sancion": "No", "url": ""}


def test_editar_no_pisa_el_nombre_oficial_que_llego_con_el_dialogo_abierto(raiz, tmp_path, monkeypatch):
    # Escenario A: el nombre oficial llega mientras el dialogo esta abierto; el usuario
    # solo cambia el alias y guarda. Se conserva el nombre oficial.
    monkeypatch.setattr("ui_directorio.threading.Thread", HiloMudo)
    dir_ = Directorio(str(tmp_path / "d.json"))
    e = dir_.agregar("empresas", "", "900123456")

    class DialogoFalso:
        def __init__(self, master, titulo, datos, resolver=None):
            self.visto = dict(datos)                 # lo que el usuario ve al abrir

        def wait_window(self):
            # llega el nombre oficial (escritura directa: no depende del arreglo de storage)
            dir_.actualizar("empresas", e["id"], nombre="OFICIAL SAS")
            self.resultado = {"nombre": self.visto["nombre"], "nit": self.visto["nit"],
                              "alias": "al", "etiquetas": "", "notas": ""}
    monkeypatch.setattr("ui_directorio.DialogoEdicion", DialogoFalso)
    v = VentanaDirectorio(raiz, dir_, lambda: None, lambda: None)
    panel = v.paneles["empresas"]
    panel.tree.selection_set(e["id"])
    panel.editar()
    item = dir_.obtener("empresas", e["id"])
    assert item["nombre"] == "OFICIAL SAS" and item["nombre_resuelto"] is True
    assert item["alias"] == "al"
    v.destroy()


def test_resolver_async_no_pisa_un_nombre_escrito_mientras_buscaba(app, monkeypatch):
    # Escenario B: el usuario escribe el nombre mientras la busqueda esta en vuelo
    import app_secop
    monkeypatch.setattr(app_secop.threading, "Thread", HiloInmediato)
    e = app.directorio.agregar("empresas", "", "900123456")

    def resolver(client, nit):
        app.directorio.actualizar("empresas", e["id"], nombre="Escrito a mano")
        return "OFICIAL SAS"
    monkeypatch.setattr(app_secop, "resolver_nombre_oficial", resolver)
    app._resolver_nombre_async(e["id"], "900123456")
    _procesar(app)
    assert app.directorio.obtener("empresas", e["id"])["nombre"] == "Escrito a mano"


def test_resolver_pendientes_no_pisa_un_nombre_escrito_mientras_buscaba(raiz, tmp_path, monkeypatch):
    monkeypatch.setattr("ui_directorio.threading.Thread", HiloDiferido)
    HiloDiferido.pendientes = []
    dir_ = Directorio(str(tmp_path / "d.json"))
    e = dir_.agregar("empresas", "", "900123456")
    monkeypatch.setattr("ui_directorio.resolver_nombre_oficial", lambda client, nit: "OFICIAL SAS")
    v = VentanaDirectorio(raiz, dir_, lambda: None, lambda: None)
    dir_.actualizar("empresas", e["id"], nombre="Escrito a mano")   # antes de que responda
    HiloDiferido.correr_todos()
    _procesar(raiz)
    assert dir_.obtener("empresas", e["id"])["nombre"] == "Escrito a mano"
    v.destroy()


def test_resolver_pendientes_no_se_solapa(raiz, tmp_path, monkeypatch):
    monkeypatch.setattr("ui_directorio.threading.Thread", HiloDiferido)
    HiloDiferido.pendientes = []
    dir_ = Directorio(str(tmp_path / "d.json"))
    dir_.agregar("empresas", "", "900123456")
    monkeypatch.setattr("ui_directorio.resolver_nombre_oficial", lambda client, nit: "")
    v = VentanaDirectorio(raiz, dir_, lambda: None, lambda: None)
    v._resolver_pendientes()                         # el del constructor sigue en vuelo
    assert len(HiloDiferido.pendientes) == 1
    HiloDiferido.correr_todos()
    v._resolver_pendientes()                         # terminado el anterior, se puede repetir
    assert len(HiloDiferido.pendientes) == 1
    HiloDiferido.correr_todos()
    v.destroy()


def test_dialogo_no_pisa_un_nombre_escrito_mientras_buscaba(raiz, monkeypatch):
    monkeypatch.setattr("ui_directorio.threading.Thread", HiloDiferido)
    HiloDiferido.pendientes = []
    d = DialogoEdicion(raiz, "Nuevo", {"nit": "900123456"}, resolver=lambda nit: "OFICIAL SAS")
    d._resolver_nombre()
    d.ent_nombre.insert(0, "Escrito a mano")
    HiloDiferido.correr_todos()
    _procesar(raiz)
    assert d.ent_nombre.get() == "Escrito a mano"


@pytest.mark.parametrize("existente", [True, False])
def test_fallo_al_escribir_el_directorio_no_rompe_la_consulta(app, monkeypatch, existente):
    # existente=True: falla marcar_consulta en el hilo; False: falla agregar en la UI
    import app_secop
    from search import Filtros
    if existente:
        app.directorio.agregar("empresas", "", "900123456")

    def falla():
        raise PermissionError("bloqueado")
    monkeypatch.setattr(app.directorio, "guardar", falla)
    monkeypatch.setattr(app_secop.AppSECOP, "_iniciar_conteo", lambda self: None)

    class QueryFalsa:
        def __init__(self, client):
            self.omitidos = []

        def consultar_pagina(self, *a, **k):
            return [_fila()], {}, [], False
    monkeypatch.setattr(app_secop, "SECOPQuery", QueryFalsa)
    app._set_consultando(True)
    app._hilo_consulta({"900123456": "900123456"}, Filtros(nit_proveedor="900123456"), 0,
                       app._consulta_id)
    _procesar(app)
    assert app._consultando is False and len(app.tree.get_children()) == 1
    assert "directorio" in app.lbl_estado.cget("text").lower()


def test_consulta_cancelada_no_marca_ultima_consulta(app, monkeypatch):
    import app_secop
    from search import Filtros
    e = app.directorio.agregar("empresas", "ACME", "900123456")
    llamadas = []

    class QueryFalsa:
        def __init__(self, client):
            self.omitidos = []

        def consultar_pagina(self, *a, **k):
            llamadas.append(1)
            if len(llamadas) == 2:
                app._consulta_id += 1                # se cancela durante la segunda empresa
            return [_fila()], {}, [], False
    monkeypatch.setattr(app_secop, "SECOPQuery", QueryFalsa)
    app._hilo_consulta({"ACME": "900123456", "Otra": "800000001"}, Filtros(texto="x"), 0,
                       app._consulta_id)
    _procesar(app)
    assert app.directorio.obtener("empresas", e["id"])["ultima_consulta"] == ""


def test_guardar_entidad_con_nombre_repetido_selecciona_el_registro_correcto(app, monkeypatch):
    import app_secop
    monkeypatch.setattr(app_secop.messagebox, "showinfo", lambda *a, **k: None)
    app.directorio.agregar("entidades", "Alcaldia", "800000001")
    app._refrescar_combos()
    app.entry_entidad_nombre.insert(0, "Alcaldia")
    app.entry_entidad_nit.insert(0, "800000002")
    app._guardar_entidad_manual()
    assert app._item_seleccionado("entidades")["nit"] == "800000002"
    app.var_entidad.set("TODAS")
    app._guardar_entidad_manual()                    # ya existe: selecciona ese mismo
    assert app._item_seleccionado("entidades")["nit"] == "800000002"


def test_guardar_empresa_con_nombre_repetido_selecciona_el_registro_correcto(app, monkeypatch):
    import app_secop
    monkeypatch.setattr(app_secop.AppSECOP, "_resolver_nombre_async", lambda self, i, n: None)
    app.directorio.agregar("empresas", "900123456", "111111111")   # se llama como el NIT nuevo
    app._refrescar_combos()
    app.entry_nit.insert(0, "900123456")
    app._guardar_empresa_manual()
    assert app._item_seleccionado("empresas")["nit"] == "900123456"


def test_errores_de_escritura_en_la_ui_se_avisan_sin_traceback(app, monkeypatch):
    import app_secop
    errores = []
    monkeypatch.setattr(app_secop.messagebox, "showerror", lambda *a, **k: errores.append(a))
    monkeypatch.setattr("ui_directorio.messagebox.showerror", lambda *a, **k: errores.append(a))
    monkeypatch.setattr("ui_directorio.messagebox.askyesno", lambda *a, **k: True)
    monkeypatch.setattr(app_secop.messagebox, "askyesno", lambda *a, **k: True)
    monkeypatch.setattr("ui_directorio.threading.Thread", HiloMudo)
    a = app.directorio.agregar("entidades", "Alcaldia", "800000001")
    b = app.directorio.agregar("entidades", "Gobernacion", "800000002")
    app._refrescar_combos()

    def falla(*x, **k):
        raise PermissionError("bloqueado")
    monkeypatch.setattr(app.directorio, "guardar", falla)
    app.entry_entidad_nombre.insert(0, "Nueva")
    app._guardar_entidad_manual()
    app.entry_nit.insert(0, "900123456")
    app._guardar_empresa_manual()
    app.var_entidad.set("Alcaldia")
    app._eliminar_entidad()
    v = app._abrir_directorio("entidades")
    panel = v.paneles["entidades"]
    panel.tree.selection_set((a["id"], b["id"]))
    panel.eliminar()
    panel.tree.selection_set((a["id"], b["id"]))
    panel.fusionar()
    assert len(errores) == 5
    assert len(app.directorio.listar("entidades")) == 2         # nada cambio en memoria


def test_aviso_de_migracion_fallida_no_borra_el_aviso_previo(legado, monkeypatch):
    import app_secop
    import storage

    def migrar_falla(self, *a):
        raise PermissionError("bloqueado")
    monkeypatch.setattr(storage.Directorio, "migrar_historiales", migrar_falla)
    datos = os.environ["SECOP_DATA_DIR"]
    os.makedirs(datos, exist_ok=True)
    with open(os.path.join(datos, "directorio.json"), "w", encoding="utf-8") as f:
        f.write("{roto")
    monkeypatch.setattr(app_secop.AppSECOP, "_cargar_metadatos_async", lambda self: None)
    a = None
    for _ in range(5):
        try:
            a = app_secop.AppSECOP()
            break
        except tk.TclError:
            pass
    if a is None:
        pytest.skip("sin display")
    try:
        assert "danado" in a.directorio.aviso and "bloqueado" in a.directorio.aviso
    finally:
        a.destroy()
        del a
        gc.collect()
