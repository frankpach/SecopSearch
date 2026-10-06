#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
App SECOP II - Consulta Integrada de Empresas de Vigilancia
Integra datasets de Socrata/Datos.gov.co para debida diligencia

NUEVO:
  - Historial de empresas consultadas en JSON local
  - Filtros por UNSPSC y entidad compradora (nombre/NIT)
  - Busqueda general (sin proveedor) por UNSPSC/entidad
"""

import os
import sys
import socket
import subprocess
import threading
import time
import webbrowser
import concurrent.futures
from datetime import datetime
from tkinter import (
    Tk, Frame, Label, Button, Entry, ttk, messagebox,
    filedialog, StringVar, scrolledtext, BooleanVar, simpledialog, TclError
)

import pandas as pd
import requests
from search import (
    Filtros, condiciones, orden_dataset, primer_valor_positivo, url_de,
    construir_where as _build_where, escapar_soql as _escape_sql, resolver_nombre_oficial,
    RANGOS, MODO_PERSONALIZADO, ETIQUETA_PERSONALIZADO, RANGO_POR_DEFECTO, rango_predefinido,
    con_rango, descripcion_rango, identificar_fila, marcar_nuevas,
)
from storage import Directorio, DuplicadoError
from ui_directorio import DialogoBuscarEmpresa, VentanaDirectorio, error_guardado
from paginacion import CachePaginas, TAMANOS_PAGINA, TAMANO_POR_DEFECTO, total_paginas, total_registros
from copiador_tabla import CopiadorTabla
from exportar import ExportacionCancelada, exportar, exportar_incremental
from paginacion import UMBRAL_CONFIRMACION, requiere_confirmacion
from ui_exportar import DialogoExportar
from tabla_utils import columnas_union, ordenar_filas, texto_pantalla, valor_visible

# =============================================================================
# CONFIGURACION
# =============================================================================
ENV_FILE = ".env"

DATASETS = {
    "jbjy-vk9h": "SECOP II - Contratos",
    "p6dx-8zbt": "SECOP II - Procesos",
    "rpmr-utcd":  "SECOP Integrado",
    "qmzu-gj57":  "SECOP II - Proveedores",
    "it5q-hg94":  "SECOP II - Sanciones",
    "4n4q-k399":  "SECOP I - Sanciones",
    "iaeu-rcn6":  "SIRI - Procuraduria",
}

BASE_URL          = "https://www.datos.gov.co/resource"
CONTRACT_URL_BASE = "https://community.secop.gov.co/Public/Tendering/ContractDetailView/Index?UniqueIdentifier="

ESTADO_COLORES = {
    "cancelado":    ("#ffe0e0", "#c0392b"),
    "terminado":    ("#fff8e1", "#e67e22"),
    "en ejecucion": ("#e8f5e9", "#27ae60"),
    "adjudicado":   ("#e3f2fd", "#1565c0"),
    "liquidado":    ("#f3e5f5", "#7b1fa2"),
    "modificado":   ("#e8f5e9", "#2e7d32"),
}

# =============================================================================
# UTILIDADES
# =============================================================================

def leer_env():
    creds = {}
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    creds[k.strip()] = v.strip()
    return creds


def formatear_pesos(valor):
    try:
        return f"${int(float(valor)):,}".replace(",", ".")
    except (ValueError, TypeError):
        return str(valor) if valor else ""


def formatear_fecha(fecha_str):
    if not fecha_str:
        return ""
    try:
        if "T" in str(fecha_str):
            dt = datetime.fromisoformat(str(fecha_str).replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d")
        return str(fecha_str)[:10]
    except Exception:
        return str(fecha_str)[:10]


def tag_para_estado(estado):
    if not estado:
        return "par"
    e = estado.lower()
    for k in ESTADO_COLORES:
        if k in e:
            return k
    return "par"


def validar_nit(nit):
    digitos = nit.replace("-", "").replace(".", "")
    return digitos.isdigit() and 8 <= len(digitos) <= 11


def _rutas_historial(nombre):
    """Rutas candidatas de los JSON antiguos: cwd, carpeta del programa y datos empaquetados."""
    bases = [os.getcwd(), os.path.dirname(os.path.abspath(sys.argv[0])), getattr(sys, "_MEIPASS", None)]
    return [os.path.join(b, nombre) for b in dict.fromkeys(b for b in bases if b)]


# =============================================================================
# CLIENTE API
# =============================================================================

class SECOPClient:
    def __init__(self, creds):
        self.session = requests.Session()
        user = creds.get("user")
        password = creds.get("password")
        self.auth = (user, password) if user and password else None

    def get(self, dataset_id, params=None, timeout=120):
        url = f"{BASE_URL}/{dataset_id}.json"
        for intento in range(3):
            ultimo = intento == 2
            try:
                resp = self.session.get(url, params=params, auth=self.auth, timeout=timeout)
            except (requests.ConnectionError, requests.Timeout):
                if ultimo:
                    raise
                time.sleep(1.5 * (intento + 1))
                continue
            if resp.status_code in (500, 502, 503, 504) and not ultimo:
                time.sleep(1.5 * (intento + 1))
                continue
            resp.raise_for_status()
            return resp.json()

    def get_metadata(self, dataset_id):
        url = f"https://www.datos.gov.co/api/views/{dataset_id}.json"
        resp = self.session.get(url, auth=self.auth, timeout=30)
        resp.raise_for_status()
        return resp.json()


# =============================================================================
# LOGICA DE CONSULTA (separada de la UI)
# =============================================================================

class SECOPQuery:
    def __init__(self, client: SECOPClient):
        self.client = client
        self.omitidos = []
        self.ultimos_errores = []

    # -------------------------------------------------------------------------
    # AYUDANTE: consulta un dataset con paginacion
    # -------------------------------------------------------------------------
    def _fetch_dataset(self, dataset_id, conds, order_col, limit, offset, q_text=None, extra_params=None):
        """Ejecuta GET paginado a un dataset. Retorna lista de registros.
        Si q_text se proporciona, usa $q (full-text search, mucho mas rapido que LIKE).
        El tamano de pagina (`limit`) lo decide quien llama; aqui no se recorta."""
        params = {"$limit": limit, "$offset": offset, "$order": order_col}
        if extra_params:
            params.update(extra_params)
        if q_text:
            params["$q"] = q_text
        where = _build_where(conds)
        if where:
            params["$where"] = where
        return self.client.get(dataset_id, params)

    # -------------------------------------------------------------------------
    # CONSULTA PAGINADA (lazy loading) — una pagina a la vez
    # -------------------------------------------------------------------------
    def consultar_pagina(self, nombre, nit=None, filtros=None,
                         offset=0, page_size=100, on_progress=None):
        """
        Devuelve SOLO la pagina solicitada.
          filas   — lista normalizada (max page_size)
          detalle — dict {nombre_tab: [filas_crudas]} de esta pagina
          errores — lista de strings
          has_more— bool, True si probablemente hay mas paginas
        `filtros` es un search.Filtros; `nit` (proveedor) tiene prioridad sobre
        filtros.nit_proveedor. Los datasets que no pueden aplicar algun filtro
        activo se omiten y quedan en self.omitidos.
        """
        filas = []
        detalle = {}
        errores = []
        omitidos = []
        has_more = False

        f = (filtros or Filtros()).limpio()
        if nit:
            f.nit_proveedor = str(nit).strip()

        def _fetch(dataset_id):
            r = condiciones(dataset_id, f)
            if r is None:
                omitidos.append(DATASETS[dataset_id])
                return []
            conds, q_text = r
            return self._fetch_dataset(dataset_id, conds, orden_dataset(dataset_id, f),
                                       page_size, offset, q_text=q_text)

        if on_progress:
            on_progress(f"{nombre or 'Busqueda'}: consultando datasets (offset {offset})...")
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                future_contratos = executor.submit(_fetch, "jbjy-vk9h")
                future_procesos = executor.submit(_fetch, "p6dx-8zbt")
                future_integrado = executor.submit(_fetch, "rpmr-utcd")

                data_contratos = future_contratos.result(timeout=180)
                data_procesos = future_procesos.result(timeout=180)
                data_integrado = future_integrado.result(timeout=180)
        except Exception as e:
            errores.append(f"Error en consulta paralela: {e}. Intentando secuencial...")
            omitidos.clear()
            # Fallback secuencial
            try:
                data_contratos = _fetch("jbjy-vk9h")
            except Exception as e2:
                errores.append(f"Contratos fallback: {e2}")
                data_contratos = []
            try:
                data_procesos = _fetch("p6dx-8zbt")
            except Exception as e2:
                errores.append(f"Procesos fallback: {e2}")
                data_procesos = []
            try:
                data_integrado = _fetch("rpmr-utcd")
            except Exception as e2:
                errores.append(f"Integrado fallback: {e2}")
                data_integrado = []
        self.omitidos = sorted(set(omitidos))

        # Procesar Contratos
        if data_contratos:
            detalle["Contratos SECOP II"] = data_contratos
            has_more = has_more or len(data_contratos) >= page_size
        for r in data_contratos:
            contract_id = r.get("id_contrato", "")
            filas.append({
                "empresa":   nombre or r.get("proveedor_adjudicado", "—"),
                "nit":       nit or r.get("documento_proveedor", "—"),
                "fuente":    "SECOP II",
                "entidad":   r.get("nombre_entidad", ""),
                "entidad_nit": r.get("nit_entidad", ""),
                "id_contrato": contract_id,
                "referencia":  r.get("referencia_del_contrato", ""),
                "objeto":    r.get("objeto_del_contrato") or r.get("objeto_del_contrato_a_ejecutar") or "",
                "valor":     formatear_pesos(r.get("valor_del_contrato_con_adiciones") or r.get("valor_del_contrato", "")),
                "pagado":    formatear_pesos(r.get("valor_pagado", "")),
                "pendiente": formatear_pesos(r.get("valor_pendiente_de_pago", "")),
                "estado":    r.get("estado_contrato", ""),
                "fecha_firma": formatear_fecha(r.get("fecha_de_firma", "")),
                "fecha_fin":   formatear_fecha(r.get("fecha_de_fin_del_contrato", "")),
                "sancion":   "No",
                "url":       f"{CONTRACT_URL_BASE}{contract_id}" if contract_id else "",
            })

        # Procesar Procesos
        if data_procesos:
            detalle["Procesos SECOP II"] = data_procesos
            has_more = has_more or len(data_procesos) >= page_size
        for r in data_procesos:
            filas.append({
                "empresa":   nombre or r.get("nombre_del_proveedor", "—"),
                "nit":       nit or r.get("nit_del_proveedor_adjudicado", "—"),
                "fuente":    "Proceso",
                "entidad":   r.get("entidad", ""),
                "entidad_nit": r.get("nit_entidad", ""),
                "id_contrato": r.get("id_del_proceso", ""),
                "referencia":  r.get("referencia_del_proceso", ""),
                "objeto":    r.get("nombre_del_procedimiento", ""),
                "valor":     formatear_pesos(primer_valor_positivo(
                    r.get("valor_total_adjudicacion"), r.get("precio_base"))),
                "pagado":    "",
                "pendiente": "",
                "estado":    r.get("estado_del_procedimiento", ""),
                "fecha_firma": formatear_fecha(r.get("fecha_adjudicacion", "")),
                "fecha_fin":   "",
                "sancion":   "No",
                "url":       url_de(r.get("urlproceso")),
            })

        # Procesar Integrado
        if data_integrado:
            detalle["SECOP Integrado (historico)"] = data_integrado
            has_more = has_more or len(data_integrado) >= page_size
        for r in data_integrado:
            filas.append({
                "empresa":   nombre or r.get("nom_raz_social_contratista", "—"),
                "nit":       nit or r.get("documento_proveedor", "—"),
                "fuente":    "SECOP I",
                "entidad":   r.get("nombre_de_la_entidad", ""),
                "entidad_nit": r.get("nit_de_la_entidad", ""),
                "id_contrato": r.get("numero_del_contrato", ""),
                "referencia":  r.get("numero_del_contrato", ""),
                "objeto":    r.get("objeto_a_contratar") or r.get("objeto_del_proceso") or r.get("objeto_del_contrato") or "",
                "valor":     formatear_pesos(r.get("valor_contrato", "")),
                "pagado":    "",
                "pendiente": "",
                "estado":    r.get("estado_del_proceso", ""),
                "fecha_firma": formatear_fecha(r.get("fecha_de_firma_del_contrato", "")),
                "fecha_fin":   formatear_fecha(r.get("fecha_fin_ejecuci_n", "")),
                "sancion":   "No",
                "url":       url_de(r.get("url_contrato")),
            })

        # --- Proveedores (qmzu-gj57) — solo pagina 1 y si hay NIT ---
        if nit and offset == 0:
            if on_progress:
                on_progress(f"{nombre}: consultando registro de proveedor...")
            try:
                data = self.client.get("qmzu-gj57", {"$where": f"nit='{_escape_sql(nit)}'", "$limit": 10}, timeout=60)
                if data:
                    detalle["Proveedor SECOP II"] = data
            except Exception as e:
                errores.append(f"Proveedores ({nombre}): {e}")

        # --- Sanciones SECOP II (it5q-hg94) — solo pagina 1 ---
        if offset == 0:
            if on_progress:
                on_progress(f"{nombre or 'Busqueda'}: verificando sanciones...")
            try:
                q = nombre if nombre else (nit if nit else "")
                if q:
                    data = self.client.get("it5q-hg94", {"$q": q, "$limit": 50}, timeout=60)
                    if data:
                        detalle["Sanciones SECOP II"] = data
                    for r in data:
                        filas.append({
                            "empresa":   nombre or r.get("nombre_proveedor_objeto_de", "—"),
                            "nit":       nit or "",
                            "fuente":    "Sancion SECOP II",
                            "entidad":   r.get("nombre_entidad_creadora", ""),
                            "entidad_nit": "",
                            "id_contrato": "",
                            "referencia":  r.get("tipo_de_sancion", ""),
                            "objeto":    r.get("descripcion", ""),
                            "valor":     formatear_pesos(r.get("valor", "")),
                            "pagado":    formatear_pesos(r.get("valor_pagado", "")),
                            "pendiente": "",
                            "estado":    r.get("estado", "SANCION"),
                            "fecha_firma": formatear_fecha(r.get("fecha_evento", "")),
                            "fecha_fin":   "",
                            "sancion":   "SI",
                            "url":       "",
                        })
            except Exception as e:
                errores.append(f"Sanciones SECOP II: {e}")

        # --- Sanciones SECOP I (4n4q-k399) — solo pagina 1 ---
        if offset == 0:
            try:
                q = nombre if nombre else (nit if nit else "")
                if q:
                    data = self.client.get("4n4q-k399", {"$q": q, "$limit": 50}, timeout=60)
                    if data:
                        detalle["Sanciones SECOP I"] = data
                    for r in data:
                        filas.append({
                            "empresa":   nombre or r.get("nombre_contratista", "—"),
                            "nit":       nit or "",
                            "fuente":    "Sancion SECOP I",
                            "entidad":   r.get("nombre_entidad", ""),
                            "entidad_nit": "",
                            "id_contrato": r.get("numero_de_resolucion", ""),
                            "referencia":  r.get("numero_de_resolucion", ""),
                            "objeto":    "",
                            "valor":     formatear_pesos(r.get("valor_sancion", "")),
                            "pagado":    "",
                            "pendiente": "",
                            "estado":    "SANCION",
                            "fecha_firma": formatear_fecha(r.get("fecha_de_firmeza", "")),
                            "fecha_fin":   "",
                            "sancion":   "SI",
                            "url":       "",
                        })
            except Exception as e:
                errores.append(f"Sanciones SECOP I: {e}")

        # --- SIRI Procuraduria (iaeu-rcn6) — solo pagina 1 y si hay NIT ---
        if nit and offset == 0:
            try:
                data = self.client.get("iaeu-rcn6", {
                    "$where": f"numero_identificacion='{_escape_sql(nit)}'",
                    "$limit": 50,
                }, timeout=60)
                if data:
                    detalle["SIRI Procuraduria"] = data
                for r in data:
                    filas.append({
                        "empresa":   nombre or "",
                        "nit":       nit,
                        "fuente":    "SIRI Procuraduria",
                        "entidad":   r.get("autoridad", ""),
                        "entidad_nit": "",
                        "id_contrato": "",
                        "referencia":  r.get("tipo_inhabilidad", ""),
                        "objeto":    r.get("sanciones", ""),
                        "valor":     "",
                        "pagado":    "",
                        "pendiente": "",
                        "estado":    "INHABILIDAD",
                        "fecha_firma": formatear_fecha(r.get("fecha_efectos_juridicos", "")),
                        "fecha_fin":   "",
                        "sancion":   "SI",
                        "url":       "",
                    })
            except Exception as e:
                errores.append(f"SIRI: {e}")

        if not filas:
            filas.append({
                "empresa":   nombre or "Busqueda general",
                "nit":       nit or "—",
                "fuente":    "—",
                "entidad":   "Sin registros en SECOP",
                "entidad_nit": "",
                "id_contrato": "",
                "referencia":  "",
                "objeto":    "",
                "valor":     "",
                "pagado":    "",
                "pendiente": "",
                "estado":    "SIN CONTRATOS",
                "fecha_firma": "",
                "fecha_fin":   "",
                "sancion":   "No",
                "url":       "",
            })

        return filas, detalle, errores, has_more

    # -------------------------------------------------------------------------
    # CONTEO E ITERACION PAGINA A PAGINA (para exportar)
    # -------------------------------------------------------------------------
    def contar(self, nombre, nit=None, filtros=None):
        """Total real por dataset (count(*)) con los mismos filtros. Los errores se propagan."""
        f = (filtros or Filtros()).limpio()
        if nit:
            f.nit_proveedor = str(nit).strip()
        total = {}
        for ds in ("jbjy-vk9h", "p6dx-8zbt", "rpmr-utcd"):
            r = condiciones(ds, f)
            if r is None:                          # el dataset no soporta algun filtro activo
                total[DATASETS[ds]] = 0
                continue
            conds, q_text = r
            params = {"$select": "count(*)"}
            if q_text:
                params["$q"] = q_text
            where = _build_where(conds)
            if where:
                params["$where"] = where
            datos = self.client.get(ds, params, timeout=60)
            total[DATASETS[ds]] = int(datos[0].get("count", 0)) if datos else 0
        return total

    def iterar_paginas(self, nombre, nit=None, filtros=None, page_size=100,
                       on_progress=None, cancelado=None, max_paginas=100000):
        """Genera (filas, detalle) pagina a pagina SIN acumular. Los errores de cada
        pagina quedan en self.ultimos_errores. Se detiene si cancelado() es True."""
        self.ultimos_errores = []
        offset, pagina = 0, 1
        while pagina <= max_paginas:
            if cancelado and cancelado():
                return
            if on_progress:
                on_progress(f"Descargando pagina {pagina} (offset {offset})...")
            filas, detalle, errs, has_more = self.consultar_pagina(
                nombre, nit, filtros, offset=offset, page_size=page_size)
            self.ultimos_errores.extend(errs)
            filas = [f for f in filas if f.get("fuente") != "—"]   # sin la fila de relleno
            if not filas and not detalle:
                return
            yield filas, detalle
            if not has_more:
                return
            offset += page_size
            pagina += 1


# =============================================================================
# APLICACION UI
# =============================================================================

COLUMNAS = [
    ("empresa",      "Empresa",         180),
    ("fuente",       "Fuente",           90),
    ("entidad",      "Entidad",         200),
    ("entidad_nit",  "NIT Entidad",     120),
    ("id_contrato",  "ID Contrato",     150),
    ("objeto",       "Objeto",          220),
    ("valor",        "Valor",           110),
    ("pagado",       "Pagado",          110),
    ("pendiente",    "Pendiente",       110),
    ("estado",       "Estado",          110),
    ("fecha_firma",  "Firma",            90),
    ("fecha_fin",    "Fin",              90),
    ("sancion",      "Sancion",          70),
]

COLUMNAS_EXPORTACION = COLUMNAS + [
    ("nit",        "NIT Empresa", 0),
    ("referencia", "Referencia",  0),
    ("url",        "URL SECOP",   0),
]

COLS_IDS = [c[0] for c in COLUMNAS]

PAGINA_NOVEDADES = 100     # tamano fijo al ejecutar busquedas guardadas (comparacion consistente)


class AppSECOP(Tk):
    def __init__(self):
        super().__init__()
        self.title("SECOP II - Debida Diligencia")
        self.geometry("1550x950")
        self.configure(bg="#f0f2f5")
        self.minsize(1200, 700)

        self.creds = leer_env()
        self.client = SECOPClient(self.creds)
        self.query = SECOPQuery(self.client)

        # Directorio persistente (migra los JSON antiguos la primera vez)
        self.directorio = Directorio()
        try:
            self.directorio.migrar_historiales(_rutas_historial("empresas_historial.json"),
                                               _rutas_historial("entidades_historial.json"))
        except OSError as e:                    # la app arranca igual; se avisa en el Directorio
            self.directorio.aviso = "\n".join(filter(None, [
                self.directorio.aviso, f"No se pudo importar el historial antiguo: {e}"]))
        self._ids_combo = {"empresas": {}, "entidades": {}}   # {clave del combo: id}
        self._ventana_directorio = None

        self._filas = []
        self._url_map = {}
        self._filas_por_item = {}
        self._errores = []
        self._omitidos = []
        self._nuevos = set()           # filas nuevas desde la ultima ejecucion de una busqueda guardada
        self._busqueda_activa = None   # id de la busqueda guardada que se esta ejecutando
        self._consultando = False
        self._exportando = False       # consulta y exportacion son excluyentes

        # Paginacion lazy loading: solo la pagina actual vive en memoria
        self._filas_por_pagina = TAMANO_POR_DEFECTO
        self._pagina_actual = 1
        self._pagina_previa = None     # para restaurar si se cancela una carga
        self._has_more = False         # si hay mas paginas disponibles
        self._conteos = None           # {dataset: total} real; llega en segundo plano
        self._total_paginas = None
        self._cache = CachePaginas()   # ultimas paginas visitadas (ir y volver sin consultar)
        self._pagina_detalle = {}      # detalle crudo SOLO de la pagina actual
        self._consulta_id = 0          # descarta resultados de consultas canceladas o viejas
        self._cancelar = threading.Event()
        self._contando = None          # _consulta_id del conteo en curso (evita duplicarlo)
        self._tamano_previo = None     # (tamano, cache) para deshacer un cambio de tamano cancelado
        self._filtros_activos = None   # dict con filtros para reconsultar paginas
        self._orden_inverso = {}       # estado de ordenamiento por columna

        # MCP Server panel
        self.mcp_process = None
        self.mcp_puerto = 8000

        self._configurar_estilos()
        self._crear_header()
        self._crear_panel_control()
        self._crear_panel_metadatos()
        self._crear_notebook()
        self._crear_panel_mcp()
        self._crear_barra_estado()

        self.protocol("WM_DELETE_WINDOW", self._on_closing)
        self.after(300, self._cargar_metadatos_async)
        self.after(1500, self._aviso_inicio)

    # -------------------------------------------------------------------------
    # ESTILOS
    # -------------------------------------------------------------------------
    def _configurar_estilos(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("TFrame",      background="#f0f2f5")
        s.configure("TLabel",      background="#f0f2f5", font=("Segoe UI", 10))
        s.configure("TButton",     font=("Segoe UI", 10, "bold"), padding=6)
        s.configure("Accent.TButton", font=("Segoe UI", 10, "bold"), padding=6,
                    foreground="white", background="#1a5490")
        s.configure("Header.TLabel", font=("Segoe UI", 15, "bold"), foreground="#1a5490",
                    background="#f0f2f5")
        s.configure("Sub.TLabel",    font=("Segoe UI", 10), foreground="#555",
                    background="#f0f2f5")
        s.configure("Status.TLabel", font=("Segoe UI", 9, "italic"), foreground="#444",
                    background="#e8eaf0")
        s.configure("Meta.TLabel",   font=("Segoe UI", 8), foreground="#666",
                    background="#f0f2f5")
        s.configure("Treeview",      rowheight=24, font=("Segoe UI", 9))
        s.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))

    # -------------------------------------------------------------------------
    # HEADER
    # -------------------------------------------------------------------------
    def _crear_header(self):
        frm = ttk.Frame(self, padding=(12, 8))
        frm.pack(fill="x")
        ttk.Label(frm, text="SECOP II — Debida Diligencia", style="Header.TLabel").pack(side="left")
        ttk.Label(frm, text="  Vigilancia y Seguridad Privada | Colombia Compra Eficiente",
                  style="Sub.TLabel").pack(side="left", padx=(6, 0))
        ttk.Button(frm, text="Directorio...", command=self._abrir_directorio).pack(side="right")

    # -------------------------------------------------------------------------
    # PANEL CONTROL
    # -------------------------------------------------------------------------
    def _crear_panel_control(self):
        frm = ttk.LabelFrame(self, text="Consulta", padding=(10, 6))
        frm.pack(fill="x", padx=10, pady=(0, 4))

        # --- Fila 0: Empresa + NIT ---
        ttk.Label(frm, text="Empresa:").grid(row=0, column=0, sticky="w", padx=(0, 4))
        self.var_empresa = StringVar(value="TODAS")
        self.combo_empresa = ttk.Combobox(frm, textvariable=self.var_empresa,
                                          state="readonly", width=42)
        self._refrescar_combo_empresas()
        self.combo_empresa.grid(row=0, column=1, sticky="w", padx=(0, 4))
        acc_emp = ttk.Frame(frm)
        acc_emp.grid(row=0, column=2, sticky="w", padx=(0, 12))
        ttk.Button(acc_emp, text="Editar", width=7, command=lambda: self._editar_seleccion("empresas")).pack(side="left", padx=1)
        ttk.Button(acc_emp, text="Eliminar", width=8, command=self._eliminar_empresa).pack(side="left", padx=1)

        ttk.Label(frm, text="NIT manual:").grid(row=0, column=3, sticky="w", padx=(0, 4))
        self.entry_nit = ttk.Entry(frm, width=18)
        self.entry_nit.grid(row=0, column=4, sticky="w", padx=(0, 4))
        ttk.Button(frm, text="Guardar", width=8,
                   command=self._guardar_empresa_manual).grid(row=0, column=5, sticky="w", padx=(0, 12))

        # --- Fila 1: Entidad + filtros ---
        ttk.Label(frm, text="Entidad:").grid(row=1, column=0, sticky="w", padx=(0, 4), pady=(6, 0))
        self.var_entidad = StringVar(value="TODAS")
        self.combo_entidad = ttk.Combobox(frm, textvariable=self.var_entidad,
                                          state="readonly", width=42)
        self._refrescar_combo_entidades()
        self.combo_entidad.grid(row=1, column=1, sticky="w", padx=(0, 4), pady=(6, 0))
        self.combo_entidad.bind("<<ComboboxSelected>>", self._on_entidad_selected)
        acc_ent = ttk.Frame(frm)
        acc_ent.grid(row=1, column=2, sticky="w", padx=(0, 12), pady=(6, 0))
        ttk.Button(acc_ent, text="Editar", width=7, command=lambda: self._editar_seleccion("entidades")).pack(side="left", padx=1)
        ttk.Button(acc_ent, text="Eliminar", width=8, command=self._eliminar_entidad).pack(side="left", padx=1)

        ttk.Label(frm, text="Entidad NIT:").grid(row=1, column=3, sticky="w", padx=(0, 4), pady=(6, 0))
        self.entry_entidad_nit = ttk.Entry(frm, width=18)
        self.entry_entidad_nit.grid(row=1, column=4, sticky="w", padx=(0, 4), pady=(6, 0))
        ttk.Button(frm, text="Guardar", width=8,
                   command=self._guardar_entidad_manual).grid(row=1, column=5, sticky="w", padx=(0, 12), pady=(6, 0))

        # --- Fila 2: UNSPSC + Entidad nombre + Botones ---
        ttk.Label(frm, text="UNSPSC:").grid(row=2, column=0, sticky="w", padx=(0, 4), pady=(6, 0))
        self.entry_unspsc = ttk.Entry(frm, width=20)
        self.entry_unspsc.grid(row=2, column=1, sticky="w", padx=(0, 4), pady=(6, 0))

        ttk.Label(frm, text="Entidad (nombre):").grid(row=2, column=2, sticky="w", padx=(0, 4), pady=(6, 0))
        self.entry_entidad_nombre = ttk.Entry(frm, width=35)
        self.entry_entidad_nombre.grid(row=2, column=3, columnspan=2, sticky="w", padx=(0, 12), pady=(6, 0))

        btn_frm = ttk.Frame(frm)
        btn_frm.grid(row=2, column=5, sticky="w", pady=(6, 0))

        self.btn_consultar = ttk.Button(btn_frm, text="Consultar",
                                        command=self._iniciar_consulta, style="Accent.TButton")
        self.btn_consultar.pack(side="left", padx=2)
        self.btn_exportar = ttk.Button(btn_frm, text="Exportar...", command=self._exportar)
        self.btn_exportar.pack(side="left", padx=2)
        self.btn_limpiar = ttk.Button(btn_frm, text="Limpiar", command=self._limpiar)
        self.btn_limpiar.pack(side="left", padx=2)
        self.btn_cancelar = ttk.Button(btn_frm, text="Cancelar", command=self._cancelar_operacion,
                                       state="disabled")
        self.btn_cancelar.pack(side="left", padx=2)
        ttk.Label(btn_frm, text="Por pagina:").pack(side="left", padx=(10, 2))
        self.var_tamano = StringVar(value=str(TAMANO_POR_DEFECTO))
        self.combo_tamano = ttk.Combobox(btn_frm, textvariable=self.var_tamano, state="readonly",
                                         width=5, values=[str(t) for t in TAMANOS_PAGINA])
        self.combo_tamano.pack(side="left")
        self.combo_tamano.bind("<<ComboboxSelected>>", lambda e: self._on_tamano())

        # Barra de progreso
        self.progress = ttk.Progressbar(frm, mode="indeterminate", length=180)
        self.progress.grid(row=0, column=6, rowspan=3, sticky="w", padx=(12, 0))
        self.progress.grid_remove()

        self._crear_panel_busqueda_avanzada(frm)

    def _refrescar_combo_empresas(self):
        self._ids_combo["empresas"] = {k: it["id"] for k, it in self.directorio.claves("empresas").items()}
        self.combo_empresa["values"] = ["TODAS"] + list(self._ids_combo["empresas"])

    def _refrescar_combo_entidades(self):
        self._ids_combo["entidades"] = {k: it["id"] for k, it in self.directorio.claves("entidades").items()}
        self.combo_entidad["values"] = ["TODAS"] + list(self._ids_combo["entidades"])

    MODALIDADES = ["Contratación directa", "Licitación pública", "Selección abreviada",
                   "Concurso de méritos", "Mínima cuantía", "Régimen especial"]

    def _crear_panel_busqueda_avanzada(self, frm):
        # --- Fila 3: texto libre + buscar empresa + filtros avanzados ---
        ttk.Label(frm, text="Texto del objeto:").grid(row=3, column=0, sticky="w", padx=(0, 4), pady=(6, 0))
        self.entry_texto = ttk.Entry(frm, width=45)
        self.entry_texto.grid(row=3, column=1, sticky="w", padx=(0, 4), pady=(6, 0))
        self.entry_texto.bind("<Return>", lambda e: self._iniciar_consulta())
        self.btn_buscar_empresa = ttk.Button(frm, text="Buscar empresa por nombre...",
                                             command=self._abrir_buscar_empresa)
        self.btn_buscar_empresa.grid(row=3, column=2, columnspan=2, sticky="w",
                                     padx=(0, 12), pady=(6, 0))
        self.var_avanzado = BooleanVar(value=False)
        ttk.Checkbutton(frm, text="Filtros avanzados", variable=self.var_avanzado,
                        command=self._toggle_avanzado).grid(row=3, column=4, sticky="w", pady=(6, 0))

        # --- Fila 4: rango de fechas (SIEMPRE visible; por defecto el ultimo año) ---
        ttk.Label(frm, text="Fechas:").grid(row=4, column=0, sticky="w", padx=(0, 4), pady=(6, 0))
        fr = ttk.Frame(frm)
        fr.grid(row=4, column=1, columnspan=5, sticky="w", pady=(6, 0))
        self.var_rango = StringVar(value=RANGOS["ultimo_anio"][0])
        self.combo_rango = ttk.Combobox(
            fr, textvariable=self.var_rango, state="readonly", width=20,
            values=[etiqueta for etiqueta, _ in RANGOS.values()] + [ETIQUETA_PERSONALIZADO])
        self.combo_rango.pack(side="left")
        self.combo_rango.bind("<<ComboboxSelected>>", lambda e: self._on_rango())
        # Solo un cambio real del TEXTO pasa a "Personalizado" (no Tab, flechas, Ctrl+C...):
        # se vigila la variable, y lo que escribe el propio programa no cuenta
        self._fechas_escritas = ("", "")    # lo ultimo que escribieron _on_rango/_aplicar_rango
        self._escribiendo_fechas = False
        ttk.Label(fr, text="   Desde:").pack(side="left")
        self.var_desde = StringVar()
        self.ent_desde = ttk.Entry(fr, width=12, textvariable=self.var_desde)
        self.ent_desde.pack(side="left", padx=(2, 8))
        ttk.Label(fr, text="Hasta:").pack(side="left")
        self.var_hasta = StringVar()
        self.ent_hasta = ttk.Entry(fr, width=12, textvariable=self.var_hasta)
        self.ent_hasta.pack(side="left", padx=(2, 8))
        for var in (self.var_desde, self.var_hasta):
            var.trace_add("write", lambda *a: self._on_fecha_editada())
        ttk.Label(fr, text="AAAA-MM-DD; vacio = sin limite. Sanciones y SIRI no usan fechas.",
                  style="Meta.TLabel").pack(side="left")
        self._on_rango()

        # --- Fila 5: filtros avanzados (plegable) ---
        self.frm_avanzado = ttk.Frame(frm)
        self.frm_avanzado.grid(row=5, column=0, columnspan=6, sticky="w", pady=(6, 0))
        self.ent_av = {}
        campos = [("valor_min", "Valor min:", 14), ("valor_max", "Valor max:", 14),
                  ("estado", "Estado:", 14), ("departamento", "Departamento:", 14)]
        for i, (clave, etiqueta, ancho) in enumerate(campos):
            ttk.Label(self.frm_avanzado, text=etiqueta).grid(row=0, column=i * 2, sticky="w", padx=(0, 2))
            e = ttk.Entry(self.frm_avanzado, width=ancho)
            e.grid(row=0, column=i * 2 + 1, sticky="w", padx=(0, 10))
            self.ent_av[clave] = e
        ttk.Label(self.frm_avanzado, text="Modalidad:").grid(row=0, column=8, sticky="w", padx=(0, 2))
        self.var_modalidad = StringVar()
        self.combo_modalidad = ttk.Combobox(self.frm_avanzado, textvariable=self.var_modalidad,
                                            values=self.MODALIDADES, width=24)
        self.combo_modalidad.grid(row=0, column=9, sticky="w")
        self.frm_avanzado.grid_remove()

        # --- Fila 6: busquedas guardadas ---
        ttk.Label(frm, text="Busquedas guardadas:").grid(row=6, column=0, sticky="w", padx=(0, 4), pady=(6, 0))
        self.var_busqueda = StringVar()
        self.combo_busqueda = ttk.Combobox(frm, textvariable=self.var_busqueda, state="readonly", width=42)
        self.combo_busqueda.grid(row=6, column=1, sticky="w", padx=(0, 4), pady=(6, 0))
        acc = ttk.Frame(frm)
        acc.grid(row=6, column=2, columnspan=4, sticky="w", pady=(6, 0))
        self._btns_busqueda = {}            # se desactivan durante consultas y exportaciones
        for clave, texto, cmd in (("ejecutar", "Ejecutar", self._ejecutar_busqueda_guardada),
                                  ("todas", "Ejecutar todas", self._ejecutar_todas),
                                  ("guardar", "Guardar actual...", self._guardar_busqueda),
                                  ("eliminar", "Eliminar", self._eliminar_busqueda)):
            self._btns_busqueda[clave] = ttk.Button(acc, text=texto, command=cmd)
            self._btns_busqueda[clave].pack(side="left", padx=2)
        self._refrescar_combo_busquedas()

    def _toggle_avanzado(self):
        if self.var_avanzado.get():
            self.frm_avanzado.grid()
        else:
            self.frm_avanzado.grid_remove()

    def _refrescar_combo_busquedas(self):
        self.combo_busqueda["values"] = [b["nombre"] for b in self.directorio.listar_busquedas()]

    def _abrir_buscar_empresa(self):
        DialogoBuscarEmpresa(self, self._client_nuevo, self.directorio,
                             self._usar_proveedor, self._refrescar_combos)

    def _usar_proveedor(self, nit, nombre):
        self.var_empresa.set("TODAS")
        self.entry_nit.delete(0, "end")
        self.entry_nit.insert(0, nit)
        self.lbl_estado.config(text=f"Proveedor seleccionado: {nombre} ({nit})")

    # ---- rango de fechas -------------------------------------------------
    @staticmethod
    def _poner(entry, valor):
        entry.delete(0, "end")
        entry.insert(0, valor)

    def _clave_rango_actual(self):
        etiqueta = self.var_rango.get()
        return next((k for k, (e, _) in RANGOS.items() if e == etiqueta), MODO_PERSONALIZADO)

    def _on_rango(self):
        """Elegir un rango predefinido rellena Desde/Hasta (se recalculan en cada consulta)."""
        clave = self._clave_rango_actual()
        if clave != MODO_PERSONALIZADO:
            self._poner_fechas(*rango_predefinido(clave))

    def _poner_fechas(self, desde, hasta):
        """Escribe Desde/Hasta desde el programa: no cuenta como edicion del usuario."""
        self._escribiendo_fechas = True
        try:
            self._poner(self.ent_desde, desde)
            self._poner(self.ent_hasta, hasta)
        finally:
            self._escribiendo_fechas = False
        self._fechas_escritas = (self.ent_desde.get(), self.ent_hasta.get())

    def _on_fecha_editada(self):
        """Pasa a "Personalizado" solo si el texto difiere de lo que escribio el programa."""
        if self._escribiendo_fechas:
            return
        if (self.ent_desde.get(), self.ent_hasta.get()) != self._fechas_escritas:
            self.var_rango.set(ETIQUETA_PERSONALIZADO)

    def _leer_rango(self):
        clave = self._clave_rango_actual()
        if clave == MODO_PERSONALIZADO:
            return {"modo": MODO_PERSONALIZADO, "desde": self.ent_desde.get().strip(),
                    "hasta": self.ent_hasta.get().strip()}
        return {"modo": clave}

    def _aplicar_rango_a_widgets(self, rango):
        rango = rango or RANGO_POR_DEFECTO
        modo = rango.get("modo", "ultimo_anio")
        if modo == MODO_PERSONALIZADO:
            self.var_rango.set(ETIQUETA_PERSONALIZADO)
            self._poner_fechas(rango.get("desde", ""), rango.get("hasta", ""))
        else:
            self.var_rango.set(RANGOS.get(modo, RANGOS["ultimo_anio"])[0])
            self._on_rango()

    # ---- filtros: widgets <-> Filtros ------------------------------------
    def _leer_filtros(self):
        nit_manual = self.entry_nit.get().strip()
        empresa_sel = self.var_empresa.get()
        nit_prov = nit_manual or (self.empresas.get(empresa_sel) or "" if empresa_sel != "TODAS" else "")
        entidad_nombre = self.entry_entidad_nombre.get().strip()
        entidad_nit = self.entry_entidad_nit.get().strip()
        entidad_sel = self.var_entidad.get()
        if entidad_sel != "TODAS" and entidad_sel in self.entidades:
            entidad_nombre = entidad_nombre or entidad_sel
            entidad_nit = entidad_nit or self.entidades[entidad_sel]
        if self._clave_rango_actual() != MODO_PERSONALIZADO:
            self._on_rango()               # un rango predefinido siempre se recalcula a "hoy"
        base = Filtros(
            texto=self.entry_texto.get(), nit_proveedor=nit_prov,
            entidad_nombre=entidad_nombre, entidad_nit=entidad_nit,
            unspsc=self.entry_unspsc.get(), modalidad=self.var_modalidad.get(),
            **{k: e.get() for k, e in self.ent_av.items()},
        )
        return con_rango(base, self._leer_rango())

    def _cargar_filtros_en_widgets(self, f, rango=None):
        self._poner(self.entry_texto, f.texto)
        self._poner(self.entry_nit, f.nit_proveedor)
        self.var_empresa.set("TODAS")
        self.var_entidad.set("TODAS")
        self._poner(self.entry_entidad_nombre, f.entidad_nombre)
        self._poner(self.entry_entidad_nit, f.entidad_nit)
        self._poner(self.entry_unspsc, f.unspsc)
        self.var_modalidad.set(f.modalidad)
        for clave, entry in self.ent_av.items():
            self._poner(entry, getattr(f, clave))
        self._aplicar_rango_a_widgets(rango)
        avanzado = any(getattr(f, k) for k in ("valor_min", "valor_max", "estado",
                                                "departamento", "modalidad"))
        self.var_avanzado.set(avanzado)
        self._toggle_avanzado()

    # -------------------------------------------------------------------------
    # DIRECTORIO (storage.Directorio es la unica fuente de verdad)
    # -------------------------------------------------------------------------
    @property
    def empresas(self):
        return self.directorio.nombres_a_nit("empresas")

    @property
    def entidades(self):
        return self.directorio.nombres_a_nit("entidades")

    def _client_nuevo(self):
        return SECOPClient(self.creds)

    def _ventana_directorio_abierta(self):
        v = self._ventana_directorio
        try:
            return v if v is not None and v.winfo_exists() else None
        except TclError:
            return None

    def _abrir_directorio(self, tipo="empresas", id_=None):
        """Abre (o trae al frente) la unica ventana Directorio, en `tipo` y con `id_` seleccionado."""
        v = self._ventana_directorio_abierta()
        if v is None:
            v = self._ventana_directorio = VentanaDirectorio(
                self, self.directorio, self._client_nuevo, self._refrescar_combos, tipo_inicial=tipo)
        else:
            v.deiconify()
            v.lift()
        v.mostrar(tipo, id_)
        return v

    def _refrescar_combos(self):
        """Recarga los combos desde el directorio. La seleccion sigue al registro (por id)
        aunque haya cambiado de nombre; si el registro ya no existe vuelve a TODAS."""
        for tipo, var, refrescar in (("empresas", self.var_empresa, self._refrescar_combo_empresas),
                                     ("entidades", self.var_entidad, self._refrescar_combo_entidades)):
            actual = var.get()
            id_previo = self._ids_combo[tipo].get(actual)
            refrescar()
            if actual == "TODAS":
                continue
            ids = self._ids_combo[tipo]
            if id_previo is not None:
                clave = next((k for k, i in ids.items() if i == id_previo), None)
            else:
                clave = actual if actual in ids else None
            var.set(clave or "TODAS")
        v = self._ventana_directorio_abierta()
        if v is not None:
            v.refrescar()

    def _resolver_nombre_async(self, item_id, nit):
        def trabajo():
            try:
                nombre = resolver_nombre_oficial(self._client_nuevo(), nit)
                # Solo si sigue pendiente y con el mismo NIT: no pisa un nombre escrito a mano
                if not self.directorio.completar_nombre("empresas", item_id, nit, nombre):
                    return
            except (DuplicadoError, KeyError, ValueError, OSError, requests.RequestException):
                return
            self._refrescar_combos_desde_hilo()
        threading.Thread(target=trabajo, daemon=True).start()

    def _refrescar_combos_desde_hilo(self):
        """Pide al hilo de la UI recargar combos y ventana Directorio tras un cambio hecho
        desde un hilo de trabajo."""
        try:
            self.after(0, self._refrescar_combos)
        except (TclError, RuntimeError):            # la app ya se cerro
            pass

    def _seleccionar_en_combo(self, tipo, id_):
        """Recarga el combo de `tipo` y selecciona el registro `id_` por su clave visible
        (los nombres repetidos se muestran como "Nombre (NIT)")."""
        if tipo == "empresas":
            self._refrescar_combo_empresas()
        else:
            self._refrescar_combo_entidades()
        clave = next((k for k, i in self._ids_combo[tipo].items() if i == id_), "TODAS")
        (self.var_empresa if tipo == "empresas" else self.var_entidad).set(clave)

    def _item_seleccionado(self, tipo):
        var = self.var_empresa if tipo == "empresas" else self.var_entidad
        return self.directorio.claves(tipo).get(var.get())

    def _editar_seleccion(self, tipo):
        item = self._item_seleccionado(tipo)
        if not item:
            messagebox.showwarning("Seleccion", "Seleccione un registro del directorio para editar.")
            return None
        return self._abrir_directorio(tipo, item["id"])

    def _guardar_empresa_manual(self):
        nit = self.entry_nit.get().strip()
        if not nit:
            messagebox.showwarning("NIT vacio", "Ingrese un NIT para guardar.")
            return
        if not validar_nit(nit):
            messagebox.showwarning("NIT invalido", "El NIT debe tener entre 8 y 11 digitos.")
            return
        existente = self.directorio.buscar_por_nit("empresas", nit)
        if existente:
            messagebox.showinfo("Existente", f"Empresa '{existente['nombre']}' con NIT {nit} ya esta en el directorio.")
            self._seleccionar_en_combo("empresas", existente["id"])
            return
        try:
            item = self.directorio.agregar("empresas", "", nit)  # nombre pendiente de resolver
        except OSError as e:
            error_guardado(e)
            return
        self._seleccionar_en_combo("empresas", item["id"])
        self.lbl_estado.config(text=f"Empresa {nit} guardada; buscando nombre oficial...")
        self._resolver_nombre_async(item["id"], nit)

    def _eliminar_empresa(self):
        item = self._item_seleccionado("empresas")
        if not item:
            messagebox.showwarning("Seleccion", "Seleccione una empresa del directorio para eliminar.")
            return
        if messagebox.askyesno("Confirmar", f"Eliminar '{item['nombre']}' del directorio?"):
            try:
                self.directorio.eliminar("empresas", item["id"])
            except KeyError:
                pass
            except OSError as e:
                error_guardado(e)
                return
            self._refrescar_combos()
            self.lbl_estado.config(text=f"Empresa '{item['nombre']}' eliminada del directorio.")

    def _guardar_entidad_manual(self):
        nit = self.entry_entidad_nit.get().strip()
        nombre = self.entry_entidad_nombre.get().strip()
        if not nit and not nombre:
            messagebox.showwarning("Datos vacios", "Ingrese al menos nombre o NIT de la entidad.")
            return
        try:
            item = self.directorio.agregar("entidades", nombre, nit)
        except DuplicadoError as e:
            messagebox.showinfo("Existente", f"Entidad '{e.existente['nombre']}' ya esta en el directorio.")
            self._seleccionar_en_combo("entidades", e.existente["id"])
            return
        except OSError as e:
            error_guardado(e)
            return
        self._seleccionar_en_combo("entidades", item["id"])
        self.lbl_estado.config(text=f"Entidad '{item['nombre']}' guardada en el directorio.")

    def _eliminar_entidad(self):
        item = self._item_seleccionado("entidades")
        if not item:
            messagebox.showwarning("Seleccion", "Seleccione una entidad del directorio para eliminar.")
            return
        if messagebox.askyesno("Confirmar", f"Eliminar '{item['nombre']}' del directorio de entidades?"):
            try:
                self.directorio.eliminar("entidades", item["id"])
            except KeyError:
                pass
            except OSError as e:
                error_guardado(e)
                return
            self._refrescar_combos()
            self.lbl_estado.config(text=f"Entidad '{item['nombre']}' eliminada del directorio.")

    def _on_entidad_selected(self, event=None):
        sel = self.var_entidad.get()
        if sel != "TODAS" and sel in self.entidades:
            nit = self.entidades[sel]
            self.entry_entidad_nombre.delete(0, "end")
            self.entry_entidad_nombre.insert(0, sel)
            self.entry_entidad_nit.delete(0, "end")
            if nit:
                self.entry_entidad_nit.insert(0, nit)

    # -------------------------------------------------------------------------
    # PANEL METADATOS
    # -------------------------------------------------------------------------
    def _crear_panel_metadatos(self):
        frm = ttk.LabelFrame(self, text="Estado de fuentes", padding=(10, 4))
        frm.pack(fill="x", padx=10, pady=(0, 4))

        self._meta_labels = {}
        for i, (ds_id, ds_nombre) in enumerate(DATASETS.items()):
            col = i % 4
            row = i // 4
            lbl = ttk.Label(frm, text=f"{ds_nombre}: —", style="Meta.TLabel")
            lbl.grid(row=row, column=col, sticky="w", padx=12, pady=1)
            self._meta_labels[ds_id] = lbl

    # -------------------------------------------------------------------------
    # NOTEBOOK
    # -------------------------------------------------------------------------
    def _crear_notebook(self):
        frm = ttk.LabelFrame(self, text="Resultados", padding=5)
        frm.pack(fill="both", expand=True, padx=10, pady=(0, 4))

        self.notebook = ttk.Notebook(frm)
        self.notebook.pack(fill="both", expand=True)

        self._tab_resumen = ttk.Frame(self.notebook)
        self.notebook.add(self._tab_resumen, text="  Resumen  ")
        self._construir_tabla_resumen(self._tab_resumen)

        self._tabs_detalle = {}

    def _construir_tabla_resumen(self, parent):
        self.tree = ttk.Treeview(parent, columns=COLS_IDS, show="headings", selectmode="extended")

        for col_id, col_titulo, col_ancho in COLUMNAS:
            self.tree.heading(col_id, text=col_titulo,
                              command=lambda c=col_id: self._ordenar(c))
            anchor = "center" if col_id in ("valor", "pagado", "pendiente", "fecha_firma",
                                            "fecha_fin", "sancion", "fuente") else "w"
            self.tree.column(col_id, width=col_ancho, anchor=anchor, minwidth=50)

        self.tree.tag_configure("par",   background="#f7f9fc")
        self.tree.tag_configure("impar", background="white")
        for estado, (bg, fg) in ESTADO_COLORES.items():
            self.tree.tag_configure(estado, background=bg, foreground=fg)
        self.tree.tag_configure("sin contratos", background="#f5f5f5", foreground="#999")
        self.tree.tag_configure("sancion",        background="#ffe0e0", foreground="#c0392b")
        self.tree.tag_configure("con_url", foreground="#1a5490")

        sy = ttk.Scrollbar(parent, orient="vertical",   command=self.tree.yview)
        sx = ttk.Scrollbar(parent, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)

        self.tree.bind("<Double-1>", self._abrir_contrato)
        self.tree.bind("<Motion>",   self._cursor_hover)
        self.copiador = CopiadorTabla(
            self, self.tree, COLS_IDS, [c[1] for c in COLUMNAS],
            lambda: self._filas_por_item,
            lambda msg: self.lbl_estado.config(text=msg),
            extra_menu=self._menu_url,
        )
        self.copiador.instalar()

        ttk.Label(parent,
                  text="Doble clic: abrir en SECOP  |  Ctrl+C: copiar seleccion  |  Clic derecho: copiar/opciones  |  Clic en columna: ordenar",
                  style="Meta.TLabel").grid(row=2, column=0, sticky="w", pady=(2, 0))

        # Controles de paginacion
        self._pag_frm = ttk.Frame(parent)
        self._pag_frm.grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))

        self.btn_first = ttk.Button(self._pag_frm, text="|<<", width=4, command=lambda: self._cambiar_pagina(1))
        self.btn_prev  = ttk.Button(self._pag_frm, text="<",   width=3, command=lambda: self._cambiar_pagina(self._pagina_actual - 1))
        self.lbl_pag   = ttk.Label(self._pag_frm, text="Pagina 1 de 1 (0 registros)", style="Meta.TLabel")
        self.btn_next  = ttk.Button(self._pag_frm, text=">",   width=3, command=lambda: self._cambiar_pagina(self._pagina_actual + 1))
        self.btn_last  = ttk.Button(self._pag_frm, text=">>|", width=4, command=self._ultima_pagina)

        self.btn_first.pack(side="left", padx=2)
        self.btn_prev.pack(side="left", padx=2)
        self.lbl_pag.pack(side="left", padx=6)
        self.btn_next.pack(side="left", padx=2)
        self.btn_last.pack(side="left", padx=2)
        ttk.Label(self._pag_frm, text="Ir a:", style="Meta.TLabel").pack(side="left", padx=(12, 2))
        self.ent_ir = ttk.Entry(self._pag_frm, width=5)
        self.ent_ir.pack(side="left")
        self.ent_ir.bind("<Return>", lambda e: self._ir_a_pagina())
        ttk.Button(self._pag_frm, text="Ir", width=3, command=self._ir_a_pagina).pack(side="left", padx=2)
        self._pag_frm.grid_remove()  # Oculto hasta que haya datos

        self.lbl_rango = ttk.Label(parent, text="", style="Meta.TLabel")
        self.lbl_rango.grid(row=4, column=0, columnspan=2, sticky="w", pady=(2, 0))
        self.tree.tag_configure("nuevo", background="#fff3b0")

    # -------------------------------------------------------------------------
    # PANEL MCP SERVER (HTTPS)
    # -------------------------------------------------------------------------
    def _crear_panel_mcp(self):
        frm = ttk.LabelFrame(self, text="MCP Server", padding=(10, 4))
        frm.pack(fill="x", side="bottom", padx=10, pady=(4, 0))

        self.lbl_mcp_estado = ttk.Label(frm, text="Estado: Detenido", foreground="#c0392b", font=("Segoe UI", 9, "bold"))
        self.lbl_mcp_estado.pack(side="left", padx=(0, 12))

        self.lbl_mcp_url = ttk.Label(frm, text="", foreground="#1565c0", font=("Segoe UI", 9))
        self.lbl_mcp_url.pack(side="left", padx=(0, 12))

        self.btn_mcp_iniciar = ttk.Button(frm, text="Iniciar", command=self._mcp_iniciar)
        self.btn_mcp_iniciar.pack(side="left", padx=2)

        self.btn_mcp_detener = ttk.Button(frm, text="Detener", command=self._mcp_detener, state="disabled")
        self.btn_mcp_detener.pack(side="left", padx=2)

        self.btn_mcp_copiar = ttk.Button(frm, text="Copiar config Claude", command=self._mcp_copiar_config)
        self.btn_mcp_copiar.pack(side="left", padx=2)

    @staticmethod
    def _puerto_libre(puerto):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(("127.0.0.1", puerto)) != 0

    def _cert_dir(self):
        if getattr(sys, "frozen", False):
            return os.path.dirname(sys.executable)
        return os.getcwd()

    def _generar_cert_localhost(self, crt_path, key_path):
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        import datetime
        import ipaddress

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "CO"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "SECOP Local"),
            x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
        ])
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.utcnow() - datetime.timedelta(days=1))
            .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
            .add_extension(
                x509.SubjectAlternativeName([
                    x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
                ]),
                critical=False,
            )
            .sign(key, hashes.SHA256())
        )
        with open(key_path, "wb") as f:
            f.write(key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            ))
        with open(crt_path, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))

    def _instalar_cert_windows(self, crt_path):
        try:
            ps_cmd = (
                f'Start-Process certutil -ArgumentList "-addstore","-f","ROOT","{crt_path}" '
                f'-Verb RunAs -Wait -WindowStyle Hidden'
            )
            subprocess.run(
                ["powershell", "-Command", ps_cmd],
                check=True,
                timeout=30,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            return True
        except Exception:
            return False

    def _mcp_iniciar(self):
        puerto = self.mcp_puerto
        while not self._puerto_libre(puerto):
            resp = messagebox.askyesno(
                "Puerto ocupado",
                f"El puerto {puerto} ya esta en uso.\n\n"
                f"Desea intentar con el puerto {puerto + 1}?"
            )
            if not resp:
                return
            puerto += 1
        self.mcp_puerto = puerto

        cert_dir = self._cert_dir()
        crt_path = os.path.join(cert_dir, "secop-localhost.crt")
        key_path = os.path.join(cert_dir, "secop-localhost.key")

        if not (os.path.exists(crt_path) and os.path.exists(key_path)):
            self.lbl_estado.config(text="MCP: generando certificado SSL...")
            threading.Thread(
                target=self._mcp_generar_y_arrancar,
                args=(puerto, crt_path, key_path),
                daemon=True,
            ).start()
        else:
            self._mcp_lanzar_subprocess(puerto, crt_path, key_path)

    def _mcp_generar_y_arrancar(self, puerto, crt_path, key_path):
        try:
            self._generar_cert_localhost(crt_path, key_path)
        except Exception as e:
            # `e` deja de existir al salir del except: el mensaje se fija como argumento por defecto
            self.after(0, lambda msg=str(e): messagebox.showerror("Certificado SSL", f"No se pudo generar:\n{msg}"))
            self.after(0, self._mcp_reset_ui)
            return

        instalado = self._instalar_cert_windows(crt_path)
        if not instalado:
            self.after(0, lambda: messagebox.showwarning(
                "Certificado SSL",
                "No se pudo instalar automáticamente el certificado.\n\n"
                f"Archivo: {crt_path}\n\n"
                "Para que Claude Desktop confíe en el servidor:\n"
                "1. Haga doble clic en secop-localhost.crt\n"
                "2. Instalar certificado → Equipo local\n"
                "3. Colocar en: Autoridades de certificación raíz de confianza"
            ))

        self.after(0, lambda: self._mcp_lanzar_subprocess(puerto, crt_path, key_path))

    def _mcp_lanzar_subprocess(self, puerto, crt_path, key_path):
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "--mcp-sse-ssl", str(puerto), crt_path, key_path]
        else:
            script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "secop_hibrido.py")
            cmd = [sys.executable, script, "--mcp-sse-ssl", str(puerto), crt_path, key_path]
        try:
            kwargs = {}
            if os.name == "nt":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            self.mcp_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **kwargs,
            )
        except Exception as e:
            messagebox.showerror("Error MCP", f"No se pudo iniciar el servidor MCP:\n{e}")
            self._mcp_reset_ui()
            return

        def check():
            import time
            time.sleep(1.5)
            if self.mcp_process.poll() is not None:
                self.after(0, self._mcp_reset_ui)
                self.after(0, lambda: messagebox.showerror(
                    "MCP Server",
                    "El proceso MCP termino inesperadamente.\n"
                    "Verifique que el certificado SSL este instalado en el almacen de confianza."
                ))
            else:
                url = f"https://localhost:{puerto}/sse"
                self.lbl_mcp_estado.config(text="Estado: Corriendo (HTTPS)", foreground="#27ae60")
                self.lbl_mcp_url.config(text=url)
                self.btn_mcp_iniciar.config(state="disabled")
                self.btn_mcp_detener.config(state="normal")
                self.lbl_estado.config(text=f"MCP Server HTTPS: {url}")
        threading.Thread(target=check, daemon=True).start()
        threading.Thread(target=self._mcp_monitorear, daemon=True).start()

    def _mcp_reset_ui(self):
        self.lbl_mcp_estado.config(text="Estado: Detenido", foreground="#c0392b")
        self.lbl_mcp_url.config(text="")
        self.btn_mcp_iniciar.config(state="normal")
        self.btn_mcp_detener.config(state="disabled")

    def _mcp_detener(self):
        if self.mcp_process:
            self.mcp_process.terminate()
            try:
                self.mcp_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.mcp_process.kill()
                self.mcp_process.wait(timeout=2)
            self.mcp_process = None
        self._mcp_reset_ui()
        self.lbl_estado.config(text="MCP Server detenido.")

    def _mcp_monitorear(self):
        proc = self.mcp_process
        if proc is None:
            return
        try:
            proc.wait()
        except Exception:
            pass
        if self.mcp_process is not None:
            self.after(0, self._mcp_detener)

    def _mcp_copiar_config(self):
        if not self.mcp_process:
            messagebox.showwarning("MCP detenido", "El servidor MCP no esta corriendo.")
            return
        url = f"https://localhost:{self.mcp_puerto}/sse"
        config = (
            '{\n'
            '  "mcpServers": {\n'
            '    "secop": {\n'
            '      "url": "' + url + '"\n'
            '    }\n'
            '  }\n'
            '}\n'
        )
        self.clipboard_clear()
        self.clipboard_append(config)
        self.lbl_estado.config(text="Configuracion Claude Desktop copiada al portapapeles.")

    def _on_closing(self):
        if self.mcp_process:
            self.mcp_process.terminate()
            try:
                self.mcp_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.mcp_process.kill()
        self.destroy()

    # -------------------------------------------------------------------------
    # BARRA DE ESTADO
    # -------------------------------------------------------------------------
    def _crear_barra_estado(self):
        self.lbl_estado = ttk.Label(
            self, text="Listo. Seleccione una empresa o ingrese filtros y presione Consultar.",
            style="Status.TLabel", padding=(10, 3)
        )
        self.lbl_estado.pack(fill="x", side="bottom")

    # -------------------------------------------------------------------------
    # METADATOS ASYNC
    # -------------------------------------------------------------------------
    def _cargar_metadatos_async(self):
        threading.Thread(target=self._cargar_metadatos, daemon=True).start()

    def _cargar_metadatos(self):
        self.after(0, lambda: self.lbl_estado.config(text="Verificando estado de fuentes..."))
        for ds_id in DATASETS:
            try:
                meta = self.client.get_metadata(ds_id)
                updated = meta.get("updatedAt") or meta.get("rowsUpdatedAt", "")
                fecha = formatear_fecha(str(updated)) if updated else "—"
                texto = f"{DATASETS[ds_id]}: {fecha}"
            except Exception:
                texto = f"{DATASETS[ds_id]}: no disponible"
            self.after(0, lambda t=texto, d=ds_id: self._meta_labels[d].config(text=t))
        self.after(0, lambda: self.lbl_estado.config(
            text="Fuentes verificadas. Listo para consultar."))

    # -------------------------------------------------------------------------
    # CONSULTA PRINCIPAL
    # -------------------------------------------------------------------------
    def _iniciar_consulta(self, busqueda_id=None):
        if self._consultando or self._exportando:
            return

        nit_manual = self.entry_nit.get().strip()
        empresa_sel = self.var_empresa.get()

        # La empresa del combo debe seguir en el directorio y tener NIT
        if not nit_manual and empresa_sel != "TODAS":
            nit_sel = self.empresas.get(empresa_sel)
            if nit_sel is None:                 # ya no esta en el directorio
                self._refrescar_combos()
                messagebox.showwarning("Empresa", "La empresa seleccionada ya no esta en el directorio.")
                return
            if not nit_sel:
                messagebox.showwarning("Empresa sin NIT",
                    f"'{empresa_sel}' no tiene NIT en el directorio. Agreguelo con Editar.")
                return

        filtros = self._leer_filtros()          # ya con las fechas del rango calculadas

        if filtros.vacio():                     # las fechas no cuentan como criterio
            messagebox.showwarning("Filtros vacios",
                "Ingrese al menos un criterio: empresa/NIT de proveedor, texto, UNSPSC, "
                "entidad compradora o un filtro avanzado.")
            return
        if nit_manual and not validar_nit(nit_manual):
            messagebox.showwarning("NIT invalido",
                "El NIT ingresado no es valido. Debe contener entre 8 y 11 digitos.")
            return
        if filtros.entidad_nit and not validar_nit(filtros.entidad_nit):
            messagebox.showwarning("NIT entidad invalido", "El NIT de la entidad no es valido.")
            return
        # Fechas escritas a mano, valores, etc.: condiciones() no los valida ni escapa
        errores = filtros.errores()
        if errores:
            messagebox.showwarning("Filtros invalidos", "\n".join(errores))
            return

        # Armar lista de empresas a consultar
        if nit_manual:
            empresas = {nit_manual: nit_manual}
        elif empresa_sel != "TODAS":
            empresas = {empresa_sel: filtros.nit_proveedor}
        else:
            empresas = {None: None}  # Busqueda general

        self._limpiar_tabla()                   # tambien borra las marcas de nuevas
        # _limpiar_tabla() deja _filtros_activos en None: se asigna DESPUES
        self._filtros_activos = {"empresas": empresas, "filtros": filtros}
        self._busqueda_activa = busqueda_id     # se compara con la ejecucion anterior en la pagina 1
        self._filas_por_pagina = int(self.var_tamano.get())
        self._consulta_id += 1
        self._cancelar.clear()
        self._pagina_previa = None
        self._errores = []
        self._omitidos = []
        self._pagina_actual = 1
        self._has_more = False
        self.lbl_rango.config(text=descripcion_rango(filtros)
                              + "  (sanciones y SIRI: sin filtro de fechas)")
        self._set_consultando(True)

        threading.Thread(
            target=self._hilo_consulta,
            args=(empresas, filtros, 0, self._consulta_id),
            daemon=True,
        ).start()

    def _hilo_consulta(self, empresas, filtros, offset, token):
        """Consulta UNA pagina (lazy loading) usando un cliente local para evitar problemas de hilos.
        `token` es el _consulta_id con que se lanzo: si cambio (cancelada o reemplazada), el
        resultado se descarta sin tocar la UI. Una excepcion termina la consulta y se informa."""
        try:
            self._consultar_pagina_en_hilo(empresas, filtros, offset, token)
        except Exception as e:
            # `e` deja de existir al salir del except: el mensaje se calcula aqui
            msg = str(e) or type(e).__name__
            self.after(0, lambda m=msg: self._fallo_consulta(m, token))

    def _fallo_consulta(self, msg, token):
        if token != self._consulta_id:
            return
        self._restaurar_estado_previo()
        self.lbl_estado.config(text=f"Error en la consulta: {msg}")

    def _consultar_pagina_en_hilo(self, empresas, filtros, offset, token):
        # Cliente local para este hilo (requests.Session no es thread-safe)
        client_local = SECOPClient(self.creds)
        query_local = SECOPQuery(client_local)

        filas = []
        detalle = {}
        errores = []
        has_more_global = False
        nuevas_empresas = []
        nuevas_entidades = []
        consultadas = []                    # [(nit, nombre encontrado)] para el directorio

        for nombre, nit in empresas.items():
            f, d, e, has_more = query_local.consultar_pagina(
                nombre=nombre,
                nit=nit,
                filtros=filtros,
                offset=offset,
                page_size=self._filas_por_pagina,
                on_progress=lambda msg: self.after(0, lambda m=msg: self._progreso_consulta(m, token))
            )
            if token != self._consulta_id:          # cancelada o reemplazada: no tocar nada
                return
            filas.extend(f)
            errores.extend(e)
            has_more_global = has_more_global or has_more
            for tab_nombre, tab_data in d.items():
                if tab_nombre not in detalle:
                    detalle[tab_nombre] = []
                detalle[tab_nombre].extend(tab_data)

            # Directorio: anotar la empresa consultada (solo en primera pagina)
            if offset == 0 and nit:
                nombre_a_guardar = None
                for row in f:
                    if row.get("estado") != "SIN CONTRATOS":
                        cand = row.get("empresa", "")
                        if cand and cand != "—" and cand != nit:
                            nombre_a_guardar = cand
                            break
                consultadas.append((nit, nombre_a_guardar))

        if token != self._consulta_id:
            return
        # Solo una consulta vigente actualiza el directorio; si el disco falla, los
        # resultados se muestran igual y se avisa en la barra de estado.
        aviso_dir = ""
        if offset == 0:
            try:
                nuevas_empresas, nuevas_entidades = self._registrar_consulta_en_directorio(
                    consultadas, filtros, filas)
            except OSError as e:
                aviso_dir = f"No se pudo actualizar el directorio: {e}"
        # Los omitidos viajan con el resultado: el hilo no escribe estado de la UI
        omitidos = list(query_local.omitidos)

        def entregar():
            # Se revisa de nuevo en el hilo de la UI: una cancelacion pudo llegar despues
            # de la comprobacion anterior y antes de que este callback se ejecute.
            if token != self._consulta_id:
                return
            self._mostrar_resultados_pagina(
                filas, detalle, errores, has_more_global, offset,
                nuevas_empresas, nuevas_entidades, omitidos)
            if aviso_dir:
                self.lbl_estado.config(text=self.lbl_estado.cget("text") + "  |  " + aviso_dir)
        self.after(0, entregar)

    def _registrar_consulta_en_directorio(self, consultadas, filtros, filas):
        """(Hilo de trabajo) Marca la ultima consulta de los registros existentes, completa
        nombres pendientes y devuelve (nuevas_empresas, nuevas_entidades) para agregarlas
        desde la UI. Puede lanzar OSError si el directorio no se puede escribir."""
        nuevas_empresas, nuevas_entidades = [], []
        toco = False
        for nit, nombre_a_guardar in consultadas:
            existente = self.directorio.buscar_por_nit("empresas", nit)
            if existente:
                self.directorio.marcar_consulta("empresas", existente["id"])
                if nombre_a_guardar:
                    try:
                        self.directorio.completar_nombre("empresas", existente["id"], nit,
                                                         nombre_a_guardar)
                    except (DuplicadoError, KeyError):
                        pass
                toco = True
            else:
                nuevas_empresas.append((nombre_a_guardar or nit, nit))

        if filtros.entidad_nombre or filtros.entidad_nit:
            ent_nit = filtros.entidad_nit or ""
            existente = self.directorio.buscar_por_nit("entidades", ent_nit) if ent_nit else None
            if existente is None:
                nombre_ent = (filtros.entidad_nombre or "").lower()
                existente = next((e for e in self.directorio.listar("entidades")
                                  if e["nombre"].lower() == nombre_ent), None)
            if existente:
                self.directorio.marcar_consulta("entidades", existente["id"])
                toco = True
            elif filas and any(row.get("estado") != "SIN CONTRATOS" for row in filas):
                nuevas_entidades.append((filtros.entidad_nombre or ent_nit, ent_nit))
        if toco:
            self._refrescar_combos_desde_hilo()
        return nuevas_empresas, nuevas_entidades

    def _progreso_consulta(self, msg, token):
        if token == self._consulta_id:
            self.lbl_estado.config(text=msg)

    def _mostrar_resultados_pagina(self, filas, detalle, errores, has_more, offset,
                                    nuevas_empresas, nuevas_entidades, omitidos=None):
        self._errores.extend(errores)
        self._has_more = has_more
        self._pagina_detalle = detalle          # solo la pagina actual; no se acumula
        if omitidos is not None:                # None: pagina servida desde la cache
            self._omitidos = omitidos
        self._tamano_previo = None              # un cambio de tamano ya no se puede deshacer

        # Actualizar el directorio (un fallo de disco no impide mostrar la pagina)
        aviso_dir = ""
        if nuevas_empresas or nuevas_entidades:
            aviso_dir = self._actualizar_historiales(nuevas_empresas, nuevas_entidades)

        # Las ultimas paginas se guardan para revisitarlas sin consultar la API; una pagina
        # con errores puede estar incompleta: no se guarda y se vuelve a pedir al revisitarla
        if not errores:
            self._cache.guardar(self._pagina_actual, (filas, detalle, [], has_more))

        # Busqueda guardada: solo la pagina 1 se compara con la ejecucion anterior, y antes
        # de renderizar para que las marcas de nuevas esten listas
        n_nuevos = 0
        if offset == 0:
            if errores and self._busqueda_activa:
                # pagina incompleta: compararla daria falsas novedades la proxima vez
                self._busqueda_activa = None
                aviso_dir = "  |  ".join(filter(None, [
                    aviso_dir, "Busqueda guardada sin registrar (hubo errores en la consulta)"]))
            try:
                n_nuevos = self._procesar_busqueda_guardada(filas)
            except (OSError, KeyError) as e:    # se muestran los resultados igual
                n_nuevos = len(self._nuevos)
                aviso_dir = "  |  ".join(filter(None, [
                    aviso_dir, f"No se pudo registrar la ejecucion de la busqueda: {e}"]))

        # Renderizar pagina
        self._filas = filas  # Solo la pagina actual en memoria de UI
        self._renderizar_tabla_lazy(filas, offset)
        self._reconstruir_tabs_detalle(detalle)

        self._set_consultando(False)
        self._actualizar_barra_paginacion()

        # Status
        total_visible = len([f for f in filas if f["fuente"] != "—"])
        sanciones = len([f for f in filas if f["sancion"] == "SI"])
        msg = f"Pagina {self._pagina_actual} cargada: {total_visible} registros mostrados"
        if n_nuevos:
            msg += f"  |  {n_nuevos} NUEVO(S) desde la ultima ejecucion"
        if self._filtros_activos:
            msg += "  |  " + descripcion_rango(self._filtros_activos["filtros"])
        if self._has_more:
            msg += "  |  Hay mas paginas disponibles"
        if sanciones:
            msg += f"  |  ATENCION: {sanciones} sanciones/inhabilidades"
        if self._errores:
            msg += f"  |  {len(self._errores)} errores"
        if self._omitidos:
            msg += "  |  Omitidos (filtro no soportado): " + ", ".join(self._omitidos)
        if aviso_dir:
            msg += "  |  " + aviso_dir
        self.lbl_estado.config(text=msg)

        if errores and offset == 0:
            self._mostrar_errores()
        if offset == 0 and self._conteos is None and self._filtros_activos:
            self._iniciar_conteo()

    def _actualizar_historiales(self, nuevas_empresas, nuevas_entidades):
        """Agrega empresas/entidades descubiertas al directorio y refresca los combos.
        Devuelve un aviso (texto) si el directorio no se pudo escribir; si no, ""."""
        n_emp = n_ent = 0
        aviso = ""
        try:
            for nombre, nit in nuevas_empresas:
                try:
                    self.directorio.agregar("empresas", nombre, nit, nombre_resuelto=(nombre != nit))
                    n_emp += 1
                except (DuplicadoError, ValueError):
                    pass
            for nombre, nit in nuevas_entidades:
                try:
                    self.directorio.agregar("entidades", nombre, nit)
                    n_ent += 1
                except (DuplicadoError, ValueError):
                    pass
        except OSError as e:
            aviso = f"No se pudo actualizar el directorio: {e}"
        if n_emp or n_ent:
            self._refrescar_combos()
            msgs = []
            if n_emp:
                msgs.append(f"{n_emp} empresa(s) agregada(s)")
            if n_ent:
                msgs.append(f"{n_ent} entidad(es) agregada(s)")
            self.lbl_estado.config(text="Directorio actualizado: " + ", ".join(msgs))
        return aviso

    @staticmethod
    def _formatear_detalle(col, valor):
        if isinstance(valor, (dict, list)):
            return valor_visible(valor)
        v = "" if valor is None else str(valor)
        low = col.lower()
        if "valor" in low and v and v.replace(".", "").isdigit():
            return formatear_pesos(v)
        if "fecha" in low:
            return formatear_fecha(v)
        return v

    def _construir_tab_detalle(self, parent, nombre, data):
        """Crea un Treeview con todas las columnas del dataset crudo."""
        if not data:
            ttk.Label(parent, text="Sin datos.", style="Meta.TLabel").pack(padx=10, pady=10)
            return

        # Columnas: privadas (_empresa, _nit) al final; las demas primero.
        # Union de claves porque Socrata omite las columnas nulas.
        todas = columnas_union(data)
        cols = [c for c in todas if not c.startswith("_")] + [c for c in todas if c.startswith("_")]
        titulos = [c.replace("_", " ").strip().title() for c in cols]

        tree = ttk.Treeview(parent, columns=cols, show="headings", selectmode="extended")
        for c, titulo in zip(cols, titulos):
            tree.heading(c, text=titulo)
            tree.column(c, width=130, anchor="w", minwidth=60)

        sy = ttk.Scrollbar(parent, orient="vertical",   command=tree.yview)
        sx = ttk.Scrollbar(parent, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)

        tree.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)

        tree.tag_configure("par",   background="#f7f9fc")
        tree.tag_configure("impar", background="white")

        filas_por_item = {}
        for i, row in enumerate(data):
            fila = {c: self._formatear_detalle(c, row.get(c)) for c in cols}
            vals = [texto_pantalla(fila[c], 120) for c in cols]
            tag = "par" if i % 2 == 0 else "impar"
            item = tree.insert("", "end", values=vals, tags=(tag,))
            filas_por_item[item] = fila

        CopiadorTabla(self, tree, cols, titulos, lambda: filas_por_item,
                      lambda msg: self.lbl_estado.config(text=msg)).instalar()

        ttk.Label(parent,
                  text=f"{len(data)} registros  |  datos crudos del dataset  |  Ctrl+C copia la seleccion",
                  style="Meta.TLabel").grid(row=2, column=0, sticky="w", pady=(2, 0))

    def _renderizar_tabla_lazy(self, filas, offset):
        """Renderiza SOLO la pagina actual."""
        self.tree.delete(*self.tree.get_children())
        self._url_map = {}
        self._filas_por_item = {}

        for i, fila in enumerate(filas, start=offset):
            vals = [texto_pantalla(fila.get(c, ""), 80) if c == "objeto" else fila.get(c, "")
                    for c in COLS_IDS]
            tags = []
            if fila.get("sancion") == "SI":
                tags.append("sancion")
            else:
                estado_tag = tag_para_estado(fila.get("estado", ""))
                if estado_tag != "par":
                    tags.append(estado_tag)
                else:
                    tags.append("par" if i % 2 == 0 else "impar")
            if identificar_fila(fila) in self._nuevos:
                # Una sancion nueva sigue en rojo: "sancion" se creo antes que "nuevo" y los
                # tags creados primero tienen prioridad; el color de estado si cede al amarillo
                tags = ["sancion", "nuevo"] if fila.get("sancion") == "SI" else ["nuevo"]
            if fila.get("url"):
                tags.append("con_url")
            item = self.tree.insert("", "end", values=vals, tags=tuple(tags))
            self._filas_por_item[item] = fila
            if fila.get("url"):
                self._url_map[item] = fila["url"]

    def _cambiar_pagina(self, pagina, forzar=False):
        if not self._filtros_activos or self._consultando or self._exportando or pagina < 1:
            return
        if pagina == self._pagina_actual and not forzar:
            return
        if self._total_paginas and pagina > self._total_paginas:
            return
        self._pagina_previa = self._pagina_actual
        self._pagina_actual = pagina
        offset = (pagina - 1) * self._filas_por_pagina
        en_cache = self._cache.obtener(pagina)
        if en_cache is not None:
            filas, detalle, _errores, has_more = en_cache
            self._errores = []                  # los de otra pagina no aplican a esta
            self._mostrar_resultados_pagina(filas, detalle, [], has_more, offset, [], [])
            return
        self._errores = []
        self._set_consultando(True)
        filtros = self._filtros_activos
        threading.Thread(
            target=self._hilo_consulta,
            args=(filtros["empresas"], filtros["filtros"], offset, self._consulta_id),
            daemon=True,
        ).start()

    def _ultima_pagina(self):
        if self._total_paginas:
            self._cambiar_pagina(self._total_paginas)

    def _ir_a_pagina(self):
        try:
            pagina = int(self.ent_ir.get().strip())
        except ValueError:
            messagebox.showwarning("Ir a pagina", "Escriba un numero de pagina.")
            return
        if self._total_paginas:
            pagina = min(pagina, self._total_paginas)
        self._cambiar_pagina(max(1, pagina))

    def _on_tamano(self):
        nuevo = int(self.var_tamano.get())
        if nuevo == self._filas_por_pagina:
            return
        recargar = bool(self._filtros_activos and not self._consultando)
        # Si la recarga se cancela o falla se vuelve al tamano, la pagina y la cache anteriores
        self._tamano_previo = (self._filas_por_pagina, self._cache) if recargar else None
        self._filas_por_pagina = nuevo
        self._cache = CachePaginas()
        if self._conteos:
            self._total_paginas = total_paginas(self._conteos, nuevo)
        if recargar:
            self._cambiar_pagina(1, forzar=True)

    def _actualizar_barra_paginacion(self):
        pag, total = self._pagina_actual, self._total_paginas
        hay_siguiente = self._has_more or bool(total and pag < total)
        if pag > 1 or hay_siguiente or (total and total > 1):
            self._pag_frm.grid()
        else:
            self._pag_frm.grid_remove()
        if total:
            aprox = f"{total_registros(self._conteos):,}".replace(",", ".")
            pos = f"{pag} de {total} (≈{aprox} registros)"
        else:
            pos = f"{pag}{'+' if self._has_more else ''}"
        reales = sum(1 for f in self._filas if f.get("fuente") != "—")   # sin la fila de relleno
        self.lbl_pag.config(
            text=f"Pagina {pos}  |  hasta {self._filas_por_pagina} por dataset  |  {reales} filas")
        self.btn_first.config(state="normal" if pag > 1 else "disabled")
        self.btn_prev.config(state="normal" if pag > 1 else "disabled")
        self.btn_next.config(state="normal" if hay_siguiente else "disabled")
        self.btn_last.config(state="normal" if total and pag < total else "disabled")

    # ---- total real en segundo plano -------------------------------------
    def _iniciar_conteo(self):
        if self._contando == self._consulta_id:     # ya hay un conteo en curso para esta consulta
            return
        self._contando = self._consulta_id
        f = self._filtros_activos
        threading.Thread(target=self._hilo_contar,
                         args=(f["empresas"], f["filtros"], self._consulta_id),
                         daemon=True).start()

    def _hilo_contar(self, empresas, filtros, token):
        query = SECOPQuery(SECOPClient(self.creds))
        total = {}
        try:
            for nombre, nit in empresas.items():
                for ds, n in query.contar(nombre, nit, filtros).items():
                    total[ds] = total.get(ds, 0) + n
        except Exception:
            total = None               # sin total: se conserva la paginacion "estimada" (N+)
        self.after(0, lambda: self._aplicar_conteos(total, token))

    def _aplicar_conteos(self, conteos, token):
        """conteos=None: el conteo fallo (se podra reintentar)."""
        if token == self._contando:
            self._contando = None
        if token != self._consulta_id or conteos is None or not self._filtros_activos:
            return
        self._conteos = conteos
        self._total_paginas = total_paginas(conteos, self._filas_por_pagina)
        self._actualizar_barra_paginacion()

    # ---- pestañas de detalle: se reconstruyen por pagina -------------------
    def _destruir_tabs_detalle(self):
        for frm in list(self._tabs_detalle.values()):
            self.notebook.forget(frm)
            frm.destroy()              # forget() solo oculta: sin destroy() quedan en memoria
        self._tabs_detalle.clear()

    def _reconstruir_tabs_detalle(self, detalle):
        seleccionada = self.notebook.select()
        actual = self.notebook.tab(seleccionada, "text").strip() if seleccionada else ""
        self._destruir_tabs_detalle()
        for tab_nombre, tab_data in detalle.items():
            frm = ttk.Frame(self.notebook)
            self.notebook.add(frm, text=f"  {tab_nombre}  ")
            self._tabs_detalle[tab_nombre] = frm
            self._construir_tab_detalle(frm, tab_nombre, tab_data)
        destino = self._tabs_detalle.get(actual)
        self.notebook.select(destino if destino is not None else self._tab_resumen)

    # ---- cancelacion -------------------------------------------------------
    def _cancelar_operacion(self):
        if self._exportando:
            # Solo se cancela la exportacion: la consulta y su pagina siguen validas.
            # El hilo lo confirma con _exportacion_cancelada() y borra lo escrito.
            self._cancelar.set()
            self.lbl_estado.config(text="Cancelando exportacion...")
            return
        self._consulta_id += 1         # lo que llegue de una consulta en vuelo se descarta
        self._cancelar.set()           # las exportaciones largas revisan este evento
        if self._consultando:
            self._restaurar_estado_previo()
        self.lbl_estado.config(text="Operacion cancelada.")
        # Un conteo en vuelo llevaba el token anterior y se descartara: se relanza con el nuevo
        if self._filtros_activos and self._conteos is None:
            self._iniciar_conteo()

    def _restaurar_estado_previo(self):
        """Deshace el cambio de pagina (y de tamano) de una carga cancelada o fallida."""
        if self._pagina_previa:
            self._pagina_actual = self._pagina_previa
        if self._tamano_previo:
            self._filas_por_pagina, self._cache = self._tamano_previo
            self.var_tamano.set(str(self._filas_por_pagina))
            if self._conteos:
                self._total_paginas = total_paginas(self._conteos, self._filas_por_pagina)
        self._tamano_previo = None
        if not self._filas:
            self._filtros_activos = None
        self._set_consultando(False)
        if self._filtros_activos:
            self._actualizar_barra_paginacion()

    def _ordenar(self, col):
        # En lazy loading solo se ordena la pagina visible, por tipo real
        inverso = self._orden_inverso.get(col, False)
        filas_ordenadas = ordenar_filas(self._filas, col, inverso)
        self._orden_inverso[col] = not inverso
        self._renderizar_tabla_lazy(filas_ordenadas, (self._pagina_actual - 1) * self._filas_por_pagina)

    # -------------------------------------------------------------------------
    # BUSQUEDAS GUARDADAS Y NOVEDADES
    # -------------------------------------------------------------------------
    def _procesar_busqueda_guardada(self, filas):
        """Marca como NUEVAS las filas ausentes en la ejecucion anterior y registra esta.
        Puede lanzar OSError si el directorio no se puede escribir (las marcas ya quedan)."""
        busqueda_id, self._busqueda_activa = self._busqueda_activa, None
        if not busqueda_id:                          # p. ej. al volver a la pagina 1 desde la cache
            return len(self._nuevos)
        self._nuevos = set()
        b = self.directorio.obtener_busqueda(busqueda_id)
        if b is None:
            return 0
        reales = [f for f in filas if f.get("fuente") != "—"]
        if b["ultima_ejecucion"]:                    # la primera vez no se marca nada
            self._nuevos = {identificar_fila(f) for f in marcar_nuevas(reales, b["ultimos_ids"])}
        self.directorio.registrar_ejecucion(busqueda_id, [identificar_fila(f) for f in reales])
        return len(self._nuevos)

    def _guardar_busqueda(self):
        filtros = self._leer_filtros()
        if filtros.vacio():
            messagebox.showwarning("Busqueda vacia", "Defina al menos un criterio antes de guardar.")
            return
        problemas = self._problemas_filtros(filtros)    # fechas, valores y NIT (manual o entidad)
        if problemas:
            messagebox.showwarning("Filtros invalidos", "\n".join(problemas))
            return
        nombre = simpledialog.askstring("Guardar busqueda", "Nombre de la busqueda:", parent=self)
        if not nombre or not nombre.strip():
            return
        nombre = nombre.strip()
        existente = self.directorio.buscar_busqueda_por_nombre(nombre)
        if existente and not messagebox.askyesno(
                "Sobrescribir busqueda",
                f"Ya existe la busqueda '{existente['nombre']}'. ¿Reemplazarla?\n\n"
                "Su historial de novedades se reinicia: la proxima ejecucion no marcara "
                "nada como nuevo.", parent=self):
            return
        try:
            # Se guarda el MODO del rango (p. ej. "ultimo_anio"), no las fechas calculadas
            self.directorio.guardar_busqueda(nombre, filtros.a_dict(incluir_fechas=False),
                                             self._leer_rango())
        except OSError as e:
            error_guardado(e)
            return
        self._refrescar_combo_busquedas()
        self.var_busqueda.set(nombre)
        self.lbl_estado.config(text=f"Busqueda '{nombre}' guardada.")

    def _busqueda_elegida(self):
        b = self.directorio.buscar_busqueda_por_nombre(self.var_busqueda.get())
        if b is None:
            messagebox.showwarning("Busqueda", "Seleccione una busqueda guardada.")
        return b

    def _ejecutar_busqueda_guardada(self):
        if self._consultando or self._exportando:
            return
        b = self._busqueda_elegida()
        if b is None:
            return
        try:
            filtros = Filtros.desde_dict(b.get("filtros"))
            self._cargar_filtros_en_widgets(filtros, b.get("rango"))
        except (AttributeError, TypeError):          # datos guardados danados
            messagebox.showwarning("Busqueda", f"La busqueda '{b['nombre']}' esta danada.")
            return
        self.var_tamano.set(str(PAGINA_NOVEDADES))   # tamano fijo: comparacion de novedades consistente
        self._iniciar_consulta(busqueda_id=b["id"])
        if not self._consultando:                    # no arranco (filtros invalidos): tamano previo
            self.var_tamano.set(str(self._filas_por_pagina))

    def _eliminar_busqueda(self):
        b = self._busqueda_elegida()
        if b is None or not messagebox.askyesno("Confirmar", f"Eliminar la busqueda '{b['nombre']}'?"):
            return
        try:
            self.directorio.eliminar_busqueda(b["id"])
        except KeyError:
            pass
        except OSError as e:
            error_guardado(e)
            return
        self.var_busqueda.set("")
        self._refrescar_combo_busquedas()

    def _ejecutar_todas(self):
        if self._consultando or self._exportando:
            return
        busquedas = [dict(b) for b in self.directorio.listar_busquedas()]   # copia para el hilo
        if not busquedas:
            messagebox.showinfo("Busquedas", "No hay busquedas guardadas.")
            return
        self._cancelar.clear()
        self._pagina_previa = None                   # no hay cambio de pagina que deshacer
        self._set_consultando(True)
        threading.Thread(target=self._hilo_ejecutar_todas,
                         args=(busquedas, self._consulta_id), daemon=True).start()

    def _ejecucion_cancelada(self, token):
        return token != self._consulta_id or self._cancelar.is_set()

    @staticmethod
    def _problemas_filtros(filtros):
        """Lo que impide consultar con `filtros` (fechas, valores y NIT); [] si nada."""
        problemas = list(filtros.errores())
        if filtros.nit_proveedor and not validar_nit(filtros.nit_proveedor):
            problemas.append("NIT de proveedor invalido (8 a 11 digitos).")
        if filtros.entidad_nit and not validar_nit(filtros.entidad_nit):
            problemas.append("NIT de entidad invalido (8 a 11 digitos).")
        return problemas

    def _hilo_ejecutar_todas(self, busquedas, token):
        """(Hilo de trabajo) Ejecuta la pagina 1 de cada busqueda y cuenta las novedades.
        `token`: si _consulta_id cambia (Cancelar) se detiene y no registra ni toca la UI.
        Pase lo que pase, el final se entrega a la UI (que se libera si el token sigue vigente)."""
        resumen = []
        try:
            query = SECOPQuery(SECOPClient(self.creds))
            for b in busquedas:
                if self._ejecucion_cancelada(token):
                    return
                nombre = str(b.get("nombre") or "?")
                self.after(0, lambda n=nombre: self._progreso_consulta(f"Ejecutando '{n}'...", token))
                try:
                    # el rango se recalcula a "hoy" en cada ejecucion; lo guardado se valida
                    filtros = con_rango(Filtros.desde_dict(b.get("filtros")), b.get("rango"))
                    problemas = self._problemas_filtros(filtros) or (
                        ["sin criterios"] if filtros.vacio() else [])
                    if problemas:
                        resumen.append(f"{nombre}: filtros invalidos, no se ejecuto "
                                       f"({'; '.join(problemas)})")
                        continue
                    # Igual que "Ejecutar" (pone el NIT en el campo manual): mismas filas e ids
                    nit = filtros.nit_proveedor or None
                    filas, _, errs, _ = query.consultar_pagina(nit, nit, filtros, offset=0,
                                                               page_size=PAGINA_NOVEDADES)
                    if errs:                         # pagina incompleta: no se registra
                        resumen.append(f"{nombre}: error ({errs[0]}); no se registro")
                        continue
                    reales = [f for f in filas if f.get("fuente") != "—"]
                    primera = not b.get("ultima_ejecucion")
                    nuevos = 0 if primera else len(marcar_nuevas(reales, b.get("ultimos_ids") or []))
                    if self._ejecucion_cancelada(token):     # Cancelar llego durante la consulta
                        return
                    self.directorio.registrar_ejecucion(b["id"], [identificar_fila(f) for f in reales])
                    resumen.append(f"{nombre}: " + ("primera ejecucion registrada"
                                                    if primera else f"{nuevos} nuevo(s)"))
                except Exception as e:               # datos corruptos, red, disco o busqueda borrada
                    resumen.append(f"{nombre}: error ({str(e) or type(e).__name__})")
        except Exception as e:                       # p. ej. no se pudo crear el cliente
            resumen.append(f"Error: {str(e) or type(e).__name__}")
        finally:
            self.after(0, lambda: self._fin_ejecutar_todas(resumen, token))

    def _fin_ejecutar_todas(self, resumen, token):
        if token != self._consulta_id:               # cancelada: la UI ya se restauro
            return
        self._set_consultando(False)
        self.lbl_estado.config(text="Busquedas guardadas ejecutadas.")
        messagebox.showinfo("Novedades de busquedas guardadas", "\n".join(resumen))

    def _aviso_inicio(self):
        if self.directorio.aviso:
            messagebox.showwarning("Directorio", self.directorio.aviso)
            self.directorio.aviso = ""               # se avisa una sola vez
        n = len(self.directorio.listar_busquedas())
        if n and messagebox.askyesno(
                "Busquedas guardadas",
                f"Hay {n} busqueda(s) guardada(s). ¿Ejecutarlas ahora para ver novedades?"):
            self._ejecutar_todas()

    # -------------------------------------------------------------------------
    # ACCIONES EN TABLA RESUMEN
    # -------------------------------------------------------------------------
    def _abrir_contrato(self, event=None):
        sel = self.tree.selection()
        if not sel:
            return
        url = self._url_map.get(sel[0], "")
        if url:
            webbrowser.open(url, new=2)
            self.lbl_estado.config(text=f"Abriendo: {url}")
        else:
            self.lbl_estado.config(text="Este registro no tiene URL directa en SECOP II.")

    def _menu_url(self, menu, item):
        url = self._url_map.get(item, "")
        if not url:
            return
        menu.add_command(label="Abrir en navegador",
                         command=lambda: webbrowser.open(url, new=2))
        menu.add_command(label="Copiar URL",
                         command=lambda: (self.clipboard_clear(),
                                          self.clipboard_append(url),
                                          self.lbl_estado.config(text="URL copiada al portapapeles.")))
        menu.add_separator()

    def _cursor_hover(self, event):
        item = self.tree.identify_row(event.y)
        if item and item in self._url_map:
            self.tree.config(cursor="hand2")
            url = self._url_map[item]
            self.lbl_estado.config(text=f"Doble clic para abrir: {url}")
        else:
            self.tree.config(cursor="")

    # -------------------------------------------------------------------------
    # ERRORES
    # -------------------------------------------------------------------------
    def _mostrar_errores(self):
        top = __import__("tkinter").Toplevel(self)
        top.title("Errores de consulta")
        top.geometry("600x300")
        txt = scrolledtext.ScrolledText(top, font=("Consolas", 9), wrap="word")
        txt.pack(fill="both", expand=True, padx=8, pady=8)
        txt.insert("end", "\n".join(self._errores))
        txt.config(state="disabled")

    # -------------------------------------------------------------------------
    # ESTADO UI
    # -------------------------------------------------------------------------
    def _set_consultando(self, activo):
        self._consultando = activo
        self._actualizar_controles()

    def _set_exportando(self, activo):
        self._exportando = activo
        self._actualizar_controles()

    def _actualizar_controles(self):
        """Consulta y exportacion son excluyentes: los controles dependen de ambas."""
        activo = self._consultando or self._exportando
        state = "disabled" if activo else "normal"
        self.btn_consultar.config(state=state,
                                  text="Consultando..." if self._consultando else "Consultar")
        self.btn_exportar.config(state=state)
        self.btn_limpiar.config(state=state)
        self.combo_empresa.config(state="disabled" if activo else "readonly")
        self.combo_entidad.config(state="disabled" if activo else "readonly")
        self.entry_nit.config(state=state)
        self.entry_unspsc.config(state=state)
        self.entry_entidad_nombre.config(state=state)
        self.entry_entidad_nit.config(state=state)
        self.entry_texto.config(state=state)
        self.ent_desde.config(state=state)
        self.ent_hasta.config(state=state)
        self.combo_rango.config(state="disabled" if activo else "readonly")
        for btn in list(self._btns_busqueda.values()) + [self.btn_buscar_empresa]:
            btn.config(state=state)
        self.btn_cancelar.config(state="normal" if activo else "disabled")
        self.combo_tamano.config(state="disabled" if activo else "readonly")
        if activo:
            self.progress.grid()
            self.progress.start(12)
        else:
            self.progress.stop()
            self.progress.grid_remove()

    # -------------------------------------------------------------------------
    # EXPORTACION: pagina/seleccion desde memoria; "todos" pagina a pagina a disco
    # -------------------------------------------------------------------------
    def _exportar(self):
        if self._consultando or self._exportando:
            return
        if not self._filas and not self._filtros_activos:
            messagebox.showwarning("Sin datos", "Realice una consulta primero.")
            return
        total = total_registros(self._conteos) if self._conteos else None
        previo = self.directorio.preferencia("exportar", {})
        dlg = DialogoExportar(self, COLUMNAS_EXPORTACION, len(self._filas),
                              len(self.tree.selection()), previo, total_estimado=total)
        dlg.wait_window()
        opc = dlg.resultado
        if not opc:
            return
        try:
            self.directorio.guardar_preferencia("exportar", opc)
        except OSError:                         # solo es una comodidad: se exporta igual
            self.lbl_estado.config(text="No se pudo recordar la eleccion de exportacion.")

        if opc["alcance"] == "todos" and requiere_confirmacion(total):
            if total is None:
                msg = ("No se pudo estimar el total de registros; la exportacion completa "
                       "puede ser muy grande.\n\n¿Continuar?")
            else:
                msg = (f"Se exportaran aproximadamente {total:,} registros "
                       f"(mas de {UMBRAL_CONFIRMACION:,}).\n\n¿Continuar?").replace(",", ".")
            if not messagebox.askyesno("Confirmar exportacion", msg, parent=self):
                return

        sello = f"{datetime.now():%Y%m%d_%H%M}"
        fmt = opc["formato"]
        if fmt == "csv_dataset":
            destino = filedialog.askdirectory(parent=self)
        else:
            ext = {"xlsx": ".xlsx", "csv": ".csv", "json": ".json"}[fmt]
            destino = filedialog.asksaveasfilename(
                parent=self, defaultextension=ext, filetypes=[(fmt.upper(), "*" + ext)],
                initialfile=f"SECOP_{sello}{ext}")
        if not destino:
            return
        titulos = {c[0]: c[1] for c in COLUMNAS_EXPORTACION}
        self._cancelar.clear()         # el evento es compartido con la cancelacion de consultas
        self._set_exportando(True)
        if opc["alcance"] == "todos":
            threading.Thread(target=self._hilo_exportar,
                             args=(opc, destino, titulos, sello, self._filtros_activos),
                             daemon=True).start()
            return
        filas = self._filas if opc["alcance"] == "pagina" else self.copiador.filas_seleccionadas()
        self._escribir_exportacion(opc, iter([(filas, {})]), destino, titulos, sello)

    def _hilo_exportar(self, opc, destino, titulos, sello, filtros):
        """Descarga pagina a pagina directo a disco (nada se acumula en memoria)."""
        query = SECOPQuery(SECOPClient(self.creds))
        errores = []                   # paginas de algun dataset que fallaron: se avisan al final

        def paginas():
            for nombre, nit in filtros["empresas"].items():
                yield from query.iterar_paginas(
                    nombre, nit, filtros["filtros"], page_size=500,
                    on_progress=lambda m: self.after(0, lambda t=m: self.lbl_estado.config(text=t)),
                    cancelado=self._cancelar.is_set)
                errores.extend(query.ultimos_errores)
        self._escribir_exportacion(opc, paginas(), destino, titulos, sello, errores)

    def _escribir_exportacion(self, opc, paginas, destino, titulos, sello, errores=None):
        try:
            archivos, n = exportar_incremental(
                opc["formato"], opc["columnas"], destino, paginas, titulos,
                opc.get("delimitador", ","), sello, self._cancelar.is_set)
        except ExportacionCancelada:
            self.after(0, self._exportacion_cancelada)
            return
        except Exception as e:
            msg = str(e) or type(e).__name__   # `e` no existe cuando corra el lambda
            self.after(0, lambda m=msg: self._exportacion_error(m))
            return
        self.after(0, lambda: self._exportacion_ok(archivos, n, errores))

    def _exportacion_ok(self, archivos, n, errores=None):
        self._set_exportando(False)
        self.lbl_estado.config(text=f"Exportacion completada: {n} registros.")
        texto = "Archivo(s) guardado(s):\n" + "\n".join(archivos)
        if errores:
            texto += (f"\n\nATENCION: se registraron {len(errores)} error(es) durante la descarga; "
                      "el archivo puede estar incompleto:\n" + "\n".join(errores[:5]))
            messagebox.showwarning("Exportacion incompleta", texto)
            return
        messagebox.showinfo("Exportacion", texto)

    def _exportacion_error(self, mensaje):
        self._set_exportando(False)
        messagebox.showerror("Error de exportacion", mensaje)

    def _exportacion_cancelada(self):
        self._set_exportando(False)
        self.lbl_estado.config(text="Exportacion cancelada; no se guardo ningun archivo.")

    # -------------------------------------------------------------------------
    # LIMPIAR
    # -------------------------------------------------------------------------
    def _limpiar_tabla(self):
        self.tree.delete(*self.tree.get_children())
        self._filas = []
        self._url_map = {}
        self._filas_por_item = {}
        self._pagina_detalle = {}
        self._cache.vaciar()
        self._conteos = None
        self._total_paginas = None
        self._consulta_id += 1         # un conteo o una pagina en vuelo ya no aplican
        self._contando = None
        self._tamano_previo = None
        self._pagina_actual = 1
        self._has_more = False
        self._filtros_activos = None
        self._nuevos = set()
        self.lbl_rango.config(text="")
        self._pag_frm.grid_remove()
        self._destruir_tabs_detalle()

    def _limpiar(self):
        self._limpiar_tabla()
        self.entry_nit.delete(0, "end")
        self.entry_unspsc.delete(0, "end")
        self.entry_entidad_nombre.delete(0, "end")
        self.entry_entidad_nit.delete(0, "end")
        self.var_empresa.set("TODAS")
        self.var_entidad.set("TODAS")
        self.entry_texto.delete(0, "end")
        for e in self.ent_av.values():
            e.delete(0, "end")
        self.var_modalidad.set("")
        self._aplicar_rango_a_widgets(None)     # vuelve a "Ultimo año"
        self.lbl_estado.config(text="Resultados limpiados.")


# =============================================================================
# ARRANQUE
# =============================================================================
if __name__ == "__main__":
    app = AppSECOP()
    app.mainloop()
