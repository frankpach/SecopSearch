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
import json
import socket
import subprocess
import threading
import time
import webbrowser
import concurrent.futures
from datetime import datetime
from tkinter import (
    Tk, Frame, Label, Button, Entry, ttk, messagebox,
    filedialog, StringVar, scrolledtext, BooleanVar, simpledialog
)

import pandas as pd
import requests
from search import (
    Filtros, condiciones, orden_dataset, primer_valor_positivo, url_de,
    construir_where as _build_where, escapar_soql as _escape_sql,
)
from paginacion import CachePaginas, TAMANOS_PAGINA, TAMANO_POR_DEFECTO, total_paginas, total_registros
from copiador_tabla import CopiadorTabla
from tabla_utils import columnas_union, ordenar_filas, texto_pantalla, valor_visible

# =============================================================================
# CONFIGURACION
# =============================================================================
ENV_FILE = ".env"
HISTORIAL_FILE = "empresas_historial.json"
HISTORIAL_ENTIDADES_FILE = "entidades_historial.json"

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
# HISTORIAL JSON - EMPRESAS
# =============================================================================

def cargar_historial():
    """Carga lista de empresas desde JSON local. Retorna dict {nombre: nit}."""
    if os.path.exists(HISTORIAL_FILE):
        try:
            with open(HISTORIAL_FILE, "r", encoding="utf-8") as f:
                lista = json.load(f)
            return {item["nombre"]: item["nit"] for item in lista if "nombre" in item and "nit" in item}
        except Exception:
            pass
    return {}


def guardar_historial(empresas_dict):
    """Guarda dict {nombre: nit} como lista JSON con timestamps."""
    lista = []
    for nombre, nit in empresas_dict.items():
        lista.append({"nombre": nombre, "nit": nit, "ultima_consulta": datetime.now().isoformat()})
    try:
        with open(HISTORIAL_FILE, "w", encoding="utf-8") as f:
            json.dump(lista, f, indent=2, ensure_ascii=False)
    except Exception as e:
        import sys
        sys.stderr.write(f"[WARN] No se pudo guardar historial empresas: {e}\n")


# =============================================================================
# HISTORIAL JSON - ENTIDADES
# =============================================================================

def cargar_historial_entidades():
    """Carga lista de entidades desde JSON local. Retorna dict {nombre: nit}."""
    if os.path.exists(HISTORIAL_ENTIDADES_FILE):
        try:
            with open(HISTORIAL_ENTIDADES_FILE, "r", encoding="utf-8") as f:
                lista = json.load(f)
            return {item["nombre"]: item["nit"] for item in lista if "nombre" in item and "nit" in item}
        except Exception:
            pass
    return {}


def guardar_historial_entidades(entidades_dict):
    """Guarda dict {nombre: nit} como lista JSON con timestamps."""
    lista = []
    for nombre, nit in entidades_dict.items():
        lista.append({"nombre": nombre, "nit": nit, "ultima_consulta": datetime.now().isoformat()})
    try:
        with open(HISTORIAL_ENTIDADES_FILE, "w", encoding="utf-8") as f:
            json.dump(lista, f, indent=2, ensure_ascii=False)
    except Exception as e:
        import sys
        sys.stderr.write(f"[WARN] No se pudo guardar historial entidades: {e}\n")


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

COLS_IDS = [c[0] for c in COLUMNAS]


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

        # Cargar historiales
        self.empresas = cargar_historial()
        self.entidades = cargar_historial_entidades()

        self._filas = []
        self._url_map = {}
        self._filas_por_item = {}
        self._errores = []
        self._omitidos = []
        self._consultando = False

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
        ttk.Button(frm, text="Eliminar", width=8,
                   command=self._eliminar_empresa).grid(row=0, column=2, sticky="w", padx=(0, 12))

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
        ttk.Button(frm, text="Eliminar", width=8,
                   command=self._eliminar_entidad).grid(row=1, column=2, sticky="w", padx=(0, 12), pady=(6, 0))

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
        self.btn_excel = ttk.Button(btn_frm, text="Exportar Excel", command=self._exportar_excel)
        self.btn_excel.pack(side="left", padx=2)
        self.btn_csv = ttk.Button(btn_frm, text="Exportar CSV", command=self._exportar_csv)
        self.btn_csv.pack(side="left", padx=2)
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

    def _refrescar_combo_empresas(self):
        self.combo_empresa["values"] = ["TODAS"] + list(self.empresas.keys())

    def _refrescar_combo_entidades(self):
        self.combo_entidad["values"] = ["TODAS"] + list(self.entidades.keys())

    # -------------------------------------------------------------------------
    # GESTION HISTORIAL
    # -------------------------------------------------------------------------
    def _guardar_empresa_manual(self):
        nit = self.entry_nit.get().strip()
        if not nit:
            messagebox.showwarning("NIT vacio", "Ingrese un NIT para guardar.")
            return
        if not validar_nit(nit):
            messagebox.showwarning("NIT invalido", "El NIT debe tener entre 8 y 11 digitos.")
            return
        # Si ya existe, solo actualizar; si no, agregar con nombre = nit por ahora
        nombre = None
        for n, v in self.empresas.items():
            if v == nit:
                nombre = n
                break
        if nombre:
            messagebox.showinfo("Existente", f"Empresa '{nombre}' con NIT {nit} ya esta en el historial.")
            self.var_empresa.set(nombre)
            return
        # Agregar nueva
        self.empresas[nit] = nit
        guardar_historial(self.empresas)
        self._refrescar_combo_empresas()
        self.var_empresa.set(nit)
        self.lbl_estado.config(text=f"Empresa {nit} guardada en historial.")

    def _eliminar_empresa(self):
        sel = self.var_empresa.get()
        if sel == "TODAS" or sel not in self.empresas:
            messagebox.showwarning("Seleccion", "Seleccione una empresa del historial para eliminar.")
            return
        if messagebox.askyesno("Confirmar", f"Eliminar '{sel}' del historial?"):
            del self.empresas[sel]
            guardar_historial(self.empresas)
            self._refrescar_combo_empresas()
            self.var_empresa.set("TODAS")
            self.lbl_estado.config(text=f"Empresa '{sel}' eliminada del historial.")

    def _guardar_entidad_manual(self):
        nit = self.entry_entidad_nit.get().strip()
        nombre = self.entry_entidad_nombre.get().strip()
        if not nit and not nombre:
            messagebox.showwarning("Datos vacios", "Ingrese al menos nombre o NIT de la entidad.")
            return
        key = nombre if nombre else nit
        if key in self.entidades:
            messagebox.showinfo("Existente", f"Entidad '{key}' ya esta en el historial.")
            self.var_entidad.set(key)
            return
        self.entidades[key] = nit
        guardar_historial_entidades(self.entidades)
        self._refrescar_combo_entidades()
        self.var_entidad.set(key)
        self.lbl_estado.config(text=f"Entidad '{key}' guardada en historial.")

    def _eliminar_entidad(self):
        sel = self.var_entidad.get()
        if sel == "TODAS" or sel not in self.entidades:
            messagebox.showwarning("Seleccion", "Seleccione una entidad del historial para eliminar.")
            return
        if messagebox.askyesno("Confirmar", f"Eliminar '{sel}' del historial de entidades?"):
            del self.entidades[sel]
            guardar_historial_entidades(self.entidades)
            self._refrescar_combo_entidades()
            self.var_entidad.set("TODAS")
            self.lbl_estado.config(text=f"Entidad '{sel}' eliminada del historial.")

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
    def _iniciar_consulta(self):
        if self._consultando:
            return

        nit_manual = self.entry_nit.get().strip()
        empresa_sel = self.var_empresa.get()
        unspsc = self.entry_unspsc.get().strip()
        entidad_nombre = self.entry_entidad_nombre.get().strip()
        entidad_nit = self.entry_entidad_nit.get().strip()
        entidad_sel = self.var_entidad.get()

        # Si selecciono entidad del dropdown y no hay campos llenos, autollenar
        if entidad_sel != "TODAS" and entidad_sel in self.entidades:
            if not entidad_nombre:
                entidad_nombre = entidad_sel
            if not entidad_nit:
                entidad_nit = self.entidades[entidad_sel]

        has_supplier = bool(nit_manual) or (empresa_sel != "TODAS")
        has_filters = bool(unspsc or entidad_nombre or entidad_nit)

        if not has_supplier and not has_filters:
            messagebox.showwarning("Filtros vacios",
                "Ingrese al menos un criterio: empresa/NIT de proveedor, UNSPSC, o entidad compradora.")
            return

        if nit_manual and not validar_nit(nit_manual):
            messagebox.showwarning("NIT invalido",
                "El NIT ingresado no es valido. Debe contener entre 8 y 11 digitos.")
            return

        if entidad_nit and not validar_nit(entidad_nit):
            messagebox.showwarning("NIT entidad invalido",
                "El NIT de la entidad no es valido.")
            return

        # Armar lista de empresas a consultar
        if nit_manual:
            empresas = {nit_manual: nit_manual}
        elif empresa_sel != "TODAS":
            empresas = {empresa_sel: self.empresas[empresa_sel]}
        else:
            empresas = {None: None}  # Busqueda general

        filtros = Filtros(
            nit_proveedor=nit_manual or (self.empresas.get(empresa_sel, "") if empresa_sel != "TODAS" else ""),
            unspsc=unspsc, entidad_nombre=entidad_nombre, entidad_nit=entidad_nit,
        )
        errs_filtros = filtros.errores()
        if errs_filtros:
            messagebox.showwarning("Filtros invalidos", "\n".join(errs_filtros))
            return

        self._limpiar_tabla()
        # _limpiar_tabla() deja _filtros_activos en None: se asigna DESPUES
        self._filtros_activos = {"empresas": empresas, "filtros": filtros}
        self._filas_por_pagina = int(self.var_tamano.get())
        self._consulta_id += 1
        self._cancelar.clear()
        self._pagina_previa = None
        self._errores = []
        self._omitidos = []
        self._pagina_actual = 1
        self._has_more = False
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

            # Guardar empresa en historial (solo en primera pagina)
            if offset == 0 and nit:
                nombre_a_guardar = None
                for row in f:
                    if row.get("estado") != "SIN CONTRATOS":
                        cand = row.get("empresa", "")
                        if cand and cand != "—" and cand != nit:
                            nombre_a_guardar = cand
                            break
                if not nombre_a_guardar:
                    nombre_a_guardar = nit
                if nombre_a_guardar not in self.empresas:
                    nuevas_empresas.append((nombre_a_guardar, nit))

        # Guardar entidad en historial (solo en primera pagina)
        if offset == 0 and (filtros.entidad_nombre or filtros.entidad_nit):
            ent_key = filtros.entidad_nombre if filtros.entidad_nombre else filtros.entidad_nit
            ent_nit = filtros.entidad_nit if filtros.entidad_nit else ""
            if ent_key and ent_key not in self.entidades:
                if filas and any(row.get("estado") != "SIN CONTRATOS" for row in filas):
                    nuevas_entidades.append((ent_key, ent_nit))

        if token != self._consulta_id:
            return
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
        self.after(0, entregar)

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

        # Actualizar historiales
        if nuevas_empresas or nuevas_entidades:
            self._actualizar_historiales(nuevas_empresas, nuevas_entidades)

        # Las ultimas paginas se guardan para revisitarlas sin consultar la API; una pagina
        # con errores puede estar incompleta: no se guarda y se vuelve a pedir al revisitarla
        if not errores:
            self._cache.guardar(self._pagina_actual, (filas, detalle, [], has_more))

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
        if self._has_more:
            msg += "  |  Hay mas paginas disponibles"
        if sanciones:
            msg += f"  |  ATENCION: {sanciones} sanciones/inhabilidades"
        if self._errores:
            msg += f"  |  {len(self._errores)} errores"
        if self._omitidos:
            msg += "  |  Omitidos (filtro no soportado): " + ", ".join(self._omitidos)
        self.lbl_estado.config(text=msg)

        if errores and offset == 0:
            self._mostrar_errores()
        if offset == 0 and self._conteos is None and self._filtros_activos:
            self._iniciar_conteo()

    def _actualizar_historiales(self, nuevas_empresas, nuevas_entidades):
        """Agrega empresas/entidades nuevas al historial y refresca los combos."""
        cambio = False
        for nombre, nit in nuevas_empresas:
            if nombre not in self.empresas:
                self.empresas[nombre] = nit
                cambio = True
        if cambio:
            guardar_historial(self.empresas)
            self._refrescar_combo_empresas()

        cambio_ent = False
        for nombre, nit in nuevas_entidades:
            if nombre not in self.entidades:
                self.entidades[nombre] = nit
                cambio_ent = True
        if cambio_ent:
            guardar_historial_entidades(self.entidades)
            self._refrescar_combo_entidades()

        msgs = []
        if nuevas_empresas:
            msgs.append(f"{len(nuevas_empresas)} empresa(s) agregada(s)")
        if nuevas_entidades:
            msgs.append(f"{len(nuevas_entidades)} entidad(es) agregada(s)")
        if msgs:
            self.lbl_estado.config(text="Historial actualizado: " + ", ".join(msgs))

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
            if fila.get("url"):
                tags.append("con_url")
            item = self.tree.insert("", "end", values=vals, tags=tuple(tags))
            self._filas_por_item[item] = fila
            if fila.get("url"):
                self._url_map[item] = fila["url"]

    def _cambiar_pagina(self, pagina, forzar=False):
        if not self._filtros_activos or self._consultando or pagina < 1:
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
        state = "disabled" if activo else "normal"
        self.btn_consultar.config(state=state,
                                  text="Consultando..." if activo else "Consultar")
        self.btn_excel.config(state=state)
        self.btn_csv.config(state=state)
        self.btn_limpiar.config(state=state)
        self.combo_empresa.config(state="disabled" if activo else "readonly")
        self.combo_entidad.config(state="disabled" if activo else "readonly")
        self.entry_nit.config(state=state)
        self.entry_unspsc.config(state=state)
        self.entry_entidad_nombre.config(state=state)
        self.entry_entidad_nit.config(state=state)
        self.btn_cancelar.config(state="normal" if activo else "disabled")
        self.combo_tamano.config(state="disabled" if activo else "readonly")
        if activo:
            self.progress.grid()
            self.progress.start(12)
        else:
            self.progress.stop()
            self.progress.grid_remove()

    # -------------------------------------------------------------------------
    # EXPORTACION COMPLETA (background thread — descarga TODO)
    # -------------------------------------------------------------------------
    def _exportar_excel(self):
        if not self._filtros_activos:
            messagebox.showwarning("Sin datos", "Realice una consulta primero.")
            return
        filepath = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            initialfile=f"SECOP_{datetime.now():%Y%m%d_%H%M}.xlsx",
        )
        if not filepath:
            return
        self._set_exportando(True)
        threading.Thread(
            target=self._hilo_exportar_excel,
            args=(filepath,),
            daemon=True,
        ).start()

    def _hilo_exportar_excel(self, filepath):
        filtros = self._filtros_activos
        try:
            filas, detalle = self._hilo_exportar_datos(filtros)
            self.after(0, lambda: self.lbl_estado.config(text="Exportando: escribiendo Excel..."))
            with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
                df_resumen = pd.DataFrame(filas)
                df_resumen.to_excel(writer, sheet_name="Resumen", index=False)
                for nombre_tab, datos_crudos in detalle.items():
                    if datos_crudos:
                        hoja = nombre_tab.replace("/", "-").replace("\\", "-")[:31]
                        pd.DataFrame(datos_crudos).to_excel(writer, sheet_name=hoja, index=False)
            self.after(0, lambda: (
                self._set_exportando(False),
                self.lbl_estado.config(text=f"Exportacion Excel completada: {len(filas)} registros."),
                messagebox.showinfo("Exportacion", f"Archivo guardado:\n{filepath}")
            ))
        except Exception as e:
            self.after(0, lambda: (
                self._set_exportando(False),
                messagebox.showerror("Error de exportacion", str(e))
            ))

    def _exportar_csv(self):
        if not self._filtros_activos:
            messagebox.showwarning("Sin datos", "Realice una consulta primero.")
            return
        folder = filedialog.askdirectory()
        if not folder:
            return
        self._set_exportando(True)
        threading.Thread(
            target=self._hilo_exportar_csv,
            args=(folder,),
            daemon=True,
        ).start()

    def _hilo_exportar_csv(self, folder):
        try:
            filas, detalle = self._hilo_exportar_datos(self._filtros_activos)
            self.after(0, lambda: self.lbl_estado.config(text="Exportando: escribiendo CSVs..."))
            ts = f"{datetime.now():%Y%m%d_%H%M}"
            archivos = []

            fp_resumen = os.path.join(folder, f"SECOP_Resumen_{ts}.csv")
            pd.DataFrame(filas).to_csv(fp_resumen, index=False, encoding="utf-8-sig")
            archivos.append(os.path.basename(fp_resumen))

            for nombre_tab, datos_crudos in detalle.items():
                if datos_crudos:
                    nombre_archivo = nombre_tab.replace(" ", "_").replace("/", "-")[:40]
                    fp = os.path.join(folder, f"SECOP_{nombre_archivo}_{ts}.csv")
                    pd.DataFrame(datos_crudos).to_csv(fp, index=False, encoding="utf-8-sig")
                    archivos.append(os.path.basename(fp))

            msg = f"{len(archivos)} archivos CSV guardados en:\n{folder}\n\n" + "\n".join(archivos)
            self.after(0, lambda: (
                self._set_exportando(False),
                self.lbl_estado.config(text=f"Exportacion CSV completada: {len(filas)} registros."),
                messagebox.showinfo("Exportacion", msg)
            ))
        except Exception as e:
            self.after(0, lambda: (
                self._set_exportando(False),
                messagebox.showerror("Error de exportacion", str(e))
            ))

    def _hilo_exportar_datos(self, filtros):
        """PUENTE TEMPORAL: junta las paginas en memoria hasta que la Tarea 8 exporte a disco."""
        query_local = SECOPQuery(SECOPClient(self.creds))
        todas_filas, todo_detalle = [], {}
        for nombre, nit in filtros["empresas"].items():
            for filas, detalle in query_local.iterar_paginas(
                    nombre, nit, filtros["filtros"], page_size=500,
                    on_progress=lambda msg: self.after(0, lambda m=msg: self.lbl_estado.config(text=m))):
                todas_filas.extend(filas)
                for k, v in detalle.items():
                    todo_detalle.setdefault(k, []).extend(v)
        return todas_filas, todo_detalle

    def _set_exportando(self, activo):
        state = "disabled" if activo else "normal"
        self.btn_excel.config(state=state)
        self.btn_csv.config(state=state)
        self.btn_cancelar.config(state="normal" if activo else "disabled")
        if activo:
            self.progress.grid()
            self.progress.start(12)
        else:
            self.progress.stop()
            self.progress.grid_remove()

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
        self.lbl_estado.config(text="Resultados limpiados.")


# =============================================================================
# ARRANQUE
# =============================================================================
if __name__ == "__main__":
    app = AppSECOP()
    app.mainloop()
