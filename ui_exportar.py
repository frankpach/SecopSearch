# -*- coding: utf-8 -*-
"""Dialogo modal 'Exportar': alcance, columnas y formato."""
from tkinter import BooleanVar, StringVar, TclError, Toplevel, messagebox, ttk

FORMATOS = [
    ("xlsx", "Excel (.xlsx) con formato"),
    ("csv", "CSV unico"),
    ("csv_dataset", "CSV por dataset (solo con 'todos los resultados')"),
    ("json", "JSON"),
]


class DialogoExportar(Toplevel):
    def __init__(self, master, columnas, n_pagina, n_sel, previo=None, total_estimado=None):
        super().__init__(master)
        previo = previo or {}
        self.title("Exportar")
        self.transient(master)
        self.resizable(False, False)
        self.resultado = None

        alcance = previo.get("alcance", "pagina")
        if alcance == "seleccion" and n_sel == 0:
            alcance = "pagina"
        # Variables ligadas a este dialogo (no al Tk "por defecto", que puede ser otro)
        self.var_alcance = StringVar(self, value=alcance if alcance in ("pagina", "seleccion", "todos") else "pagina")
        formato = previo.get("formato", "xlsx")
        self.var_formato = StringVar(self, value=formato if formato in dict(FORMATOS) else "xlsx")
        self.var_delim = StringVar(self, value=previo.get("delimitador", ","))

        marco = ttk.Frame(self, padding=12)
        marco.pack(fill="both", expand=True)

        caja = ttk.LabelFrame(marco, text="Que exportar", padding=8)
        caja.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        ttk.Radiobutton(caja, text=f"Pagina actual ({n_pagina} filas)", value="pagina",
                        variable=self.var_alcance, command=self._actualizar).pack(anchor="w")
        self.rb_sel = ttk.Radiobutton(caja, text=f"Filas seleccionadas ({n_sel})", value="seleccion",
                                      variable=self.var_alcance, command=self._actualizar)
        self.rb_sel.pack(anchor="w")
        if n_sel == 0:
            self.rb_sel.state(["disabled"])
        texto_todos = "Todos los resultados (descarga completa desde la API)"
        if total_estimado:
            texto_todos = (f"Todos los resultados (≈{total_estimado:,} registros; "
                           "descarga completa)").replace(",", ".")
        self.rb_todos = ttk.Radiobutton(caja, text=texto_todos, value="todos",
                                        variable=self.var_alcance, command=self._actualizar)
        self.rb_todos.pack(anchor="w")

        fmt = ttk.LabelFrame(marco, text="Formato", padding=8)
        fmt.grid(row=1, column=0, sticky="nsew", padx=(0, 8), pady=(8, 0))
        self.rb_formato = {}
        for clave, etiqueta in FORMATOS:
            rb = ttk.Radiobutton(fmt, text=etiqueta, value=clave, variable=self.var_formato)
            rb.pack(anchor="w")
            self.rb_formato[clave] = rb
        fila = ttk.Frame(fmt)
        fila.pack(anchor="w", pady=(4, 0))
        ttk.Label(fila, text="Separador CSV:").pack(side="left")
        ttk.Combobox(fila, textvariable=self.var_delim, values=[",", ";"],
                     state="readonly", width=3).pack(side="left", padx=4)

        cols = ttk.LabelFrame(marco, text="Columnas", padding=8)
        cols.grid(row=0, column=1, rowspan=2, sticky="nsew")
        elegidas = previo.get("columnas")
        self.vars_columnas = {}
        for i, (cid, titulo, *_resto) in enumerate(columnas):
            marcada = True if not elegidas else cid in elegidas
            v = BooleanVar(self, value=marcada)
            self.vars_columnas[cid] = v
            ttk.Checkbutton(cols, text=titulo, variable=v).grid(row=i % 10, column=i // 10,
                                                                 sticky="w", padx=4)
        botones = ttk.Frame(cols)
        botones.grid(row=10, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Button(botones, text="Todas", command=lambda: self._marcar(True)).pack(side="left", padx=2)
        ttk.Button(botones, text="Ninguna", command=lambda: self._marcar(False)).pack(side="left", padx=2)

        pie = ttk.Frame(marco)
        pie.grid(row=2, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(pie, text="Cancelar", command=self.destroy).pack(side="right", padx=4)
        ttk.Button(pie, text="Exportar", style="Accent.TButton",
                   command=self._aceptar).pack(side="right")

        self._actualizar()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        try:
            self.grab_set()
        except TclError:        # ventana aun no visible (p. ej. en pruebas)
            pass

    def _marcar(self, valor):
        for v in self.vars_columnas.values():
            v.set(valor)

    def _actualizar(self):
        solo_todos = self.var_alcance.get() == "todos"
        self.rb_formato["csv_dataset"].state(["!disabled"] if solo_todos else ["disabled"])
        if not solo_todos and self.var_formato.get() == "csv_dataset":
            self.var_formato.set("xlsx")

    def _aceptar(self):
        elegidas = [c for c, v in self.vars_columnas.items() if v.get()]
        if not elegidas:
            messagebox.showwarning("Columnas", "Seleccione al menos una columna.", parent=self)
            return
        self.resultado = {
            "alcance": self.var_alcance.get(),
            "formato": self.var_formato.get(),
            "columnas": elegidas,
            "delimitador": self.var_delim.get(),
        }
        self.destroy()
