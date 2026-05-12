#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MCP Server for SECOP II Queries
Exposes tools for LLMs to query Colombian public procurement data.

NUEVO:
  - Historial de empresas desde JSON local
  - Filtros por UNSPSC y entidad compradora (nombre/NIT)
  - Busqueda general sin proveedor

Usage with Claude Desktop / Cursor / etc:
  {
    "secop": {
      "command": "python",
      "args": ["D:/.../mcp_secop.py"]
    }
  }

Or run standalone:
  python mcp_secop.py
"""

import os
import json
from datetime import datetime
from typing import Optional

import requests
from mcp.server.fastmcp import FastMCP

# =============================================================================
# CONFIG
# =============================================================================
ENV_FILE = ".env"
HISTORIAL_FILE = "empresas_historial.json"
HISTORIAL_ENTIDADES_FILE = "entidades_historial.json"
BASE_URL = "https://www.datos.gov.co/resource"
CONTRACT_URL_PREFIX = "https://community.secop.gov.co/Public/Tendering/ContractDetailView/Index?UniqueIdentifier="

DOMAINS = {
    "p6dx-8zbt": "SECOP II - Procesos de Contratacion",
    "jbjy-vk9h": "SECOP II - Contratos Electronicos",
    "rpmr-utcd": "SECOP Integrado",
    "qmzu-gj57": "SECOP II - Proveedores Registrados",
    "it5q-hg94": "SECOP II - Multas y Sanciones",
    "4n4q-k399": "SECOP I - Multas y Sanciones",
    "iaeu-rcn6": "Antecedentes SIRI (Procuraduria)",
}

# =============================================================================
# HISTORIAL - EMPRESAS
# =============================================================================

def cargar_historial():
    if os.path.exists(HISTORIAL_FILE):
        try:
            with open(HISTORIAL_FILE, "r", encoding="utf-8") as f:
                lista = json.load(f)
            return {item["nombre"]: item["nit"] for item in lista if "nombre" in item and "nit" in item}
        except Exception:
            pass
    return {}


def guardar_historial(empresas_dict):
    lista = [{"nombre": k, "nit": v, "ultima_consulta": datetime.now().isoformat()}
             for k, v in empresas_dict.items()]
    try:
        with open(HISTORIAL_FILE, "w", encoding="utf-8") as f:
            json.dump(lista, f, indent=2, ensure_ascii=False)
    except Exception as e:
        import sys
        sys.stderr.write(f"[WARN] No se pudo guardar historial empresas: {e}\n")


# =============================================================================
# HISTORIAL - ENTIDADES
# =============================================================================

def cargar_historial_entidades():
    if os.path.exists(HISTORIAL_ENTIDADES_FILE):
        try:
            with open(HISTORIAL_ENTIDADES_FILE, "r", encoding="utf-8") as f:
                lista = json.load(f)
            return {item["nombre"]: item["nit"] for item in lista if "nombre" in item and "nit" in item}
        except Exception:
            pass
    return {}


def guardar_historial_entidades(entidades_dict):
    lista = [{"nombre": k, "nit": v, "ultima_consulta": datetime.now().isoformat()}
             for k, v in entidades_dict.items()]
    try:
        with open(HISTORIAL_ENTIDADES_FILE, "w", encoding="utf-8") as f:
            json.dump(lista, f, indent=2, ensure_ascii=False)
    except Exception as e:
        import sys
        sys.stderr.write(f"[WARN] No se pudo guardar historial entidades: {e}\n")


# =============================================================================
# CLIENT
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


class SECOPClient:
    def __init__(self, creds=None):
        if creds is None:
            creds = leer_env()
        self.session = requests.Session()
        self.auth = None
        user = creds.get("user")
        password = creds.get("password")
        if user and password:
            self.auth = (user, password)

    def get(self, dataset_id, params=None):
        url = f"{BASE_URL}/{dataset_id}.json"
        response = self.session.get(url, params=params, auth=self.auth, timeout=60)
        response.raise_for_status()
        return response.json()

    def get_metadata(self, dataset_id):
        url = f"https://www.datos.gov.co/api/views/{dataset_id}.json"
        response = self.session.get(url, auth=self.auth, timeout=30)
        response.raise_for_status()
        return response.json()


def _escape_sql(val):
    return str(val).replace("'", "''")


def _build_where(conditions):
    return " AND ".join(conditions) if conditions else ""


client = SECOPClient()
mcp = FastMCP("secop")


# =============================================================================
# TOOLS
# =============================================================================

@mcp.tool()
def secop_list_companies() -> str:
    """List the companies saved in the local search history with their NIT numbers."""
    empresas = cargar_historial()
    if not empresas:
        return "# Empresas en Historial Local\n\nNo hay empresas guardadas. Use secop_search_and_save_company para agregar una."
    lines = ["# Empresas en Historial Local", ""]
    for nombre, nit in empresas.items():
        lines.append(f"- **{nombre}** | NIT: `{nit}`")
    return "\n".join(lines)


@mcp.tool()
def secop_list_entities() -> str:
    """List the buyer entities saved in the local search history with their NIT numbers."""
    entidades = cargar_historial_entidades()
    if not entidades:
        return "# Entidades en Historial Local\n\nNo hay entidades guardadas."
    lines = ["# Entidades en Historial Local", ""]
    for nombre, nit in entidades.items():
        lines.append(f"- **{nombre}** | NIT: `{nit}`")
    return "\n".join(lines)


@mcp.tool()
def secop_search_and_save_company(nit: str) -> str:
    """Search SECOP for a company by NIT and save it to local history.

    Args:
        nit: Supplier NIT (without verification digit).
    """
    try:
        data = client.get("jbjy-vk9h", {"$where": f"documento_proveedor='{_escape_sql(nit)}'", "$limit": 1})
    except Exception as e:
        return f"Error buscando empresa: {e}"

    empresas = cargar_historial()
    nombre = nit
    if data:
        nombre = data[0].get("proveedor_adjudicado", nit)
    if nombre in empresas:
        return f"Empresa '{nombre}' (NIT: {nit}) ya existe en el historial."
    empresas[nombre] = nit
    guardar_historial(empresas)
    return f"Empresa '{nombre}' (NIT: {nit}) guardada en el historial."


@mcp.tool()
def secop_search_and_save_entity(nit: Optional[str] = None, name: Optional[str] = None) -> str:
    """Save a buyer entity to local history.

    Args:
        nit: Entity NIT (optional).
        name: Entity name (optional).
    """
    if not nit and not name:
        return "Error: Debe proporcionar al menos nombre o NIT de la entidad."
    entidades = cargar_historial_entidades()
    key = name if name else nit
    if key in entidades:
        return f"Entidad '{key}' ya existe en el historial."
    entidades[key] = nit or ""
    guardar_historial_entidades(entidades)
    return f"Entidad '{key}' guardada en el historial."


@mcp.tool()
def secop_query_contracts(
    nit: Optional[str] = None,
    unspsc: Optional[str] = None,
    entidad_nombre: Optional[str] = None,
    entidad_nit: Optional[str] = None,
    limit: int = 50,
) -> str:
    """Query SECOP II electronic contracts by supplier NIT, UNSPSC code, or buyer entity.

    Args:
        nit: Supplier NIT (without verification digit). Optional for broad searches.
        unspsc: UNSPSC product/service classification code (partial match allowed).
        entidad_nombre: Buyer entity name (partial match).
        entidad_nit: Buyer entity NIT (exact match).
        limit: Max records to return (default 50).
    """
    conds = []
    if nit:
        conds.append(f"documento_proveedor='{_escape_sql(nit)}'")
    if unspsc:
        conds.append(f"codigo_de_categoria_principal LIKE '%{_escape_sql(unspsc)}%'")
    if entidad_nombre:
        conds.append(f"nombre_entidad LIKE '%{_escape_sql(entidad_nombre)}%'")
    if entidad_nit:
        conds.append(f"nit_entidad='{_escape_sql(entidad_nit)}'")

    if not conds:
        return "Error: Debe proporcionar al menos un filtro (nit, unspsc, entidad_nombre o entidad_nit)."

    params = {"$where": _build_where(conds), "$limit": limit, "$order": "fecha_de_firma DESC"}
    try:
        data = client.get("jbjy-vk9h", params)
    except Exception as e:
        return f"Error querying contracts: {e}"

    if not data:
        return "No se encontraron contratos con los filtros especificados."

    lines = [f"# Contratos SECOP II ({len(data)} registros)", ""]
    for i, r in enumerate(data, 1):
        contract_id = r.get("id_contrato", "")
        contract_url = f"{CONTRACT_URL_PREFIX}{contract_id}" if contract_id else ""
        lines.append(
            f"{i}. **{contract_id or 'N/A'}** | "
            f"Proveedor: {r.get('proveedor_adjudicado', 'N/A')} | "
            f"Entidad: {r.get('nombre_entidad', 'N/A')} | "
            f"Estado: {r.get('estado_contrato', 'N/A')} | "
            f"Valor: ${float(r.get('valor_del_contrato', 0) or 0):,.0f} | "
            f"Fecha Firma: {str(r.get('fecha_de_firma', ''))[:10]}"
        )
        if contract_url:
            lines.append(f"   [Ver contrato en SECOP]({contract_url})")
        lines.append("")
    return "\n".join(lines)


@mcp.tool()
def secop_query_processes(
    nit: Optional[str] = None,
    unspsc: Optional[str] = None,
    entidad_nombre: Optional[str] = None,
    entidad_nit: Optional[str] = None,
    limit: int = 50,
) -> str:
    """Query SECOP II procurement processes by supplier NIT, UNSPSC, or buyer entity.

    Args:
        nit: Supplier NIT (without verification digit). Optional for broad searches.
        unspsc: UNSPSC code (partial match).
        entidad_nombre: Buyer entity name (partial match).
        entidad_nit: Buyer entity NIT (exact match).
        limit: Max records (default 50).
    """
    conds = []
    if nit:
        conds.append(f"nit_del_proveedor_adjudicado='{_escape_sql(nit)}'")
    if unspsc:
        conds.append(f"codigo_principal_de_categoria LIKE '%{_escape_sql(unspsc)}%'")
    if entidad_nombre:
        conds.append(f"entidad LIKE '%{_escape_sql(entidad_nombre)}%'")
    if entidad_nit:
        conds.append(f"nit_entidad='{_escape_sql(entidad_nit)}'")

    if not conds:
        return "Error: Debe proporcionar al menos un filtro (nit, unspsc, entidad_nombre o entidad_nit)."

    params = {"$where": _build_where(conds), "$limit": limit, "$order": "fecha_adjudicacion DESC"}
    try:
        data = client.get("p6dx-8zbt", params)
    except Exception as e:
        return f"Error querying processes: {e}"

    if not data:
        return "No se encontraron procesos con los filtros especificados."

    lines = [f"# Procesos SECOP II ({len(data)} registros)", ""]
    for i, r in enumerate(data, 1):
        lines.append(
            f"{i}. **{r.get('id_del_proceso', 'N/A')}** | "
            f"Proveedor: {r.get('nombre_del_proveedor', 'N/A')} | "
            f"Entidad: {r.get('entidad', 'N/A')} | "
            f"Estado: {r.get('estado_del_procedimiento', 'N/A')} | "
            f"Adjudicacion: ${float(r.get('valor_total_adjudicacion', 0) or 0):,.0f} | "
            f"Modalidad: {r.get('modalidad_de_contratacion', 'N/A')}"
        )
    return "\n".join(lines)


@mcp.tool()
def secop_query_supplier(nit: str) -> str:
    """Query the SECOP II supplier registry for a given NIT.

    Args:
        nit: Supplier NIT (without verification digit).
    """
    try:
        data = client.get("qmzu-gj57", {"$where": f"nit='{_escape_sql(nit)}'", "$limit": 10})
    except Exception as e:
        return f"Error querying supplier registry: {e}"

    if not data:
        return f"No supplier registry entry found for NIT `{nit}`."

    r = data[0]
    lines = [
        f"# Proveedor Registrado (NIT: {nit})",
        "",
        f"- **Nombre:** {r.get('nombre', 'N/A')}",
        f"- **Activo:** {r.get('esta_activa', 'N/A')}",
        f"- **Departamento:** {r.get('departamento', 'N/A')}",
        f"- **Municipio:** {r.get('municipio', 'N/A')}",
        f"- **Representante Legal:** {r.get('nombre_representante_legal', 'N/A')}",
        f"- **Fecha Creacion:** {str(r.get('fecha_creacion', ''))[:10]}",
        f"- **Correo:** {r.get('correo', 'N/A')}",
        f"- **Telefono:** {r.get('telefono', 'N/A')}",
    ]
    return "\n".join(lines)


@mcp.tool()
def secop_query_sanctions(name: str, limit: int = 50) -> str:
    """Query sanctions (SECOP II, SECOP I) for a company name.

    Args:
        name: Company name (or keyword) to search.
        limit: Max records per dataset (default 50).
    """
    results = {}
    for ds_id in ("it5q-hg94", "4n4q-k399"):
        try:
            data = client.get(ds_id, {"$q": name, "$limit": limit})
            results[DOMAINS[ds_id]] = data
        except Exception as e:
            results[DOMAINS[ds_id]] = {"error": str(e)}

    lines = [f"# Sanciones para: {name}", ""]
    for ds_name, data in results.items():
        lines.append(f"## {ds_name}")
        if isinstance(data, dict) and "error" in data:
            lines.append(f"Error: {data['error']}")
        elif not data:
            lines.append("No se encontraron registros.")
        else:
            lines.append(f"Registros: {len(data)}")
            for r in data[:10]:
                if ds_name == DOMAINS["it5q-hg94"]:
                    lines.append(
                        f"- {r.get('nombre_proveedor_objeto_de', 'N/A')} | "
                        f"Tipo: {r.get('tipo_de_sancion', 'N/A')} | "
                        f"Valor: ${float(r.get('valor', 0) or 0):,.0f} | "
                        f"Estado: {r.get('estado', 'N/A')}"
                    )
                else:
                    lines.append(
                        f"- {r.get('nombre_contratista', 'N/A')} | "
                        f"Valor: ${float(r.get('valor_sancion', 0) or 0):,.0f} | "
                        f"Resolucion: {r.get('numero_de_resolucion', 'N/A')}"
                    )
        lines.append("")
    return "\n".join(lines)


@mcp.tool()
def secop_get_dataset_info() -> str:
    """Get freshness status (last update) for all SECOP datasets."""
    lines = ["# Estado de Datasets SECOP", ""]
    for ds_id, ds_name in DOMAINS.items():
        try:
            meta = client.get_metadata(ds_id)
            updated = meta.get("updatedAt", meta.get("rowsUpdatedAt", "N/A"))
            count = meta.get("rowsUpdatedBy", "N/A")
            lines.append(f"- **{ds_name}** | Ultima actualizacion: `{updated}` | Registros: `{count}`")
        except Exception as e:
            lines.append(f"- **{ds_name}** | Error: {str(e)[:60]}")
    return "\n".join(lines)


@mcp.tool()
def secop_full_due_diligence(
    nit: str,
    company_name: Optional[str] = None,
    unspsc: Optional[str] = None,
    entidad_nombre: Optional[str] = None,
    entidad_nit: Optional[str] = None,
) -> str:
    """Run a full due-diligence query across all SECOP datasets for a given NIT.

    Args:
        nit: Supplier NIT (without verification digit).
        company_name: Optional company name for sanctions search.
        unspsc: Optional UNSPSC filter for contracts/processes.
        entidad_nombre: Optional buyer entity name filter.
        entidad_nit: Optional buyer entity NIT filter.
    """
    name = company_name or nit
    lines = [f"# Debida Diligencia SECOP — {name} (NIT: {nit})", ""]

    lines.append("## 1. Registro de Proveedor")
    lines.append(secop_query_supplier(nit))
    lines.append("")

    lines.append("## 2. Contratos Electronicos")
    lines.append(secop_query_contracts(
        nit=nit, unspsc=unspsc, entidad_nombre=entidad_nombre, entidad_nit=entidad_nit, limit=100))
    lines.append("")

    lines.append("## 3. Procesos de Contratacion")
    lines.append(secop_query_processes(
        nit=nit, unspsc=unspsc, entidad_nombre=entidad_nombre, entidad_nit=entidad_nit, limit=100))
    lines.append("")

    lines.append("## 4. Sanciones")
    lines.append(secop_query_sanctions(name, limit=100))
    lines.append("")

    lines.append("## 5. Resumen de Riesgo")
    lines.append("- Revisar contratos cancelados o con altos saldos pendientes.")
    lines.append("- Verificar estado activo/inactivo en el registro de proveedores.")
    lines.append("- Revisar sanciones vigentes.")
    return "\n".join(lines)


# =============================================================================
# MAIN
# =============================================================================
if __name__ == "__main__":
    mcp.run(transport="stdio")
