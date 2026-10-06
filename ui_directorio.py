# -*- coding: utf-8 -*-
"""Ventana Directorio (empresas y entidades), dialogo de edicion y busqueda
de empresa por nombre."""
import threading
from tkinter import StringVar, TclError, Text, Toplevel, messagebox, ttk

from search import buscar_proveedores, resolver_nombre_oficial
from storage import DuplicadoError


def _existe(widget):
    try:
        return bool(widget.winfo_exists())
    except (TclError, RuntimeError):
        return False


def _seguro(widget, fn):
    """Programa fn en el hilo de Tk (llamable desde otros hilos). Si la ventana ya se
    cerro cuando le toca ejecutarse, el resultado se descarta sin tocar widgets."""
    def correr():
        if _existe(widget):
            fn()
    try:
        widget.after(0, correr)
    except (TclError, RuntimeError):     # la aplicacion ya se cerro
        pass


class DialogoEdicion(Toplevel):
    def __init__(self, master, titulo, datos, resolver=None):
        super().__init__(master)
        self.title(titulo)
        self.transient(master)
        self.resizable(False, False)
        self.resultado = None
        self._resolver = resolver
        self.btn_resolver = None
        marco = ttk.Frame(self, padding=12)
        marco.pack(fill="both", expand=True)

        def fila(r, texto):
            ttk.Label(marco, text=texto).grid(row=r, column=0, sticky="nw", pady=3, padx=(0, 8))

        fila(0, "Nombre:")
        self.ent_nombre = ttk.Entry(marco, width=50)
        self.ent_nombre.grid(row=0, column=1, sticky="w")
        fila(1, "NIT:")
        self.ent_nit = ttk.Entry(marco, width=22)
        self.ent_nit.grid(row=1, column=1, sticky="w")
        if resolver:
            self.btn_resolver = ttk.Button(marco, text="Buscar nombre oficial",
                                           command=self._resolver_nombre)
            self.btn_resolver.grid(row=1, column=1, sticky="e")
        fila(2, "Alias:")
        self.ent_alias = ttk.Entry(marco, width=50)
        self.ent_alias.grid(row=2, column=1, sticky="w")
        fila(3, "Etiquetas (coma):")
        self.ent_etiquetas = ttk.Entry(marco, width=50)
        self.ent_etiquetas.grid(row=3, column=1, sticky="w")
        fila(4, "Notas:")
        self.txt_notas = Text(marco, width=50, height=5, wrap="word")
        self.txt_notas.grid(row=4, column=1, sticky="w")

        self.ent_nombre.insert(0, datos.get("nombre", ""))
        self.ent_nit.insert(0, datos.get("nit", ""))
        self.ent_alias.insert(0, datos.get("alias", ""))
        etiquetas = datos.get("etiquetas", "")
        self.ent_etiquetas.insert(0, ", ".join(etiquetas) if isinstance(etiquetas, list) else etiquetas)
        self.txt_notas.insert("1.0", datos.get("notas", ""))

        pie = ttk.Frame(marco)
        pie.grid(row=5, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(pie, text="Cancelar", command=self.destroy).pack(side="right", padx=4)
        ttk.Button(pie, text="Guardar", style="Accent.TButton", command=self._aceptar).pack(side="right")
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        try:
            self.grab_set()
        except TclError:        # ventana aun no visible (p. ej. en pruebas)
            pass
        self.ent_nombre.focus_set()

    def _resolver_nombre(self):
        nit = self.ent_nit.get().strip()
        if not nit:
            messagebox.showwarning("NIT", "Escriba el NIT primero.", parent=self)
            return
        if self.btn_resolver is not None:
            self.btn_resolver.config(state="disabled")
        resolver = self._resolver

        def vigente():
            """La respuesta solo sirve si el NIT del dialogo sigue siendo el consultado."""
            if self.btn_resolver is not None:
                self.btn_resolver.config(state="normal")
            return self.ent_nit.get().strip() == nit

        def poner(nombre):
            if vigente():
                self.ent_nombre.delete(0, "end")
                self.ent_nombre.insert(0, nombre)

        def sin_resultado():
            if vigente():
                messagebox.showinfo("Proveedores",
                                    "No se encontro ese NIT en el registro de proveedores.",
                                    parent=self)

        def fallo(mensaje):
            if vigente():
                messagebox.showerror("Proveedores", mensaje, parent=self)

        def trabajo():
            try:
                nombre = resolver(nit)
            except Exception as e:
                msg = str(e) or type(e).__name__
                _seguro(self, lambda m=msg: fallo(m))
                return
            if nombre:
                _seguro(self, lambda n=nombre: poner(n))
            else:
                _seguro(self, sin_resultado)
        threading.Thread(target=trabajo, daemon=True).start()

    def _aceptar(self):
        nombre = self.ent_nombre.get().strip()
        nit = self.ent_nit.get().strip()
        if not nombre and not nit:
            messagebox.showwarning("Datos vacios", "Ingrese al menos nombre o NIT.", parent=self)
            return
        self.resultado = {
            "nombre": nombre, "nit": nit, "alias": self.ent_alias.get().strip(),
            "etiquetas": self.ent_etiquetas.get().strip(),
            "notas": self.txt_notas.get("1.0", "end").strip(),
        }
        self.destroy()


class PanelLista(ttk.Frame):
    COLUMNAS = (("nombre", "Nombre", 260), ("nit", "NIT", 110), ("alias", "Alias", 120),
                ("etiquetas", "Etiquetas", 140), ("ultima_consulta", "Ultima consulta", 110))

    def __init__(self, master, ventana, tipo):
        super().__init__(master, padding=6)
        self.ventana, self.tipo = ventana, tipo
        self.dir = ventana.directorio
        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Label(top, text="Filtrar:").pack(side="left")
        # Variable ligada a este panel (no al Tk "por defecto", que puede ser otro)
        self.var_filtro = StringVar(self)
        self.var_filtro.trace_add("write", lambda *a: self.refrescar())
        ttk.Entry(top, textvariable=self.var_filtro, width=40).pack(side="left", padx=6)
        self.tree = ttk.Treeview(self, columns=[c[0] for c in self.COLUMNAS], show="headings",
                                 selectmode="extended", height=14)
        for cid, titulo, ancho in self.COLUMNAS:
            self.tree.heading(cid, text=titulo)
            self.tree.column(cid, width=ancho, anchor="w")
        self.tree.pack(fill="both", expand=True, pady=6)
        self.tree.bind("<Double-1>", lambda e: self.editar())
        botones = ttk.Frame(self)
        botones.pack(fill="x")
        for texto, cmd in (("Nuevo", self.nuevo), ("Editar", self.editar),
                           ("Eliminar", self.eliminar), ("Fusionar (2 seleccionados)", self.fusionar)):
            ttk.Button(botones, text=texto, command=cmd).pack(side="left", padx=2)
        self.refrescar()

    def refrescar(self):
        seleccion = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        for it in self.dir.listar(self.tipo, self.var_filtro.get()):
            marca = "" if it.get("nombre_resuelto", True) else "  (nombre pendiente)"
            self.tree.insert("", "end", iid=it["id"], values=(
                it["nombre"] + marca, it["nit"], it["alias"],
                ", ".join(it["etiquetas"]), (it["ultima_consulta"] or "")[:10]))
        conservar = [i for i in seleccion if self.tree.exists(i)]
        if conservar:
            self.tree.selection_set(conservar)

    def seleccionar(self, id_):
        if not self.tree.exists(id_) and self.var_filtro.get():
            self.var_filtro.set("")                 # el filtro lo ocultaba
        if self.tree.exists(id_):
            self.tree.selection_set((id_,))
            self.tree.see(id_)
            self.tree.focus(id_)

    def _seleccion(self):
        return sorted(self.tree.selection(), key=self.tree.index)

    def _resolver(self):
        return self.ventana.resolver if self.tipo == "empresas" else None

    def _tras_cambio(self):
        if _existe(self):
            self.refrescar()
        self.ventana.al_cambiar()

    def _registro_borrado(self):
        messagebox.showinfo("Directorio", "Ese registro ya no existe en el directorio.", parent=self)
        self._tras_cambio()

    def nuevo(self):
        d = DialogoEdicion(self.winfo_toplevel(), f"Nueva {self.tipo[:-1]}", {},
                           resolver=self._resolver())
        d.wait_window()
        if not d.resultado or not _existe(self):
            return
        r = d.resultado
        try:
            item = self.dir.agregar(self.tipo, r["nombre"], r["nit"], r["alias"], r["notas"],
                                    r["etiquetas"], nombre_resuelto=True)
        except DuplicadoError as e:
            messagebox.showinfo("Ya existe", f"'{e.existente['nombre']}' ya tiene ese NIT o nombre. "
                                "Seleccionelo en la lista y use Editar.", parent=self)
            return
        self._tras_cambio()
        if not item["nombre_resuelto"] and self.tipo == "empresas":
            self.ventana._resolver_pendientes()      # solo NIT: buscar el nombre oficial

    def editar(self):
        sel = self._seleccion()
        if len(sel) != 1:
            messagebox.showinfo("Editar", "Seleccione un solo registro.", parent=self)
            return
        item = self.dir.obtener(self.tipo, sel[0])
        if item is None:
            self._registro_borrado()
            return
        d = DialogoEdicion(self.winfo_toplevel(), "Editar", item, resolver=self._resolver())
        d.wait_window()
        if not d.resultado or not _existe(self):
            return
        r = d.resultado
        campos = {"nit": r["nit"], "alias": r["alias"], "etiquetas": r["etiquetas"],
                  "notas": r["notas"]}
        if r["nombre"] != item["nombre"]:
            campos["nombre"] = r["nombre"]       # sin cambio: se conserva "nombre pendiente"
        try:
            self.dir.actualizar(self.tipo, item["id"], **campos)
        except KeyError:
            self._registro_borrado()
            return
        except DuplicadoError as e:
            if not messagebox.askyesno(
                    "NIT duplicado",
                    f"'{e.existente['nombre']}' ya tiene ese NIT.\n"
                    "¿Fusionar este registro dentro de ese? (se conservan sus datos y se "
                    "agregan etiquetas y notas de este)", parent=self):
                return
            try:
                self.dir.fusionar(self.tipo, e.existente["id"], item["id"])
            except KeyError:
                self._registro_borrado()
                return
        self._tras_cambio()

    def eliminar(self):
        sel = self._seleccion()
        if not sel:
            messagebox.showinfo("Eliminar", "Seleccione al menos un registro.", parent=self)
            return
        if not messagebox.askyesno("Confirmar", f"¿Eliminar {len(sel)} registro(s) del directorio?",
                                   parent=self):
            return
        for id_ in sel:
            try:
                self.dir.eliminar(self.tipo, id_)
            except KeyError:                     # ya se habia eliminado
                pass
        self._tras_cambio()

    def fusionar(self):
        sel = self._seleccion()
        if len(sel) != 2:
            messagebox.showinfo("Fusionar", "Seleccione exactamente dos registros.", parent=self)
            return
        destino, origen = self.dir.obtener(self.tipo, sel[0]), self.dir.obtener(self.tipo, sel[1])
        if destino is None or origen is None:
            self._registro_borrado()
            return
        if not messagebox.askyesno(
                "Fusionar",
                f"Se conserva '{destino['nombre']}' y se elimina '{origen['nombre']}' "
                "(sus etiquetas y notas pasan al primero). ¿Continuar?", parent=self):
            return
        try:
            self.dir.fusionar(self.tipo, destino["id"], origen["id"])
        except KeyError:
            self._registro_borrado()
            return
        self._tras_cambio()


class VentanaDirectorio(Toplevel):
    def __init__(self, master, directorio, client_factory, al_cambiar, tipo_inicial="empresas"):
        super().__init__(master)
        self.title("Directorio de empresas y entidades")
        self.geometry("860x460")
        self.directorio = directorio
        self.client_factory = client_factory
        self.al_cambiar = al_cambiar
        self.resolver = lambda nit: resolver_nombre_oficial(client_factory(), nit)
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True)
        self.paneles = {}
        for tipo, titulo in (("empresas", "  Empresas  "), ("entidades", "  Entidades  ")):
            p = PanelLista(self.nb, self, tipo)
            self.nb.add(p, text=titulo)
            self.paneles[tipo] = p
        self.mostrar(tipo_inicial)
        if directorio.aviso:
            messagebox.showwarning("Directorio", directorio.aviso, parent=self)
            directorio.aviso = ""                # se avisa una sola vez
        self._resolver_pendientes()

    def mostrar(self, tipo, id_=None):
        """Selecciona la pestana `tipo` y, si se indica, el registro `id_`."""
        panel = self.paneles.get(tipo)
        if panel is None:
            return
        self.nb.select(panel)
        if id_:
            panel.seleccionar(id_)

    def refrescar(self):
        for p in self.paneles.values():
            p.refrescar()

    def _resolver_pendientes(self):
        """Reintenta en segundo plano los nombres oficiales de empresas guardadas solo con NIT."""
        pendientes = [e for e in self.directorio.listar("empresas")
                      if not e.get("nombre_resuelto", True) and e["nit"]]
        if not pendientes:
            return
        directorio, resolver, al_cambiar = self.directorio, self.resolver, self.al_cambiar

        def avisar():
            # Se programa sobre `master`: si esta ventana ya se cerro, la app igual se entera
            if _existe(self):
                self.paneles["empresas"].refrescar()
            al_cambiar()

        def trabajo():
            cambio = False
            for e in pendientes:
                try:
                    nombre = resolver(e["nit"])
                    if nombre:
                        directorio.actualizar("empresas", e["id"], nombre=nombre)
                        cambio = True
                except Exception:
                    continue
            if cambio:
                _seguro(self.master, avisar)
        threading.Thread(target=trabajo, daemon=True).start()


class DialogoBuscarEmpresa(Toplevel):
    def __init__(self, master, client_factory, directorio, al_usar, al_cambiar):
        super().__init__(master)
        self.title("Buscar empresa por nombre")
        self.geometry("760x420")
        self.client_factory, self.directorio = client_factory, directorio
        self.al_usar, self.al_cambiar = al_usar, al_cambiar
        self._busqueda = 0           # descarta respuestas de busquedas anteriores
        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        ttk.Label(top, text="Nombre (varias palabras):").pack(side="left")
        self.var_texto = StringVar(self)
        ent = ttk.Entry(top, textvariable=self.var_texto, width=40)
        ent.pack(side="left", padx=6)
        ent.bind("<Return>", lambda e: self.buscar())
        self.btn_buscar = ttk.Button(top, text="Buscar", command=self.buscar)
        self.btn_buscar.pack(side="left")
        cols = ("nombre", "nit", "departamento", "municipio", "esta_activa")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", selectmode="extended")
        for c, t, w in (("nombre", "Nombre", 300), ("nit", "NIT", 110), ("departamento", "Departamento", 120),
                        ("municipio", "Municipio", 110), ("esta_activa", "Activa", 60)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=8)
        self.lbl = ttk.Label(self, text="Escriba al menos 3 caracteres.", style="Meta.TLabel")
        self.lbl.pack(anchor="w", padx=8)
        pie = ttk.Frame(self, padding=8)
        pie.pack(fill="x")
        ttk.Button(pie, text="Usar como proveedor", command=self.usar).pack(side="left", padx=2)
        ttk.Button(pie, text="Guardar en directorio", command=self.guardar).pack(side="left", padx=2)
        ttk.Button(pie, text="Cerrar", command=self.destroy).pack(side="right")
        self._filas = {}
        ent.focus_set()

    def buscar(self):
        texto = self.var_texto.get()
        self._busqueda += 1
        token = self._busqueda
        self.btn_buscar.config(state="disabled")
        self.lbl.config(text="Buscando...")
        client_factory = self.client_factory

        def mostrar(filas):
            if token == self._busqueda:
                self._mostrar(filas)

        def fin(mensaje):
            if token == self._busqueda:
                self._fin(mensaje)

        def trabajo():
            try:
                filas = buscar_proveedores(client_factory(), texto)
            except ValueError as e:
                msg = str(e)
                _seguro(self, lambda m=msg: fin(m))
                return
            except Exception as e:
                msg = f"Error: {e}"
                _seguro(self, lambda m=msg: fin(m))
                return
            _seguro(self, lambda f=filas: mostrar(f))
        threading.Thread(target=trabajo, daemon=True).start()

    def _fin(self, mensaje):
        self.btn_buscar.config(state="normal")
        self.lbl.config(text=mensaje)

    def _mostrar(self, filas):
        self.tree.delete(*self.tree.get_children())
        self._filas = {}
        for r in filas:
            iid = self.tree.insert("", "end", values=(
                r.get("nombre", ""), r.get("nit", ""), r.get("departamento", ""),
                r.get("municipio", ""), r.get("esta_activa", "")))
            self._filas[iid] = r
        self._fin(f"{len(filas)} coincidencia(s)." if filas else "Sin coincidencias.")

    def _elegidas(self):
        return [self._filas[i] for i in self.tree.selection() if i in self._filas]

    def usar(self):
        sel = self._elegidas()
        if len(sel) != 1:
            messagebox.showinfo("Usar", "Seleccione una sola empresa.", parent=self)
            return
        self.al_usar(sel[0].get("nit", ""), sel[0].get("nombre", ""))
        self.destroy()

    def guardar(self):
        sel = self._elegidas()
        if not sel:
            messagebox.showinfo("Guardar", "Seleccione al menos una empresa.", parent=self)
            return
        nuevas = 0
        for r in sel:
            try:
                self.directorio.agregar("empresas", r.get("nombre", ""), r.get("nit", ""))
                nuevas += 1
            except (DuplicadoError, ValueError):
                continue
        self.al_cambiar()
        messagebox.showinfo("Directorio", f"{nuevas} empresa(s) agregada(s) "
                            f"({len(sel) - nuevas} ya existian).", parent=self)
