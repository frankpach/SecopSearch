# -*- coding: utf-8 -*-
"""Utilidades puras de tabla (sin Tk): valores crudos vs visibles, orden por
tipo y serializacion de filas a TSV/CSV/JSON."""
import csv
import io
import json
import re
from datetime import date

_PESOS_RE = re.compile(r"^\$\s*-?\d{1,3}(\.\d{3})*$")
# Fecha sola o marca ISO de Socrata ('2025-03-01T00:00:00.000'): se toma la fecha
_FECHA_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})"
                       r"(?:[T ]([01]\d|2[0-3]):[0-5]\d(?::[0-5]\d(?:\.\d+)?)?"
                       r"(?:Z|[+-]\d{2}:?\d{2})?)?$")
_NUM_RE = re.compile(r"^-?\d+(\.\d+)?$")


def _texto(valor):
    if valor is None:
        return ""
    if isinstance(valor, dict):
        if "url" in valor:
            return str(valor["url"])
        return json.dumps(valor, ensure_ascii=False)
    if isinstance(valor, (list, tuple)):
        return json.dumps(valor, ensure_ascii=False)
    return str(valor)


def parse_pesos(texto):
    """'$1.234.567' -> 1234567; cualquier otra cosa -> None."""
    if texto is None:
        return None
    t = str(texto).strip()
    if not _PESOS_RE.match(t):
        return None
    return int(t.replace("$", "").replace(".", "").strip())


def parse_fecha(texto):
    t = str(texto or "").strip()
    m = _FECHA_RE.match(t)
    if not m:
        return None
    try:
        return date.fromisoformat(m.group(1))
    except ValueError:
        return None


def valor_visible(valor):
    return _texto(valor)


def valor_crudo(valor):
    """Pesos formateados -> int; numeros se dejan; el resto como texto."""
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        return valor
    texto = _texto(valor)
    n = parse_pesos(texto)
    return n if n is not None else texto


def clave_orden(valor):
    """(0, numero) | (1, fecha ordinal) | (2, texto en minusculas)."""
    texto = _texto(valor).strip()
    n = parse_pesos(texto)
    if n is None and _NUM_RE.match(texto):
        n = float(texto)
    if n is not None:
        return (0, n)
    f = parse_fecha(texto)
    if f is not None:
        return (1, f.toordinal())
    return (2, texto.lower())


def ordenar_filas(filas, col, inverso=False):
    """Ordena por tipo real; las celdas vacias quedan siempre al final."""
    con = [f for f in filas if _texto(f.get(col)).strip() != ""]
    sin = [f for f in filas if _texto(f.get(col)).strip() == ""]
    con.sort(key=lambda f: clave_orden(f.get(col)), reverse=inverso)
    return con + sin


def _celda(valor, crudo):
    return valor_crudo(valor) if crudo else valor_visible(valor)


def _serializar(filas, columnas, encabezados, delimitador, crudo, con_encabezado):
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=delimitador, lineterminator="\n")
    if con_encabezado:
        w.writerow(encabezados or columnas)
    for f in filas:
        w.writerow([_celda(f.get(c), crudo) for c in columnas])
    out = buf.getvalue()
    return out[:-1] if out.endswith("\n") else out


def filas_a_tsv(filas, columnas, encabezados=None, con_encabezado=True, crudo=True):
    return _serializar(filas, columnas, encabezados, "\t", crudo, con_encabezado)


def filas_a_csv(filas, columnas, encabezados=None, con_encabezado=True,
                crudo=True, delimitador=","):
    return _serializar(filas, columnas, encabezados, delimitador, crudo, con_encabezado)


def filas_a_json(filas, columnas, crudo=True):
    datos = [{c: _celda(f.get(c), crudo) for c in columnas} for f in filas]
    return json.dumps(datos, ensure_ascii=False, indent=2)


def columnas_union(filas):
    """Union de claves en orden de primera aparicion (Socrata omite nulos)."""
    vistas = {}
    for f in filas:
        for k in f:
            vistas.setdefault(k, None)
    return list(vistas)


def texto_pantalla(valor, limite=80):
    """Recorta SOLO para mostrar en pantalla; nunca para copiar o exportar."""
    t = _texto(valor)
    return t if len(t) <= limite else t[: limite - 1] + "…"
