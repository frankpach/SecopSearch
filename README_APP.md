# SECOP II - App de Consulta Integrada

Aplicacion de escritorio con interfaz grafica (GUI) para consultar informacion de empresas en los datasets publicos de SECOP II via API Socrata.

## Descripcion

Esta herramienta permite realizar debida diligencia automatizada sobre empresas de vigilancia y seguridad privada (o cualquier proveedor) consultando simultaneamente 7 datasets oficiales de Colombia Compra Eficiente.

## Funcionalidades

- **Consulta integrada**: proveedor (empresa/NIT), entidad compradora, UNSPSC o texto libre sobre el objeto del contrato o proceso.
- **Rango de fechas**: por defecto el ultimo año (selector siempre visible, con rangos predefinidos o fechas propias); se aplica a todas las consultas y el pie de la tabla muestra el rango aplicado. Sanciones y SIRI no usan fechas.
- **Filtros avanzados**: rango de valor, modalidad, estado y departamento (combinables).
- **Buscar empresa por nombre**: encuentra el NIT en el registro de proveedores (varias palabras).
- **Busquedas guardadas y novedades**: guarda una consulta con nombre, re-ejecutala y las filas nuevas desde la ultima ejecucion salen resaltadas. Al abrir la app ofrece ejecutarlas todas.
- **Directorio editable**: empresas y entidades con nombre, NIT, alias, etiquetas y notas; editar, fusionar duplicados y busqueda por texto.
- **Copia**: seleccion multiple, Ctrl+C (pega en Excel con columnas alineadas), copiar celda, fila, columna, como CSV o JSON; numeros sin formato por defecto.
- **Paginacion**: paginas de 50/100/200/500 filas por dataset (100 por defecto), total real de registros, ultima pagina e ir a pagina N, cache de las ultimas 5 paginas y boton Cancelar.
- **Exportacion**: dialogo con alcance (pagina actual, filas seleccionadas o todos los resultados), columnas y formato (Excel con formato, CSV unico, CSV por dataset, JSON). "Todos los resultados" escribe directo a disco pagina a pagina (no usa memoria), pide confirmacion si supera 1.000 registros y se puede cancelar sin dejar archivos parciales.

## Datos y directorio

El directorio se guarda en `%APPDATA%\SecopSearch\directorio.json` (empresas, entidades, busquedas guardadas y preferencias). La primera vez se importan `empresas_historial.json` y `entidades_historial.json` (si existen) y se dejan copias `.bak`; los originales no se borran. Si el archivo se danara, se respalda como `directorio.json.corrupto-<fecha>` y se crea uno nuevo.

Al filtrar por UNSPSC, modalidad, estado o departamento, los datasets que no tienen esa columna (p. ej. SECOP Integrado no tiene UNSPSC) se omiten y la barra de estado lo indica.

## Datasets consultados

| ID | Nombre | Tipo |
|----|--------|------|
| p6dx-8zbt | SECOP II - Procesos de Contratacion | Procesos |
| jbjy-vk9h | SECOP II - Contratos Electronicos | Ejecucion contractual |
| rpmr-utcd | SECOP Integrado | Historico I + II |
| qmzu-gj57 | SECOP II - Proveedores Registrados | Catalogo de proveedores |
| it5q-hg94 | SECOP II - Multas y Sanciones | Sanciones vigentes |
| 4n4q-k399 | SECOP I - Multas y Sanciones | Sanciones historicas |
| iaeu-rcn6 | Antecedentes SIRI | Sanciones disciplinarias (Procuraduria) |

## Requisitos

- Python 3.8+
- Dependencias: `requests`, `openpyxl`, `tkinter`; `cryptography` solo para el certificado del servidor MCP (pruebas: `pytest`, ver `requirements-dev.txt`)

## Instalacion

### Opcion 1: Usar entorno virtual ya creado

```powershell
# Activar entorno virtual
.\venv_secop\Scripts\activate

# Ejecutar aplicacion
python app_secop.py
```

### Opcion 2: Instalar desde cero

```powershell
# Crear entorno virtual
python -m venv venv_secop

# Activar
.\venv_secop\Scripts\activate

# Instalar dependencias
pip install requests openpyxl

# Ejecutar
python app_secop.py
```

## Configuracion de credenciales

La aplicacion lee las credenciales del archivo `.env` ubicado en el mismo directorio. El formato debe ser:

```
socrataClaveAPI=TU_CLAVE_API
socrataClaveSecretaAPI=TU_SECRETO
user=TU_EMAIL
password=TU_PASSWORD
```

> **Nota**: Si no hay credenciales validas, la app funciona en modo publico (limitado).

## Empresas preconfiguradas

Las siguientes empresas estan precargadas para consulta rapida:

| Empresa | NIT |
|---------|-----|
| SERVIES LTDA | 890104906 |
| SUPREMA LTDA | 825000286 |
| SEGURIDAD PEGASO LTDA | 9004686350 |
| SEGURIDAD HEROICA DE COLOMBIA LTDA | 9003879253 |
| IDMA SECURITY LIMITADA | 9014115368 |

## Como usar

1. **Definir criterios**: empresa (combo, NIT manual o "Buscar empresa por nombre..."), entidad, UNSPSC o texto del objeto
2. **(Opcional) Ajustar fechas**: elija un rango predefinido o escriba fechas propias (por defecto, el ultimo año)
3. **(Opcional) Filtros avanzados**: marque la casilla para filtrar por valor, estado, departamento o modalidad
4. **Presionar "Consultar"**: La app cargara los datos de la API pagina a pagina
5. **Revisar resultados**: navegue por las paginas y por las pestanas de cada dataset
6. **Exportar**: use "Exportar..." y elija alcance, columnas y formato
7. **(Opcional) Guardar la busqueda**: "Guardar actual..." para re-ejecutarla luego y ver las novedades

## Estructura de la interfaz

```
+-------------------------------------------------------------+
| SECOP II - Debida Diligencia                [Directorio...] |
+-------------------------------------------------------------+
| Consulta                                                    |
| Empresa: [TODAS ▼]           NIT manual: [________]         |
| Entidad: [TODAS ▼]           Entidad NIT: [________]        |
| UNSPSC: [______]  Entidad (nombre): [______]                |
|   [Consultar] [Exportar...] [Limpiar] [Cancelar] Por pagina |
| Texto del objeto: [_________] [Buscar empresa por nombre...] |
|                                [x] Filtros avanzados        |
| Fechas: [Ultimo año ▼]  Desde: [____]  Hasta: [____]        |
| Filtros avanzados: Valor min/max, Estado, Departamento,     |
|                    Modalidad (plegable)                     |
| Busquedas guardadas: [______ ▼] [Ejecutar] [Ejecutar todas] |
|                      [Guardar actual...] [Eliminar]         |
+-------------------------------------------------------------+
| Estado de Datasets                                          |
| SECOP II Procesos: 2026-05-11... | Contratos: 2026-05-06...|
| ...                                                         |
+-------------------------------------------------------------+
| Resultados                                                  |
| [Resumen] [Procesos] [Contratos] [Proveedores] [...]       |
| +---------------------------------------------------------+ |
| | Empresa | NIT | Dataset | Registros | Valor | Estado    | |
| | ...                                                     | |
| +---------------------------------------------------------+ |
| [|<<] [<] Pagina 1 de N (total) [>] [>>|]  Ir a: [__] [Ir]  |
+-------------------------------------------------------------+
| Listo. Seleccione parametros y presione Consultar.          |
+-------------------------------------------------------------+
```

## Notas importantes

- La API de Socrata tiene limites de consulta. Si excede el limite, espere un momento y reintente.
- Los datos mostrados son los publicados por Colombia Compra Eficiente. Pueden tener hasta 24-48h de retraso.
- Los valores monetarios se muestran en pesos colombianos (COP).
- Las fechas se formatean automaticamente a formato legible.

## Solucion de problemas

| Problema | Solucion |
|----------|----------|
| "No se pudo conectar autenticado" | Verifique las credenciales en `.env` |
| "Sin resultados" | Intente con otro NIT o verifique la conexion a internet |
| La app se congela | Espere, las consultas a la API pueden tomar varios segundos |
| Error al exportar | Verifique que tenga permisos de escritura en la carpeta |
| Error 500/503 de datos.gov.co | La app reintenta 2 veces; si persiste, espere unos minutos |

## Licencia

Herramienta desarrollada para fines de debida diligencia en procesos de contratacion publica. Uso interno.

## Contacto

Para soporte tecnico, consulte el informe final de debida diligencia en el archivo `INFORME_FINAL_DEBIDA_DILIGENCIA.md`.
