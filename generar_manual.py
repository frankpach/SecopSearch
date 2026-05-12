#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Genera el manual de usuario de la App SECOP II en PDF.
Ejecutar: python generar_manual.py
"""

from fpdf import FPDF, XPos, YPos
from datetime import datetime

def _s(text):
    """Reemplaza caracteres fuera de latin-1 por equivalentes ASCII."""
    return (text
        .replace("-", "-")   # em dash
        .replace("-", "-")   # en dash
        .replace("’", "'")   # comilla derecha
        .replace("‘", "'")   # comilla izquierda
        .replace("“", '"')
        .replace("”", '"')
        .replace("-", "-")   # bullet
        .replace("é", "e")
        .encode("latin-1", errors="replace").decode("latin-1")
    )

OUTPUT = "MANUAL_APP_SECOP_II.pdf"


class PDF(FPDF):
    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=18)

    def header(self):
        self.set_fill_color(26, 84, 144)
        self.rect(0, 0, 210, 12, "F")
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(255, 255, 255)
        self.set_xy(10, 2)
        self.cell(0, 8, "SECOP II - App de Consulta Integrada  |  Manual de Usuario", align="L")
        self.set_text_color(0, 0, 0)
        self.ln(8)

    def footer(self):
        pass

    # ------------------------------------------------------------------
    def titulo_seccion(self, texto):
        self.ln(4)
        self.set_fill_color(26, 84, 144)
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(255, 255, 255)
        self.cell(0, 8, f"  {texto}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
        self.set_text_color(0, 0, 0)
        self.ln(2)

    def subtitulo(self, texto):
        self.ln(2)
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(26, 84, 144)
        self.cell(0, 7, texto, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(0, 0, 0)

    def parrafo(self, texto, indent=0):
        self.set_font("Helvetica", "", 9.5)
        self.set_x(10 + indent)
        self.multi_cell(0, 5.5, texto)
        self.ln(1)

    def bullet(self, texto, indent=8):
        self.set_font("Helvetica", "", 9.5)
        self.set_x(10 + indent)
        self.multi_cell(0, 5.5, f"  -  {texto}")

    def nota(self, texto):
        self.set_fill_color(232, 240, 254)
        self.set_font("Helvetica", "I", 9)
        self.set_x(10)
        self.multi_cell(0, 5.5, f"  Nota: {texto}", fill=True)
        self.ln(1)

    def alerta(self, texto):
        self.set_fill_color(255, 243, 205)
        self.set_font("Helvetica", "B", 9)
        self.set_x(10)
        self.multi_cell(0, 5.5, f"  Atencion: {texto}", fill=True)
        self.ln(1)

    def tabla_header(self, cols, anchos):
        self.set_fill_color(44, 62, 80)
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(255, 255, 255)
        for col, ancho in zip(cols, anchos):
            self.cell(ancho, 7, col, border=0, fill=True)
        self.ln()
        self.set_text_color(0, 0, 0)

    def tabla_fila(self, datos, anchos, par=True):
        self.set_fill_color(247, 249, 252 if par else 255)
        self.set_font("Helvetica", "", 8.5)
        for dato, ancho in zip(datos, anchos):
            self.cell(ancho, 6, str(dato)[:40], border=0, fill=True)
        self.ln()

    def linea_sep(self):
        self.set_draw_color(200, 200, 200)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(2)


# ======================================================================
def generar():
    pdf = PDF()
    pdf.set_margins(10, 16, 10)

    # ==================================================================
    # PORTADA
    # ==================================================================
    pdf.add_page()
    pdf.set_fill_color(26, 84, 144)
    pdf.rect(0, 0, 210, 297, "F")

    pdf.set_font("Helvetica", "B", 28)
    pdf.set_text_color(255, 255, 255)
    pdf.set_xy(0, 60)
    pdf.cell(210, 14, "SECOP II", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(210, 10, "App de Consulta Integrada", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)

    pdf.set_font("Helvetica", "", 13)
    pdf.cell(210, 8, "Debida Diligencia en Contratacion Publica", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(12)

    pdf.set_fill_color(255, 255, 255)
    pdf.set_draw_color(255, 255, 255)
    pdf.rect(30, 130, 150, 0.5, "F")
    pdf.ln(6)

    pdf.set_font("Helvetica", "", 11)
    pdf.set_xy(0, 148)
    pdf.cell(210, 8, "Manual de Usuario - Version 2.0", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(210, 8, f"Colombia Compra Eficiente | API Socrata", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 9)
    pdf.cell(210, 8, "Cartagena de Indias D. T. y C, 28 de Abril de 2026", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_xy(0, 240)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(180, 210, 255)
    pdf.cell(210, 6, "Creado por: FRANK PACHECO", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(0, 0, 0)

    # ==================================================================
    # INDICE
    # ==================================================================
    pdf.add_page()
    pdf.titulo_seccion("Contenido")
    secciones = [
        ("1", "Descripcion general", "3"),
        ("2", "Requisitos e instalacion", "3"),
        ("3", "Configuracion de credenciales", "4"),
        ("4", "Interfaz de usuario", "4"),
        ("5", "Panel de Consulta - campos y controles", "5"),
        ("6", "Flujos de busqueda", "6"),
        ("7", "Tabla de resultados - Resumen", "7"),
        ("8", "Tabs de detalle por dataset", "8"),
        ("9", "Historial de empresas y entidades", "9"),
        ("10", "Paginacion y carga progresiva", "9"),
        ("11", "Exportacion a Excel y CSV", "10"),
        ("12", "Fuentes de datos (datasets)", "10"),
        ("13", "Colores y estados de contratos", "11"),
        ("14", "Solucion de problemas frecuentes", "11"),
        ("15", "Glosario", "12"),
    ]
    pdf.set_font("Helvetica", "", 10)
    for num, titulo, pag in secciones:
        pdf.set_x(14)
        pdf.cell(10, 7, f"{num}.", align="R")
        pdf.cell(140, 7, titulo)
        pdf.cell(0, 7, pag, align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # ==================================================================
    # 1. DESCRIPCION GENERAL
    # ==================================================================
    pdf.add_page()
    pdf.titulo_seccion("1. Descripcion general")
    pdf.parrafo(
        "La App SECOP II es una herramienta de escritorio que permite consultar de forma integrada "
        "los datasets publicos de Colombia Compra Eficiente (datos.gov.co) mediante la API Socrata. "
        "Fue desarrollada para realizar debida diligencia sobre empresas de vigilancia y seguridad "
        "privada participantes en procesos de contratacion publica, pero puede usarse para cualquier "
        "proveedor o entidad contratante."
    )
    pdf.subtitulo("Capacidades principales")
    caps = [
        "Consultar contratos, procesos, sanciones e inhabilidades simultaneamente en 7 datasets oficiales.",
        "Buscar por proveedor (NIT), entidad contratante (nombre o NIT), categoria UNSPSC, o combinaciones.",
        "Guardar un historial local de empresas y entidades consultadas para acceso rapido.",
        "Visualizar resultados con codigos de color segun el estado del contrato.",
        "Abrir cualquier contrato SECOP II directamente en el navegador con doble clic.",
        "Paginar resultados grandes sin bloquear la interfaz (carga progresiva en hilo separado).",
        "Exportar resultados completos a Excel o CSV.",
        "Ver datos crudos de cada dataset en tabs de detalle independientes.",
    ]
    for c in caps:
        pdf.bullet(c)

    # ==================================================================
    # 2. REQUISITOS E INSTALACION
    # ==================================================================
    pdf.titulo_seccion("2. Requisitos e instalacion")
    pdf.subtitulo("Requisitos del sistema")
    pdf.bullet("Windows 10/11 (64 bits)")
    pdf.bullet("Python 3.8 o superior")
    pdf.bullet("Conexion a Internet (para consultar la API de datos.gov.co)")
    pdf.bullet("Dependencias Python: requests, pandas, openpyxl, fpdf2")

    pdf.subtitulo("Instalacion rapida (entorno virtual ya creado)")
    pdf.parrafo("Si el entorno virtual venv_secop ya existe en la carpeta del proyecto:", indent=4)
    pdf.set_font("Courier", "", 9)
    pdf.set_fill_color(240, 240, 240)
    pdf.set_x(14)
    pdf.multi_cell(0, 5.5,
        ".\\venv_secop\\Scripts\\activate\n"
        "python app_secop.py",
        fill=True
    )
    pdf.set_font("Helvetica", "", 9.5)
    pdf.ln(2)

    pdf.subtitulo("Instalacion desde cero")
    pdf.set_font("Courier", "", 9)
    pdf.set_fill_color(240, 240, 240)
    pdf.set_x(14)
    pdf.multi_cell(0, 5.5,
        "python -m venv venv_secop\n"
        ".\\venv_secop\\Scripts\\activate\n"
        "pip install requests pandas openpyxl fpdf2",
        fill=True
    )
    pdf.set_font("Helvetica", "", 9.5)

    # ==================================================================
    # 3. CREDENCIALES
    # ==================================================================
    pdf.titulo_seccion("3. Configuracion de credenciales")
    pdf.parrafo(
        "La app lee las credenciales de acceso a la API Socrata desde el archivo .env ubicado "
        "en la misma carpeta que app_secop.py. El formato es:"
    )
    pdf.set_font("Courier", "", 9)
    pdf.set_fill_color(240, 240, 240)
    pdf.set_x(14)
    pdf.multi_cell(0, 5.5,
        "socrataClaveAPI=TU_CLAVE_API\n"
        "socrataClaveSecretaAPI=TU_SECRETO\n"
        "user=TU_EMAIL\n"
        "password=TU_PASSWORD",
        fill=True
    )
    pdf.set_font("Helvetica", "", 9.5)
    pdf.ln(2)
    pdf.nota(
        "Si el archivo .env no existe o las credenciales son invalidas, la app opera en modo "
        "publico (sin autenticacion). El modo publico tiene limites de tasa mas estrictos y "
        "puede recibir errores 429 (Too Many Requests) con consultas masivas."
    )

    # ==================================================================
    # 4. INTERFAZ DE USUARIO
    # ==================================================================
    pdf.add_page()
    pdf.titulo_seccion("4. Interfaz de usuario")
    pdf.parrafo("La ventana principal esta compuesta por cinco zonas:")

    zonas = [
        ("Encabezado", "Titulo de la aplicacion. Fijo, no interactivo."),
        ("Panel de Consulta", "Tres filas de controles para definir los parametros de busqueda."),
        ("Estado de fuentes", "Muestra la fecha de ultima actualizacion de cada dataset en datos.gov.co."),
        ("Area de Resultados", "Notebook con el tab Resumen (siempre visible) y tabs de detalle dinamicos."),
        ("Barra de estado", "Mensajes de progreso, conteos y URLs al pasar el cursor sobre filas."),
    ]
    anchos_z = [50, 140]
    pdf.tabla_header(["Zona", "Descripcion"], anchos_z)
    for i, (zona, desc) in enumerate(zonas):
        pdf.tabla_fila([zona, desc], anchos_z, par=(i % 2 == 0))

    pdf.ln(4)
    pdf.alerta(
        "Durante una consulta activa todos los controles se deshabilitan y aparece una barra "
        "de progreso animada. No cierre la ventana mientras consulta."
    )

    # ==================================================================
    # 5. PANEL DE CONSULTA
    # ==================================================================
    pdf.titulo_seccion("5. Panel de Consulta - campos y controles")

    pdf.subtitulo("Fila 1 - Proveedor (empresa a investigar)")
    campos_f1 = [
        ("Empresa", "Desplegable con el historial de empresas guardadas. Seleccione 'TODAS' para consultar todas las del historial simultaneamente."),
        ("Boton Eliminar", "Elimina la empresa seleccionada del historial local (pide confirmacion)."),
        ("NIT manual", "Ingrese el NIT de cualquier empresa no guardada en el historial (8-11 digitos)."),
        ("Boton Guardar", "Agrega el NIT manual al historial para consultas futuras."),
    ]
    for campo, desc in campos_f1:
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.set_x(14)
        pdf.cell(40, 6, campo + ":")
        pdf.set_font("Helvetica", "", 9.5)
        pdf.multi_cell(0, 6, desc)

    pdf.subtitulo("Fila 2 - Entidad contratante (opcional)")
    campos_f2 = [
        ("Entidad", "Desplegable con el historial de entidades guardadas. Al seleccionar una, rellena automaticamente los campos de nombre y NIT."),
        ("Boton Eliminar", "Elimina la entidad seleccionada del historial."),
        ("Entidad NIT", "NIT de la entidad contratante para filtrar por ella en los datasets."),
        ("Boton Guardar", "Guarda la entidad (nombre + NIT) en el historial de entidades."),
    ]
    for campo, desc in campos_f2:
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.set_x(14)
        pdf.cell(40, 6, campo + ":")
        pdf.set_font("Helvetica", "", 9.5)
        pdf.multi_cell(0, 6, desc)

    pdf.subtitulo("Fila 3 - Filtros adicionales y acciones")
    campos_f3 = [
        ("UNSPSC", "Codigo de categoria de producto/servicio segun el estandar UNSPSC. Filtra contratos por categoria. Ejemplo: 92101500 (vigilancia)."),
        ("Entidad (nombre)", "Texto libre para buscar por nombre de entidad contratante usando full-text search."),
        ("Consultar", "Inicia la busqueda con los parametros actuales. Carga la primera pagina de resultados."),
        ("Exportar Excel", "Descarga TODOS los datos (paginando internamente) y genera un archivo .xlsx."),
        ("Exportar CSV", "Igual que Excel pero en formato .csv."),
        ("Limpiar", "Borra los resultados y reinicia los filtros a sus valores por defecto."),
    ]
    for campo, desc in campos_f3:
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.set_x(14)
        pdf.cell(40, 6, campo + ":")
        pdf.set_font("Helvetica", "", 9.5)
        pdf.multi_cell(0, 6, desc)

    # ==================================================================
    # 6. FLUJOS DE BUSQUEDA
    # ==================================================================
    pdf.add_page()
    pdf.titulo_seccion("6. Flujos de busqueda")

    pdf.subtitulo("A. Buscar todos los contratos de una empresa")
    pdf.parrafo("Caso de uso: debida diligencia sobre un proveedor especifico.")
    pasos_a = [
        "En 'Empresa' seleccione la empresa del historial, O escriba su NIT en 'NIT manual'.",
        "Deje 'Entidad', 'Entidad NIT', 'UNSPSC' y 'Entidad (nombre)' en blanco.",
        "Presione 'Consultar'.",
        "El Resumen mostrara todos los contratos del proveedor en SECOP I y II, mas sanciones e inhabilidades.",
    ]
    for i, p in enumerate(pasos_a, 1):
        pdf.bullet(f"{i}. {p}")
    pdf.ln(2)

    pdf.subtitulo("B. Buscar todos los contratos de una entidad contratante")
    pdf.parrafo("Caso de uso: ver con quienes contrata una entidad publica.")
    pasos_b = [
        "Deje 'Empresa' en 'TODAS' y 'NIT manual' en blanco.",
        "En 'Entidad (nombre)' escriba parte del nombre de la entidad (ej: 'Barranquilla Verde').",
        "Opcionalmente ingrese el NIT de la entidad en 'Entidad NIT' para mayor precision.",
        "Presione 'Consultar'.",
    ]
    for i, p in enumerate(pasos_b, 1):
        pdf.bullet(f"{i}. {p}")
    pdf.nota("Las busquedas por nombre de entidad usan full-text search ($q) que es mas rapido que busqueda exacta.")
    pdf.ln(2)

    pdf.subtitulo("C. Buscar contratos de una empresa con una entidad especifica")
    pdf.parrafo("Caso de uso: verificar si empresa X ha contratado con entidad Y.")
    pasos_c = [
        "Seleccione la empresa en 'Empresa' o ingrese su NIT.",
        "Ingrese el nombre o NIT de la entidad en los campos correspondientes.",
        "Presione 'Consultar'.",
        "Los resultados mostraran solo los contratos que cruzan ambos filtros.",
    ]
    for i, p in enumerate(pasos_c, 1):
        pdf.bullet(f"{i}. {p}")
    pdf.ln(2)

    pdf.subtitulo("D. Buscar por categoria UNSPSC")
    pdf.parrafo("Caso de uso: encontrar todos los contratos de vigilancia de una entidad.")
    pasos_d = [
        "Ingrese el codigo UNSPSC en el campo correspondiente (ej: 92101500).",
        "Opcionalmente combine con nombre de entidad.",
        "Presione 'Consultar'.",
    ]
    for i, p in enumerate(pasos_d, 1):
        pdf.bullet(f"{i}. {p}")
    pdf.ln(2)

    pdf.subtitulo("E. Consultar todas las empresas del historial")
    pdf.parrafo(
        "Si 'Empresa' esta en 'TODAS' y no hay NIT manual, la app consulta todas las empresas "
        "del historial de forma secuencial y acumula los resultados en el Resumen."
    )
    pdf.alerta(
        "Consultar TODAS las empresas puede tardar varios minutos dependiendo del numero de "
        "empresas en el historial y la velocidad de la API."
    )

    # ==================================================================
    # 7. TABLA RESUMEN
    # ==================================================================
    pdf.add_page()
    pdf.titulo_seccion("7. Tabla de resultados - Resumen")
    pdf.parrafo(
        "El tab 'Resumen' es la vista principal. Muestra una fila por cada contrato o registro "
        "encontrado, con las columnas mas relevantes para la debida diligencia."
    )

    pdf.subtitulo("Columnas disponibles")
    columnas = [
        ("Empresa", "Nombre o NIT del proveedor consultado."),
        ("Fuente", "Dataset de origen: SECOP II, SECOP I, Sancion SECOP II, SIRI Procuraduria, etc."),
        ("Entidad", "Nombre de la entidad contratante."),
        ("NIT Entidad", "NIT de la entidad contratante."),
        ("ID Contrato", "Identificador unico del contrato en SECOP II (CO1.PCCNTR.XXXXXXX). Las filas en azul tienen enlace directo."),
        ("Objeto", "Descripcion del objeto contractual (primeros 80 caracteres)."),
        ("Valor", "Valor total del contrato con adiciones."),
        ("Pagado", "Valor pagado registrado en SECOP II a fecha de corte."),
        ("Pendiente", "Valor pendiente de pago registrado en SECOP II."),
        ("Estado", "Estado actual del contrato (ver seccion 13 para colores)."),
        ("Firma", "Fecha de firma del contrato."),
        ("Fin", "Fecha de fin del contrato."),
        ("Sancion", "SI si la fila proviene de un dataset de sanciones o SIRI."),
    ]
    anchos_c = [32, 158]
    pdf.tabla_header(["Columna", "Descripcion"], anchos_c)
    for i, (col, desc) in enumerate(columnas):
        pdf.tabla_fila([col, desc], anchos_c, par=(i % 2 == 0))

    pdf.ln(4)
    pdf.subtitulo("Interaccion con la tabla")
    interacciones = [
        "Clic en encabezado de columna: ordena ascendente/descendente.",
        "Cursor sobre una fila con URL: cambia a manita y muestra la URL en la barra de estado.",
        "Doble clic en una fila: abre el contrato en el navegador (solo filas SECOP II con ID).",
        "Clic derecho: menu contextual con opciones 'Abrir en navegador', 'Copiar URL' y 'Copiar fila completa'.",
    ]
    for i in interacciones:
        pdf.bullet(i)

    # ==================================================================
    # 8. TABS DE DETALLE
    # ==================================================================
    pdf.titulo_seccion("8. Tabs de detalle por dataset")
    pdf.parrafo(
        "Despues de cada consulta, la app crea automaticamente tabs adicionales para cada "
        "dataset que haya devuelto datos. Estos tabs muestran los registros crudos con TODAS "
        "las columnas originales del dataset, sin filtrar ni normalizar."
    )
    tabs = [
        ("Contratos SECOP II", "Dataset jbjy-vk9h. Contratos electronicos en ejecucion o ejecutados."),
        ("SECOP II - Procesos", "Dataset p6dx-8zbt. Procesos de contratacion (incluye no adjudicados)."),
        ("SECOP Integrado (historico)", "Dataset rpmr-utcd. Contratos SECOP I y II historicos."),
        ("Proveedor SECOP II", "Dataset qmzu-gj57. Registro del proveedor en la plataforma."),
        ("Sanciones SECOP II", "Dataset it5q-hg94. Multas y sanciones vigentes."),
        ("Sanciones SECOP I", "Dataset 4n4q-k399. Multas y sanciones historicas."),
        ("SIRI Procuraduria", "Dataset iaeu-rcn6. Inhabilidades e incompatibilidades."),
    ]
    anchos_t = [55, 135]
    pdf.tabla_header(["Tab", "Contenido"], anchos_t)
    for i, (tab, desc) in enumerate(tabs):
        pdf.tabla_fila([tab, desc], anchos_t, par=(i % 2 == 0))

    pdf.ln(3)
    pdf.nota(
        "Los tabs desaparecen al limpiar o iniciar una nueva consulta. Solo aparecen si el "
        "dataset devolvio al menos un registro."
    )

    # ==================================================================
    # 9. HISTORIAL
    # ==================================================================
    pdf.add_page()
    pdf.titulo_seccion("9. Historial de empresas y entidades")
    pdf.parrafo(
        "La app mantiene dos archivos JSON locales en la misma carpeta que app_secop.py:"
    )
    pdf.bullet("empresas_historial.json - guarda nombre, NIT y fecha de ultima consulta de cada empresa.")
    pdf.bullet("entidades_historial.json - guarda nombre y NIT de cada entidad contratante guardada.")
    pdf.ln(2)
    pdf.parrafo("Operaciones disponibles:")
    hist_ops = [
        ("Guardar empresa", "Ingrese el NIT en 'NIT manual' y presione 'Guardar'. La empresa queda disponible en el desplegable."),
        ("Guardar entidad", "Ingrese nombre y/o NIT en los campos de Entidad y presione 'Guardar'."),
        ("Eliminar empresa/entidad", "Seleccione en el desplegable y presione 'Eliminar'. Pide confirmacion."),
        ("Consultar historial completo", "Seleccione 'TODAS' en el desplegable de empresa para consultar todas las guardadas de una vez."),
    ]
    for op, desc in hist_ops:
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.set_x(14)
        pdf.cell(45, 6, op + ":")
        pdf.set_font("Helvetica", "", 9.5)
        pdf.multi_cell(0, 6, desc)

    # ==================================================================
    # 10. PAGINACION
    # ==================================================================
    pdf.titulo_seccion("10. Paginacion y carga progresiva")
    pdf.parrafo(
        "Para evitar bloquear la interfaz y respetar los limites de la API, los resultados "
        "se cargan de a 500 registros por pagina (primera pagina al presionar 'Consultar'). "
        "Si hay mas datos disponibles, los controles de paginacion aparecen debajo de la tabla."
    )
    pdf.subtitulo("Controles de paginacion")
    pag_ctrl = [
        ("|<<", "Ir a la primera pagina."),
        ("<", "Pagina anterior."),
        ("Pagina X de Y (N registros)", "Indicador de posicion actual y total acumulado."),
        (">", "Pagina siguiente (carga la siguiente desde la API)."),
        (">>|", "Ultima pagina conocida (solo avanza si se han cargado todas)."),
    ]
    for ctrl, desc in pag_ctrl:
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.set_x(14)
        pdf.cell(35, 6, ctrl)
        pdf.set_font("Helvetica", "", 9.5)
        pdf.multi_cell(0, 6, desc)
    pdf.nota(
        "El boton 'Exportar Excel/CSV' descarga TODOS los datos (no solo la pagina visible) "
        "paginando internamente de forma automatica. Puede tardar mas que una consulta normal."
    )

    # ==================================================================
    # 11. EXPORTACION
    # ==================================================================
    pdf.titulo_seccion("11. Exportacion a Excel y CSV")
    pdf.parrafo(
        "Ambos botones de exportacion estan disponibles despues de realizar una consulta. "
        "La exportacion descarga la totalidad de los datos disponibles (no solo la pagina visible)."
    )
    pdf.subtitulo("Exportar Excel (.xlsx)")
    pdf.bullet("Genera un archivo con una hoja que contiene todas las filas del Resumen normalizado.")
    pdf.bullet("El nombre por defecto incluye la fecha y hora: SECOP_20260511_1430.xlsx")
    pdf.bullet("Se abre el dialogo de guardar archivo para elegir ubicacion y nombre.")
    pdf.subtitulo("Exportar CSV (.csv)")
    pdf.bullet("Igual que Excel pero en formato CSV con codificacion UTF-8 BOM (compatible con Excel en Windows).")
    pdf.bullet("Util para importar en otras herramientas de analisis (Power BI, Google Sheets, etc.).")

    # ==================================================================
    # 12. FUENTES DE DATOS
    # ==================================================================
    pdf.add_page()
    pdf.titulo_seccion("12. Fuentes de datos (datasets)")
    datasets = [
        ("jbjy-vk9h", "SECOP II - Contratos Electronicos", "Contratos en ejecucion y ejecutados. Campo clave: documento_proveedor."),
        ("p6dx-8zbt", "SECOP II - Procesos", "Procesos de contratacion adjudicados. Campo clave: nit_del_proveedor_adjudicado."),
        ("rpmr-utcd", "SECOP Integrado", "Historico combinado SECOP I + II. Campo clave: documento_proveedor."),
        ("qmzu-gj57", "Proveedores SECOP II", "Registro de proveedores en la plataforma. Campo clave: nit."),
        ("it5q-hg94", "Sanciones SECOP II", "Multas y sanciones vigentes. Busqueda por nombre ($q)."),
        ("4n4q-k399", "Sanciones SECOP I", "Multas historicas SECOP I. Busqueda por nombre ($q)."),
        ("iaeu-rcn6", "SIRI Procuraduria", "Inhabilidades e incompatibilidades. Campo clave: numero_identificacion."),
    ]
    anchos_d = [28, 45, 117]
    pdf.tabla_header(["ID Dataset", "Nombre", "Descripcion y campo de busqueda"], anchos_d)
    for i, (ds_id, nombre, desc) in enumerate(datasets):
        pdf.tabla_fila([ds_id, nombre, desc], anchos_d, par=(i % 2 == 0))

    pdf.ln(3)
    pdf.nota(
        "Los datos en datos.gov.co pueden tener un retraso de 24-48 horas respecto a SECOP II. "
        "La fecha de ultima actualizacion de cada dataset se muestra en el panel 'Estado de fuentes'."
    )

    # ==================================================================
    # 13. COLORES Y ESTADOS
    # ==================================================================
    pdf.titulo_seccion("13. Colores y estados de contratos")
    estados = [
        ("Cancelado", "Rojo claro / texto rojo oscuro", "El contrato fue cancelado antes de ejecutarse."),
        ("Terminado", "Amarillo claro / texto naranja", "El contrato concluyo normalmente."),
        ("En Ejecucion", "Verde claro / texto verde oscuro", "El contrato esta activo y en curso."),
        ("Adjudicado", "Azul claro / texto azul oscuro", "Adjudicado pero aun no iniciado."),
        ("Liquidado", "Lila claro / texto morado", "Contrato liquidado formalmente."),
        ("Modificado", "Verde claro / texto verde", "El contrato tiene prorroga o adicion."),
        ("Sin Contratos", "Gris / texto gris", "La empresa no tiene registros en SECOP."),
        ("Sancion", "Rojo / texto rojo", "Registro proveniente de dataset de sanciones o SIRI."),
    ]
    anchos_e = [30, 55, 105]
    pdf.tabla_header(["Estado", "Color", "Significado"], anchos_e)
    for i, (est, color, sig) in enumerate(estados):
        pdf.tabla_fila([est, color, sig], anchos_e, par=(i % 2 == 0))

    # ==================================================================
    # 14. SOLUCION DE PROBLEMAS
    # ==================================================================
    pdf.add_page()
    pdf.titulo_seccion("14. Solucion de problemas frecuentes")
    problemas = [
        (
            "La ventana no responde al consultar",
            "Normal durante la carga inicial. La consulta corre en hilo separado. Espere a que "
            "la barra de progreso desaparezca. Si persiste mas de 3 minutos, puede haber un "
            "problema de red."
        ),
        (
            "Error 429 Too Many Requests",
            "La API de Socrata impuso un limite de tasa. Espere 30-60 segundos y reintente. "
            "Con credenciales en .env el limite es mayor. Verifique que .env este configurado."
        ),
        (
            "Error 403 Forbidden en un dataset",
            "El dataset puede requerir autenticacion o estar temporalmente restringido. "
            "Verifique las credenciales en .env."
        ),
        (
            "No se encontraron registros para una empresa conocida",
            "Verifique que el NIT este correcto (sin guion de verificacion o con el, dependiendo "
            "de como este registrado en SECOP). Pruebe con el NIT con y sin el ultimo digito."
        ),
        (
            "El tab de detalle no aparece",
            "El dataset no devolvio registros para esa empresa. Es normal para empresas sin "
            "contratos publicos o sin sanciones registradas."
        ),
        (
            "Doble clic no abre el navegador",
            "La fila seleccionada proviene de SECOP I o de un dataset de sanciones y no tiene "
            "URL directa. Solo los contratos SECOP II con ID CO1.PCCNTR tienen enlace."
        ),
        (
            "La exportacion tarda mucho",
            "La exportacion descarga todos los datos paginando la API (no solo la pagina visible). "
            "Para empresas con muchos contratos puede tardar varios minutos."
        ),
        (
            "Error al guardar Excel: permiso denegado",
            "El archivo puede estar abierto en Excel. Cierre el archivo y reintente, o elija "
            "una ubicacion diferente."
        ),
    ]
    for prob, sol in problemas:
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.set_x(10)
        pdf.multi_cell(0, 6, f"Problema: {prob}")
        pdf.set_font("Helvetica", "", 9.5)
        pdf.set_x(14)
        pdf.multi_cell(0, 6, f"Solucion: {sol}")
        pdf.linea_sep()

    # ==================================================================
    # 15. GLOSARIO
    # ==================================================================
    pdf.titulo_seccion("15. Glosario")
    terminos = [
        ("API Socrata", "Interfaz de programacion usada por datos.gov.co para exponer los datasets de Colombia Compra Eficiente."),
        ("SECOP I", "Sistema Electronico de Contratacion Publica primera generacion (contratos anteriores a ~2015)."),
        ("SECOP II", "Plataforma de contratacion publica de segunda generacion, activa desde 2015."),
        ("UNSPSC", "Clasificacion internacional de productos y servicios (United Nations Standard Products and Services Code)."),
        ("NIT", "Numero de Identificacion Tributaria. Identificador unico de personas juridicas en Colombia."),
        ("SIRI", "Sistema de Informacion de Registro de Sanciones e Inhabilidades de la Procuraduria General."),
        ("SoQL", "Socrata Query Language. Lenguaje de consulta similar a SQL usado en la API de Socrata."),
        ("Full-text search ($q)", "Metodo de busqueda por texto libre en la API Socrata, mas rapido que LIKE para grandes volumenes."),
        ("Dataset", "Conjunto de datos publicado en datos.gov.co, identificado por un codigo de 9 caracteres."),
        ("Debida diligencia", "Proceso de investigacion y verificacion sobre una empresa antes de contratarla."),
        ("Paginacion", "Tecnica de cargar los resultados en bloques (paginas) para no saturar la API ni la interfaz."),
        ("Historial local", "Archivos JSON guardados en la carpeta del proyecto que persisten entre sesiones."),
    ]
    anchos_g = [45, 145]
    pdf.tabla_header(["Termino", "Definicion"], anchos_g)
    for i, (term, defn) in enumerate(terminos):
        pdf.tabla_fila([term, defn], anchos_g, par=(i % 2 == 0))

    # ==================================================================
    # GUARDAR
    # ==================================================================
    pdf.output(OUTPUT)
    print(f"PDF generado: {OUTPUT}")


if __name__ == "__main__":
    generar()


