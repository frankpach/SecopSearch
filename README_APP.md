# SECOP II - App de Consulta Integrada

Aplicacion de escritorio con interfaz grafica (GUI) para consultar informacion de empresas en los datasets publicos de SECOP II via API Socrata.

## Descripcion

Esta herramienta permite realizar debida diligencia automatizada sobre empresas de vigilancia y seguridad privada (o cualquier proveedor) consultando simultaneamente 7 datasets oficiales de Colombia Compra Eficiente.

## Funcionalidades

- **Consulta integrada**: Busqueda por empresa predefinida, dataset especifico o NIT manual
- **Metadatos en tiempo real**: Muestra fecha de ultima actualizacion de cada dataset
- **Resultados por tabs**: Visualizacion organizada por dataset
- **Tabla resumen**: Consolidado de registros, valores, estados y fechas
- **Exportacion a Excel**: Archivo .xlsx con hoja por dataset + resumen
- **Exportacion a CSV**: Archivos .csv individuales por dataset

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
- Dependencias: `sodapy`, `pandas`, `openpyxl`, `tkinter`

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
pip install sodapy pandas openpyxl requests

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

1. **Seleccionar empresa**: Use el dropdown "Empresa" o dejelo en "TODAS"
2. **(Opcional) Ingresar NIT**: Si desea consultar otra empresa, escriba el NIT
3. **Seleccionar dataset**: Use "TODOS" para consultar todos, o uno especifico
4. **Presionar "Consultar"**: La app cargara los datos de la API
5. **Revisar resultados**: Navegue por las pestanas para ver cada dataset
6. **Exportar**: Use "Exportar Excel" o "Exportar CSV" para guardar

## Estructura de la interfaz

```
+-------------------------------------------------------------+
| SECOP II - Consulta Integrada                               |
+-------------------------------------------------------------+
| Parametros de Busqueda                                      |
| Empresa: [TODAS ▼]  Dataset: [TODOS ▼]  NIT: [________]    |
| [Consultar] [Exportar Excel] [Exportar CSV] [Limpiar]      |
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
| Error al exportar Excel | Verifique que tenga permisos de escritura en la carpeta |

## Licencia

Herramienta desarrollada para fines de debida diligencia en procesos de contratacion publica. Uso interno.

## Contacto

Para soporte tecnico, consulte el informe final de debida diligencia en el archivo `INFORME_FINAL_DEBIDA_DILIGENCIA.md`.
