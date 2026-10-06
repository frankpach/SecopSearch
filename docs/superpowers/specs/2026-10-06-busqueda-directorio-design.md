# Búsqueda avanzada y directorio editable — Diseño

Fecha: 2026-10-06 · Estado: aprobado; implementado según el plan

## Objetivo
Que SECOP Search sirva para descubrir oportunidades y hacer debida diligencia sin saber el NIT, y que las empresas y entidades guardadas sean un directorio editable y confiable.

**Éxito:** encontrar un proceso o contrato por palabras clave; renombrar, corregir o anotar una entidad sin borrarla y recrearla.

**Supuestos:** la app sigue siendo de escritorio (Tkinter) y usa los mismos datasets de Socrata (datos.gov.co).

## Fuera de alcance
- Publicidad y versión web (Google AdSense no permite anuncios en apps de escritorio; fase posterior).
- Alertas en segundo plano o notificaciones del sistema.
- Limpieza de `.exe` en git y de `dist/secop-localhost.key` (recomendado aparte).
- Reescritura de la interfaz.

## 1. Datos: `storage.py`
- Archivo `%APPDATA%/SecopSearch/directorio.json`:
  `{ "version": 1, "empresas": [], "entidades": [], "busquedas": [] }`.
- Empresa/entidad: `id` (uuid), `nombre`, `nit`, `alias`, `notas`, `etiquetas[]`, `creado`, `ultima_consulta`. `ultima_consulta` solo cambia al consultar ese registro.
- Primer arranque: migra `empresas_historial.json` y `entidades_historial.json` (si existen), sin borrarlos, y escribe una copia `.bak`.
- Escritura atómica: archivo temporal y `os.replace`.
- Un NIT no puede repetirse dentro de empresas ni dentro de entidades; si ocurre se ofrece fusionar.

## 2. Edición (UI)
- Ventana "Directorio" con pestañas Empresas y Entidades: tabla, filtro de texto, Nuevo, Editar, Eliminar.
- Diálogo de edición: nombre, NIT, alias, notas, etiquetas.
- Al guardar solo con NIT se intenta resolver el nombre oficial en `qmzu-gj57`; si falla se guarda igual y se reintenta en la siguiente apertura del directorio.
- Los combos del panel principal se alimentan de este directorio.

## 3. Búsqueda: `search.py`
- Objeto `Filtros`: `texto`, `nit_proveedor`, `entidad_nombre`, `entidad_nit`, `unspsc`, `fecha_desde`, `fecha_hasta`, `valor_min`, `valor_max`, `modalidad`, `estado`, `departamento`.
- Traducción a `$q` y `$where` con el escape de comillas centralizado (`_escape_sql`). Sin red, para poder probarla.
- **Texto libre:** consulta procesos (`p6dx-8zbt`), contratos (`jbjy-vk9h`) y SECOP Integrado (`rpmr-utcd`) en paralelo; no se deduplica (cada dataset se consulta una vez por página, y contratos y procesos son entidades distintas).
- **Empresa por nombre:** campo y botón Buscar sobre `qmzu-gj57`; lista (nombre, NIT) con "Guardar en directorio".
- Panel plegable "Filtros avanzados". Se mantiene la regla de al menos un criterio.
- **Rango de fechas por defecto: último año, en todas las consultas** (incluidas las de NIT de proveedor). El rango por defecto no cuenta como criterio para la regla de al menos uno.
  - El selector de fechas está **siempre visible** (fuera del panel plegable): lista de rangos predefinidos (Último año, 6 meses, 3 meses, 30 días, 5 años, Todo el historial, Personalizado) más los campos Desde y Hasta (AAAA-MM-DD). Elegir un rango predefinido rellena los campos; editar un campo pasa a "Personalizado"; "Todo el historial" los vacía. Sin dependencias nuevas (no hay calendario gráfico).
  - Los rangos predefinidos se calculan al momento de consultar (hoy y hoy−N días); no se congelan.
  - Al consultar, la barra de estado y el pie de la tabla indican el rango aplicado ("Fechas: 2025-10-06 a 2026-10-06"), para que ningún resultado se interprete como historial completo. Las sanciones y SIRI no usan fechas y no se filtran.
  - El mismo rango filtra por la fecha de cada dataset (firma del contrato, publicación del proceso, firma en SECOP Integrado).

## 4. Búsquedas guardadas y alertas
- Se guarda `Filtros` + `nombre`, `ultimos_ids[]`, `ultima_ejecucion`. Del rango de fechas se guarda el **modo** (un rango predefinido, que se recalcula al ejecutar, o fechas personalizadas fijas), no las fechas calculadas.
- Al reejecutar, las filas cuyo identificador no estaba en `ultimos_ids` se marcan "NUEVO" y se cuentan en la barra de estado.
- Botón "Ejecutar todas las guardadas" y aviso al abrir la app. Solo mientras la app está abierta.

## 6. Copia y exportación de tablas: `tabla_utils.py`
Problemas actuales: selección de una sola fila (`browse`); solo "Copiar fila completa" en el menú, sin Ctrl+C; sin copia de celda o columna; pestañas de detalle sin menú ni copia y con texto recortado a 120 caracteres; valores copiados con formato (`$1.234.567`); exportación siempre vuelve a descargar todo desde la API; Excel sin formato; CSV en varios archivos; orden por texto (`"9" > "10"`).

**Copia**
- Selección múltiple (`extended`), Shift/Ctrl y Ctrl+A.
- Ctrl+C copia las filas seleccionadas como TSV (se pega en Excel); sin selección copia la celda bajo el cursor.
- Menú contextual: Copiar celda, fila, filas seleccionadas (con o sin encabezados), columna (visibles o seleccionadas), y copiar como texto, CSV o JSON.
- Números crudos por defecto (`1234567`), opción de copiar como se ve. Nunca se recorta el texto al copiar; solo en pantalla.
- Tabla resumen y pestañas de detalle comparten la misma implementación.

**Exportación**
- Diálogo "Exportar": alcance (página actual, filas seleccionadas, todos los resultados vía API), selección de columnas, formato (Excel, CSV único, JSON, CSV por dataset). Recuerda la última elección.
- Excel: encabezados en negrita, fila fija, autofiltro, anchos ajustados, valores numéricos con formato de pesos, fechas reales, hipervínculos a SECOP.
- Página y selección usan los datos en memoria (instantáneo); solo "todos" consulta la API.
- Orden por tipo real (número, fecha, texto).
- Pruebas pytest de los conversores a TSV/CSV/JSON y del orden por tipo, sin interfaz gráfica.

Nota de implementación: la sección 6 se reparte en `tabla_utils.py` (puro), `exportar.py` (exportación incremental), `copiador_tabla.py` y `ui_exportar.py` (Tk). La sección 7 vive en `paginacion.py` (puro) y en `app_secop.py`. El JSON admite además las claves `preferencias` (última elección del diálogo Exportar) y `migrado`. No se deduplica por URL en la búsqueda de texto: cada dataset se consulta una vez por página, y contratos y procesos son entidades distintas.

## 7. Paginación y memoria
Problemas actuales: `_detalle_cache` acumula el detalle de todas las páginas visitadas; exportar "todos" acumula hasta 20 páginas (10.000 registros) en memoria y escribe al final; las pestañas de detalle solo se construyen en la página 1; cada página pide `page_size` filas a cada uno de los 3 datasets (hasta 3× el tamaño), pero la etiqueta asume 1×; sin total real ni última página; volver a una página ya vista vuelve a consultar la API.

**Paginación**
- Tras la primera página, una consulta en segundo plano `count(*)` por dataset con los mismos filtros da el total real: "Página 3 de 17 (≈8.230 registros)". Si el conteo falla, se conserva el comportamiento actual (total estimado) sin bloquear.
- Se habilitan "última página" e "ir a página N" (el total de páginas es el máximo entre los conteos por dataset dividido por el tamaño de página).
- Tamaño de página por dataset seleccionable: 50, 100, 200 o 500; **100 por defecto**. La etiqueta dice "hasta N por dataset".

**Memoria**
- Solo la página actual vive en la tabla; el detalle crudo no se acumula entre páginas.
- Caché de las últimas 5 páginas visitadas (ir y volver sin consultar de nuevo); se invalida al cambiar los filtros o el tamaño de página.
- Las pestañas de detalle se reconstruyen en cada página.

**Exportar "todos"**
- Escritura incremental a disco, página por página: CSV y JSON directo; Excel con openpyxl en modo `write_only`. No se acumulan filas en memoria.
- Se elimina el tope silencioso de 20 páginas. Antes de empezar se muestra el total estimado ("se exportarán ≈N registros") y **se pide confirmación si supera 1.000 registros**.
- Botón **Cancelar** durante cualquier carga o exportación larga; al cancelar se cierra y se borra el archivo parcial.
- Pruebas pytest: cálculo de páginas y total, caché de páginas (límite 5, invalidación), exportación incremental y cancelación con un cliente falso.

## 5. Errores y pruebas
- Errores de red a la barra de estado, sin bloquear la ventana.
- pytest para `storage` (migración, duplicados, escritura atómica) y para `Filtros` → parámetros Socrata, sin llamadas de red.
- `app_secop.py` cambia solo en los puntos de integración.
