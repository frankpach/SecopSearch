from datetime import date

import pytest

from search import (
    ETIQUETA_PERSONALIZADO, RANGOS, Filtros, buscar_proveedores, condiciones, con_rango,
    construir_where, descripcion_rango, escapar_soql, identificar_fila, marcar_nuevas,
    orden_dataset, parametros_proveedor_por_nombre, primer_valor_positivo, rango_predefinido,
    resolver_nombre_oficial, url_de,
)


class ClienteFalso:
    def __init__(self, respuesta):
        self.respuesta, self.llamadas = respuesta, []

    def get(self, dataset_id, params=None, timeout=120):
        self.llamadas.append((dataset_id, params))
        return self.respuesta


def test_vacio_y_ida_y_vuelta_dict():
    assert Filtros().vacio() and Filtros(texto="  ").vacio()
    f = Filtros(texto="logistico", valor_min="1.000")
    assert not f.vacio()
    assert f.a_dict() == {"texto": "logistico", "valor_min": "1.000"}
    assert Filtros.desde_dict(f.a_dict()) == f
    assert Filtros.desde_dict(None) == Filtros()


def test_errores_de_validacion():
    assert Filtros(fecha_desde="2024-13-01").errores()
    assert Filtros(fecha_desde="24-1-1").errores()
    assert Filtros(fecha_desde="2024-05-02", fecha_hasta="2024-05-01").errores()
    assert Filtros(valor_min="abc").errores()
    assert Filtros(valor_min="²").errores()
    assert Filtros(valor_min="2.000.000", valor_max="1.000.000").errores()
    assert Filtros(valor_min="$1.000.000", fecha_desde="2024-01-01").errores() == []


def test_rango_predefinido():
    hoy = date(2026, 10, 6)
    assert rango_predefinido("ultimo_anio", hoy) == ("2025-10-06", "2026-10-06")
    assert rango_predefinido("30_dias", hoy) == ("2026-09-06", "2026-10-06")
    assert rango_predefinido("todo", hoy) == ("", "")
    with pytest.raises(KeyError):
        rango_predefinido("nada", hoy)


def test_con_rango_predefinido_personalizado_y_desconocido():
    hoy = date(2026, 10, 6)
    base = Filtros(texto="x")
    f = con_rango(base, {"modo": "ultimo_anio"}, hoy)
    assert (f.fecha_desde, f.fecha_hasta) == ("2025-10-06", "2026-10-06") and f.texto == "x"
    f = con_rango(base, {"modo": "personalizado", "desde": " 2024-01-01 ", "hasta": ""}, hoy)
    assert (f.fecha_desde, f.fecha_hasta) == ("2024-01-01", "")
    assert con_rango(base, {"modo": "inventado"}, hoy).fecha_desde == "2025-10-06"   # desconocido: ultimo año
    assert con_rango(base, None, hoy).fecha_desde == "2025-10-06"
    assert con_rango(base, {"modo": "todo"}, hoy).fecha_desde == ""
    assert base.fecha_desde == ""                                   # no muta el original


def test_el_rango_nunca_cuenta_como_criterio():
    assert Filtros(fecha_desde="2024-01-01", fecha_hasta="2024-12-31").vacio()
    assert not Filtros(texto="x", fecha_desde="2024-01-01").vacio()
    assert con_rango(Filtros(), {"modo": "ultimo_anio"}).vacio()


def test_a_dict_puede_omitir_las_fechas():
    f = Filtros(texto="x", fecha_desde="2024-01-01")
    assert f.a_dict() == {"texto": "x", "fecha_desde": "2024-01-01"}
    assert f.a_dict(incluir_fechas=False) == {"texto": "x"}


def test_descripcion_rango():
    assert descripcion_rango(Filtros()) == "Fechas: todo el historial"
    assert descripcion_rango(Filtros(fecha_desde="2025-10-06", fecha_hasta="2026-10-06")) == \
        "Fechas: 2025-10-06 a 2026-10-06"
    assert descripcion_rango(Filtros(fecha_desde="2025-10-06")) == "Fechas: desde 2025-10-06"
    assert descripcion_rango(Filtros(fecha_hasta="2026-10-06")) == "Fechas: hasta 2026-10-06"


def test_etiquetas_de_rangos_unicas_y_distintas_de_personalizado():
    etiquetas = [e for e, _ in RANGOS.values()]
    assert len(set(etiquetas)) == len(etiquetas) and ETIQUETA_PERSONALIZADO not in etiquetas
    assert RANGOS["ultimo_anio"][0] == "Último año" and RANGOS["30_dias"][0] == "Últimos 30 días"
    assert RANGOS["6_meses"][0] == "Últimos 6 meses"


def test_comillas_se_escapan_en_texto_y_entidad():
    assert escapar_soql("O'Brien") == "O''Brien"
    conds, q = condiciones("p6dx-8zbt", Filtros(entidad_nombre="O'Brien", nit_proveedor="900123456"))
    assert "upper(entidad) LIKE '%O''BRIEN%'" in conds
    assert "nit_del_proveedor_adjudicado='900123456'" in conds
    assert q is None


def test_inyeccion_en_nit_y_estado_queda_escapada():
    conds, _ = condiciones("jbjy-vk9h", Filtros(nit_proveedor="1' OR '1'='1", estado="x'--"))
    texto = " ".join(conds)
    # el NIT se canonicaliza (sin espacios) y las comillas siguen duplicadas
    assert "documento_proveedor='1''OR''1''=''1'" in texto
    assert "LIKE '%X''--%'" in texto


def test_porcentaje_y_tildes_pasan_sin_romper():
    conds, q = condiciones("p6dx-8zbt", Filtros(texto="100% logística", modalidad="Contratación directa"))
    assert q == "100% logística"
    assert "upper(modalidad_de_contratacion) LIKE '%CONTRATACIÓN DIRECTA%'" in conds


def test_busqueda_general_usa_q_para_entidad_y_texto():
    conds, q = condiciones("jbjy-vk9h", Filtros(texto="logistico", entidad_nombre="Alcaldia"))
    assert conds == [] and q == "logistico Alcaldia"


def test_con_proveedor_la_entidad_es_condicion_no_q():
    conds, q = condiciones("jbjy-vk9h", Filtros(nit_proveedor="900123456", entidad_nombre="Alcaldia"))
    assert q is None and "upper(nombre_entidad) LIKE '%ALCALDIA%'" in conds


def test_fechas_valores_departamento_procesos():
    f = Filtros(fecha_desde="2024-01-01", fecha_hasta="2024-12-31",
                valor_min="$1.000.000", valor_max="5000000", departamento="antioquia")
    conds, _ = condiciones("p6dx-8zbt", f)
    assert "fecha_de_publicacion_del >= '2024-01-01T00:00:00'" in conds
    assert "fecha_de_publicacion_del <= '2024-12-31T23:59:59'" in conds
    assert "precio_base >= 1000000" in conds and "precio_base <= 5000000" in conds
    assert "upper(departamento_entidad) LIKE '%ANTIOQUIA%'" in conds


def test_mapeo_de_columnas_por_dataset():
    f = Filtros(entidad_nit="800000001", valor_min="1", modalidad="directa", estado="activo")
    c, _ = condiciones("jbjy-vk9h", f)
    assert "nit_entidad='800000001'" in c and "valor_del_contrato >= 1" in c
    assert "upper(estado_contrato) LIKE '%ACTIVO%'" in c
    i, _ = condiciones("rpmr-utcd", f)
    assert "nit_de_la_entidad='800000001'" in i and "valor_contrato >= 1" in i
    assert "upper(modalidad_de_contrataci_n) LIKE '%DIRECTA%'" in i
    assert "upper(estado_del_proceso) LIKE '%ACTIVO%'" in i


def test_dataset_sin_columna_para_un_filtro_activo_se_omite():
    assert condiciones("rpmr-utcd", Filtros(unspsc="80111600")) is None
    assert condiciones("jbjy-vk9h", Filtros(unspsc="80111600")) is not None


def test_orden():
    assert orden_dataset("p6dx-8zbt", Filtros(texto="x")) == "fecha_de_publicacion_del DESC"
    assert orden_dataset("p6dx-8zbt", Filtros(nit_proveedor="9")) == "fecha_adjudicacion DESC"
    assert orden_dataset("jbjy-vk9h", Filtros()) == "fecha_de_firma DESC"
    assert orden_dataset("rpmr-utcd", Filtros()) == "fecha_de_firma_del_contrato DESC"


def test_construir_where():
    assert construir_where(["a=1", "b=2"]) == "a=1 AND b=2"
    assert construir_where([]) == ""


def test_identificar_y_marcar_nuevas():
    a = {"fuente": "SECOP II", "id_contrato": "C1", "referencia": "R", "entidad_nit": "1",
         "entidad": "E", "fecha_firma": "2024-01-01"}
    b = dict(a, id_contrato="C2")
    sin = {"fuente": "—", "id_contrato": ""}
    assert identificar_fila(a) != identificar_fila(b)
    assert marcar_nuevas([a, b, sin], [identificar_fila(a)]) == [b]
    assert marcar_nuevas([a], []) == [a]


def test_url_de():
    assert url_de({"url": "https://x"}) == "https://x"
    assert url_de('{"url": "https://y"}') == "https://y"
    assert url_de("https://z") == "https://z"
    assert url_de(None) == "" and url_de("texto raro") == ""


def test_primer_valor_positivo():
    assert primer_valor_positivo("0", "", None, "65000000.5") == "65000000.5"
    assert primer_valor_positivo("0", "") == ""


def test_parametros_proveedor_por_nombre():
    p = parametros_proveedor_por_nombre("seguridad pegaso")
    assert p["$where"] == "upper(nombre) LIKE '%SEGURIDAD%' AND upper(nombre) LIKE '%PEGASO%'"
    assert p["$limit"] == 50
    assert "O''BRIEN" in parametros_proveedor_por_nombre("o'brien sas")["$where"]
    with pytest.raises(ValueError):
        parametros_proveedor_por_nombre("ab")


def test_buscar_proveedores_y_resolver_nombre():
    cli = ClienteFalso([{"nit": "900123456", "nombre": "ACME SAS"}])
    assert buscar_proveedores(cli, "acme")[0]["nit"] == "900123456"
    assert cli.llamadas[0][0] == "qmzu-gj57"
    assert resolver_nombre_oficial(cli, "900123456") == "ACME SAS"
    assert cli.llamadas[1][1]["$where"] == "nit='900123456'"
    assert resolver_nombre_oficial(ClienteFalso([]), "1") == ""


# ---- revision final: el nombre visible no es criterio; NIT canonico; avanzados --------

def test_con_nit_de_entidad_el_nombre_no_se_usa_como_criterio():
    f = Filtros(entidad_nombre="Alcaldia Medellin (cliente VIP)", entidad_nit="890905211")
    conds, q = condiciones("jbjy-vk9h", f)                  # busqueda general
    assert q is None and conds == ["nit_entidad='890905211'"]
    conds, q = condiciones("jbjy-vk9h", Filtros(nit_proveedor="900123456",
                                               entidad_nombre="Alias", entidad_nit="890905211"))
    assert not any("nombre_entidad" in c for c in conds)
    conds, q = condiciones("jbjy-vk9h", Filtros(entidad_nombre="Alcaldia"))   # sin NIT: si
    assert q == "Alcaldia"


def test_nits_con_puntos_y_guion_se_envian_canonicos():
    conds, _ = condiciones("jbjy-vk9h", Filtros(nit_proveedor="900.123.456-7",
                                               entidad_nit=" 800.000.001 "))
    assert "documento_proveedor='9001234567'" in conds
    assert "nit_entidad='800000001'" in conds


def test_descripcion_de_filtros_avanzados():
    from search import descripcion_avanzados, n_avanzados
    f = Filtros(texto="x", estado="activo", valor_min="1.000", modalidad="Directa")
    assert n_avanzados(f) == 3
    d = descripcion_avanzados(f)
    assert "Estado: activo" in d and "Valor min: 1.000" in d and "Modalidad: Directa" in d
    assert descripcion_avanzados(Filtros(texto="x")) == "" and n_avanzados(Filtros()) == 0
