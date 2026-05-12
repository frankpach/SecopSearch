# SKILL: SECOP-II-Query

> **Version:** 1.2.0  
> **Author:** AI Agent  
> **Domain:** datos.gov.co (Socrata)  
> **Scope:** Public procurement data (Colombia)  
> **Tags:** secop, contracting, due-diligence, socrata, colombia

---

## 1. Overview

This skill enables an AI agent to query Colombian public procurement data (SECOP II and related datasets) via the Socrata Open Data API (SODA). It supports searching for companies by NIT, name, or custom criteria across 7 integrated datasets, retrieving contract execution status, sanctions, and supplier registration metadata.

The skill is designed for **due diligence workflows** on private security companies but works for any supplier registered in SECOP.

---

## 2. Prerequisites

### 2.1 Environment
- Python 3.8+
- Working directory contains:
  - `secop_hibrido.py` — Unified launcher (GUI + MCP)
  - `app_secop.py` — GUI application script
  - `mcp_secop.py` — MCP Server for LLM integration
  - `.env` with valid Socrata credentials (username/password)
  - `venv_secop/` virtual environment (pre-configured)

### 2.2 Required Packages
```
requests>=2.30.0
pandas>=2.0.0
openpyxl>=3.1.0
```

> **NOTE:** `sodapy` is NOT used. The library has issues with invalid app tokens on datos.gov.co. We use `requests` directly.

### 2.3 Credentials (from .env)
```ini
user=<socrata_username>
password=<socrata_password>
```

> **IMPORTANT:** The `socrataClaveAPI` token may be INVALID (403 error). Always use Basic Auth (username/password) or public mode.

---

## 3. Datasets Reference

| Dataset ID | Name | Description | Last Known Update |
|------------|------|-------------|-------------------|
| `p6dx-8zbt` | SECOP II - Procesos de Contratacion | Procurement processes (awarded or not) | Daily |
| `jbjy-vk9h` | SECOP II - Contratos Electronicos | Signed contracts with execution data | Daily |
| `rpmr-utcd` | SECOP Integrado | Unified SECOP I + II contracts | Weekly |
| `qmzu-gj57` | SECOP II - Proveedores Registrados | Supplier registry metadata | Daily |
| `it5q-hg94` | SECOP II - Multas y Sanciones | Fines and sanctions (SECOP II) | Monthly |
| `4n4q-k399` | SECOP I - Multas y Sanciones | Historical fines (SECOP I) | Monthly |
| `iaeu-rcn6` | Antecedentes SIRI | Disciplinary sanctions (Procuraduria) | Daily |

### 3.1 Key Columns by Dataset

**Procesos (`p6dx-8zbt`):**
- `nit_del_proveedor_adjudicado` — Supplier NIT
- `nombre_del_proveedor` — Supplier name
- `valor_total_adjudicacion` — Awarded value
- `estado_del_procedimiento` — Process status
- `modalidad_de_contratacion` — Contracting modality
- `fecha_adjudicacion` — Award date

**Contratos (`jbjy-vk9h`):**
- `documento_proveedor` — Supplier document/NIT
- `proveedor_adjudicado` — Supplier name
- `valor_del_contrato` — Contract value
- `valor_pagado` — Amount paid
- `valor_pendiente_de_pago` — Pending payment
- `estado_contrato` — Contract status
- `fecha_de_firma` — Signature date
- `fecha_de_inicio_del_contrato` — Start date
- `fecha_de_fin_del_contrato` — End date

**Proveedores (`qmzu-gj57`):**
- `nit` — Supplier NIT
- `nombre` — Supplier name
- `esta_activa` — Active status
- `departamento`, `municipio` — Location
- `nombre_representante_legal` — Legal representative
- `fecha_creacion` — Registration date

**Sanciones (`it5q-hg94`, `4n4q-k399`):**
- `nombre_proveedor_objeto_de` / `nombre_contratista` — Sanctioned party
- `tipo_de_sancion` — Sanction type
- `valor` / `valor_sancion` — Fine amount
- `estado` — Status
- `fecha_evento` / `fecha_de_firmeza` — Date

---

## 4. Workflow

### 4.1 Standard Query Flow

```
READ .env credentials (user/password)
    ↓
INITIALIZE requests.Session() with Basic Auth
    ↓
DETERMINE target companies (from predefined list or user input)
    ↓
FOR each dataset:
    BUILD SoQL query (WHERE documento_proveedor='NIT' OR q='NAME')
    EXECUTE requests.get(url, params=..., auth=(user, password))
    STORE results in cache
    ↓
AGGREGATE results (count records, sum values, extract statuses)
    ↓
FORMAT output (table or structured report)
    ↓
OPTIONALLY export to Excel/CSV
```

### 4.2 Predefined Company List

Use these NITs for security company due diligence:

| Company Name | NIT (SECOP format) | NIT (full) |
|--------------|-------------------|------------|
| SERVIES LTDA | 890104906 | 890104906-4 |
| SUPREMA LTDA | 825000286 | 825000286-2 |
| SEGURIDAD PEGASO LTDA | 9004686350 | 900.468.635-0 |
| SEGURIDAD HEROICA DE COLOMBIA LTDA | 9003879253 | 900.387.925-3 |
| IDMA SECURITY LIMITADA | 9014115368 | 901.411.536-8 |

> **Note:** SECOP stores NITs without verification digit. Try both formats if queries fail.

---

## 5. API Client Implementation

### 5.1 Recommended Client (using requests)

```python
import requests
import os

class SECOPClient:
    BASE_URL = "https://www.datos.gov.co/resource"
    
    def __init__(self, creds):
        self.session = requests.Session()
        self.auth = None
        
        user = creds.get("user")
        password = creds.get("password")
        if user and password:
            self.auth = (user, password)
    
    def get(self, dataset_id, params=None):
        url = f"{self.BASE_URL}/{dataset_id}.json"
        response = self.session.get(url, params=params, auth=self.auth, timeout=60)
        response.raise_for_status()
        return response.json()
    
    def get_metadata(self, dataset_id):
        url = f"https://www.datos.gov.co/api/views/{dataset_id}.json"
        response = self.session.get(url, auth=self.auth, timeout=30)
        response.raise_for_status()
        return response.json()


def read_env():
    creds = {}
    with open(".env", "r", encoding="utf-8") as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1)
                creds[k] = v
    return creds

# Usage
client = SECOPClient(read_env())
```

### 5.2 Why NOT use sodapy?

The `sodapy` library passes the `X-App-Token` header, which causes **403 Invalid app_token** errors on datos.gov.co even with valid tokens. The solution is to use `requests` directly with Basic Auth only.

```python
# AVOID - This fails with 403
from sodapy import Socrata
client = Socrata("www.datos.gov.co", "your_token")  # 403 Invalid app_token

# USE INSTEAD - This works
import requests
session = requests.Session()
response = session.get("https://www.datos.gov.co/resource/p6dx-8zbt.json",
                       auth=("user", "password"))
```

---

## 6. API Query Patterns

### 6.1 Query Contracts by NIT

```python
nit = "825000286"
params = {
    "$where": f"documento_proveedor='{nit}'",
    "$limit": 100
}
results = client.get("jbjy-vk9h", params)
```

### 6.2 Query Processes by NIT

```python
nit = "825000286"
params = {
    "$where": f"nit_del_proveedor_adjudicado='{nit}'",
    "$limit": 100
}
results = client.get("p6dx-8zbt", params)
```

### 6.3 Multi-Dataset Search

```python
datasets = {
    "jbjy-vk9h": "Contratos",
    "p6dx-8zbt": "Procesos",
    "qmzu-gj57": "Proveedores",
}

nit = "825000286"
all_results = {}

for ds_id, ds_name in datasets.items():
    if ds_id == "qmzu-gj57":
        where = f"nit='{nit}'"
    elif ds_id == "p6dx-8zbt":
        where = f"nit_del_proveedor_adjudicado='{nit}'"
    else:
        where = f"documento_proveedor='{nit}'"
    
    try:
        res = client.get(ds_id, {"$where": where, "$limit": 500})
        all_results[ds_name] = res
    except Exception as e:
        all_results[ds_name] = {"error": str(e)}
```

### 6.4 Name-Based Search (Fallback)

```python
# When NIT search returns empty, try text search
params = {"$q": "SUPREMA", "$limit": 100}
results = client.get("jbjy-vk9h", params)
```

### 6.5 Filter by Date Range

```python
where = (
    f"documento_proveedor='{nit}' "
    f"AND fecha_de_firma >= '2022-01-01T00:00:00.000'"
)
params = {"$where": where, "$limit": 500}
results = client.get("jbjy-vk9h", params)
```

---

## 7. Output Formatting

### 7.1 Standard Report Structure

```markdown
## SECOP II Query Results — [Company Name]
**NIT:** [NIT]  
**Query Date:** [YYYY-MM-DD HH:MM]  
**Datasets Checked:** [List]

### 7.1.1 Contracts (jbjy-vk9h)
| Contract ID | Entity | Value | Paid | Pending | Status | Start Date | End Date |
|-------------|--------|-------|------|---------|--------|------------|----------|
| ... | ... | ... | ... | ... | ... | ... | ... |

**Summary:**
- Total contracts: [N]
- Total value: $[X]
- Total paid: $[Y]
- Total pending: $[Z]
- Active contracts: [N]
- Canceled contracts: [N]

### 7.1.2 Processes (p6dx-8zbt)
| Process ID | Entity | Awarded Value | Status | Award Date |
|------------|--------|---------------|--------|------------|
| ... | ... | ... | ... | ... |

### 7.1.3 Sanctions
| Dataset | Sanctions Found | Details |
|---------|-----------------|---------|
| SECOP II | [N] | ... |
| SECOP I | [N] | ... |
| SIRI | [N] | ... |

### 7.1.4 Supplier Registry (qmzu-gj57)
- **Status:** [Active/Inactive]
- **Registered:** [Date]
- **Location:** [City, Department]
- **Legal Rep:** [Name]

---
**Risk Assessment:** [LOW / MEDIUM / HIGH]  
**Key Findings:** [Bulleted list]
```

### 7.2 Excel Export Structure

| Sheet Name | Content |
|------------|---------|
| `Resumen` | Summary table with all companies and datasets |
| `Contratos` | Raw data from jbjy-vk9h |
| `Procesos` | Raw data from p6dx-8zbt |
| `Proveedores` | Raw data from qmzu-gj57 |
| `Sanciones_II` | Raw data from it5q-hg94 |
| `Sanciones_I` | Raw data from 4n4q-k399 |
| `SIRI` | Raw data from iaeu-rcn6 |
| `Integrado` | Raw data from rpmr-utcd |

---

## 8. Error Handling

| Error | Cause | Resolution |
|-------|-------|------------|
| `403 Invalid app_token` | sodapy passing invalid token | Use `requests` directly without token header |
| `401 Unauthorized` | Invalid credentials | Check `.env` file; verify username/password |
| `404 Not Found` | Dataset ID changed | Check current ID at datos.gov.co |
| `400 Bad Request` | Malformed SoQL | Review WHERE clause syntax; use single quotes |
| Empty results | NIT not in dataset | Try alternate NIT format; use text search (`$q`) |
| Timeout | Large query | Reduce `$limit`; add date filters |

---

## 9. Advanced Patterns

### 9.1 Check Contract Execution Health

```python
def analyze_contract_health(records):
    """Flags contracts with payment or execution issues."""
    flags = []
    for r in records:
        total = float(r.get("valor_del_contrato", 0) or 0)
        paid = float(r.get("valor_pagado", 0) or 0)
        pending = float(r.get("valor_pendiente_de_pago", 0) or 0)
        status = r.get("estado_contrato", "").lower()
        
        if status == "cancelado":
            flags.append(f"CANCELED: {r.get('id_contrato')} — ${total:,.0f}")
        elif pending > total * 0.5:
            flags.append(f"HIGH_PENDING: {r.get('id_contrato')} — pending=${pending:,.0f}")
        elif paid == 0 and total > 0:
            flags.append(f"UNPAID: {r.get('id_contrato')} — ${total:,.0f}")
    return flags
```

### 9.2 Detect Duplicate Adjudications

```python
from collections import Counter

process_ids = [r.get("id_del_proceso") for r in processes]
duplicates = {k: v for k, v in Counter(process_ids).items() if v > 1}
```

### 9.3 Aggregate by Entity

```python
import pandas as pd

# Group contracts by government entity
df = pd.DataFrame(records)
entity_summary = df.groupby("nombre_entidad").agg({
    "valor_del_contrato": "sum",
    "valor_pagado": "sum",
    "id_contrato": "count"
}).rename(columns={"id_contrato": "contract_count"})
```

---

## 10. Integration with Due Diligence Reports

When this skill is invoked as part of a due diligence workflow:

1. **Input:** Company name + NIT (from user or predefined list)
2. **Execute:** Query all 7 datasets
3. **Analyze:** Cross-reference with risk criteria:
   - Any canceled contract → **HIGH risk flag**
   - Pending payments > 50% → **MEDIUM risk flag**
   - No contracts found + company claims experience → **MEDIUM risk flag**
   - Sanctions found → **HIGH risk flag**
   - Inactive supplier registry → **HIGH risk flag**
4. **Output:** Append SECOP findings to the due diligence report in section format (see §7.1)

---

## 11. Hybrid Launcher & MCP Server

The project now ships as a single hybrid executable that can run in **GUI mode** (default) or **MCP Server mode** (`--mcp`).

### 11.1 Files

| File | Purpose |
|------|---------|
| `secop_hibrido.py` | Unified entry point. Detects `--mcp` flag and routes to GUI or MCP server. |
| `app_secop.py` | Desktop GUI (tkinter) with lazy-loading pagination, parallel queries, Excel/CSV export. |
| `mcp_secop.py` | FastMCP server exposing SECOP datasets as tools for LLMs (Claude, ChatGPT, etc.). |
| `dist/SECOP_Hibrido.exe` | Compiled PyInstaller executable (~38 MB). Supports both modes. |

### 11.2 GUI Mode (Default)

Double-click `dist/SECOP_Hibrido.exe` or run:
```bash
.\dist\SECOP_Hibrido.exe
```

Features:
- **Lazy-loading pagination**: Loads 50 rows at a time with Next/Prev buttons.
- **Parallel dataset queries**: Searches up to 7 datasets concurrently using thread-local `requests.Session`.
- **Entity & UNSPSC filters**: Dropdowns populated from historical JSON files.
- **Full export**: Excel/CSV export downloads **all pages** in a background thread.
- **Historical persistence**: `empresas_historial.json` + `entidades_historial.json` with add/delete UI.

### 11.3 MCP Server Mode (stdio)

Launch the MCP server for LLM integration via stdio (Claude Desktop lo inicia como subproceso):
```bash
.\dist\SECOP_Hibrido.exe --mcp
```

Configure in **Claude Desktop** (`%APPDATA%\Claude\settings.json`):
```json
{
  "mcpServers": {
    "secop": {
      "command": "D:/.../dist/SECOP_Hibrido.exe",
      "args": ["--mcp"]
    }
  }
}
```

### 11.4 MCP Server Mode (SSE + HTTPS) — desde el GUI

El panel **MCP Server** en la parte inferior del GUI permite encender/apagar el servidor MCP de forma interactiva. Usa **HTTPS** en `localhost` para cumplir con los requisitos de seguridad de Claude Desktop.

**Funcionamiento:**
1. Haga clic en **Iniciar**.
2. La app genera automáticamente un certificado autofirmado (`secop-localhost.crt` + `.key`).
3. Intenta instalar el certificado en el **Almacén de confianza de Windows** (requiere UAC la primera vez).
4. Si el puerto 8000 está ocupado, pregunta si desea usar `8001`, `8002`, etc.
5. El estado cambia a 🟢 **Corriendo (HTTPS)** y muestra la URL.
6. Haga clic en **Copiar config Claude** para obtener el JSON listo para pegar en `settings.json`.

Configuración resultante:
```json
{
  "mcpServers": {
    "secop": {
      "url": "https://localhost:8000/sse"
    }
  }
}
```

> **Nota:** Si la instalación automática del certificado falla, instálelo manualmente: doble clic en `secop-localhost.crt` → Instalar certificado → Equipo local → Autoridades de certificación raíz de confianza.

### 11.4 MCP Tools Reference

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `secop_query_contracts` | Query **Contratos Electronicos** (`jbjy-vk9h`) | `nit`, `nombre`, `entidad`, `fecha_inicio`, `fecha_fin`, `limit` |
| `secop_query_processes` | Query **Procesos de Contratacion** (`p6dx-8zbt`) | `nit`, `nombre`, `entidad`, `fecha_inicio`, `fecha_fin`, `limit` |
| `secop_query_integrated` | Query **SECOP Integrado** (`rpmr-utcd`) | `nit`, `nombre`, `entidad`, `fecha_inicio`, `fecha_fin`, `limit` |
| `secop_query_suppliers` | Query **Proveedores Registrados** (`qmzu-gj57`) | `nit`, `nombre`, `limit` |
| `secop_query_sanctions` | Query **Multas y Sanciones** (SECOP II + SECOP I) | `nit`, `nombre`, `limit` |
| `secop_query_siri` | Query **Antecedentes SIRI** (`iaeu-rcn6`) | `nit`, `nombre`, `limit` |
| `secop_query_unified` | Query **all 7 datasets in parallel** | `nit`, `nombre`, `entidad`, `fecha_inicio`, `fecha_fin`, `limit` |
| `secop_company_overview` | High-level summary of a supplier | `nit`, `nombre` |
| `secop_full_due_diligence` | Comprehensive due diligence report | `nit`, `nombre`, `incluir_historial` |
| `secop_analyze_contracts` | Analyze contract execution health | `nit`, `nombre`, `entidad`, `fecha_inicio`, `fecha_fin` |

**Query logic:**
- If `nit` is provided → searches by exact NIT in the dataset's NIT column.
- If only `nombre` is provided → uses full-text search (`$q`) for fast multi-column matching.
- If `entidad` is provided → additionally filters by entity name (exact NIT if numeric, otherwise `$q`).
- Date filters use `fecha_de_firma` (contracts), `fecha_adjudicacion` (processes), or `fecha_de_inicio` (integrated).

### 11.5 Thread Safety

- `requests.Session` is **not thread-safe**.
- The GUI spawns a new thread per search; each thread creates its own `SECOPClient` instance.
- The MCP server runs tools sequentially by default; each tool call instantiates a fresh client.

---

## 12. Command Reference

### 11.1 Running the GUI App
```bash
# Windows (PowerShell)
.\venv_secop\Scripts\activate
python app_secop.py
```

### 11.2 Running Tests
```bash
# Diagnose API connectivity
.\venv_secop\Scripts\python.exe test_socrata.py
```

### 11.3 Quick API Check
```bash
# Test public access
python -c "import requests; r = requests.get('https://www.datos.gov.co/resource/p6dx-8zbt.json?\$limit=1'); print(r.status_code, len(r.json()))"

# Test authenticated access
python -c "import requests; r = requests.get('https://www.datos.gov.co/resource/p6dx-8zbt.json?\$limit=1', auth=('user', 'pass')); print(r.status_code, len(r.json()))"
```

---

## 13. Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-05-11 | Initial release with sodapy |
| 1.1.0 | 2026-05-11 | **FIX:** Replaced sodapy with requests due to invalid app_token errors. Now uses Basic Auth or public mode. |
| 1.2.0 | 2026-05-11 | **NEW:** Hybrid launcher (`secop_hibrido.py`) + compiled EXE (`dist/SECOP_Hibrido.exe`). Supports GUI mode (default) and MCP Server mode (`--mcp`). Added 10+ MCP tools for LLM integration (Claude Desktop, ChatGPT Desktop). |
| 1.2.1 | 2026-05-11 | **NEW:** Panel MCP Server en el GUI con HTTPS. Genera certificado autofirmado para `localhost`, detecta puertos ocupados con fallback, e integra botón para copiar configuración Claude Desktop SSE. |

---

## 14. References

- Socrata API Docs: https://dev.socrata.com/
- SECOP II Datasets: https://www.datos.gov.co/browse?q=SECOP
- Colombia Compra Eficiente: https://colombiacompra.gov.co
- SoQL Query Language: https://dev.socrata.com/docs/queries/

---

**END OF SKILL**
