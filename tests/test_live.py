import pytest

from search import Filtros, buscar_proveedores, condiciones, construir_where, orden_dataset

pytestmark = pytest.mark.live

COMPLETO = Filtros(texto="logistico", fecha_desde="2024-01-01", fecha_hasta="2025-12-31",
                   valor_min="1000000", valor_max="900000000000", departamento="Antioquia",
                   estado="a", modalidad="Contratación directa")


@pytest.fixture(scope="module")
def cliente():
    from app_secop import SECOPClient
    return SECOPClient({})


@pytest.mark.parametrize("ds", ["jbjy-vk9h", "p6dx-8zbt", "rpmr-utcd"])
def test_filtros_aceptados_por_la_api(cliente, ds):
    conds, q = condiciones(ds, COMPLETO)
    params = {"$limit": 1, "$where": construir_where(conds), "$order": orden_dataset(ds, COMPLETO)}
    if q:
        params["$q"] = q
    assert isinstance(cliente.get(ds, params, timeout=120), list)


def test_busqueda_de_proveedor_por_nombre(cliente):
    filas = buscar_proveedores(cliente, "seguridad", limite=5)
    assert filas and {"nit", "nombre"} <= set(filas[0])


def test_conteo_real_con_q_y_where(cliente):
    from app_secop import SECOPQuery
    cont = SECOPQuery(cliente).contar(None, None,
                                      Filtros(texto="operador logistico", fecha_desde="2025-10-01"))
    assert set(cont) == {"SECOP II - Contratos", "SECOP II - Procesos", "SECOP Integrado"}
    assert all(isinstance(n, int) and n >= 0 for n in cont.values())
