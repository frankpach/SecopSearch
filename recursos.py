# -*- coding: utf-8 -*-
"""Recursos empaquetados (logo): rutas en ejecucion normal y en PyInstaller, y
carga tolerante del icono. Solo Tk: sin Pillow en tiempo de ejecucion."""
import math
import os
import sys
import tkinter as tk

LADO_LOGO_ENCABEZADO = 36


def ruta_recurso(*partes):
    """Ruta a un recurso: dentro del exe (sys._MEIPASS) o junto al codigo."""
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, *partes)


def aplicar_icono(ventana, png, ico=None, lado=LADO_LOGO_ENCABEZADO):
    """Pone el logo como icono de la ventana y de la barra de tareas.
    Devuelve (icono, logo_pequeno) como PhotoImage -- el llamador debe guardar las
    referencias para que no las recoja el GC -- o (None, None) si no se pudo cargar."""
    try:
        icono = tk.PhotoImage(master=ventana, file=png)
        ventana.iconphoto(True, icono)
        factor = max(1, math.ceil(max(icono.width(), icono.height()) / lado))
        logo = icono.subsample(factor)
    except (tk.TclError, OSError):
        return None, None
    if ico and sys.platform == "win32" and os.path.isfile(ico):
        try:
            ventana.iconbitmap(default=ico)    # .ico multi-tamano: nitido en la barra de tareas
        except tk.TclError:
            pass
    return icono, logo
