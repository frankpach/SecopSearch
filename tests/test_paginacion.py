from paginacion import (
    MAX_PAGINAS_CACHE, TAMANO_POR_DEFECTO, TAMANOS_PAGINA, UMBRAL_CONFIRMACION,
    CachePaginas, requiere_confirmacion, total_paginas, total_registros,
)


def test_constantes_acordadas():
    assert TAMANO_POR_DEFECTO == 100 and TAMANOS_PAGINA == (50, 100, 200, 500)
    assert UMBRAL_CONFIRMACION == 1000 and MAX_PAGINAS_CACHE == 5


def test_total_paginas_usa_el_dataset_mas_grande():
    assert total_paginas({"a": 250, "b": 90}, 100) == 3
    assert total_paginas({"a": 300}, 100) == 3
    assert total_paginas({"a": 301}, 100) == 4
    assert total_paginas({"a": 0, "b": 0}, 100) == 1
    assert total_paginas({}, 100) == 1
    assert total_paginas({"a": "250"}, 100) == 3          # Socrata devuelve el conteo como texto


def test_total_registros():
    assert total_registros({"a": 250, "b": "90"}) == 340
    assert total_registros({}) == 0


def test_confirmacion_solo_por_encima_de_1000():
    assert requiere_confirmacion(1000) is False
    assert requiere_confirmacion(1001) is True
    assert requiere_confirmacion(0) is False
    assert requiere_confirmacion(None) is True            # total desconocido: se pregunta


def test_cache_lru():
    c = CachePaginas(3)
    for p in (1, 2, 3):
        c.guardar(p, f"p{p}")
    assert c.obtener(1) == "p1"                           # la 1 pasa a ser la mas reciente
    c.guardar(4, "p4")                                    # expulsa la menos reciente: la 2
    assert c.obtener(2) is None and c.obtener(1) == "p1" and c.obtener(4) == "p4"
    assert len(c) == 3 and 3 in c


def test_cache_sobrescribe_y_vacia():
    c = CachePaginas()
    c.guardar(1, "a")
    c.guardar(1, "b")
    assert len(c) == 1 and c.obtener(1) == "b"
    c.vaciar()
    assert len(c) == 0 and c.obtener(1) is None


def test_cache_por_defecto_guarda_cinco():
    c = CachePaginas()
    for p in range(10):
        c.guardar(p, p)
    assert len(c) == 5 and 9 in c and 4 not in c
