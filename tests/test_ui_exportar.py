import os
import tkinter as tk

import pytest

from ui_exportar import DialogoExportar

COLS = [("a", "A", 10), ("b", "B", 10), ("c", "C", 10)]


@pytest.fixture
def raiz():
    # Con reintentos: en Windows crear un Tk falla a veces con TclError aunque haya
    # display; solo se salta si falla siempre. Uno por prueba (como `app`) para no
    # convivir con el Tk de AppSECOP en las pruebas del flujo de la app.
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


def test_valores_por_defecto(raiz):
    d = DialogoExportar(raiz, COLS, n_pagina=5, n_sel=0, previo=None)
    assert d.var_alcance.get() == "pagina" and d.var_formato.get() == "xlsx"
    d._aceptar()
    assert d.resultado["columnas"] == ["a", "b", "c"]
    assert d.resultado["delimitador"] == ","


def test_seleccion_deshabilitada_sin_filas_seleccionadas(raiz):
    d = DialogoExportar(raiz, COLS, 5, 0, {"alcance": "seleccion"})
    assert d.var_alcance.get() == "pagina"
    d2 = DialogoExportar(raiz, COLS, 5, 3, {"alcance": "seleccion"})
    assert d2.var_alcance.get() == "seleccion"


def test_recuerda_columnas_y_formato(raiz):
    previo = {"alcance": "todos", "formato": "csv", "columnas": ["b"], "delimitador": ";"}
    d = DialogoExportar(raiz, COLS, 5, 0, previo)
    d._aceptar()
    assert d.resultado == {"alcance": "todos", "formato": "csv",
                           "columnas": ["b"], "delimitador": ";"}


def test_csv_por_dataset_solo_con_todos(raiz):
    d = DialogoExportar(raiz, COLS, 5, 0, {"alcance": "pagina", "formato": "csv_dataset"})
    assert d.var_formato.get() == "xlsx"


def test_total_estimado_en_la_etiqueta(raiz):
    d = DialogoExportar(raiz, COLS, 5, 0, None, total_estimado=45000)
    assert "45.000" in d.rb_todos.cget("text")


def test_sin_columnas_no_acepta(raiz, monkeypatch):
    d = DialogoExportar(raiz, COLS, 5, 0)
    for v in d.vars_columnas.values():
        v.set(False)
    monkeypatch.setattr("ui_exportar.messagebox.showwarning", lambda *a, **k: None)
    d._aceptar()
    assert d.resultado is None


# ---- flujo de exportacion en AppSECOP ------------------------------------------

def _filas(n):
    return [{"fuente": "SECOP II", "id_contrato": f"C{i}", "empresa": "E", "nit": "1",
             "entidad": "X", "entidad_nit": "", "referencia": "", "objeto": "o", "valor": "1000",
             "pagado": "", "pendiente": "", "estado": "Activo", "fecha_firma": "2025-01-01",
             "fecha_fin": "", "sancion": "No", "url": ""} for i in range(n)]


class HiloFalso:
    """Sustituye threading.Thread: registra lo que se lanzaria, sin hilos."""
    lanzados = []

    def __init__(self, target=None, args=(), daemon=None, **k):
        self.target, self.args = target, args

    def start(self):
        HiloFalso.lanzados.append((self.target, self.args))


def _procesar(app):
    for _ in range(3):
        app.update()


@pytest.fixture
def lista(app, monkeypatch):
    """App con una pagina cargada, sin hilos, ni dialogos bloqueantes."""
    import app_secop
    from search import Filtros
    HiloFalso.lanzados = []
    monkeypatch.setattr(app_secop.threading, "Thread", HiloFalso)
    monkeypatch.setattr(app_secop.AppSECOP, "_iniciar_conteo", lambda self: None)
    avisos = {"info": [], "error": [], "aviso": []}
    monkeypatch.setattr(app_secop.messagebox, "showinfo", lambda *a, **k: avisos["info"].append(a))
    monkeypatch.setattr(app_secop.messagebox, "showwarning",
                        lambda *a, **k: avisos["aviso"].append(a))
    monkeypatch.setattr(app_secop.messagebox, "showerror", lambda *a, **k: avisos["error"].append(a))
    app.avisos = avisos
    app._filtros_activos = {"empresas": {None: None}, "filtros": Filtros(texto="x")}
    app._filas = _filas(3)
    return app


def _dialogo_con(monkeypatch, resultado):
    import app_secop

    class DialogoFalso:
        def __init__(self, *a, **k):
            self.resultado = resultado
            DialogoFalso.kwargs = k

        def wait_window(self):
            pass
    monkeypatch.setattr(app_secop, "DialogoExportar", DialogoFalso)
    return DialogoFalso


def test_exportar_pagina_actual_escribe_desde_memoria(lista, monkeypatch, tmp_path):
    import app_secop
    destino = str(tmp_path / "pagina.csv")
    _dialogo_con(monkeypatch, {"alcance": "pagina", "formato": "csv",
                               "columnas": ["id_contrato", "valor"], "delimitador": ";"})
    monkeypatch.setattr(app_secop.filedialog, "asksaveasfilename", lambda **k: destino)
    lista._exportar()
    _procesar(lista)
    assert HiloFalso.lanzados == []                     # sin API: se escribe la pagina en memoria
    with open(destino, encoding="utf-8-sig") as f:
        lineas = f.read().splitlines()
    assert lineas[0] == "ID Contrato;Valor" and len(lineas) == 4
    assert lista._exportando is False and lista.avisos["info"]
    assert str(lista.btn_exportar.cget("state")) == "normal"


def test_exportar_todos_sobre_el_umbral_pide_confirmacion_y_respeta_el_no(lista, monkeypatch):
    import app_secop
    lista._conteos = {"SECOP II - Contratos": 4000, "SECOP II - Procesos": 500}
    dlg = _dialogo_con(monkeypatch, {"alcance": "todos", "formato": "xlsx",
                                     "columnas": ["id_contrato"], "delimitador": ","})
    preguntas = []
    monkeypatch.setattr(app_secop.messagebox, "askyesno",
                        lambda titulo, msg, **k: preguntas.append(msg) or False)
    pedido = []
    monkeypatch.setattr(app_secop.filedialog, "asksaveasfilename", lambda **k: pedido.append(1))
    lista._exportar()
    assert dlg.kwargs["total_estimado"] == 4500
    assert len(preguntas) == 1 and "4.500" in preguntas[0]
    assert pedido == [] and HiloFalso.lanzados == [] and lista._exportando is False


def test_exportar_todos_sin_total_tambien_pide_confirmacion(lista, monkeypatch):
    import app_secop
    lista._conteos = None
    _dialogo_con(monkeypatch, {"alcance": "todos", "formato": "csv",
                               "columnas": ["id_contrato"], "delimitador": ","})
    preguntas = []
    monkeypatch.setattr(app_secop.messagebox, "askyesno",
                        lambda titulo, msg, **k: preguntas.append(msg) or False)
    lista._exportar()
    assert len(preguntas) == 1 and "No se pudo estimar" in preguntas[0]


def test_exportar_todos_limpia_cancelar_y_lanza_el_hilo(lista, monkeypatch, tmp_path):
    import app_secop
    lista._conteos = {"SECOP II - Contratos": 10}            # bajo el umbral: sin confirmacion
    _dialogo_con(monkeypatch, {"alcance": "todos", "formato": "csv_dataset",
                               "columnas": ["id_contrato"], "delimitador": ","})
    monkeypatch.setattr(app_secop.messagebox, "askyesno",
                        lambda *a, **k: pytest.fail("no debe pedir confirmacion"))
    monkeypatch.setattr(app_secop.filedialog, "askdirectory", lambda **k: str(tmp_path))
    lista._cancelar.set()                                   # quedo de una cancelacion anterior
    lista._exportar()
    assert not lista._cancelar.is_set()
    assert len(HiloFalso.lanzados) == 1
    objetivo, args = HiloFalso.lanzados[0]
    assert objetivo == lista._hilo_exportar and args[1] == str(tmp_path)
    assert lista._exportando is True
    assert str(lista.btn_exportar.cget("state")) == "disabled"
    assert str(lista.btn_cancelar.cget("state")) == "normal"


def test_hilo_exportar_escribe_pagina_a_pagina(lista, monkeypatch, tmp_path):
    import app_secop
    paginas = [(_filas(2), {"SECOP II - Contratos": [{"id": "1"}]}), (_filas(3), {})]
    monkeypatch.setattr(app_secop.SECOPQuery, "iterar_paginas",
                        lambda self, *a, **k: iter(paginas))
    destino = str(tmp_path / "todo.json")
    opc = {"alcance": "todos", "formato": "json", "columnas": ["id_contrato"], "delimitador": ","}
    lista._set_exportando(True)
    lista._hilo_exportar(opc, destino, {}, "s", lista._filtros_activos)
    _procesar(lista)
    assert os.path.exists(destino) and lista._exportando is False
    assert "5 registros" in lista.lbl_estado.cget("text")


def test_errores_de_pagina_durante_la_descarga_se_avisan(lista, monkeypatch, tmp_path):
    import app_secop

    def iterar(self, *a, **k):
        self.ultimos_errores = ["SECOP II - Procesos: 503"]
        yield _filas(2), {}
    monkeypatch.setattr(app_secop.SECOPQuery, "iterar_paginas", iterar)
    destino = str(tmp_path / "todo.csv")
    opc = {"alcance": "todos", "formato": "csv", "columnas": ["id_contrato"], "delimitador": ","}
    lista._set_exportando(True)
    lista._hilo_exportar(opc, destino, {}, "s", lista._filtros_activos)
    _procesar(lista)
    assert os.path.exists(destino) and lista.avisos["info"] == []
    assert len(lista.avisos["aviso"]) == 1 and "503" in lista.avisos["aviso"][0][1]


def test_cancelar_a_mitad_de_exportacion_no_deja_archivo(lista, monkeypatch, tmp_path):
    import app_secop

    def iterar(self, *a, cancelado=None, **k):
        yield _filas(2), {}
        lista._cancelar_operacion()                         # el usuario pulsa Cancelar
        if cancelado():
            return
        yield _filas(2), {}
    monkeypatch.setattr(app_secop.SECOPQuery, "iterar_paginas", iterar)
    destino = str(tmp_path / "todo.xlsx")
    opc = {"alcance": "todos", "formato": "xlsx", "columnas": ["id_contrato"], "delimitador": ","}
    lista._cancelar.clear()
    lista._set_exportando(True)
    lista._hilo_exportar(opc, destino, {}, "s", lista._filtros_activos)
    _procesar(lista)
    assert not any(n.startswith("todo") for n in os.listdir(tmp_path))   # ni .part ni final
    assert lista._exportando is False
    assert "cancelada" in lista.lbl_estado.cget("text").lower()
    assert lista.avisos["info"] == [] and lista.avisos["error"] == []


def test_error_de_exportacion_se_informa(lista, monkeypatch, tmp_path):
    opc = {"alcance": "pagina", "formato": "csv", "columnas": ["id_contrato"], "delimitador": ","}
    lista._set_exportando(True)
    lista._escribir_exportacion(opc, iter([([], {})]), str(tmp_path / "x.csv"), {}, "s")
    _procesar(lista)                                       # NameError si el lambda usara `e`
    assert lista.avisos["error"] and "No hay filas" in lista.avisos["error"][0][1]
    assert lista._exportando is False


def test_cancelar_durante_exportacion_no_toca_la_consulta(lista):
    lista._set_exportando(True)
    token = lista._consulta_id
    lista.lbl_estado.config(text="Descargando pagina 3...")
    lista._cancelar_operacion()
    assert lista._cancelar.is_set()
    assert lista._consulta_id == token
    assert lista.lbl_estado.cget("text") != "Operacion cancelada."
    assert lista._exportando is True                       # termina cuando el hilo lo confirma


def test_consulta_y_exportacion_son_excluyentes(lista):
    lista._set_exportando(True)
    lista._set_consultando(False)                          # p. ej. un fallo tardio de consulta
    assert str(lista.btn_exportar.cget("state")) == "disabled"
    assert str(lista.btn_consultar.cget("state")) == "disabled"
    assert str(lista.btn_cancelar.cget("state")) == "normal"
    lista._cambiar_pagina(2)
    lista.entry_unspsc.insert(0, "80111600")
    lista._iniciar_consulta()
    assert HiloFalso.lanzados == [] and lista._pagina_actual == 1
    lista._set_exportando(False)
    assert str(lista.btn_exportar.cget("state")) == "normal"
    assert str(lista.btn_cancelar.cget("state")) == "disabled"


def test_no_se_exporta_mientras_se_consulta(lista, monkeypatch):
    import app_secop
    monkeypatch.setattr(app_secop, "DialogoExportar",
                        lambda *a, **k: pytest.fail("no debe abrir el dialogo"))
    lista._set_consultando(True)
    lista._exportar()
    assert lista._exportando is False
