# -*- coding: utf-8 -*-
"""Directorio persistente de empresas, entidades y busquedas guardadas."""
import copy
import json
import os
import shutil
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime

VERSION = 1
TIPOS = ("empresas", "entidades")
CAMPOS_EDITABLES = {"nombre", "nit", "alias", "notas", "etiquetas", "nombre_resuelto"}
MAX_IDS = 2000


def directorio_datos():
    base = os.environ.get("SECOP_DATA_DIR")
    if not base:
        raiz = os.environ.get("APPDATA") or os.path.expanduser("~")
        base = os.path.join(raiz, "SecopSearch")
    os.makedirs(base, exist_ok=True)
    return base


def _ahora():
    return datetime.now().isoformat(timespec="seconds")


def nit_canonico(nit):
    return str(nit or "").replace("-", "").replace(".", "").replace(" ", "").strip()


def _etiquetas(valor):
    if isinstance(valor, str):
        valor = valor.split(",")
    vistas = []
    for e in valor or []:
        e = str(e).strip()
        if e and e not in vistas:
            vistas.append(e)
    return vistas


class DuplicadoError(ValueError):
    def __init__(self, existente):
        super().__init__(f"Ya existe '{existente['nombre']}' con ese NIT o nombre.")
        self.existente = existente


class Directorio:
    def __init__(self, ruta=None):
        self.ruta = ruta or os.path.join(directorio_datos(), "directorio.json")
        self.aviso = ""
        self._lock = threading.RLock()
        self.datos = self._vacio()
        self._cargar()

    @staticmethod
    def _vacio():
        return {"version": VERSION, "empresas": [], "entidades": [], "busquedas": []}

    # ---- persistencia --------------------------------------------------
    def _cargar(self):
        if not os.path.exists(self.ruta):
            return
        try:
            with open(self.ruta, "r", encoding="utf-8-sig") as f:
                datos = json.load(f)
            if not isinstance(datos, dict):
                raise ValueError("formato")
            for clave in ("empresas", "entidades", "busquedas"):
                if not isinstance(datos.setdefault(clave, []), list):
                    raise ValueError(clave)
            datos.setdefault("version", VERSION)
            self.datos = datos
        except (OSError, ValueError):
            destino = f"{self.ruta}.corrupto-{datetime.now():%Y%m%d%H%M%S}"
            try:
                os.replace(self.ruta, destino)
            except OSError:
                destino = "(no se pudo respaldar)"
            self.aviso = (f"El directorio estaba danado; se respaldo en {destino} "
                          "y se creo uno nuevo.")

    def guardar(self):
        os.makedirs(os.path.dirname(self.ruta) or ".", exist_ok=True)
        tmp = self.ruta + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.datos, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.ruta)
        except BaseException:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise

    @contextmanager
    def _tx(self):
        """Bloquea, ejecuta, guarda; si algo falla restaura la memoria."""
        with self._lock:
            snap = copy.deepcopy(self.datos)
            try:
                yield
                self.guardar()
            except BaseException:
                self.datos = snap
                raise

    # ---- empresas / entidades -----------------------------------------
    def _lista(self, tipo):
        if tipo not in TIPOS:
            raise ValueError(f"tipo invalido: {tipo}")
        return self.datos[tipo]

    def listar(self, tipo, filtro=""):
        with self._lock:
            items = list(self._lista(tipo))
        f = filtro.strip().lower()
        if not f:
            return items

        def coincide(it):
            texto = " ".join([it.get("nombre", ""), it.get("nit", ""), it.get("alias", ""),
                              it.get("notas", ""), " ".join(it.get("etiquetas", []))])
            return f in texto.lower()
        return [it for it in items if coincide(it)]

    def obtener(self, tipo, id_):
        with self._lock:
            return next((it for it in self._lista(tipo) if it["id"] == id_), None)

    def buscar_por_nit(self, tipo, nit):
        canon = nit_canonico(nit)
        if not canon:
            return None
        with self._lock:
            return next((it for it in self._lista(tipo)
                         if nit_canonico(it.get("nit")) == canon), None)

    def buscar_duplicado(self, tipo, nit, nombre, excluir_id=None):
        canon = nit_canonico(nit)
        for it in self._lista(tipo):
            if it["id"] == excluir_id:
                continue
            if canon:
                if nit_canonico(it.get("nit")) == canon:
                    return it
            elif (not nit_canonico(it.get("nit"))
                  and it["nombre"].strip().lower() == nombre.strip().lower()):
                return it
        return None

    def _agregar_item(self, tipo, nombre, nit="", alias="", notas="", etiquetas=None,
                      nombre_resuelto=True):
        """Agrega en memoria (sin guardar). Debe llamarse dentro de `_tx`."""
        nombre = str(nombre or "").strip()
        nit = str(nit or "").strip()
        if not nombre and not nit:
            raise ValueError("Se requiere nombre o NIT.")
        resuelto = bool(nombre) and nombre_resuelto
        nombre = nombre or nit
        dup = self.buscar_duplicado(tipo, nit, nombre)
        if dup:
            raise DuplicadoError(dup)
        item = {"id": uuid.uuid4().hex, "nombre": nombre, "nit": nit,
                "alias": str(alias or "").strip(), "notas": str(notas or "").strip(),
                "etiquetas": _etiquetas(etiquetas), "nombre_resuelto": resuelto,
                "creado": _ahora(), "ultima_consulta": ""}
        self._lista(tipo).append(item)
        return item

    def agregar(self, tipo, nombre, nit="", alias="", notas="", etiquetas=None,
                nombre_resuelto=True):
        with self._tx():
            item = self._agregar_item(tipo, nombre, nit, alias, notas, etiquetas,
                                      nombre_resuelto)
        return item

    def actualizar(self, tipo, id_, **campos):
        invalidos = set(campos) - CAMPOS_EDITABLES
        if invalidos:
            raise ValueError(f"campos no editables: {sorted(invalidos)}")
        with self._tx():
            item = self.obtener(tipo, id_)
            if item is None:
                raise KeyError(id_)
            nuevo = dict(item)
            nuevo.update(campos)
            nuevo["nombre"] = str(nuevo.get("nombre") or "").strip()
            nuevo["nit"] = str(nuevo.get("nit") or "").strip()
            if not nuevo["nombre"] and not nuevo["nit"]:
                raise ValueError("Se requiere nombre o NIT.")
            nuevo["nombre"] = nuevo["nombre"] or nuevo["nit"]
            for k in ("alias", "notas"):
                nuevo[k] = str(nuevo.get(k) or "").strip()
            if "etiquetas" in campos:
                nuevo["etiquetas"] = _etiquetas(campos["etiquetas"])
            if "nombre" in campos and "nombre_resuelto" not in campos:
                nuevo["nombre_resuelto"] = bool(str(campos["nombre"] or "").strip())
            dup = self.buscar_duplicado(tipo, nuevo["nit"], nuevo["nombre"], excluir_id=id_)
            if dup:
                raise DuplicadoError(dup)
            item.update(nuevo)
        return item

    def eliminar(self, tipo, id_):
        with self._tx():
            item = self.obtener(tipo, id_)
            if item is None:
                raise KeyError(id_)
            self._lista(tipo).remove(item)

    def fusionar(self, tipo, id_destino, id_origen):
        if id_destino == id_origen:
            raise ValueError("No se puede fusionar un registro consigo mismo.")
        with self._tx():
            d = self.obtener(tipo, id_destino)
            o = self.obtener(tipo, id_origen)
            if d is None or o is None:
                raise KeyError("registro inexistente")
            d["etiquetas"] = _etiquetas(d["etiquetas"] + o["etiquetas"])
            if o["notas"] and o["notas"] not in d["notas"]:
                d["notas"] = (d["notas"] + "\n" + o["notas"]).strip()
            if not d["nombre_resuelto"] and o["nombre_resuelto"]:
                d["nombre"], d["nombre_resuelto"] = o["nombre"], True
            if not d["alias"]:
                d["alias"] = o["alias"]
            if not d["nit"]:
                d["nit"] = o["nit"]
            d["ultima_consulta"] = max(d["ultima_consulta"], o["ultima_consulta"])
            d["creado"] = min(d["creado"], o["creado"])
            self._lista(tipo).remove(o)
        return d

    def marcar_consulta(self, tipo, id_):
        with self._tx():
            item = self.obtener(tipo, id_)
            if item is not None:
                item["ultima_consulta"] = _ahora()

    def claves(self, tipo):
        """{clave visible en combos: item}. Nombres repetidos se desambiguan con el NIT."""
        res = {}
        for it in self.listar(tipo):
            clave = it["nombre"]
            if clave in res:
                clave = f"{clave} ({it['nit'] or it['id'][:6]})"
            res[clave] = it
        return res

    def nombres_a_nit(self, tipo):
        return {k: it["nit"] for k, it in self.claves(tipo).items()}

    # ---- busquedas guardadas ------------------------------------------
    def guardar_busqueda(self, nombre, filtros, rango=None):
        """`rango` guarda el MODO de las fechas (no las fechas calculadas): un rango
        predefinido como {"modo": "ultimo_anio"} se recalcula al ejecutar."""
        nombre = str(nombre or "").strip()
        if not nombre:
            raise ValueError("La busqueda necesita un nombre.")
        rango = dict(rango) if rango else {"modo": "ultimo_anio"}
        with self._tx():
            existente = self.buscar_busqueda_por_nombre(nombre)
            if existente:
                existente.update({"filtros": dict(filtros), "rango": rango,
                                  "ultimos_ids": [], "ultima_ejecucion": ""})
                return existente
            item = {"id": uuid.uuid4().hex, "nombre": nombre, "filtros": dict(filtros),
                    "rango": rango, "ultimos_ids": [], "ultima_ejecucion": "",
                    "creado": _ahora()}
            self.datos["busquedas"].append(item)
        return item

    def listar_busquedas(self):
        with self._lock:
            return list(self.datos["busquedas"])

    def obtener_busqueda(self, id_):
        with self._lock:
            return next((b for b in self.datos["busquedas"] if b["id"] == id_), None)

    def buscar_busqueda_por_nombre(self, nombre):
        n = str(nombre or "").strip().lower()
        with self._lock:
            return next((b for b in self.datos["busquedas"] if b["nombre"].lower() == n), None)

    def eliminar_busqueda(self, id_):
        with self._tx():
            b = self.obtener_busqueda(id_)
            if b is None:
                raise KeyError(id_)
            self.datos["busquedas"].remove(b)

    def registrar_ejecucion(self, id_, ids):
        with self._tx():
            b = self.obtener_busqueda(id_)
            if b is None:
                raise KeyError(id_)
            b["ultimos_ids"] = list(ids)[:MAX_IDS]
            b["ultima_ejecucion"] = _ahora()

    # ---- preferencias --------------------------------------------------
    def preferencia(self, clave, defecto=None):
        with self._lock:
            return copy.deepcopy(self.datos.get("preferencias", {}).get(clave, defecto))

    def guardar_preferencia(self, clave, valor):
        with self._tx():
            self.datos.setdefault("preferencias", {})[clave] = valor

    # ---- migracion -----------------------------------------------------
    def migrar_historiales(self, rutas_empresas, rutas_entidades):
        """Importa los JSON antiguos una sola vez, todo o nada. Devuelve (n_empresas, n_entidades)."""
        with self._lock:
            if self.datos.get("migrado") or self.datos["empresas"] or self.datos["entidades"]:
                return (0, 0)
            total = {"empresas": 0, "entidades": 0}
            leidos = []
            with self._tx():
                for tipo, rutas in (("empresas", rutas_empresas), ("entidades", rutas_entidades)):
                    for ruta in rutas:
                        if not os.path.exists(ruta):
                            continue
                        try:
                            with open(ruta, "r", encoding="utf-8-sig") as f:
                                lista = json.load(f)
                        except (OSError, ValueError):
                            continue
                        if not isinstance(lista, list):
                            continue
                        leidos.append(ruta)
                        for it in lista:
                            if not isinstance(it, dict) or not it.get("nombre"):
                                continue
                            nombre, nit = str(it["nombre"]), str(it.get("nit") or "")
                            try:
                                nuevo = self._agregar_item(tipo, nombre, nit,
                                                           nombre_resuelto=(nombre != nit))
                            except DuplicadoError:
                                continue
                            nuevo["ultima_consulta"] = str(it.get("ultima_consulta") or "")
                            total[tipo] += 1
                self.datos["migrado"] = True
            for ruta in leidos:                      # respaldo solo tras guardar con exito
                try:
                    shutil.copy2(ruta, ruta + ".bak")
                except OSError:
                    pass
            return total["empresas"], total["entidades"]
