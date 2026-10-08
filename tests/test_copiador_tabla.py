import tkinter as tk
from tkinter import ttk

import pytest

from copiador_tabla import CopiadorTabla


@pytest.fixture(scope="module")
def raiz():
    # Un solo Tk por modulo: crear/destruir muchos Tk es inestable en Windows.
    try:
        r = tk.Tk()
    except tk.TclError as e:
        pytest.skip("sin display: %s" % e)
    r.withdraw()
    yield r
    r.destroy()


def armar(raiz):
    cols = ["a", "valor"]
    tree = ttk.Treeview(raiz, columns=cols, show="headings")
    filas = {}
    for a, v in [("x", "$1.000"), ("y", "$2.000"), ("z", "$3.000")]:
        item = tree.insert("", "end", values=(a, v))
        filas[item] = {"a": a, "valor": v}
    msgs = []
    cop = CopiadorTabla(raiz, tree, cols, ["A", "Valor"], lambda: filas, msgs.append)
    cop.instalar()
    return tree, cop, list(filas), msgs


def test_instalar_activa_seleccion_multiple(raiz):
    tree, _, _, _ = armar(raiz)
    assert str(tree.cget("selectmode")) == "extended"


def test_copiar_seleccion_en_orden_visual_y_numeros_crudos(raiz):
    tree, cop, items, _ = armar(raiz)
    tree.selection_set((items[2], items[0]))
    cop.copiar_seleccion()
    assert raiz.clipboard_get() == "x\t1000\nz\t3000"


def test_copiar_seleccion_con_encabezado(raiz):
    tree, cop, items, _ = armar(raiz)
    tree.selection_set(items[1])
    cop.copiar_seleccion(con_encabezado=True)
    assert raiz.clipboard_get() == "A\tValor\ny\t2000"


def test_copiar_como_se_ve(raiz):
    tree, cop, items, _ = armar(raiz)
    cop.crudo.set(False)
    tree.selection_set(items[0])
    cop.copiar_seleccion()
    assert raiz.clipboard_get() == "x\t$1.000"


def test_copiar_columna_visibles_y_seleccion(raiz):
    tree, cop, items, _ = armar(raiz)
    cop.copiar_columna("valor")
    assert raiz.clipboard_get() == "1000\n2000\n3000"
    tree.selection_set((items[0], items[2]))
    cop.copiar_columna("a", solo_seleccion=True, con_encabezado=True)
    assert raiz.clipboard_get() == "A\nx\nz"


def test_copiar_como_csv_y_json(raiz):
    tree, cop, items, _ = armar(raiz)
    tree.selection_set(items[0])
    cop.copiar_como("csv")
    assert raiz.clipboard_get() == "A,Valor\nx,1000"
    cop.copiar_como("json")
    assert '"valor": 1000' in raiz.clipboard_get()


def test_sin_seleccion_ni_celda_avisa(raiz):
    tree, cop, items, msgs = armar(raiz)
    cop.copiar_seleccion()
    assert msgs and "celda" in msgs[-1].lower()


def test_celda_recordada_se_copia_sin_seleccion(raiz):
    tree, cop, items, _ = armar(raiz)
    cop._ultima = (items[1], "valor")
    cop.copiar_celda()
    assert raiz.clipboard_get() == "2000"


def test_ctrl_a_selecciona_todo(raiz):
    tree, cop, items, _ = armar(raiz)
    assert cop._on_ctrl_a() == "break"
    assert set(tree.selection()) == set(items)
