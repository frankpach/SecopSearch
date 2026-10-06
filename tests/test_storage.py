import json
import os
import threading

import pytest

from storage import Directorio, DuplicadoError, directorio_datos, nit_canonico


def nuevo(tmp_path):
    return Directorio(str(tmp_path / "d.json"))


def test_directorio_datos_usa_variable_de_entorno(tmp_path, monkeypatch):
    monkeypatch.setenv("SECOP_DATA_DIR", str(tmp_path / "zz"))
    assert directorio_datos() == str(tmp_path / "zz")
    assert os.path.isdir(tmp_path / "zz")


def test_nit_canonico():
    assert nit_canonico(" 890.104.906-1 ") == "8901049061"
    assert nit_canonico(None) == ""


def test_agregar_y_persistir(tmp_path):
    d = nuevo(tmp_path)
    e = d.agregar("empresas", "ACME SAS", "900123456", alias="acme",
                  etiquetas="vigilancia, bogota, vigilancia")
    assert e["etiquetas"] == ["vigilancia", "bogota"]
    assert e["nombre_resuelto"] is True and e["ultima_consulta"] == ""
    d2 = nuevo(tmp_path)
    assert d2.obtener("empresas", e["id"])["alias"] == "acme"
    assert json.load(open(d2.ruta, encoding="utf-8"))["version"] == 1


def test_solo_nit_queda_pendiente_de_resolver(tmp_path):
    e = nuevo(tmp_path).agregar("empresas", "", "900123456")
    assert e["nombre"] == "900123456" and e["nombre_resuelto"] is False


def test_requiere_nombre_o_nit(tmp_path):
    with pytest.raises(ValueError):
        nuevo(tmp_path).agregar("empresas", "", "")


def test_tipo_invalido(tmp_path):
    with pytest.raises(ValueError):
        nuevo(tmp_path).listar("otros")


def test_nit_con_formatos_distintos_es_duplicado(tmp_path):
    d = nuevo(tmp_path)
    d.agregar("empresas", "A", "890.104.906-1")
    with pytest.raises(DuplicadoError) as exc:
        d.agregar("empresas", "B", "8901049061")
    assert exc.value.existente["nombre"] == "A"
    with pytest.raises(DuplicadoError):
        d.agregar("empresas", "C", " 890104906 1 ")
    assert len(d.listar("empresas")) == 1


def test_entidades_sin_nit_duplican_por_nombre_pero_con_nit_distinto_no(tmp_path):
    d = nuevo(tmp_path)
    d.agregar("entidades", "Alcaldia X", "")
    with pytest.raises(DuplicadoError):
        d.agregar("entidades", "alcaldia x", "")
    d.agregar("entidades", "Alcaldia Y", "111111111")
    d.agregar("entidades", "Alcaldia Y", "222222222")      # NIT distinto: permitido
    assert len(d.listar("entidades")) == 3


def test_actualizar_renombra_sin_perder_ultima_consulta(tmp_path):
    d = nuevo(tmp_path)
    e = d.agregar("empresas", "", "900123456")
    d.marcar_consulta("empresas", e["id"])
    antes = d.obtener("empresas", e["id"])["ultima_consulta"]
    d.actualizar("empresas", e["id"], nombre="ACME", notas="ok", etiquetas=["a", "b"])
    nuevo_e = d.obtener("empresas", e["id"])
    assert nuevo_e["nombre"] == "ACME" and nuevo_e["nombre_resuelto"] is True
    assert nuevo_e["ultima_consulta"] == antes and antes != ""


def test_actualizar_a_nit_ajeno_falla_y_no_cambia_nada(tmp_path):
    d = nuevo(tmp_path)
    a = d.agregar("empresas", "A", "111111111")
    b = d.agregar("empresas", "B", "222222222")
    with pytest.raises(DuplicadoError):
        d.actualizar("empresas", b["id"], nit="111.111.111")
    assert d.obtener("empresas", b["id"])["nit"] == "222222222"
    assert a["id"] != b["id"]


def test_actualizar_campo_invalido(tmp_path):
    d = nuevo(tmp_path)
    e = d.agregar("empresas", "A", "111111111")
    with pytest.raises(ValueError):
        d.actualizar("empresas", e["id"], id="otro")


def test_fusionar(tmp_path):
    d = nuevo(tmp_path)
    a = d.agregar("empresas", "A", "111111111", etiquetas=["x"], notas="uno")
    b = d.agregar("empresas", "A bis", "", etiquetas=["y"], notas="dos", alias="ab")
    res = d.fusionar("empresas", a["id"], b["id"])
    assert res["etiquetas"] == ["x", "y"] and "uno" in res["notas"] and "dos" in res["notas"]
    assert res["alias"] == "ab"
    assert d.obtener("empresas", b["id"]) is None


def test_eliminar(tmp_path):
    d = nuevo(tmp_path)
    e = d.agregar("empresas", "A", "111111111")
    d.eliminar("empresas", e["id"])
    assert d.listar("empresas") == []


def test_listar_con_filtro(tmp_path):
    d = nuevo(tmp_path)
    d.agregar("empresas", "ACME", "1", etiquetas=["vigilancia"])
    d.agregar("empresas", "Beta", "2", notas="proveedor clave")
    assert [e["nombre"] for e in d.listar("empresas", "vigil")] == ["ACME"]
    assert [e["nombre"] for e in d.listar("empresas", "CLAVE")] == ["Beta"]


def test_claves_y_nombres_a_nit_con_nombres_repetidos(tmp_path):
    d = nuevo(tmp_path)
    d.agregar("entidades", "Alcaldia", "111111111")
    d.agregar("entidades", "Alcaldia", "222222222")
    mapa = d.nombres_a_nit("entidades")
    assert len(mapa) == 2 and sorted(mapa.values()) == ["111111111", "222222222"]
    assert all(d.claves("entidades")[k]["nit"] == v for k, v in mapa.items())


def test_json_corrupto_se_respalda_y_avisa(tmp_path):
    ruta = tmp_path / "d.json"
    ruta.write_text("{ esto no es json", encoding="utf-8")
    d = Directorio(str(ruta))
    assert d.listar("empresas") == [] and "danado" in d.aviso
    assert any("corrupto" in n for n in os.listdir(tmp_path))
    d.agregar("empresas", "A", "111111111")            # sigue funcionando
    assert Directorio(str(ruta)).listar("empresas")[0]["nombre"] == "A"


def test_json_vacio_o_lista_se_trata_como_corrupto(tmp_path):
    for i, contenido in enumerate(("", "[]")):
        ruta = tmp_path / f"v{i}.json"
        ruta.write_text(contenido, encoding="utf-8")
        d = Directorio(str(ruta))
        assert d.listar("empresas") == [] and d.aviso


def test_guardado_atomico_y_memoria_consistente(tmp_path, monkeypatch):
    d = nuevo(tmp_path)
    d.agregar("empresas", "A", "111111111")
    antes = open(d.ruta, encoding="utf-8").read()

    def falla(*a, **k):
        raise OSError("boom")
    with monkeypatch.context() as m:
        m.setattr(os, "replace", falla)
        with pytest.raises(OSError):
            d.agregar("empresas", "B", "222222222")
    assert open(d.ruta, encoding="utf-8").read() == antes
    assert [e["nombre"] for e in d.listar("empresas")] == ["A"]


def test_busquedas_guardadas(tmp_path):
    d = nuevo(tmp_path)
    b = d.guardar_busqueda("Logistica", {"texto": "operador logistico"}, {"modo": "ultimo_anio"})
    assert b["rango"] == {"modo": "ultimo_anio"}
    d.registrar_ejecucion(b["id"], ["x|1", "x|2"])
    assert d.obtener_busqueda(b["id"])["ultimos_ids"] == ["x|1", "x|2"]
    assert d.obtener_busqueda(b["id"])["ultima_ejecucion"] != ""
    fijo = {"modo": "personalizado", "desde": "2024-01-01", "hasta": "2024-12-31"}
    b2 = d.guardar_busqueda("logistica", {"texto": "otro"}, fijo)   # mismo nombre: sobrescribe
    assert b2["id"] == b["id"] and b2["ultimos_ids"] == [] and b2["ultima_ejecucion"] == ""
    assert b2["rango"] == fijo and b2["filtros"] == {"texto": "otro"}
    assert len(d.listar_busquedas()) == 1
    assert d.buscar_busqueda_por_nombre("LOGISTICA")["id"] == b["id"]
    d.eliminar_busqueda(b["id"])
    assert d.listar_busquedas() == []
    with pytest.raises(ValueError):
        d.guardar_busqueda("  ", {})


def test_busqueda_sin_rango_usa_el_ultimo_anio(tmp_path):
    b = nuevo(tmp_path).guardar_busqueda("N", {"texto": "a"})
    assert b["rango"] == {"modo": "ultimo_anio"}


def test_registrar_ejecucion_limita_ids(tmp_path):
    d = nuevo(tmp_path)
    b = d.guardar_busqueda("N", {"texto": "a"})
    d.registrar_ejecucion(b["id"], [str(i) for i in range(5000)])
    assert len(d.obtener_busqueda(b["id"])["ultimos_ids"]) == 2000


def test_preferencias(tmp_path):
    d = nuevo(tmp_path)
    assert d.preferencia("exportar", {"a": 1}) == {"a": 1}
    d.guardar_preferencia("exportar", {"formato": "csv"})
    assert nuevo(tmp_path).preferencia("exportar") == {"formato": "csv"}


def test_migracion_desde_historiales_antiguos(tmp_path):
    emp = tmp_path / "empresas_historial.json"
    ent = tmp_path / "entidades_historial.json"
    emp.write_text(json.dumps([
        {"nombre": "SERVIES LTDA", "nit": "890104906", "ultima_consulta": "2026-05-11T10:00:00"},
        {"nombre": "900468635", "nit": "900468635", "ultima_consulta": "2026-05-11T10:00:00"},
        {"nombre": "SERVIES LTDA", "nit": "890.104.906"},          # duplicado: se ignora
    ]), encoding="utf-8")
    ent.write_text(json.dumps([{"nombre": "Alcaldia X", "nit": "800000001"}]), encoding="utf-8")
    d = nuevo(tmp_path)
    assert d.migrar_historiales([str(emp)], [str(ent)]) == (2, 1)
    assert emp.exists() and os.path.exists(str(emp) + ".bak")
    e = d.buscar_por_nit("empresas", "890104906")
    assert e["ultima_consulta"] == "2026-05-11T10:00:00" and e["nombre_resuelto"] is True
    assert d.buscar_por_nit("empresas", "900468635")["nombre_resuelto"] is False
    assert d.migrar_historiales([str(emp)], [str(ent)]) == (0, 0)    # una sola vez


def test_migracion_con_archivos_ausentes_o_danados(tmp_path):
    mal = tmp_path / "mal.json"
    mal.write_text("no json", encoding="utf-8")
    d = nuevo(tmp_path)
    assert d.migrar_historiales([str(mal), str(tmp_path / "no_existe.json")], []) == (0, 0)


def test_escrituras_concurrentes(tmp_path):
    d = nuevo(tmp_path)
    hilos = [threading.Thread(target=d.agregar, args=("empresas", f"E{i}", f"1000000{i:02d}"))
             for i in range(20)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert len(d.listar("empresas")) == 20
    assert len(nuevo(tmp_path).listar("empresas")) == 20
