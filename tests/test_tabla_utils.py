import csv
import io
import json

from tabla_utils import (
    columnas_union, clave_orden, filas_a_csv, filas_a_json, filas_a_tsv,
    ordenar_filas, parse_fecha, parse_pesos, texto_pantalla, valor_crudo,
    valor_visible,
)

FILAS = [
    {"a": "x", "valor": "$1.000", "n": "t\tab"},
    {"a": "y\nz", "valor": "", "n": 'dice "hola"'},
]


def test_parse_pesos():
    assert parse_pesos("$1.234.567") == 1234567
    assert parse_pesos("$500") == 500
    assert parse_pesos("$-1.000") == -1000
    assert parse_pesos("1234") is None
    assert parse_pesos("") is None
    assert parse_pesos(None) is None
    assert parse_pesos("$12.34") is None


def test_parse_fecha():
    assert str(parse_fecha("2024-05-01")) == "2024-05-01"
    assert parse_fecha("2024-13-01") is None
    assert str(parse_fecha("2024-05-01T00:00:00")) == "2024-05-01"      # marca ISO: la fecha
    assert str(parse_fecha("2025-03-01T00:00:00.000")) == "2025-03-01"
    assert str(parse_fecha("2025-03-01 13:45:10")) == "2025-03-01"
    assert parse_fecha("2025-03-01T99:00:00") is None
    assert parse_fecha("2025-03-01Tbasura") is None
    assert parse_fecha(None) is None


def test_valor_crudo_vs_visible():
    assert valor_crudo("$2.000.000") == 2000000
    assert valor_visible("$2.000.000") == "$2.000.000"
    assert valor_crudo(None) == ""
    assert valor_crudo(7) == 7
    assert valor_crudo({"url": "http://x"}) == "http://x"
    assert valor_crudo({"a": 1}) == '{"a": 1}'


def test_orden_numerico_no_alfabetico():
    filas = [{"valor": "$10"}, {"valor": "$9"}, {"valor": "$100"}, {"valor": ""}]
    asc = [f["valor"] for f in ordenar_filas(filas, "valor")]
    assert asc == ["$9", "$10", "$100", ""]
    desc = [f["valor"] for f in ordenar_filas(filas, "valor", inverso=True)]
    assert desc == ["$100", "$10", "$9", ""]


def test_orden_fechas_y_texto():
    filas = [{"c": "2024-03-01"}, {"c": "2023-12-31"}, {"c": "beta"}, {"c": "Alfa"}]
    assert [f["c"] for f in ordenar_filas(filas, "c")] == [
        "2023-12-31", "2024-03-01", "Alfa", "beta"]


def test_orden_mezcla_de_tipos_no_falla():
    res = ordenar_filas([{"c": "abc"}, {"c": "5"}, {"c": "$3"}, {"c": "nan"}], "c")
    assert [f["c"] for f in res][:2] == ["$3", "5"]


def test_clave_orden_ignora_nan_e_infinito_como_numero():
    assert clave_orden("nan")[0] == 2
    assert clave_orden("Infinity")[0] == 2


def test_tsv_crudo_con_encabezado():
    out = filas_a_tsv(FILAS, ["a", "valor"], ["A", "Valor"], True, True)
    lineas = out.split("\n")
    assert lineas[0] == "A\tValor"
    assert lineas[1] == "x\t1000"


def test_tsv_visible_conserva_formato():
    assert filas_a_tsv(FILAS[:1], ["valor"], None, False, False) == "$1.000"


def test_tsv_celdas_con_tab_salto_y_comillas_ida_y_vuelta():
    out = filas_a_tsv(FILAS, ["a", "n"], None, False)
    leidas = list(csv.reader(io.StringIO(out), delimiter="\t"))
    assert leidas == [["x", "t\tab"], ["y\nz", 'dice "hola"']]


def test_no_recorta_texto_largo():
    largo = "x" * 5000
    assert filas_a_tsv([{"o": largo}], ["o"], None, False) == largo


def test_csv_delimitador_punto_y_coma():
    out = filas_a_csv([{"a": "1", "b": "2"}], ["a", "b"], None, False, True, ";")
    assert out == "1;2"


def test_json_unicode_y_crudo():
    out = filas_a_json([{"a": "ñ", "valor": "$5"}], ["a", "valor"])
    assert json.loads(out) == [{"a": "ñ", "valor": 5}]
    assert "ñ" in out


def test_columnas_union_preserva_orden():
    assert columnas_union([{"a": 1, "b": 2}, {"c": 3, "a": 4}]) == ["a", "b", "c"]


def test_texto_pantalla():
    assert texto_pantalla("x" * 10, 5) == "xxxx…"
    assert texto_pantalla("abc", 5) == "abc"
    assert texto_pantalla(None) == ""


def test_marcas_iso_se_ordenan_como_fechas():
    filas = [{"f": "2025-03-01T00:00:00.000"}, {"f": "2024-12-31"}, {"f": "2025-01-15T10:00:00"}]
    assert [f["f"][:10] for f in ordenar_filas(filas, "f")] == ["2024-12-31", "2025-01-15", "2025-03-01"]
    assert clave_orden("2025-03-01T00:00:00.000")[0] == clave_orden("2025-03-01")[0]
