# -*- coding: utf-8 -*-
"""Filtros de busqueda y su traduccion a parametros Socrata. Sin Tk ni red."""
import json
import re
from dataclasses import asdict, dataclass
from datetime import date, timedelta

from storage import nit_canonico

_FECHA_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DIGITOS_RE = re.compile(r"^[0-9]+$")
CAMPOS_FECHA = ("fecha_desde", "fecha_hasta")


def escapar_soql(val):
    return str(val).replace("'", "''")


def construir_where(conds):
    return " AND ".join(conds) if conds else ""


def _digitos(valor):
    return re.sub(r"[.\s$,]", "", str(valor or ""))


def _fecha_valida(txt):
    if not _FECHA_RE.match(txt):
        return None
    try:
        return date.fromisoformat(txt)
    except ValueError:
        return None


@dataclass
class Filtros:
    texto: str = ""
    nit_proveedor: str = ""
    entidad_nombre: str = ""
    entidad_nit: str = ""
    unspsc: str = ""
    fecha_desde: str = ""
    fecha_hasta: str = ""
    valor_min: str = ""
    valor_max: str = ""
    modalidad: str = ""
    estado: str = ""
    departamento: str = ""

    def limpio(self):
        """Copia sin espacios sobrantes y con los NIT canonicos (sin puntos, guion ni
        espacios): '900.123.456-7' se acepta en la UI pero a SoQL va '9001234567'."""
        f = Filtros(**{k: str(v or "").strip() for k, v in asdict(self).items()})
        f.nit_proveedor = nit_canonico(f.nit_proveedor)
        f.entidad_nit = nit_canonico(f.entidad_nit)
        return f

    def vacio(self):
        """True si no hay ningun criterio. Las fechas NO cuentan: un rango solo
        (p. ej. el 'ultimo año' por defecto) no es un criterio de busqueda."""
        return not any(str(v or "").strip() for k, v in asdict(self).items()
                       if k not in CAMPOS_FECHA)

    def a_dict(self, incluir_fechas=True):
        return {k: v for k, v in asdict(self.limpio()).items()
                if v and (incluir_fechas or k not in CAMPOS_FECHA)}

    @classmethod
    def desde_dict(cls, d):
        d = d or {}
        return cls(**{k: str(d.get(k) or "") for k in cls.__dataclass_fields__})

    def errores(self):
        f = self.limpio()
        errs = []
        desde = hasta = None
        if f.fecha_desde:
            desde = _fecha_valida(f.fecha_desde)
            if desde is None:
                errs.append("Fecha 'desde' invalida (use AAAA-MM-DD).")
        if f.fecha_hasta:
            hasta = _fecha_valida(f.fecha_hasta)
            if hasta is None:
                errs.append("Fecha 'hasta' invalida (use AAAA-MM-DD).")
        if desde and hasta and desde > hasta:
            errs.append("La fecha 'desde' es posterior a 'hasta'.")
        vmin = vmax = None
        for etiqueta, txt in (("minimo", f.valor_min), ("maximo", f.valor_max)):
            if not txt:
                continue
            dig = _digitos(txt)
            if not _DIGITOS_RE.match(dig):
                errs.append(f"Valor {etiqueta} invalido (solo numeros).")
            elif etiqueta == "minimo":
                vmin = int(dig)
            else:
                vmax = int(dig)
        if vmin is not None and vmax is not None and vmin > vmax:
            errs.append("El valor minimo supera al maximo.")
        return errs


# Columnas verificadas contra la API real (octubre 2026). None = el dataset no
# tiene esa columna y, si el filtro esta activo, el dataset se omite.
CAMPOS_DATASET = {
    "jbjy-vk9h": dict(
        nit_proveedor="documento_proveedor", entidad_nit="nit_entidad",
        entidad_nombre="nombre_entidad", unspsc="codigo_de_categoria_principal",
        fecha="fecha_de_firma", valor="valor_del_contrato",
        modalidad="modalidad_de_contratacion", estado="estado_contrato",
        departamento="departamento", orden="fecha_de_firma DESC"),
    "p6dx-8zbt": dict(
        nit_proveedor="nit_del_proveedor_adjudicado", entidad_nit="nit_entidad",
        entidad_nombre="entidad", unspsc="codigo_principal_de_categoria",
        fecha="fecha_de_publicacion_del", valor="precio_base",
        modalidad="modalidad_de_contratacion", estado="estado_del_procedimiento",
        departamento="departamento_entidad", orden="fecha_adjudicacion DESC"),
    "rpmr-utcd": dict(
        nit_proveedor="documento_proveedor", entidad_nit="nit_de_la_entidad",
        entidad_nombre="nombre_de_la_entidad", unspsc=None,
        fecha="fecha_de_firma_del_contrato", valor="valor_contrato",
        modalidad="modalidad_de_contrataci_n", estado="estado_del_proceso",
        departamento="departamento_entidad", orden="fecha_de_firma_del_contrato DESC"),
}


def _like_upper(col, txt):
    return f"upper({col}) LIKE '%{escapar_soql(txt.upper())}%'"


def condiciones(dataset_id, filtros):
    """(conds, q_text) o None si el dataset no puede aplicar un filtro activo."""
    f = filtros.limpio()
    m = CAMPOS_DATASET[dataset_id]
    conds, partes_q = [], []
    general = not f.nit_proveedor
    if f.texto:
        partes_q.append(f.texto)
    if f.nit_proveedor:
        conds.append(f"{m['nit_proveedor']}='{escapar_soql(f.nit_proveedor)}'")
    if f.entidad_nit:
        conds.append(f"{m['entidad_nit']}='{escapar_soql(f.entidad_nit)}'")
    if f.entidad_nombre and not f.entidad_nit:   # con NIT, el nombre (alias, "Nombre (NIT)") sobra
        if general:
            partes_q.append(f.entidad_nombre)
        else:
            conds.append(_like_upper(m["entidad_nombre"], f.entidad_nombre))
    if f.unspsc:
        if m["unspsc"] is None:
            return None
        conds.append(f"{m['unspsc']} LIKE '%{escapar_soql(f.unspsc)}%'")
    if f.fecha_desde:
        conds.append(f"{m['fecha']} >= '{f.fecha_desde}T00:00:00'")
    if f.fecha_hasta:
        conds.append(f"{m['fecha']} <= '{f.fecha_hasta}T23:59:59'")
    if f.valor_min:
        conds.append(f"{m['valor']} >= {int(_digitos(f.valor_min))}")
    if f.valor_max:
        conds.append(f"{m['valor']} <= {int(_digitos(f.valor_max))}")
    for clave, valor in (("modalidad", f.modalidad), ("estado", f.estado),
                         ("departamento", f.departamento)):
        if valor:
            if m[clave] is None:
                return None
            conds.append(_like_upper(m[clave], valor))
    return conds, (" ".join(partes_q) or None)


CAMPOS_AVANZADOS = (("valor_min", "Valor min"), ("valor_max", "Valor max"),
                    ("estado", "Estado"), ("departamento", "Departamento"),
                    ("modalidad", "Modalidad"))


def _avanzados(filtros):
    f = filtros.limpio()
    return [(etiqueta, getattr(f, campo)) for campo, etiqueta in CAMPOS_AVANZADOS
            if getattr(f, campo)]


def n_avanzados(filtros):
    return len(_avanzados(filtros))


def descripcion_avanzados(filtros):
    """'Filtros avanzados: Estado: activo, ...' o '' si no hay ninguno activo."""
    activos = _avanzados(filtros)
    if not activos:
        return ""
    return "Filtros avanzados: " + ", ".join(f"{e}: {v}" for e, v in activos)


def orden_dataset(dataset_id, filtros):
    f = filtros.limpio()
    if dataset_id == "p6dx-8zbt" and not f.nit_proveedor:
        return "fecha_de_publicacion_del DESC"
    return CAMPOS_DATASET[dataset_id]["orden"]


# ---- rangos de fecha: por defecto el ultimo año, en todas las consultas -------------
RANGOS = {
    "ultimo_anio": ("Último año", 365),
    "6_meses": ("Últimos 6 meses", 182),
    "3_meses": ("Últimos 3 meses", 91),
    "30_dias": ("Últimos 30 días", 30),
    "5_anios": ("Últimos 5 años", 1826),
    "todo": ("Todo el historial", None),
}
MODO_PERSONALIZADO = "personalizado"
ETIQUETA_PERSONALIZADO = "Personalizado"
RANGO_POR_DEFECTO = {"modo": "ultimo_anio"}


def rango_predefinido(clave, hoy=None):
    """(desde, hasta) como 'AAAA-MM-DD'; ('', '') = sin limite. KeyError si no existe."""
    hoy = hoy or date.today()
    dias = RANGOS[clave][1]
    if dias is None:
        return "", ""
    return (hoy - timedelta(days=dias)).isoformat(), hoy.isoformat()


def con_rango(filtros, rango, hoy=None):
    """Copia de `filtros` con fecha_desde/fecha_hasta segun `rango`
    ({'modo': clave} o {'modo': 'personalizado', 'desde': ..., 'hasta': ...})."""
    f = filtros.limpio()
    rango = rango or RANGO_POR_DEFECTO
    modo = rango.get("modo", "ultimo_anio")
    if modo == MODO_PERSONALIZADO:
        f.fecha_desde = str(rango.get("desde") or "").strip()
        f.fecha_hasta = str(rango.get("hasta") or "").strip()
    else:
        f.fecha_desde, f.fecha_hasta = rango_predefinido(modo if modo in RANGOS else "ultimo_anio", hoy)
    return f


def descripcion_rango(filtros):
    f = filtros.limpio()
    if f.fecha_desde and f.fecha_hasta:
        return f"Fechas: {f.fecha_desde} a {f.fecha_hasta}"
    if f.fecha_desde:
        return f"Fechas: desde {f.fecha_desde}"
    if f.fecha_hasta:
        return f"Fechas: hasta {f.fecha_hasta}"
    return "Fechas: todo el historial"


def identificar_fila(fila):
    return "|".join(str(fila.get(k) or "") for k in
                    ("fuente", "id_contrato", "referencia", "entidad_nit", "entidad", "fecha_firma"))


def marcar_nuevas(filas, ids_previos):
    previos = set(ids_previos)
    return [f for f in filas
            if f.get("fuente") != "—" and identificar_fila(f) not in previos]


def url_de(valor):
    if isinstance(valor, dict):
        return str(valor.get("url") or "")
    if isinstance(valor, str):
        t = valor.strip()
        if t.startswith("{"):
            try:
                return str(json.loads(t).get("url") or "")
            except (ValueError, AttributeError):
                return ""
        return t if t.startswith(("http://", "https://")) else ""
    return ""


def primer_valor_positivo(*valores):
    for v in valores:
        try:
            if float(v) > 0:
                return str(v)
        except (TypeError, ValueError):
            continue
    return ""


def parametros_proveedor_por_nombre(texto, limite=50):
    palabras = [p for p in str(texto or "").upper().split() if p]
    if sum(len(p) for p in palabras) < 3:
        raise ValueError("Escriba al menos 3 caracteres.")
    where = " AND ".join(f"upper(nombre) LIKE '%{escapar_soql(p)}%'" for p in palabras)
    return {"$where": where, "$select": "nit,nombre,departamento,municipio,esta_activa",
            "$order": "nombre", "$limit": limite}


def buscar_proveedores(client, texto, limite=50):
    return client.get("qmzu-gj57", parametros_proveedor_por_nombre(texto, limite), timeout=60)


def resolver_nombre_oficial(client, nit):
    filas = client.get("qmzu-gj57", {"$where": f"nit='{escapar_soql(nit)}'",
                                     "$select": "nombre", "$limit": 1}, timeout=60)
    return (filas[0].get("nombre") or "").strip() if filas else ""
