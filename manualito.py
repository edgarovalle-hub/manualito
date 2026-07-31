import os
import time
import json
import re
import base64
import io
import requests
import streamlit as st
import markdown
import pandas as pd

# 1. Configuración de la página
st.set_page_config(
    page_title="Agente Documentador de Procesos - Manualito",
    layout="wide"
)

# --- CONFIGURACIÓN DE ENTORNO Y LLAVE ---
os.environ["GEMINI_API_KEY"] = st.secrets.get("GEMINI_FREE_KEY", os.getenv("GEMINI_API_KEY", ""))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- URL GOOGLE APPS SCRIPT ---
URL_APPS_SCRIPT = "https://script.google.com/macros/s/AKfycbwvFHgoogdYKKHo5zqtjt4p3hIFc9VAS_GKJFRyOwxzT1Jp0HIEY4oLpPWCNjgazmlR/exec"

# --- FUNCIONES DE CONEXIÓN CON GEMINI Y DRIVE VIA WEBHOOK ---
def inicializar_agente():
    from google import genai
    return genai.Client()

def subir_a_google_drive_via_script(nombre_archivo, contenido, es_binario=False, mime_type="text/html"):
    """
    Manda documentos (HTML o binarios como Excel en Base64) a Google Drive a través de Apps Script.
    """
    try:
        if es_binario:
            contenido_b64 = base64.b64encode(contenido).decode('utf-8')
            payload = {
                "nombre": nombre_archivo,
                "excelBase64": contenido_b64  # <-- Cambiado a 'excelBase64' para coincidir con Apps Script
            }
        else:
            payload = {
                "nombre": nombre_archivo,
                "html": contenido
            }
            
        respuesta = requests.post(URL_APPS_SCRIPT, json=payload, timeout=60)
        
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

def json_a_excel_bytes(datos_json):
    """
    Convierte el JSON de 7 módulos a un archivo Excel (.xlsx) en memoria de Bytes.
    Garantiza una pestaña por módulo.
    """
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        modulos = [
            ("modulo_1_requerimientos_flujo", "Requerimientos y Flujo"),
            ("modulo_2_roles_decisiones", "Roles y Decisiones"),
            ("modulo_3_activos_sistemas", "Activos y Sistemas"),
            ("modulo_4_metadatos_documentacion", "Metadatos y Doc"),
            ("modulo_5_controles_calidad", "Controles de Calidad"),
            ("modulo_6_seguridad_clasificacion", "Seguridad y Acceso"),
            ("modulo_7_resumen_hallazgos", "Resumen de Hallazgos")
        ]
        
        for key_json, nombre_hoja in modulos:
            contenido_modulo = datos_json.get(key_json, [])
            if isinstance(contenido_modulo, list) and len(contenido_modulo) > 0:
                df = pd.DataFrame(contenido_modulo)
            else:
                df = pd.DataFrame([{"Mensaje": "Sin información identificada"}])
            
            # Cortamos a 31 caracteres el nombre de la hoja por limitación de Excel
            df.to_excel(writer, sheet_name=nombre_hoja[:31], index=False)
            
    buffer.seek(0)
    return buffer.getvalue()

# --- DETECCIÓN AUTOMÁTICA DEL USUARIO ---
correo_autorizador = "No especificado / Usuario Local"

if hasattr(st, "context") and hasattr(st.context, "user") and getattr(st.context.user, "email", None):
    correo_autorizador = st.context.user.email
elif hasattr(st, "experimental_user") and getattr(st.experimental_user, "email", None):
    correo_autorizador = st.experimental_user.email
elif hasattr(st, "user") and getattr(st.user, "email", None):
    correo_autorizador = st.user.email

st.title("Agente de Documentación Automatizada (Manualito)")
st.markdown("""
Este agente analiza el **video o audio** de un proceso operativo y sus archivos adjuntos 
para clasificar automáticamente el proceso (**Macro / Micro / Híbrido**), evaluando el cumplimiento normativo 
y generando matrices técnicas en Excel y/o documentación en HTML/PDF.
""")

st.divider()

col_izquierda, col_derecha = st.columns([1, 1.2])

with col_izquierda:
    st.header("Carga de Evidencia")
    
    archivo_multimedia = st.file_uploader(
        "1. Sube la evidencia principal (Video .mp4, .mov, .avi O Audio .mp3, .wav, .m4a)", 
        type=["mp4", "mov", "avi", "mp3", "wav", "m4a"],
        help="Sube el video completo narrado o la grabación de audio de la sesión del proceso."
    )
    
    es_video = False
    es_audio = False
    
    if archivo_multimedia is not None:
        ext = archivo_multimedia.name.split(".")[-1].lower()
        if ext in ["mp4", "mov", "avi"]:
            st.video(archivo_multimedia)
            es_video = True
        elif ext in ["mp3", "wav", "m4a"]:
            st.audio(archivo_multimedia)
            es_audio = True
    
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
    st.header("Resultados de Documentación")
    
    # Session state
    for key in ["resultado_ia", "tipo_proceso_detectado", "json_matrices", "drive_file_auditoria", "drive_file_tecnico", "drive_file_excel"]:
        if key not in st.session_state:
            st.session_state[key] = None if "drive_file" in key or key == "json_matrices" else ""

    if not boton_procesar and not st.session_state["resultado_ia"]:
        st.info("Sube la evidencia (video/audio), llena los datos de control y haz clic en 'Generar Documentación'.")
    
    if boton_procesar:
        if archivo_multimedia is None:
            st.error("Por favor, sube un archivo de Video o Audio primero.")
        elif not (proc_id and proc_name and proc_area and proc_dir):
            st.error("Por favor, rellena todos los Campos de Control (ID, Nombre, Área y Dirección) antes de continuar.")
        else:
            with st.spinner("Analizando evidencia, clasificando el tipo de proceso y estructurando los entregables con Gemini..."):
                
                # Reset session states de Drive
                st.session_state["drive_file_auditoria"] = None
                st.session_state["drive_file_tecnico"] = None
                st.session_state["drive_file_excel"] = None
                st.session_state["correo_autorizador_guardado"] = correo_autorizador
                
                ruta_temp_media = f"temp_media_{archivo_multimedia.name}"
                lista_archivos_google = []
                
                try:
                    with open(ruta_temp_media, "wb") as f:
                        f.write(archivo_multimedia.getbuffer())
                    
                    cliente_gemini = inicializar_agente()

                    # --- MARCO NORMATIVO Y GUÍA FUNCIONAL ---
                    path_gobierno = os.path.join(BASE_DIR, "politicas", "politica_general_gobierno_dato.pdf")
                    path_metadatos = os.path.join(BASE_DIR, "politicas", "politica_gestion_metadatos.pdf")
                    path_calidad = os.path.join(BASE_DIR, "politicas", "politica_calidad_datos.pdf")
                    path_guia_relevamiento = os.path.join(BASE_DIR, "Marco_de_Relevamiento_Funcional_Tecnico.pdf")
                    
                    archivos_locales_requeridos = [path_gobierno, path_metadatos, path_calidad]
                    if os.path.exists(path_guia_relevamiento):
                        archivos_locales_requeridos.append(path_guia_relevamiento)

                    for path_p in archivos_locales_requeridos:
                        if not os.path.exists(path_p):
                            st.warning(f"Aviso: No se encontró el archivo normativo/guía en: {path_p}")

                    contenidos_para_gemini = []
                    
                    for path_p in archivos_locales_requeridos:
                        if os.path.exists(path_p):
                            up_file = cliente_gemini.files.upload(file=path_p)
                            lista_archivos_google.append(up_file)
                            contenidos_para_gemini.append(up_file)

                    # --- ARCHIVO MULTIMEDIA (VIDEO O AUDIO) ---
                    media_uploaded = cliente_gemini.files.upload(file=ruta_temp_media)
                    while media_uploaded.state.name == "PROCESSING":
                        time.sleep(2)
                        media_uploaded = cliente_gemini.files.get(name=media_uploaded.name)
                        
                    if media_uploaded.state.name == "FAILED":
                        raise ValueError(f"El procesamiento multimedia falló: {media_uploaded.error.message}")
                    
                    lista_archivos_google.append(media_uploaded)
                    contenidos_para_gemini.append(media_uploaded)

                    # --- ARCHIVOS ADJUNTOS EXTRA ---
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

                    # --- PROMPT UNIFICADO MAESTRO ---
                    encabezado_auditoria = f"# {proc_id} - {proc_name} - {proc_area} - {proc_dir}\n\n"
                    encabezado_tecnico = f"# DOC_{proc_id}_{proc_name.replace(' ', '_')}\n\n"
                    
                    prompt_maestro = f"""
                    Actúas como 'Manualito', Ingeniero de Procesos Senior y experto en Gobierno de Datos en Logrand.
                    Tu tarea es analizar la evidencia provista (audio/video y documentos) y realizar 3 cosas principales:

                    1. **CLASIFICACIÓN DEL PROCESO**:
                       Determina automáticamente si este proceso es **MACRO**, **MICRO** o **HÍBRIDO**:
                       - **MICRO**: Procesos operativos puntuales, manuales simples o tareas específicas.
                       - **MACRO**: Procesos complejos e interdepartamentales de arquitectura, flujos extensos de TI, analítica compleja o múltiples sistemas.
                       - **HÍBRIDO**: Procesos con alto impacto operativo que requieren tanto documentación técnica/auditoría como matrices exhaustivas de relevamiento Nivel 2.

                       Escribe la clasificación AL INICIO de tu respuesta de forma literal:
                       [TIPO_PROCESO: MACRO]  o  [TIPO_PROCESO: MICRO]  o  [TIPO_PROCESO: HIBRIDO]

                    2. **REPORTES DE AUDITORÍA Y MANUAL TÉCNICO** (Formato Markdown):
                       Separa estos dos reportes con la etiqueta '=== FIN_REPORTE_AUDITORIA ==='.
                       
                       =========================================
                       ENTREGABLE 1: REPORTE DE AUDITORÍA Y CONTROL
                       =========================================
                       Título exacto:
                       {encabezado_auditoria}

                       Estructura:
                       PARTE I: DIAGNÓSTICO INTEGRAL DE GOBIERNO Y CONTROL DE DATOS
                       ## 1. Identificación y Origen
                       ## 2. Linaje Operativo Observado y Nota de Discrepancia Técnica
                       (Si detectas discrepancias entre audio y video/docs, usa <div class="nota-discrepancia">)
                       ## 2.5 Diagrama de Flujo del Dato (Visual)
                       (Usa tabla HTML <table class="tabla-diagrama">)
                       ## 3. Evaluación Crítica de Cumplimiento (ALERTAS NORMATIVAS)
                          ### ALERTAS DE GOBIERNO DEL DATO
                          ### ALERTAS DE GESTIÓN DE METADATOS
                          ### ALERTAS DE CALIDAD DE DATOS

                       PARTE II: MATRICES Y ENTREGABLES DE RELEVAMIENTO
                       ## 4. Requerimientos Funcionales y de Negocio (Tabla HTML)
                       ## 5. Estructura de Gobernanza y Matriz RACI (Tablas HTML)
                       ## 6. Ecosistema Tecnológico y Mapa de Infraestructura (Tabla HTML)
                       ## 7. Diccionario de Datos y Metadatos Corporativos (Tabla HTML)
                       ## 8. Matriz de Linaje, Calidad y Reglas de Negocio (Tabla HTML)
                       ## 9. Controles de Seguridad y Matriz de Accesos
                       ## 10. Consolidación y Plan de Remediación

                       Fin del entregable 1 con los conteos físicos:
                       [INCIDENCIAS_GOBIERNO: X]
                       [INCIDENCIAS_METADATOS: Y]
                       [INCIDENCIAS_CALIDAD: Z]

                       === FIN_REPORTE_AUDITORIA ===

                       =========================================
                       ENTREGABLE 2: DOCUMENTACIÓN TÉCNICA LIMPIA
                       =========================================
                       Título exacto:
                       {encabezado_tecnico}

                       ## DIAGNÓSTICO INTEGRAL DE GOBIERNO Y CONTROL DE DATOS
                       ### 1. Identificación del Proceso (Nombre: {proc_name}, ID: {proc_id}, Área: {proc_area}/{proc_dir})
                       ### 2. Ecosistema Tecnológico (Inputs, Outputs, Herramientas, Sistemas)
                       ### 3. Paso a Paso Detallado (Algoritmo)
                       ### 4. Reglas de Negocio y Validaciones
                       ### 5. Excepciones y Manejo de Errores

                    3. **MATRICES EN JSON ESTRUCTURADO (DISCOVERIES / RELEVAMIENTO NIVEL 2)**:
                       Coloca al final de toda la respuesta la etiqueta '=== INICIO_JSON_MATRICES ===' seguida del objeto JSON estricto con los 7 módulos de relevamiento.
                       
                       ⚠️ REGLA CRÍTICA DE TRACKING/TRAZABILIDAD:
                       Debes usar un identificador común (p. ej. "{proc_id}" o el ID de requerimiento principal) que aparezca referenciado en todos los módulos (`id_requerimiento_tipo`, `id_flujo_requerimiento`, `id_requerimiento_flujo_asociado`, `id_objeto_flujo_asociado`, etc.) para asegurar el tracking entre los 7 módulos.

                       El formato del JSON debe ser exacto:
                       === INICIO_JSON_MATRICES ===
                       {{
                         "modulo_1_requerimientos_flujo": [ {{ "id_requerimiento_tipo": "{proc_id}_REQ1", "tipo_requerimiento": "", "descripcion": "", "canal_entrada": "", "solicitante_tipico": "", "informacion_minima_requerida": "", "receptor": "", "criterio_priorizacion": "", "ejecutor": "", "validador_tecnico": "", "validador_funcional": "", "evidencia_generada": "", "documentacion_actualizada": "", "dolor_recurrente": "", "politica_relacionada": "", "requiere_revision_gobierno": "", "observaciones": "" }} ],
                         "modulo_2_roles_decisiones": [ {{ "id_flujo_requerimiento": "{proc_id}_REQ1", "etapa_proceso": "", "actividad": "", "rol_actual": "", "tipo_rol": "", "area_equipo": "", "decision_asociada": "", "criterio_decision": "", "evidencia_decision": "", "rol_esperado_gobierno": "", "brecha_identificada": "", "riesgo_asociado": "", "requiere_formalizacion": "", "observaciones": "" }} ],
                         "modulo_3_activos_sistemas": [ {{ "id_objeto": "OBJ_1", "id_requerimiento_flujo_asociado": "{proc_id}_REQ1", "nombre_objeto": "", "tipo_objeto": "", "descripcion_breve": "", "uso_dentro_flujo": "", "sistema_origen": "", "sistema_destino_consumo": "", "frecuencia": "", "mecanismo_general": "", "responsable_tecnico_conocido": "", "responsable_funcional_conocido": "", "area_consumidora": "", "dominio_asociado": "", "subdominio_asociado": "", "eje_tematico_analitico": "", "modelo_datos_asociado": "", "tipo_relacion_clasificacion": "", "requiere_validacion_clasificacion": "", "dependencias_criticas": "", "impacto_si_falla": "", "brecha_identificada": "", "requiere_profundizacion_nivel_3": "", "observaciones": "" }} ],
                         "modulo_4_metadatos_documentacion": [ {{ "id_objeto": "OBJ_1", "id_requerimiento_asociado": "{proc_id}_REQ1", "nombre_objeto": "", "tipo_objeto": "", "dominio_asociado": "", "subdominio_asociado": "", "eje_tematico_analitico": "", "modelo_datos_asociado": "", "descripcion_funcional_existe": "", "documentacion_tecnica_existe": "", "diccionario_datos_existe": "", "glosario_definicion_negocio_existe": "", "reglas_negocio_documentadas": "", "linaje_general_documentado": "", "ubicacion_documentacion": "", "estado_vigencia": "", "responsable_mantenimiento": "", "responsable_validacion_funcional": "", "responsable_validacion_tecnica": "", "evidencia_disponible": "", "brecha_metadatos": "", "impacto_brecha": "", "requiere_catalogo_enriquecimiento": "", "requiere_profundizacion_nivel_3": "", "observaciones": "" }} ],
                         "modulo_5_controles_calidad": [ {{ "id_control": "CTRL_1", "id_objeto_flujo_asociado": "{proc_id}_REQ1", "nombre_objeto": "", "tipo_problema_o_control": "", "descripcion_control": "", "dimension_calidad": "", "tipo_control": "", "etapa_donde_se_aplica": "", "herramienta_o_mecanismo": "", "responsable_ejecucion": "", "responsable_validacion": "", "frecuencia_control": "", "umbral_o_criterio_aceptacion": "", "evidencia_disponible": "", "accion_ante_falla": "", "impacto_si_falla": "", "regla_documentada": "", "asociado_a_metadatos": "", "brecha_identificada": "", "requiere_profundizacion_nivel_3": "", "observaciones": "" }} ],
                         "modulo_6_seguridad_clasificacion": [ {{ "id_seguridad": "SEG_1", "id_objeto_flujo_asociado": "{proc_id}_REQ1", "nombre_objeto": "", "tipo_objeto": "", "dominio_subdominio": "", "eje_tematico_modelo": "", "tipo_informacion_contenida": "", "clasificacion_preliminar": "", "clasificacion_validada": "", "perfil_area_con_acceso": "", "tipo_acceso": "", "forma_asignacion": "", "canal_solicitud": "", "responsable_aprobacion": "", "evidencia_autorizacion": "", "existe_trazabilidad": "", "punto_exposicion": "", "riesgo_preliminar": "", "requiere_revision_seguridad": "", "requiere_profundizacion_nivel_3": "", "observaciones": "" }} ],
                         "modulo_7_resumen_hallazgos": [ {{ "modulo_nombre": "Módulo 1: Requerimientos", "id_requerimiento_asociado": "{proc_id}_REQ1", "hallazgos_principales": "", "pendientes_o_informacion_faltante": "", "pasa_a_diagnostico": "" }} ]
                       }}
                       === FIN_JSON_MATRICES ===
                    """
                    
                    contenidos_para_gemini.append(prompt_maestro)

                    from google.genai import types
                    response = cliente_gemini.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=contenidos_para_gemini,
                        config=types.GenerateContentConfig(
                            temperature=0.0,
                            system_instruction="Eres 'Manualito', el Agente Inteligente de Gobierno de Datos de Logrand."
                        )
                    )
                    
                    texto_respuesta = response.text
                    
                    # --- EXTRACCIÓN DE TIPO DE PROCESO ---
                    tipo_proceso = "MICRO"
                    match_tipo = re.search(r"\[TIPO_PROCESO:\s*(MACRO|MICRO|HIBRIDO|HÍBRIDO)\]", texto_respuesta, re.IGNORECASE)
                    if match_tipo:
                        tipo_proceso = match_tipo.group(1).upper().replace("Í", "I")
                    st.session_state["tipo_proceso_detectado"] = tipo_proceso
                    
                    # --- EXTRACCIÓN Y LIMPIEZA DE JSON ---
                    json_datos = {}
                    if "=== INICIO_JSON_MATRICES ===" in texto_respuesta:
                        partes_json = texto_respuesta.split("=== INICIO_JSON_MATRICES ===")
                        texto_respuesta_docs = partes_json[0]
                        str_json = partes_json[1].replace("=== FIN_JSON_MATRICES ===", "").strip()
                        if str_json.startswith("```json"):
                            str_json = str_json[7:]
                        if str_json.endswith("```"):
                            str_json = str_json[:-3]
                        try:
                            json_datos = json.loads(str_json.strip())
                        except Exception as json_err:
                            st.warning(f"No se pudo parsear el JSON completo: {json_err}")
                    else:
                        texto_respuesta_docs = texto_respuesta

                    st.session_state["resultado_ia"] = texto_respuesta_docs
                    st.session_state["json_matrices"] = json_datos
                    
                    st.success(f"¡Análisis completado! Proceso identificado como: **{tipo_proceso}**")
                    
                except Exception as e:
                    st.error(f"Ocurrió un error al procesar con Gemini: {str(e)}")
                
                finally:
                    if os.path.exists(ruta_temp_media):
                        os.remove(ruta_temp_media)
                    for archivo_google in lista_archivos_google:
                        try:
                            cliente_gemini.files.delete(name=archivo_google.name)
                        except:
                            pass

    # --- DESPLIEGUE Y EDICIÓN DE RESULTADOS ---
    if st.session_state["resultado_ia"]:
        tipo_proc = st.session_state["tipo_proceso_detectado"]
        st.info(f"📌 **Tipo de Proceso Detectado:** `{tipo_proc}`")
        
        texto_crudo_completo = st.session_state["resultado_ia"]
        
        # Separación Auditoría y Técnico
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
        reporte_auditoria_markdown = re.sub(r"\[TIPO_PROCESO:\s*[^\]]+\]\n*", "", reporte_auditoria_markdown)

        if tipo_proc in ["MICRO", "HIBRIDO"]:
            documentacion_final_tecnica = st.text_area(
                label="Editor del Manual Técnico Oficial (Formato Markdown)",
                value=reporte_tecnico_crudo,
                height=350
            )
        else:
            documentacion_final_tecnica = reporte_tecnico_crudo

        st.write("---")
        st.subheader("Responsable y Autorización")
        
        nombre_autorizador = st.text_input(
            label="Nombre y Puesto de quien autoriza este proceso:",
            placeholder="Ej: MK"
        ).upper()
        
        aprobado = st.checkbox("He revisado la información y confirmo que los datos son correctos.")
        correo_final = st.session_state.get("correo_autorizador_guardado", "No especificado / Usuario Local")

        if aprobado:
            if not nombre_autorizador.strip():
                st.warning("Por favor, escribe el nombre de la persona que autoriza.")
            else:
                st.success(f"¡Documentación validada por {nombre_autorizador}!")
                fecha_actual = time.strftime("%d/%m/%Y")
                
                # --- PREPARACIÓN DE ENTREGABLES HTML ---
                html_auditoria_render = markdown.markdown(reporte_auditoria_markdown)
                html_tecnico_render = markdown.markdown(documentacion_final_tecnica)
                
                # HTML Auditoría
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

                # HTML Manual Técnico
                html_documento_tecnico = f"""
                <html>
                <head>
                    <meta charset="utf-8">
                    <style>
                        body {{ font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #2c3e50; padding: 30px; }}
                        .tabla-control {{ width: 100%; border-collapse: collapse; margin-bottom: 30px; font-size: 10pt; }}
                        .tabla-control td {{ border: 1px solid #bdc3c7; padding: 10px 14px; background-color: #fafafa; }}
                        .tabla-control .header-title {{ background-color: #1e3a8a; color: #ffffff; font-weight: bold; font-size: 14pt; text-align: center; }}
                        .tabla-control .label {{ font-weight: bold; color: #34495e; width: 20%; background-color: #f1f5f9; }}
                        h1 {{ color: #1e3a8a; font-size: 18pt; border-bottom: 2px solid #1e3a8a; padding-bottom: 5px; margin-top: 0; }}
                        h2 {{ color: #1e3a8a; font-size: 14pt; margin-top: 25px; margin-bottom: 15px; text-transform: uppercase; }}
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
                    </table>
                    <div class="contenido-reporte">{html_tecnico_render}</div>
                    <table class="seccion-firma">
                        <tr><td><div class="linea-firma">Autorizado por:</div><br><span>{nombre_autorizador}</span></td></tr>
                        <tr><td><div class="linea-firma">Correo Electrónico:</div><br><span>{correo_final}</span></td></tr>
                    </table>
                </body>
                </html>
                """

                # Nombres de archivos
                nombre_archivo_auditoria = f"AUDITORIA_{proc_id}_{proc_name.replace(' ', '_')}.pdf"
                nombre_archivo_tecnico = f"DOC_{proc_id}_{proc_name.replace(' ', '_')}.pdf"
                nombre_archivo_excel = f"MATRICES_NIVEL2_{proc_id}_{proc_name.replace(' ', '_')}.xlsx"

                # Generación del archivo Excel binario
                bytes_excel = json_a_excel_bytes(st.session_state.get("json_matrices", {}))

                # --- LÓGICA DE ENVÍO A DRIVE Y DESCARGA SEGÚN TIPO DE PROCESO ---
                
                # 1. SI ES MICRO O HÍBRIDO -> Respaldar Auditoría y Manual Técnico
                if tipo_proc in ["MICRO", "HIBRIDO"]:
                    if st.session_state["drive_file_auditoria"] is None:
                        with st.spinner("Subiendo Reporte de Gobierno a Google Drive..."):
                            f_aud = subir_a_google_drive_via_script(nombre_archivo_auditoria, html_documento_auditoria)
                            if f_aud: st.session_state["drive_file_auditoria"] = f_aud
                            
                        with st.spinner("Subiendo Manual de Proceso a Google Drive..."):
                            f_tec = subir_a_google_drive_via_script(nombre_archivo_tecnico, html_documento_tecnico)
                            if f_tec: st.session_state["drive_file_tecnico"] = f_tec

                # 2. SI ES MACRO O HÍBRIDO -> Respaldar Excel
                if tipo_proc in ["MACRO", "HIBRIDO"]:
                    if st.session_state["drive_file_excel"] is None:
                        with st.spinner("Subiendo Matrices Excel de Relevamiento a Google Drive..."):
                            f_exc = subir_a_google_drive_via_script(
                                nombre_archivo_excel, 
                                bytes_excel, 
                                es_binario=True, 
                                mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                            if f_exc: st.session_state["drive_file_excel"] = f_exc

                st.success("¡Respaldos en Google Drive sincronizados correctamente!")

                # --- BOTONES DE DESCARGA VISIBLES PARA EL USUARIO ---
                st.subheader("Entregables Disponibles para Descarga")
                
                col1, col2 = st.columns(2)
                
                if tipo_proc in ["MICRO", "HIBRIDO"]:
                    with col1:
                        st.download_button(
                            label="📄 Descargar Manual Técnico (.html)",
                            data=html_documento_tecnico,
                            file_name=nombre_archivo_tecnico.replace(".pdf", ".html"),
                            mime="text/html",
                            use_container_width=True
                        )
                    with col2:
                        st.download_button(
                            label="🛡️ Descargar Reporte de Auditoría (.html)",
                            data=html_documento_auditoria,
                            file_name=nombre_archivo_auditoria.replace(".pdf", ".html"),
                            mime="text/html",
                            use_container_width=True
                        )

                if tipo_proc in ["MACRO", "HIBRIDO"]:
                    st.download_button(
                        label="📊 Descargar Matrices de Relevamiento 7 Módulos (.xlsx)",
                        data=bytes_excel,
                        file_name=nombre_archivo_excel,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
        else:
            st.warning("Por favor, marca la casilla de verificación para autorizar la exportación.")