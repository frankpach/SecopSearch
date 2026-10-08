# -*- coding: utf-8 -*-
"""Tabla de una pestana de detalle (datos crudos de un dataset): ordenar por
columna, abrir el registro en SECOP, copiar (CopiadorTabla) y exportar."""
import os
import re
import webbrowser
from tkinter import filedialog, messagebox, ttk

from copiador_tabla import CopiadorTabla
from exportar import exportar
from search import url_de
from tabla_utils import columnas_union, ordenar_filas, texto_pantalla

COLUMNAS_URL = ("urlproceso", "url_contrato")    # Contratos/Procesos SECOP II e Integrado
LIMITE_PANTALLA = 120
FORMATOS_EXTENSION = {".xlsx": "xlsx", ".csv": "csv", ".json": "json"}
TIPOS_ARCHIVO = [("Excel", "*.xlsx"), ("CSV", "*.csv"), ("JSON", "*.json")]


def url_web(valor):
    """URL http(s) de una celda (texto, JSON o dict {"url": ...}); "" si no hay."""
    url = url_de(valor).strip()
    return url if url.lower().startswith(("http://", "https://")) else ""


def abrir_url(url):
    """Abre solo URLs http(s) en el navegador. Devuelve si la abrio."""
    if not url or url_web(url) != url:
        return False
    webbrowser.open(url, new=2)
    return True


def formato_por_extension(ruta):
    return FORMATOS_EXTENSION.get(os.path.splitext(str(ruta))[1].lower())


class TablaDetalle:
    def __init__(self, raiz, parent, nombre, data, formatear, al_estado):
        """formatear(col, valor) -> texto completo de la celda;
        al_estado(msg) -> muestra un mensaje en la barra de estado."""
        self.raiz = raiz
        self.nombre = nombre
        self._estado = al_estado
        # Privadas (_empresa, _nit) al final. Union de claves: Socrata omite las nulas.
        todas = columnas_union(data)
        self.columnas = ([c for c in todas if not c.startswith("_")]
                         + [c for c in todas if c.startswith("_")])
        self.titulos = [c.replace("_", " ").strip().title() for c in self.columnas]
        col_url = next((c for c in COLUMNAS_URL if c in self.columnas), None)
        self.filas = []
        self._url_de_fila = {}                     # id(fila) -> URL http(s)
        for row in data:
            fila = {c: formatear(c, row.get(c)) for c in self.columnas}
            self.filas.append(fila)
            if col_url:
                url = url_web(row.get(col_url))
                if url:
                    self._url_de_fila[id(fila)] = url
        self._orden_inverso = {}
        self._filas_por_item = {}
        self._url_por_item = {}

        self.tree = tree = ttk.Treeview(parent, columns=self.columnas, show="headings",
                                        selectmode="extended")
        for c, titulo in zip(self.columnas, self.titulos):
            tree.heading(c, text=titulo, command=lambda c=c: self.ordenar(c))
            tree.column(c, width=130, anchor="w", minwidth=60)
        sy = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        sx = ttk.Scrollbar(parent, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        tree.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        tree.tag_configure("par", background="#f7f9fc")
        tree.tag_configure("impar", background="white")
        tree.tag_configure("con_url", foreground="#1a5490")

        tree.bind("<Double-1>", self._on_doble_clic)
        tree.bind("<Motion>", self._cursor_hover)
        self.copiador = CopiadorTabla(raiz, tree, self.columnas, self.titulos,
                                      lambda: self._filas_por_item, al_estado,
                                      extra_menu=self._menu_extra)
        self.copiador.instalar()

        self.lbl_ayuda = ttk.Label(
            parent, style="Meta.TLabel",
            text=f"{len(self.filas)} registros  |  Doble clic: abrir en SECOP  |  "
                 "Ctrl+C: copiar seleccion  |  Clic derecho: copiar/exportar/opciones  |  "
                 "Clic en columna: ordenar")
        self.lbl_ayuda.grid(row=2, column=0, sticky="w", pady=(2, 0))
        self._renderizar(self.filas)

    # ---- filas -------------------------------------------------------------
    def _renderizar(self, filas):
        self.tree.delete(*self.tree.get_children())
        self._filas_por_item = {}
        self._url_por_item = {}
        for i, fila in enumerate(filas):
            tags = ["par" if i % 2 == 0 else "impar"]
            url = self._url_de_fila.get(id(fila), "")
            if url:
                tags.append("con_url")
            vals = [texto_pantalla(fila[c], LIMITE_PANTALLA) for c in self.columnas]
            item = self.tree.insert("", "end", values=vals, tags=tuple(tags))
            self._filas_por_item[item] = fila
            if url:
                self._url_por_item[item] = url

    def ordenar(self, col):
        """Por tipo real (numeros, fechas, texto); vacias al final; alterna el sentido."""
        inverso = self._orden_inverso.get(col, False)
        self.filas = ordenar_filas(self.filas, col, inverso)
        self._orden_inverso[col] = not inverso
        self._renderizar(self.filas)

    # ---- abrir en SECOP ----------------------------------------------------
    def url_de_item(self, item):
        return self._url_por_item.get(item, "")

    def abrir_en_secop(self, item):
        url = self.url_de_item(item)
        if abrir_url(url):
            self._estado(f"Abriendo: {url}")
        else:
            self._estado("Este registro no tiene URL en SECOP.")

    def _on_doble_clic(self, event=None):
        if event is not None and self.tree.identify_region(event.x, event.y) == "heading":
            return
        sel = self.tree.selection()
        if sel:
            self.abrir_en_secop(sel[0])

    def _cursor_hover(self, event):
        item = self.tree.identify_row(event.y)
        url = self._url_por_item.get(item) if item else None
        if url:
            self.tree.config(cursor="hand2")
            self._estado(f"Doble clic para abrir: {url}")
        else:
            self.tree.config(cursor="")

    def _menu_extra(self, menu, item):
        estado = "normal" if self.url_de_item(item) else "disabled"
        menu.add_command(label="Abrir en SECOP", state=estado,
                         command=lambda: self.abrir_en_secop(item))
        menu.add_command(label="Exportar esta tabla...", command=self.exportar_tabla)
        menu.add_separator()

    # ---- exportar ----------------------------------------------------------
    def exportar_tabla(self):
        """Exporta todas las columnas y filas de la pestana, en el orden en pantalla."""
        if not self.filas:
            messagebox.showinfo("Exportar", "Esta tabla no tiene filas para exportar.",
                                parent=self.raiz)
            return
        limpio = re.sub(r"[^\w\-]+", "_", self.nombre, flags=re.UNICODE).strip("_") or "datos"
        ruta = filedialog.asksaveasfilename(
            parent=self.raiz, title=f"Exportar '{self.nombre}'",
            defaultextension=".xlsx", filetypes=TIPOS_ARCHIVO,
            initialfile=f"SECOP_{limpio}.xlsx")
        if not ruta:
            return
        formato = formato_por_extension(ruta)
        if formato is None:
            messagebox.showerror("Exportar", "Use una extension .xlsx, .csv o .json.",
                                 parent=self.raiz)
            return
        self._estado(f"Exportando '{self.nombre}'...")
        self.raiz.update_idletasks()               # que el mensaje se vea antes de escribir
        try:
            exportar(formato, self.columnas, self.filas, ruta,
                     dict(zip(self.columnas, self.titulos)), hoja=self.nombre)
        except Exception as e:
            mensaje = str(e) or type(e).__name__
            self._estado(f"Error al exportar: {mensaje}")
            messagebox.showerror("Exportar", f"No se pudo exportar la tabla:\n{mensaje}",
                                 parent=self.raiz)
            return
        self._estado(f"{len(self.filas)} filas de '{self.nombre}' exportadas a {ruta}")
