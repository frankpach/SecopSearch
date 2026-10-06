# -*- coding: utf-8 -*-
"""Paginacion pura: total de paginas, cache LRU de paginas visitadas y umbral de
confirmacion para exportaciones grandes. Sin Tk ni red."""
from collections import OrderedDict

TAMANOS_PAGINA = (50, 100, 200, 500)
TAMANO_POR_DEFECTO = 100
MAX_PAGINAS_CACHE = 5
UMBRAL_CONFIRMACION = 1000


def total_paginas(conteos, tamano):
    """conteos: {dataset: n}. Cada pagina pide `tamano` filas A CADA dataset, asi que
    el numero de paginas lo marca el dataset mas grande. Siempre >= 1."""
    mayor = max((int(n) for n in conteos.values()), default=0)
    return max(1, -(-mayor // tamano))


def total_registros(conteos):
    return sum(int(n) for n in conteos.values())


def requiere_confirmacion(total, umbral=UMBRAL_CONFIRMACION):
    """True si el total supera el umbral o no se pudo estimar (None)."""
    return total is None or total > umbral


class CachePaginas:
    """Ultimas `maximo` paginas visitadas (LRU): ir y volver sin consultar la API."""

    def __init__(self, maximo=MAX_PAGINAS_CACHE):
        self.maximo = maximo
        self._d = OrderedDict()

    def obtener(self, pagina):
        if pagina not in self._d:
            return None
        self._d.move_to_end(pagina)
        return self._d[pagina]

    def guardar(self, pagina, valor):
        self._d[pagina] = valor
        self._d.move_to_end(pagina)
        while len(self._d) > self.maximo:
            self._d.popitem(last=False)

    def vaciar(self):
        self._d.clear()

    def __len__(self):
        return len(self._d)

    def __contains__(self, pagina):
        return pagina in self._d
