import os
import time
#from turtle import color
import streamlit as st
import markdown
import re
import requests 

# 1. Configuración de la página
st.set_page_config(
    page_title="Agente Documentador de Procesos",
    layout="wide"
)

# --- CONFIGURACIÓN DE ENTORNO Y LLAVE ---
os.environ["GEMINI_API_KEY"] = st.secrets["GEMINI_FREE_KEY"]
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- URL GOOGLE APPS SCRIPT ---
URL_APPS_SCRIPT = "https://script.google.com/macros/s/AKfycbwvFHgoogdYKKHo5zqtjt4p3hIFc9VAS_GKJFRyOwxzT1Jp0HIEY4oLpPWCNjgazmlR/exec"

# --- FUNCIONES DE CONEXIÓN CON GEMINI Y DRIVE VIA WEBHOOK ---
def inicializar_agente():
    from google import genai
    return genai.Client()

def subir_a_google_drive_via_script(nombre_archivo, contenido_html):
    """Manda el documento de forma segura a través de Apps Script sin necesidad de Google Cloud Console"""
    try:
        payload = {
            "nombre": nombre_archivo,
            "html": contenido_html
        }
        # Mandamos los datos como JSON a tu script de Google
        respuesta = requests.post(URL_APPS_SCRIPT, json=payload, timeout=30)
        
        if respuesta.status_code == 200:
            resultado = respuesta.json()
            if resultado.get("status") == "success":
                return resultado.get("fileId")
            else:
                st.error(f"Error en Google Script: {resultado.get('message')}")
        else:
            st.error(f"No se pudo conectar con Google Script. Código: {respuesta.status_code}")
    except Exception as e:
        st.error(f"Error al enviar a Google Drive: {str(e)}")
    return None

# --- DETECCIÓN AUTOMÁTICA DEL USUARIO ---
correo_autorizador = "No especificado / Usuario Local"

if hasattr(st, "context") and hasattr(st.context, "user") and getattr(st.context.user, "email", None):
    correo_autorizador = st.context.user.email
elif hasattr(st, "experimental_user") and getattr(st.experimental_user, "email", None):
    correo_autorizador = st.experimental_user.email
elif hasattr(st, "user") and getattr(st.user, "email", None):
    correo_autorizador = st.user.email

st.title("Agente de Documentación Automatizada")
st.markdown("""
Este agente analiza el video de un proceso operativo, su audio y archivos adjuntos 
para generar documentación técnica e impecable de forma automática, evaluando el cumplimiento normativo.
""")

st.divider()

col_izquierda, col_derecha = st.columns([1, 1.2])

with col_izquierda:
    st.header("Carga de Evidencia")
    
    video_file = st.file_uploader(
        "1. Sube el video del proceso (.mp4, .mov, .avi)", 
        type=["mp4", "mov", "avi"],
        help="Graba tu pantalla mientras realizas el proceso y explícalo en voz alta."
    )
    
    ruta_video_local = None
    if video_file is not None:
        st.video(video_file)
        ruta_video_local = f"temp_local_{video_file.name}"
        with open(ruta_video_local, "wb") as f:
            f.write(video_file.getbuffer())
    
    adjuntos = st.file_uploader(
        "2. Archivos adjuntos / Contexto (Opcional)", 
        type=["txt", "sql", "csv", "xlsx", "pdf"],
        accept_multiple_files=True,
        help="Sube queries, plantillas de Excel o esquemas que uses en el proceso."
    )
    
    st.divider()
    st.header("Datos de Control del Proceso")
    proc_id = st.text_input("ID del Proceso", placeholder="Ej: 1234")
    proc_name = st.text_input("Nombre del Proceso", placeholder="Ej: Iniciales SQL").upper()
    proc_area = st.text_input("Área Responsable", placeholder="Ej: Soporte").upper()
    proc_dir = st.text_input("Dirección", placeholder="Ej: Dirección IT").upper()
    
    if correo_autorizador != "No especificado / Usuario Local":
        st.write(f"**Correo del autorizador:** `{correo_autorizador}`")
    else:
        st.write("**Correo del autorizador:** `[Usuario Local / No logueado]`")

    st.divider()
    boton_procesar = st.button("Generar Documentación", type="primary", use_container_width=True)

with col_derecha:
    st.header("Documentación Generada")
    
    if "resultado_ia" not in st.session_state:
        st.session_state["resultado_ia"] = ""
    if "drive_file_id" not in st.session_state:
        st.session_state["drive_file_id"] = None
    if "drive_file_id_tecnico" not in st.session_state:
        st.session_state["drive_file_id_tecnico"] = None

    if not boton_procesar and not st.session_state["resultado_ia"]:
        st.info("Sube un video, llena los datos de control y haz clic en 'Generar Documentación'.")
    
    if boton_procesar:
        if video_file is None:
            st.error("Por favor, sube un archivo de video primero.")
        elif not (proc_id and proc_name and proc_area and proc_dir):
            st.error("Por favor, rellena todos los Campos de Control (ID, Nombre, Área y Dirección) antes de continuar.")
        else:
            with st.spinner("Analizando evidencia y estructurando ambos reportes con Gemini..."):
                ruta_temporal = "temporal_proceso.mp4"
                lista_archivos_google = []
                
                try:
                    with open(ruta_temporal, "wb") as f:
                        f.write(video_file.getbuffer())
                    
                    cliente_gemini = inicializar_agente()
                    st.session_state["correo_autorizador_guardado"] = correo_autorizador
                    st.session_state["drive_file_id"] = None
                    st.session_state["drive_file_id_tecnico"] = None

                    # --- MARCO NORMATIVO ---
                    path_gobierno = os.path.join(BASE_DIR, "politicas", "politica_general_gobierno_dato.pdf")
                    path_metadatos = os.path.join(BASE_DIR, "politicas", "politica_gestion_metadatos.pdf")
                    path_calidad = os.path.join(BASE_DIR, "politicas", "politica_calidad_datos.pdf")
                    
                    for path_p in [path_gobierno, path_metadatos, path_calidad]:
                        if not os.path.exists(path_p):
                            raise FileNotFoundError(f"No se encontró el archivo normativo obligatorio en la ruta: {path_p}")
                    
                    from google.genai import types
                    upload_gobierno = cliente_gemini.files.upload(file=path_gobierno)
                    upload_metadatos = cliente_gemini.files.upload(file=path_metadatos)
                    upload_calidad = cliente_gemini.files.upload(file=path_calidad)
                    
                    lista_archivos_google.extend([upload_gobierno, upload_metadatos, upload_calidad])

                    # --- VIDEO ---
                    video_uploaded = cliente_gemini.files.upload(file=ruta_temporal)
                    while video_uploaded.state.name == "PROCESSING":
                        time.sleep(2)
                        video_uploaded = cliente_gemini.files.get(name=video_uploaded.name)
                        
                    if video_uploaded.state.name == "FAILED":
                        raise ValueError(f"El procesamiento del video falló: {video_uploaded.error.message}")
                    
                    lista_archivos_google.append(video_uploaded)

                    contenidos_para_gemini = [video_uploaded, upload_gobierno, upload_metadatos, upload_calidad]

                    if adjuntos:
                        for adjunto in adjuntos:
                            temp_adjunto_path = f"temp_{adjunto.name}"
                            with open(temp_adjunto_path, "wb") as f:
                                f.write(adjunto.getbuffer())
                            archivo_uploaded = cliente_gemini.files.upload(file=temp_adjunto_path)
                            contenidos_para_gemini.append(archivo_uploaded)
                            lista_archivos_google.append(archivo_uploaded)
                            if os.path.exists(temp_adjunto_path):
                                os.remove(temp_adjunto_path)

# --- PROMPT UNIFICADO DE DOS ENTREGABLES ---
                    encabezado_auditoria = f"# {proc_id} - {proc_name} - {proc_area} - {proc_dir}\n\n"
                    encabezado_tecnico = f"# DOC_{proc_id}_{proc_name.replace(' ', '_')}\n\n"
                    
                    prompt_maestro = f"""
                    Actúas como un Ingeniero de Procesos Senior y experto en Gobierno de Datos en Logrand. Tu objetivo es generar DOS entregables distintos en una misma respuesta, separados estrictamente por la etiqueta identificadora '=== FIN_REPORTE_AUDITORIA ==='.

                    Instrucciones de Formato General: Responde ÚNICAMENTE en formato Markdown estructurado. Está ESTRICTAMENTE PROHIBIDO usar barras '|' para tablas en cualquier sección; escribe todas las tablas usando código HTML puro (<table>, <tr>, <th>, <td>). No agregues introducciones ni saludos cordiales.

                    =========================================
                    ENTREGABLE 1: REPORTE DE AUDITORÍA Y CONTROL
                    =========================================
                    Este reporte debe iniciar con este título exacto:
                    {encabezado_auditoria}

                    Sigue estrictamente esta estructura de dos partes:

                    PARTE I: DIAGNÓSTICO INTEGRAL DE GOBIERNO Y CONTROL DE DATOS (EVALUACIÓN Y ALERTAS)

                    ## 1. Identificación y Origen
                    Detalla cómo se origina la solicitud, canales usados y criterios de aceptación mínimos.

                    ## 2. Linaje Operativo Observado y Nota de Discrepancia Técnica
                    Describe la secuencia de sistemas y la intervención manual.
                    ⚠️ SI DETECTAS DISCREPANCIA (por ejemplo: si en el audio/entrevista el usuario declara usar una base de datos o proceso automático, pero en el video se observa un copiado/pegado manual en Excel), DEBES INCLUIR UN RECUADRO CON EL CLASSIFICADOR HTML <div class="nota-discrepancia"> explicando la discrepancia exacta entre Audio y Video.

                    ## 2.5 Diagrama de Flujo del Dato (Visual)
                    Genera un diagrama de flujo horizontal usando estrictamente esta estructura HTML:
                    <table class="tabla-diagrama">
                      <tr>
                        <td class="nodo">[ORIGEN / INPUT]<span>[Detalle de la herramienta o archivo origen]</span></td>
                        <td class="flecha">➔</td>
                        <td class="nodo">[PROCESAMIENTO / TRANSFORMACIÓN]<span>[Detalle de la query o acción manual]</span></td>
                        <td class="flecha">➔</td>
                        <td class="nodo">[DESTINO / OUTPUT]<span>[Base de datos o reporte final generado]</span></td>
                      </tr>
                    </table>

                    ## 3. Evaluación Crítica de Cumplimiento (ALERTAS NORMATIVAS)
                    Busca de forma minuciosa brechas operativas contrastándolas con los tres PDFs provistos. Clasifica explícitamente las alertas:
                       
                       ### ALERTAS DE GOBIERNO DEL DATO
                       (Lístalas numeradas: 1., 2... Identifica la regla violada del PDF de gobierno, cita texto, sección, y redacta un recuadro de advertencia usando blockquotes `>`. Si no hay, pon: "Sin incidencias detectadas").
                       
                       ### ALERTAS DE GESTIÓN DE METADATOS
                       (Lístalas numeradas: 1., 2... Identifica la regla violada del PDF de metadatos, cita texto, sección, y redacta blockquotes `>`. Si no hay, pon: "Sin incidencias detectadas").
                       
                       ### ALERTAS DE CALIDAD DE DATOS
                       (Lístalas numeradas: 1., 2... Identifica la regla violada del PDF de calidad, cita texto, sección, y redacta blockquotes `>`. Si no hay, pon: "Sin incidencias detectadas").


                    PARTE II: MATRICES Y ENTREGABLES DE RELEVAMIENTO TÉCNICO-FUNCIONAL

                    ## 4. Requerimientos Funcionales y de Negocio (Módulo 1: Requerimientos)
                    Tabla HTML con: Nombre del Proceso, Área Solicitante, Canal y Frecuencia, Criterios de Aceptación, Nivel de Impacto en Negocio, Mecanismo de Priorización.

                    ## 5. Estructura de Gobernanza y Matriz de Responsabilidades (Módulo 2: Roles)
                    * Subsección A: Ficha de Asignación de Roles de Gobierno de Datos (Tabla HTML con Data Owner, Data Custodian, Data Steward, Data Consumers mapeados a los puestos reales).
                    * Subsección B: Matriz RACI Integrada de Gobierno y Operación (Tabla HTML cruzando el ciclo de vida del dato con los roles).

                    ## 6. Ecosistema Tecnológico y Mapa de Infraestructura (Módulo 3: Activos e Infraestructura)
                    Tabla HTML mapeando: Archivos/Sistemas Origen, Archivos/Sistemas Destino, Mapeo de Transformación Real, Repositorio/Seguridad, Resguardo del Conocimiento.

                    ## 7. Diccionario de Datos y Metadatos Corporativos (Módulo 4: Metadatos)
                    Tabla HTML con: Campo Técnico, Tipo de Dato, Validación de Entrada, Regla de Negocio.

                    ## 8. Matriz de Linaje, Calidad y Reglas de Negocio (Módulo 5: Calidad)
                    Tabla HTML con: Componente Técnico, Flujo (Origen -> Destino), Dimensión de Calidad Vulnerada, Acción de Remediación Técnica.

                    ## 9. Controles de Seguridad y Matriz de Accesos (Módulo 6: Seguridad y Acceso)
                    Detalla la clasificación de seguridad, mecanismos de control de acceso y brechas de seguridad identificadas.

                    ## 10. Consolidación y Plan de Remediación (Módulo 7: Consolidación)
                    Lista numerada con el plan de acciones correctivas recomendadas a corto y mediano plazo.
                    
                    ⚠️ REGLA DE CIERRE OBLIGATORIA DEL ENTREGABLE 1:
                    Al final de la sección 10, debes colocar ÚNICAMENTE este bloque de metadata exacto con los conteos físicos enteros correspondientes a tus listas de alertas:
                    [INCIDENCIAS_GOBIERNO: X]
                    [INCIDENCIAS_METADATOS: Y]
                    [INCIDENCIAS_CALIDAD: Z]

                    Coloca ahora de forma exacta esta línea divisoria:
                    === FIN_REPORTE_AUDITORIA ===

                    =========================================
                    ENTREGABLE 2: DOCUMENTACIÓN TÉCNICA LIMPIA
                    =========================================
                    Este segundo reporte es un manual limpio enfocado al negocio. No debe incluir las alertas de incumplimiento, blockquotes de riesgo, métricas de incidencias, matrices RACI, linajes o diccionarios complejos.
                    
                    Debe iniciar obligatoriamente con este título exacto:
                    {encabezado_tecnico}

                    ## DIAGNÓSTICO INTEGRAL DE GOBIERNO Y CONTROL DE DATOS

                    Desglosa la información recopilada en los siguientes 5 puntos limpios con viñetas o listas numeradas:
                    
                    ### 1. Identificación del Proceso
                    * **Nombre del Proceso:** {proc_name}
                    * **ID único:** {proc_id}
                    * **Área / Dirección:** {proc_area} / {proc_dir}
                    * **Correo del Autorizador:** [Correo detectado]
                    * **Objetivo Principal:** [Descripción ejecutiva del objetivo del proceso]

                    ### 2. Ecosistema Tecnológico (Inputs y Outputs)
                    * **Inputs:** [Detalle estructurado de archivos de entrada o insumos]
                    * **Outputs:** [Detalle de los archivos entregables finales o salidas]
                    * **Herramientas:** [Software o utilidades aplicadas]
                    * **Sistemas Implicados:** [Servidores, plataformas o bases de datos]

                    ### 3. Paso a Paso Detallado (Algoritmo del Proceso)
                    (Lista numerada y cronológica del 1 al N detallando cada acción, comandos o clicks observados en el video).

                    ### 4. Reglas de Negocio y Validaciones
                    * **Formato:** [Directrices de llenado o formato]
                    * **Claridad:** [Criterios para asegurar la legibilidad operacional]
                    * **Versionado:** [Estrategia recomendada o nomenclatura para el guardado]

                    ### 5. Excepciones y Manejo de Errores
                    * **Archivo no encontrado o dañado:** [Riesgo de falla por indisponibilidad]
                    * **Permisos:** [Comportamiento esperado ante la falta de privilegios]
                    * **Calidad:** [Descripción de la dependencia de revisión manual]
                    """
                    
                    contenidos_para_gemini.append(prompt_maestro)

                    response = cliente_gemini.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=contenidos_para_gemini,
                        config=types.GenerateContentConfig(
                            temperature=0.0,
                            system_instruction=(
                                "Eres 'Manualito', el Agente Inteligente de Gobierno de Datos de Logrand. "
                                "Generas de forma precisa y simultánea la auditoría normativa interna y el manual de procesos limpio corporativo."
                            )
                        )
                    )
                    
                    st.session_state["resultado_ia"] = response.text
                    st.success("¡Análisis completado con éxito!")
                    
                except Exception as e:
                    st.error(f"Ocurrió un error al procesar con Gemini: {str(e)}")
                
                finally:
                    if os.path.exists(ruta_temporal):
                        os.remove(ruta_temporal)
                    for archivo_google in lista_archivos_google:
                        try:
                            cliente_gemini.files.delete(name=archivo_google.name)
                        except:
                            pass

    if st.session_state["resultado_ia"]:
        st.subheader("Revisar y Modificar Documentación")
        
        texto_crudo_completo = st.session_state["resultado_ia"]
        
        # --- SEPARACIÓN DE LOS DOS REPORTES---
        partes_reporte = texto_crudo_completo.split("=== FIN_REPORTE_AUDITORIA ===")
        reporte_auditoria_crudo = partes_reporte[0].strip()
        reporte_tecnico_crudo = partes_reporte[1].strip() if len(partes_reporte) > 1 else ""

        match_gob = re.search(r"\[INCIDENCIAS_GOBIERNO:\s*([^\]]+)\]", reporte_auditoria_crudo)
        match_meta = re.search(r"\[INCIDENCIAS_METADATOS:\s*([^\]]+)\]", reporte_auditoria_crudo)
        match_cal = re.search(r"\[INCIDENCIAS_CALIDAD:\s*([^\]]+)\]", reporte_auditoria_crudo)
        
        val_gob = match_gob.group(1) if match_gob else "0"
        val_meta = match_meta.group(1) if match_meta else "0"
        val_cal = match_cal.group(1) if match_cal else "0"
        
        reporte_auditoria_markdown = re.sub(r"\[INCIDENCIAS_[A-Z]+:\s*[^\]]+\]\n*", "", reporte_auditoria_crudo)
        
        documentacion_final_tecnica = st.text_area(
            label="Editor del Manual Técnico Oficial (Formato Markdown)",
            value=reporte_tecnico_crudo,
            height=400
        )
        
        st.write("---")
        st.subheader("Responsable y Autorización")
        
        nombre_autorizador = st.text_input(
            label="Nombre y Puesto de quien autoriza este proceso:",
            placeholder="Ej: MK"
        ).upper()
        
        aprobado = st.checkbox("He revisado la documentación y confirmo que los pasos son correctos.")
        correo_final = st.session_state.get("correo_autorizador_guardado", "No especificado / Usuario Local")

        if aprobado:
            if not nombre_autorizador.strip():
                st.warning("Por favor, escribe el nombre de la persona que autoriza para poder habilitar la descarga.")
            else:
                st.success(f"¡Documento verificado y autorizado por {nombre_autorizador}!")
                
                fecha_actual = time.strftime("%d/%m/%Y")
                
                # Renderizamos los markdowns correspondientes a HTML
                html_auditoria_render = markdown.markdown(reporte_auditoria_markdown)
                html_tecnico_render = markdown.markdown(documentacion_final_tecnica)
                
                # --- DOCUMENTO 1: REPORTE DE AUDITORÍA CON ALERTAS ---
                html_documento_auditoria = f"""
                <html>
                <head>
                    <meta charset="utf-8">
                    <style>
                        body {{ font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #2c3e50; padding: 30px; }}
                        .tabla-control {{ width: 100%; border-collapse: collapse; margin-bottom: 25px; font-size: 10pt; }}
                        .tabla-control td {{ border: 1px solid #bdc3c7; padding: 10px 14px; background-color: #fafafa; }}
                        .tabla-control .header-title {{ background-color: #1e3a8a; color: #ffffff; font-weight: bold; font-size: 14pt; text-align: center; }}
                        .tabla-control .label {{ font-weight: bold; color: #34495e; width: 20%; background-color: #f1f5f9; }}
                        h1 {{ color: #1e3a8a; font-size: 18pt; border-bottom: 2px solid #1e3a8a; padding-bottom: 5px; margin-top: 0; }}
                        h2 {{ color: #2563eb; font-size: 14pt; border-bottom: 1px solid #e2e8f0; padding-bottom: 5px; margin-top: 30px; }}
                        ul, ol {{ padding-left: 25px; }}
                        li {{ margin-bottom: 6px; }}
                        blockquote {{ background-color: #fff0f0; border-left: 4px solid #d9383a; color: #b32426; padding: 10px 15px; margin: 15px 0; }}
                        table {{ width: 100%; border-collapse: collapse; margin-top: 15px; margin-bottom: 15px; }}
                        table th {{ border: 1px solid #000000; padding: 10px; font-weight: bold; background-color: #34495e; color: #ffffff; }}
                        table td {{ padding: 10px; border: 1px solid #000000; font-size: 10pt; background-color: #ffffff; }}
                        .tabla-diagrama {{ width: 100%; border-collapse: collapse; text-align: center; margin: 25px 0; }}
                        .tabla-diagrama .nodo {{ border: 2px solid #1e3a8a; background-color: #f1f5f9; padding: 12px; font-weight: bold; width: 28%; }}
                        .tabla-diagrama .nodo span {{ color: #64748b; font-size: 8.5pt; display: block; margin-top: 4px; }}
                        .tabla-diagrama .flecha {{ width: 8%; font-size: 18pt; color: #2563eb; border: none; background: none; }}
                        .seccion-firma {{ margin-top: 50px; width: 100%; border-collapse: collapse; }}
                        .seccion-firma td {{ border: none; width: 50%; text-align: center; padding-top: 20px; }}
                        .linea-firma {{ width: 70%; border-top: 1px solid #7f8c8d; margin: 0 auto; padding-top: 5px; font-weight: bold; }}
                        .nota-discrepancia {{background-color: #fff3cd; border-left: 5px solid #ffc107; color: #856404; padding: 12px 15px; margin: 15px 0; font-size: 10pt; border-radius: 4px;}}
                    </style>
                </head>
                <body>
                    <table class="tabla-control">
                        <tr><td colspan="4" class="header-title">DIAGNÓSTICO INTEGRAL DE GOBIERNO Y CONTROL DE DATOS</td></tr>
                        <tr>
                            <td class="label">ID Proceso:</td><td>{proc_id}</td>
                            <td class="label">Fecha Emisión:</td><td>{fecha_actual}</td>
                        </tr>
                        <tr>
                            <td class="label">Nombre:</td><td>{proc_name}</td>
                            <td class="label">Área / Dirección:</td><td>{proc_area} / {proc_dir}</td>
                        </tr>
                        <tr>
                            <td class="label">Correo Electrónico:</td><td>{correo_final}</td>
                            <td class="label">Estatus:</td><td style="color: #27ae60; font-weight: bold;">✔ AUTORIZADO Y VALIDADO</td>
                        </tr>
                        <tr>
                            <td colspan="2" style="background-color: #f1f5f9; font-size: 9.5pt; text-align: center;"><span><b>Política General Gobierno de Datos:</b></span><br>{val_gob} incidencias</td>
                            <td colspan="1" style="background-color: #f1f5f9; font-size: 9.5pt;"><span><b>Política Gestión Metadatos:</b></span><br>{val_meta} incidencias</td>
                            <td colspan="1" style="background-color: #f1f5f9; font-size: 9.5pt; text-align: right;"><span><b>Política Calidad de Datos:</b></span><br>{val_cal} incidencias</td>
                        </tr>
                    </table>
                    <div>{html_auditoria_render}</div>
                    <table class="seccion-firma">
                        <tr><td><div class="linea-firma">Autorizado por:</div><span>{nombre_autorizador}</span></td></tr>
                        <tr><td><div class="linea-firma">Correo Electrónico:</div><span>{correo_final}</span></td></tr>
                    </table>
                </body>
                </html>
                """

                # --- DOCUMENTO 2: MANUAL TÉCNICO CORPORATIVO LIMPIO---
                html_documento_tecnico = f"""
                <html>
                <head>
                    <meta charset="utf-8">
                    <style>
                        body {{ font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #2c3e50; padding: 30px; }}
                        .tabla-control {{ width: 100%; border-collapse: collapse; margin-bottom: 30px; font-size: 10pt; }}
                        .tabla-control td {{ border: 1px solid #bdc3c7; padding: 10px 14px; background-color: #fafafa; }}
                        .tabla-control .header-title {{ background-color: #1e3a8a; color: #ffffff; font-weight: bold; font-size: 14pt; text-align: center; letter-spacing: 0.5px; }}
                        .tabla-control .label {{ font-weight: bold; color: #34495e; width: 20%; background-color: #f1f5f9; }}
                        h1 {{ color: #1e3a8a; font-size: 18pt; border-bottom: 2px solid #1e3a8a; padding-bottom: 5px; margin-top: 0; }}
                        h2 {{ color: #1e3a8a; font-size: 14pt; margin-top: 25px; margin-bottom: 15px; text-transform: uppercase; }}
                        h3 {{ color: #2563eb; font-size: 12pt; margin-top: 20px; margin-bottom: 10px; }}
                        ul, ol {{ padding-left: 25px; }}
                        li {{ margin-bottom: 6px; }}
                        strong {{ color: #111827; }}
                        .seccion-firma {{ margin-top: 50px; width: 100%; border-collapse: collapse; }}
                        .seccion-firma td {{ border: none; width: 50%; text-align: center; padding-top: 20px; }}
                        .linea-firma {{ width: 70%; border-top: 1px solid #7f8c8d; margin: 0 auto; padding-top: 5px; font-weight: bold; }}
                    </style>
                </head>
                <body>
                    <table class="tabla-control">
                        <tr><td colspan="4" class="header-title">DOCUMENTACIÓN TÉCNICA DE PROCESOS</td></tr>
                        <tr>
                            <td class="label">ID Proceso:</td><td>{proc_id}</td>
                            <td class="label">Fecha Emisión:</td><td>{fecha_actual}</td>
                        </tr>
                        <tr>
                            <td class="label">Nombre:</td><td>{proc_name}</td>
                            <td class="label">Área / Dirección:</td><td>{proc_area} / {proc_dir}</td>
                        </tr>
                        <tr>
                            <td class="label">Correo Electrónico:</td><td>{correo_final}</td>
                            <td class="label">Estatus:</td><td style="color: #27ae60; font-weight: bold;">✔ AUTORIZADO Y VALIDADO</td>
                        </tr>
                </body>
                </html>
                """
                html_documento_tecnico += f"""
                    </table>
                    <div class="contenido-reporte">{html_tecnico_render}</div>
                    <table class="seccion-firma">
                        <tr><td><div class="linea-firma">Autorizado por:</div><br><span>{nombre_autorizador}</span></td></tr>
                        <tr><td><div class="linea-firma">Correo Electrónico:</div><br><span>{correo_final}</span></td></tr>
                    </table>
                </body>
                </html>
                """

                nombre_archivo_auditoria = f"AUDITORIA_{proc_id}_{proc_name.replace(' ', '_')}.pdf"
                nombre_archivo_tecnico = f"DOC_{proc_id}_{proc_name.replace(' ', '_')}.pdf"
                
                # --- SUBIDA AUTOMÁTICA DE AMBOS COMPONENTES A DRIVE ---
                if st.session_state["drive_file_id"] is None:
                    with st.spinner("Subiendo Reporte de Gobierno de Datos a Google Drive..."):
                        file_id_aud = subir_a_google_drive_via_script(nombre_archivo_auditoria, html_documento_auditoria)
                        if file_id_aud:
                            st.session_state["drive_file_id"] = file_id_aud
                            
                    with st.spinner("Subiendo Manual de Proceso a Google Drive..."):
                        file_id_tec = subir_a_google_drive_via_script(nombre_archivo_tecnico, html_documento_tecnico)
                        if file_id_tec:
                            st.session_state["drive_file_id_tecnico"] = file_id_tec
                            st.success("Ambos reportes se han respaldado con éxito en tu Google Drive corporativo")
                else:
                    st.info("Los respaldos de esta sesión ya se encuentran en Google Drive.")

                st.download_button(
                    label="Descargar Reporte Técnico Oficial (.html)",
                    data=html_documento_tecnico,
                    file_name=nombre_archivo_tecnico.replace(".pdf", ".html"), # Cambia la extensión local
                    mime="text/html", # Le dice a Chrome que es un sitio web/documento limpio
                    use_container_width=True
                )
        else:
            st.warning("Por favor, marca la casilla de verificación de arriba para habilitar la descarga del documento.")