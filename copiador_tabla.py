# -*- coding: utf-8 -*-
"""Copia de filas, celdas y columnas de un ttk.Treeview (Ctrl+C y menu contextual)."""
import tkinter as tk
from tkinter import BooleanVar

from tabla_utils import filas_a_csv, filas_a_json, filas_a_tsv


class CopiadorTabla:
    def __init__(self, raiz, tree, columnas, encabezados, filas_por_item,
                 al_estado=None, extra_menu=None):
        """filas_por_item: callable -> {item_id: fila(dict)} con los valores
        completos (sin recortar). extra_menu(menu, item_id): entradas extra."""
        self.raiz = raiz
        self.tree = tree
        self.columnas = list(columnas)
        self.encabezados = list(encabezados)
        self._filas_por_item = filas_por_item
        self._estado = al_estado or (lambda msg: None)
        self._extra_menu = extra_menu
        self.crudo = BooleanVar(master=raiz, value=True)
        self._ultima = (None, None)

    def instalar(self):
        t = self.tree
        t.configure(selectmode="extended")
        for seq in ("<Control-c>", "<Control-C>"):
            t.bind(seq, self._on_ctrl_c, add="+")
        for seq in ("<Control-a>", "<Control-A>"):
            t.bind(seq, self._on_ctrl_a, add="+")
        t.bind("<Button-1>", self._on_click, add="+")
        t.bind("<Button-3>", self._on_menu, add="+")

    # ---- eventos ----------------------------------------------------------
    def _columna_en(self, event):
        col = self.tree.identify_column(event.x)
        try:
            idx = int(col.lstrip("#")) - 1
        except ValueError:
            return None
        return self.columnas[idx] if 0 <= idx < len(self.columnas) else None

    def _celda_en(self, event):
        return (self.tree.identify_row(event.y) or None), self._columna_en(event)

    def _on_click(self, event):
        self._ultima = self._celda_en(event)

    def _on_ctrl_c(self, event=None):
        self.copiar_seleccion()
        return "break"

    def _on_ctrl_a(self, event=None):
        self.tree.selection_set(self.tree.get_children())
        return "break"

    # ---- datos -------------------------------------------------------------
    def _filas(self, items):
        mapa = self._filas_por_item()
        return [mapa[i] for i in items if i in mapa]

    def filas_seleccionadas(self):
        return self._filas(sorted(self.tree.selection(), key=self.tree.index))

    def filas_visibles(self):
        return self._filas(self.tree.get_children())

    def _copiar(self, texto, mensaje):
        self.raiz.clipboard_clear()
        self.raiz.clipboard_append(texto)
        self._estado(mensaje)

    # ---- acciones ----------------------------------------------------------
    def copiar_seleccion(self, con_encabezado=False):
        filas = self.filas_seleccionadas()
        if not filas:
            self.copiar_celda()
            return
        texto = filas_a_tsv(filas, self.columnas, self.encabezados,
                            con_encabezado, self.crudo.get())
        self._copiar(texto, f"{len(filas)} fila(s) copiada(s).")

    def copiar_celda(self, item=None, col=None):
        item, col = (item, col) if item else self._ultima
        if not item or not col:
            self._estado("Haga clic en una celda para copiarla.")
            return
        fila = self._filas([item])
        if not fila:
            return
        self._copiar(filas_a_tsv(fila, [col], None, False, self.crudo.get()), "Celda copiada.")

    def copiar_columna(self, col, solo_seleccion=False, con_encabezado=False):
        filas = self.filas_seleccionadas() if solo_seleccion else self.filas_visibles()
        if not filas:
            self._estado("No hay filas para copiar.")
            return
        titulo = self.encabezados[self.columnas.index(col)]
        texto = filas_a_tsv(filas, [col], [titulo], con_encabezado, self.crudo.get())
        self._copiar(texto, f"Columna '{titulo}' copiada ({len(filas)} filas).")

    def copiar_como(self, formato):
        filas = self.filas_seleccionadas() or self.filas_visibles()
        if not filas:
            self._estado("No hay filas para copiar.")
            return
        if formato == "csv":
            texto = filas_a_csv(filas, self.columnas, self.encabezados, True, self.crudo.get())
        else:
            texto = filas_a_json(filas, self.columnas, self.crudo.get())
        self._copiar(texto, f"{len(filas)} fila(s) copiada(s) como {formato.upper()}.")

    # ---- menu contextual --------------------------------------------------
    def _on_menu(self, event):
        menu = tk.Menu(self.tree, tearoff=0)
        if self.tree.identify_region(event.x, event.y) == "heading":
            col = self._columna_en(event)
            if not col:
                return "break"
            menu.add_command(label="Copiar columna (filas visibles)",
                             command=lambda: self.copiar_columna(col))
            menu.add_command(label="Copiar columna con encabezado",
                             command=lambda: self.copiar_columna(col, con_encabezado=True))
        else:
            item, col = self._celda_en(event)
            if not item:
                return "break"
            if item not in self.tree.selection():
                self.tree.selection_set(item)
            self._ultima = (item, col)
            n = len(self.tree.selection())
            hay_col = "normal" if col else "disabled"
            if self._extra_menu:
                self._extra_menu(menu, item)
            menu.add_command(label="Copiar celda", state=hay_col,
                             command=lambda: self.copiar_celda(item, col))
            menu.add_command(label=f"Copiar {n} fila(s) seleccionada(s)",
                             command=self.copiar_seleccion)
            menu.add_command(label="Copiar filas con encabezados",
                             command=lambda: self.copiar_seleccion(True))
            menu.add_command(label="Copiar columna (seleccionadas)", state=hay_col,
                             command=lambda: self.copiar_columna(col, solo_seleccion=True))
            menu.add_command(label="Copiar columna (todas las visibles)", state=hay_col,
                             command=lambda: self.copiar_columna(col))
            menu.add_separator()
            menu.add_command(label="Copiar como CSV", command=lambda: self.copiar_como("csv"))
            menu.add_command(label="Copiar como JSON", command=lambda: self.copiar_como("json"))
        menu.add_separator()
        menu.add_checkbutton(label="Copiar numeros sin formato", variable=self.crudo)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"
