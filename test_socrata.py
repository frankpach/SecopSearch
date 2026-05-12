#!/usr/bin/env python3
"""
Test de conexion Socrata - Diagnostico de autenticacion
Prueba multiples metodos para conectar con datos.gov.co
"""

import sys
import json

def test_socrata_connections():
    """Prueba 6 metodos diferentes de conexion"""
    
    print("=" * 70)
    print("DIAGNOSTICO DE CONEXION SOCRATA - datos.gov.co")
    print("=" * 70)
    
    # Leer credenciales
    creds = {}
    try:
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    creds[k.strip()] = v.strip()
        print(f"\n[OK] Credenciales leidas de .env")
        print(f"  - Clave API: {creds.get('socrataClaveAPI', 'NO ENCONTRADA')[:20]}...")
        print(f"  - Usuario: {creds.get('user', 'NO ENCONTRADO')}")
    except Exception as e:
        print(f"\n[ERROR] Error leyendo .env: {e}")
        return
    
    results = {}
    
    # TEST 1: Sin autenticacion (publico)
    print("\n" + "-" * 70)
    print("TEST 1: Conexion PUBLICA (sin credenciales)")
    print("-" * 70)
    try:
        from sodapy import Socrata
        client = Socrata("www.datos.gov.co", None)
        meta = client.get_metadata("p6dx-8zbt")
        print(f"[OK] EXITO - Metadata obtenida")
        print(f"  - Dataset: {meta.get('name')}")
        print(f"  - Ultima actualizacion: {meta.get('updatedAt')}")
        results["public"] = "OK"
    except Exception as e:
        print(f"[FALLO] {e}")
        results["public"] = str(e)
    
    # TEST 2: Solo con App Token
    print("\n" + "-" * 70)
    print("TEST 2: Solo con App Token")
    print("-" * 70)
    try:
        from sodapy import Socrata
        client = Socrata("www.datos.gov.co", creds.get("socrataClaveAPI"))
        meta = client.get_metadata("p6dx-8zbt")
        print(f"[OK] EXITO - Conexion con App Token")
        results["token_only"] = "OK"
    except Exception as e:
        print(f"[FALLO] {e}")
        results["token_only"] = str(e)
    
    # TEST 3: Con App Token + username/password (metodo original)
    print("\n" + "-" * 70)
    print("TEST 3: App Token + username/password (metodo sodapy)")
    print("-" * 70)
    try:
        from sodapy import Socrata
        client = Socrata(
            "www.datos.gov.co",
            creds.get("socrataClaveAPI"),
            username=creds.get("user"),
            password=creds.get("password"),
        )
        meta = client.get_metadata("p6dx-8zbt")
        print(f"[OK] EXITO - Conexion autenticada completa")
        results["full_auth"] = "OK"
    except Exception as e:
        print(f"[FALLO] {e}")
        results["full_auth"] = str(e)
    
    # TEST 4: Conexion directa con requests (sin sodapy)
    print("\n" + "-" * 70)
    print("TEST 4: Conexion directa con requests (sin sodapy)")
    print("-" * 70)
    try:
        import requests
        url = "https://www.datos.gov.co/resource/p6dx-8zbt.json?$limit=1"
        response = requests.get(url)
        print(f"  Status: {response.status_code}")
        print(f"  Content-Type: {response.headers.get('content-type', 'N/A')}")
        if response.status_code == 200:
            data = response.json()
            print(f"[OK] EXITO - Datos recibidos: {len(data)} registros")
            results["requests_direct"] = "OK"
        else:
            print(f"[FALLO] HTTP {response.status_code}: {response.text[:300]}")
            results["requests_direct"] = f"HTTP {response.status_code}"
    except Exception as e:
        print(f"[FALLO] {e}")
        results["requests_direct"] = str(e)
    
    # TEST 5: Conexion con requests + headers X-App-Token
    print("\n" + "-" * 70)
    print("TEST 5: Requests + X-App-Token header")
    print("-" * 70)
    try:
        import requests
        url = "https://www.datos.gov.co/resource/p6dx-8zbt.json?$limit=1"
        headers = {"X-App-Token": creds.get("socrataClaveAPI", "")}
        response = requests.get(url, headers=headers)
        print(f"  Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"[OK] EXITO - Con App Token header: {len(data)} registros")
            results["requests_token"] = "OK"
        else:
            print(f"[FALLO] HTTP {response.status_code}: {response.text[:300]}")
            results["requests_token"] = f"HTTP {response.status_code}"
    except Exception as e:
        print(f"[FALLO] {e}")
        results["requests_token"] = str(e)
    
    # TEST 6: Conexion con requests + Basic Auth
    print("\n" + "-" * 70)
    print("TEST 6: Requests + Basic Auth (user:password)")
    print("-" * 70)
    try:
        import requests
        url = "https://www.datos.gov.co/resource/p6dx-8zbt.json?$limit=1"
        auth = (creds.get("user", ""), creds.get("password", ""))
        response = requests.get(url, auth=auth)
        print(f"  Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"[OK] EXITO - Con Basic Auth: {len(data)} registros")
            results["requests_basic"] = "OK"
        else:
            print(f"[FALLO] HTTP {response.status_code}: {response.text[:300]}")
            results["requests_basic"] = f"HTTP {response.status_code}"
    except Exception as e:
        print(f"[FALLO] {e}")
        results["requests_basic"] = str(e)
    
    # TEST 7: Probar datasets individuales
    print("\n" + "-" * 70)
    print("TEST 7: Conexion a todos los datasets (metodo que funcione)")
    print("-" * 70)
    
    datasets = {
        "p6dx-8zbt": "SECOP II - Procesos",
        "jbjy-vk9h": "SECOP II - Contratos",
        "rpmr-utcd": "SECOP Integrado",
        "qmzu-gj57": "Proveedores",
        "it5q-hg94": "Multas SECOP II",
        "4n4q-k399": "Multas SECOP I",
        "iaeu-rcn6": "SIRI",
    }
    
    # Usar el metodo que haya funcionado
    working_method = None
    for method, status in results.items():
        if status == "OK":
            working_method = method
            break
    
    if not working_method:
        print("[ERROR] Ningun metodo de conexion funciono. Verifique su conexion a internet.")
        return results
    
    print(f"Usando metodo: {working_method}")
    
    for ds_id, ds_name in datasets.items():
        try:
            import requests
            url = f"https://www.datos.gov.co/resource/{ds_id}.json?$limit=1"
            
            if working_method == "requests_token":
                headers = {"X-App-Token": creds.get("socrataClaveAPI", "")}
                response = requests.get(url, headers=headers)
            elif working_method == "requests_basic":
                auth = (creds.get("user", ""), creds.get("password", ""))
                response = requests.get(url, auth=auth)
            else:
                response = requests.get(url)
            
            if response.status_code == 200:
                print(f"  [OK] {ds_name}: OK")
            else:
                print(f"  [FALLO] {ds_name}: HTTP {response.status_code}")
        except Exception as e:
            print(f"  [FALLO] {ds_name}: {str(e)[:50]}")
    
    # Resumen final
    print("\n" + "=" * 70)
    print("RESUMEN DE RESULTADOS")
    print("=" * 70)
    for method, status in results.items():
        icon = "[OK]" if status == "OK" else "[FALLO]"
        print(f"  {icon} {method}: {status}")
    
    return results


def test_query_by_nit(nit="825000286"):
    """Prueba consulta real por NIT"""
    print("\n" + "=" * 70)
    print(f"TEST: Consulta real por NIT {nit}")
    print("=" * 70)
    
    try:
        import requests
        
        # Probar sin autenticacion primero
        url = f"https://www.datos.gov.co/resource/jbjy-vk9h.json?$where=documento_proveedor='{nit}'&$limit=5"
        print(f"\nURL: {url}")
        response = requests.get(url)
        
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"[OK] EXITO - Registros encontrados: {len(data)}")
            if data:
                print(f"\nPrimer registro (campos principales):")
                campos = ["nombre_entidad", "id_contrato", "estado_contrato", 
                         "valor_del_contrato", "fecha_de_firma", "proveedor_adjudicado"]
                for c in campos:
                    if c in data[0]:
                        print(f"  - {c}: {data[0][c]}")
            return True
        else:
            print(f"[FALLO] HTTP {response.status_code}: {response.text[:300]}")
            return False
            
    except Exception as e:
        print(f"[ERROR] {e}")
        return False


def test_query_processes(nit="825000286"):
    """Prueba consulta de procesos"""
    print("\n" + "=" * 70)
    print(f"TEST: Consulta de procesos por NIT {nit}")
    print("=" * 70)
    
    try:
        import requests
        
        # La API de procesos usa 'nit_del_proveedor_adjudicado'
        url = f"https://www.datos.gov.co/resource/p6dx-8zbt.json?$where=nit_del_proveedor_adjudicado='{nit}'&$limit=5"
        print(f"\nURL: {url}")
        response = requests.get(url)
        
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"[OK] EXITO - Procesos encontrados: {len(data)}")
            if data:
                print(f"\nPrimer proceso:")
                campos = ["entidad", "nombre_del_procedimiento", "estado_del_procedimiento",
                         "valor_total_adjudicacion", "fecha_adjudicacion"]
                for c in campos:
                    if c in data[0]:
                        print(f"  - {c}: {data[0][c]}")
            return True
        else:
            print(f"[FALLO] HTTP {response.status_code}: {response.text[:300]}")
            return False
            
    except Exception as e:
        print(f"[ERROR] {e}")
        return False


if __name__ == "__main__":
    # Ejecutar todos los tests
    results = test_socrata_connections()
    
    # Si hay algun metodo que funcione, probar consultas reales
    if results and any(status == "OK" for status in results.values()):
        print("\n" + "=" * 70)
        print("PROBANDO CONSULTAS REALES...")
        print("=" * 70)
        test_query_by_nit("825000286")  # SUPREMA
        test_query_processes("825000286")
        
        print("\n" + "=" * 70)
        print("TESTS COMPLETADOS")
        print("=" * 70)
    else:
        print("\n" + "=" * 70)
        print("NO SE PUDO CONECTAR A LA API")
        print("=" * 70)
        print("\nPosibles causas:")
        print("  1. Problema de conexion a internet")
        print("  2. La API de datos.gov.co requiere autenticacion especial")
        print("  3. Las credenciales en .env son incorrectas")
        print("  4. El dominio requiere headers especificos")
        print("\nRecomendacion: Probar acceso desde navegador a:")
        print("  https://www.datos.gov.co/d/p6dx-8zbt")
        sys.exit(1)
