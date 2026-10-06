import pytest
import requests

import app_secop
from app_secop import SECOPClient, SECOPQuery
from search import Filtros


class ClienteFalso:
    def __init__(self, respuestas=None):
        self.llamadas, self.respuestas = [], respuestas or {}

    def get(self, dataset_id, params=None, timeout=120):
        self.llamadas.append((dataset_id, dict(params or {})))
        return list(self.respuestas.get(dataset_id, []))

    def datasets(self):
        return [d for d, _ in self.llamadas]


class Resp:
    def __init__(self, status, datos=None):
        self.status_code, self._d = status, datos

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def json(self):
        return self._d


def test_busqueda_general_por_texto_usa_q_y_no_consulta_sanciones():
    cli = ClienteFalso()
    q = SECOPQuery(cli)
    q.consultar_pagina(None, None, Filtros(texto="operador logistico"), page_size=50)
    assert set(cli.datasets()) == {"jbjy-vk9h", "p6dx-8zbt", "rpmr-utcd"}
    for _, params in cli.llamadas:
        assert params["$q"] == "operador logistico" and "$where" not in params
        assert params["$limit"] == 50
    orden = dict(cli.llamadas)["p6dx-8zbt"]["$order"]
    assert orden == "fecha_de_publicacion_del DESC"


def test_tamano_de_pagina_por_defecto_es_100_tambien_en_busqueda_general():
    cli = ClienteFalso()
    SECOPQuery(cli).consultar_pagina(None, None, Filtros(texto="x"))
    assert all(p["$limit"] == 100 for _, p in cli.llamadas)
    cli = ClienteFalso()
    SECOPQuery(cli).consultar_pagina(None, None, Filtros(texto="x"), page_size=500)
    assert all(p["$limit"] == 500 for _, p in cli.llamadas)          # sin tope oculto


def test_con_nit_aplica_filtro_exacto_y_consulta_sanciones():
    cli = ClienteFalso()
    SECOPQuery(cli).consultar_pagina("ACME", "900123456", Filtros(entidad_nombre="Alcaldia"))
    por_ds = dict(cli.llamadas)
    assert "documento_proveedor='900123456'" in por_ds["jbjy-vk9h"]["$where"]
    assert "upper(nombre_entidad) LIKE '%ALCALDIA%'" in por_ds["jbjy-vk9h"]["$where"]
    assert {"qmzu-gj57", "it5q-hg94", "4n4q-k399", "iaeu-rcn6"} <= set(cli.datasets())


def test_dataset_sin_columna_del_filtro_se_omite_y_se_informa():
    cli = ClienteFalso()
    q = SECOPQuery(cli)
    q.consultar_pagina(None, None, Filtros(unspsc="80111600"))
    assert "rpmr-utcd" not in cli.datasets()
    assert q.omitidos == ["SECOP Integrado"]


def test_filas_conservan_objeto_completo_y_url_de_proceso():
    largo = "o" * 300
    cli = ClienteFalso({
        "jbjy-vk9h": [{"id_contrato": "C1", "objeto_del_contrato": largo,
                       "valor_del_contrato": "1500000"}],
        "p6dx-8zbt": [{"id_del_proceso": "P1", "nombre_del_procedimiento": largo,
                       "valor_total_adjudicacion": "0", "precio_base": "65000000",
                       "urlproceso": {"url": "https://community.secop.gov.co/p1"}}],
        "rpmr-utcd": [{"numero_del_contrato": "N1", "objeto_a_contratar": largo,
                       "url_contrato": "https://community.secop.gov.co/c1"}],
    })
    filas, detalle, errores, _ = SECOPQuery(cli).consultar_pagina(None, None, Filtros(texto="x"))
    por_fuente = {f["fuente"]: f for f in filas}
    assert por_fuente["SECOP II"]["objeto"] == largo
    assert por_fuente["Proceso"]["objeto"] == largo
    assert por_fuente["Proceso"]["valor"] == "$65.000.000"
    assert por_fuente["Proceso"]["url"] == "https://community.secop.gov.co/p1"
    assert por_fuente["SECOP I"]["objeto"] == largo
    assert por_fuente["SECOP I"]["url"] == "https://community.secop.gov.co/c1"
    assert errores == []


def test_sin_resultados_devuelve_fila_sin_contratos():
    filas, _, _, has_more = SECOPQuery(ClienteFalso()).consultar_pagina(None, None, Filtros(texto="x"))
    assert len(filas) == 1 and filas[0]["estado"] == "SIN CONTRATOS" and not has_more


class Paginado(ClienteFalso):
    """Contratos: 3 filas en la pagina 0, 1 en la 1; todo lo demas vacio."""

    def get(self, dataset_id, params=None, timeout=120):
        self.llamadas.append((dataset_id, dict(params or {})))
        if dataset_id == "jbjy-vk9h" and params.get("$offset") == 0:
            return [{"id_contrato": f"C{i}"} for i in range(3)]
        if dataset_id == "jbjy-vk9h" and params.get("$offset") == 3:
            return [{"id_contrato": "C3"}]
        return []


def test_iterar_paginas_genera_pagina_a_pagina_y_omite_el_relleno():
    q = SECOPQuery(Paginado())
    paginas = list(q.iterar_paginas(None, "900123456", Filtros(), page_size=3))
    assert [[f["id_contrato"] for f in filas if f["fuente"] == "SECOP II"]
            for filas, _ in paginas] == [["C0", "C1", "C2"], ["C3"]]
    assert all(f["fuente"] != "—" for filas, _ in paginas for f in filas)
    assert "Contratos SECOP II" in paginas[0][1]


def test_iterar_paginas_es_un_generador_perezoso():
    cli = Paginado()
    it = SECOPQuery(cli).iterar_paginas(None, "900123456", Filtros(), page_size=3)
    assert cli.llamadas == []                         # nada se consulta hasta pedir la primera
    next(it)
    n = len(cli.llamadas)
    assert n > 0
    next(it)
    assert len(cli.llamadas) > n


def test_iterar_paginas_respeta_la_cancelacion():
    q = SECOPQuery(Paginado())
    assert list(q.iterar_paginas(None, "900123456", Filtros(), page_size=3,
                                 cancelado=lambda: True)) == []


def test_iterar_paginas_se_detiene_si_no_hay_resultados_y_respeta_max_paginas():
    assert list(SECOPQuery(ClienteFalso()).iterar_paginas(None, "900123456", Filtros())) == []
    q = SECOPQuery(Paginado())
    assert len(list(q.iterar_paginas(None, "900123456", Filtros(), page_size=3, max_paginas=1))) == 1


def test_contar_suma_por_dataset_con_q_y_where():
    class Contador(ClienteFalso):
        def get(self, dataset_id, params=None, timeout=120):
            self.llamadas.append((dataset_id, dict(params or {})))
            return [{"count": {"jbjy-vk9h": "12", "p6dx-8zbt": "30", "rpmr-utcd": "5"}[dataset_id]}]
    cli = Contador()
    cont = SECOPQuery(cli).contar(None, None, Filtros(texto="x", fecha_desde="2025-01-01"))
    assert cont == {"SECOP II - Contratos": 12, "SECOP II - Procesos": 30, "SECOP Integrado": 5}
    for _, p in cli.llamadas:
        assert p["$select"] == "count(*)" and p["$q"] == "x"
        assert "$order" not in p and "$limit" not in p
        assert "T00:00:00" in p["$where"]


def test_contar_omite_los_datasets_que_no_soportan_el_filtro():
    class Contador(ClienteFalso):
        def get(self, dataset_id, params=None, timeout=120):
            self.llamadas.append((dataset_id, dict(params or {})))
            return [{"count": "7"}]
    cli = Contador()
    cont = SECOPQuery(cli).contar(None, None, Filtros(unspsc="80111600"))
    assert cont["SECOP Integrado"] == 0 and "rpmr-utcd" not in cli.datasets()
    assert cont["SECOP II - Contratos"] == 7


# --- reintentos del cliente ------------------------------------------------
def _cliente(monkeypatch, respuestas):
    cli = SECOPClient({})
    cli.session.get = lambda *a, **k: respuestas.pop(0)
    monkeypatch.setattr(app_secop.time, "sleep", lambda s: None)
    return cli


def test_reintenta_ante_5xx(monkeypatch):
    cli = _cliente(monkeypatch, [Resp(503), Resp(500), Resp(200, [{"a": 1}])])
    assert cli.get("x") == [{"a": 1}]


def test_5xx_persistente_lanza(monkeypatch):
    cli = _cliente(monkeypatch, [Resp(503), Resp(503), Resp(503)])
    with pytest.raises(requests.HTTPError):
        cli.get("x")


def test_4xx_no_se_reintenta(monkeypatch):
    cli = _cliente(monkeypatch, [Resp(400)])
    with pytest.raises(requests.HTTPError):
        cli.get("x")


def test_reintenta_ante_timeout(monkeypatch):
    llamadas = []

    def get(*a, **k):
        llamadas.append(1)
        if len(llamadas) < 2:
            raise requests.Timeout("lento")
        return Resp(200, [])
    cli = SECOPClient({})
    cli.session.get = get
    monkeypatch.setattr(app_secop.time, "sleep", lambda s: None)
    assert cli.get("x") == [] and len(llamadas) == 2


def test_fetch_dataset_sin_where_ni_q_respeta_el_tamano_de_pagina():
    cli = ClienteFalso()
    SECOPQuery(cli)._fetch_dataset("jbjy-vk9h", [], "fecha_de_firma DESC", 500, 0)
    assert cli.llamadas[0][1]["$limit"] == 500 and "$where" not in cli.llamadas[0][1]
