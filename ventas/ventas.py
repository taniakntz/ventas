import streamlit as st
import pandas as pd
import requests
from io import BytesIO
from datetime import date
from supabase import create_client, Client
import folium
from streamlit_folium import st_folium
from openpyxl.styles import Font, PatternFill, Alignment

# --- 1. CONFIGURACIÓN INICIAL ---
st.set_page_config(page_title="Gestión de Pastelitos", layout="wide", initial_sidebar_state="expanded")

# --- 2. CONEXIÓN A BASE DE DATOS ---
@st.cache_resource
def init_connection() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_connection()

# --- 3. SISTEMA DE AUTENTICACIÓN BÁSICO ---
def check_password():
    def password_entered():
        if st.session_state["username"] in st.secrets["passwords"] and st.session_state["password"] == st.secrets["passwords"][st.session_state["username"]]:
            st.session_state["password_correct"] = True
            st.session_state["usuario_logeado"] = st.session_state["username"] 
            del st.session_state["password"] 
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.title("🔒 Acceso Restringido")
        st.text_input("Usuario", key="username")
        st.text_input("Contraseña", type="password", key="password", on_change=password_entered)
        return False
    elif not st.session_state["password_correct"]:
        st.title("🔒 Acceso Restringido")
        st.text_input("Usuario", key="username")
        st.text_input("Contraseña", type="password", key="password", on_change=password_entered)
        st.error("😕 Usuario o contraseña incorrectos")
        return False
    else:
        return True

if not check_password():
    st.stop()

# --- 4. LÓGICA DE NEGOCIO Y UTILIDADES ---

def decimal_a_fraccion(valor):
    if pd.isna(valor) or valor == 0:
        return "0"
    entero = int(valor)
    decimal = valor - entero
    frac_str = ""
    
    if decimal == 0.25: frac_str = "1/4"
    elif decimal == 0.5: frac_str = "1/2"
    elif decimal == 0.75: frac_str = "3/4"

    if entero == 0:
        return frac_str if frac_str else str(valor)
    elif frac_str:
        return f"{entero} {frac_str}"
    else:
        return str(entero)

def calcular_total(batata, membrillo, precio_doc, precio_med):
    total_docenas = batata + membrillo
    if total_docenas == 1.0: return precio_doc
    elif batata == 0.5 and membrillo == 0.5: return precio_doc
    
    total = 0
    for cantidad in [batata, membrillo]:
        if cantidad == 0.25: total += precio_med / 2
        elif cantidad == 0.5: total += precio_med
        elif cantidad == 0.75: total += precio_med + (precio_med / 2)
        elif cantidad >= 1:
            total += int(cantidad) * precio_doc
            resto = cantidad % 1
            if resto == 0.5: total += precio_med
            elif resto == 0.25: total += precio_med / 2
            elif resto == 0.75: total += precio_med + (precio_med / 2)
    return total

def obtener_coordenadas(direccion):
    url = f"https://nominatim.openstreetmap.org/search?q={direccion}&format=json&limit=1"
    headers = {'User-Agent': 'PastelitosApp/1.0'}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200 and len(response.json()) > 0:
            data = response.json()[0]
            return float(data['lat']), float(data['lon'])
    except Exception:
        pass
    return None, None

def exportar_excel(dataframe):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        dataframe.to_excel(writer, index=False, sheet_name='Ventas')
        worksheet = writer.sheets['Ventas']
        
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
        for cell in worksheet[1]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")
            
        for col in worksheet.columns:
            max_length = 0
            column = col[0].column_letter 
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(cell.value)
                except: pass
            adjusted_width = (max_length + 2)
            worksheet.column_dimensions[column].width = adjusted_width

    return output.getvalue()

# --- 5. INTERFAZ PRINCIPAL ---
st.sidebar.title(f"👤 {st.session_state.get('usuario_logeado', 'Usuario')}")
if st.sidebar.button("Cerrar Sesión"):
    st.session_state.clear()
    st.rerun()

# Cargar Campañas
response_camp = supabase.table("campanas").select("*").execute()
campanas_df = pd.DataFrame(response_camp.data)

# --- BLOQUE DE EMERGENCIA: SI NO HAY CAMPAÑAS ---
if campanas_df.empty:
    tab1, tab2, tab3, tab4 = st.tabs(["📦 Pedidos", "📈 Finanzas", "🚚 Reparto", "⚙️ Configuración"])
    with tab1:
        st.warning("⚠️ Sistema bloqueado. Ve a la pestaña Configuración y crea tu primera campaña para comenzar.")
    with tab4:
        st.header("⚙️ Primera Configuración")
        with st.form("form_campana_inicial", clear_on_submit=True):
            st.subheader("Crear Tu Primera Campaña")
            n_nombre = st.text_input("Nombre (Ej: Mayo 2026)")
            n_fecha = st.date_input("Fecha del Evento")
            n_p_doc = st.number_input("Precio Docena Inicial", value=7000)
            n_p_med = st.number_input("Precio Media Inicial", value=4000)
            
            if st.form_submit_button("Crear Campaña") and n_nombre:
                supabase.table("campanas").insert({
                    "nombre_campana": n_nombre,
                    "fecha_entrega": str(n_fecha),
                    "precio_docena": n_p_doc,
                    "precio_media": n_p_med,
                    "estado": "Activa"
                }).execute()
                st.success("Campaña creada. Recargando el sistema...")
                st.rerun()
    st.stop()

# --- EJECUCIÓN NORMAL: SI HAY CAMPAÑAS ---
campana_activa = st.sidebar.selectbox("Seleccionar Campaña Activa", campanas_df['nombre_campana'].tolist())
datos_campana = campanas_df[campanas_df['nombre_campana'] == campana_activa].iloc[0]
ID_CAMPANA = datos_campana['id']
PRECIO_DOCENA = float(datos_campana['precio_docena'])
PRECIO_MEDIA = float(datos_campana['precio_media'])

st.sidebar.markdown("---")
st.sidebar.write(f"**Precio Docena:** ${PRECIO_DOCENA}")
st.sidebar.write(f"**Precio Media:** ${PRECIO_MEDIA}")

# Pestañas de navegación
tab1, tab2, tab3, tab4 = st.tabs(["📦 Pedidos", "📈 Finanzas", "🚚 Reparto", "⚙️ Configuración"])

# --- PESTAÑA 1: PEDIDOS ---
with tab1:
    st.header("📝 Ingreso de Nuevo Pedido")
    
    def limpiar_formulario():
        for key in ["in_cliente", "in_bat", "in_mem", "in_mod", "in_dir", "in_ran", "in_met", "in_est"]:
            if key in st.session_state:
                del st.session_state[key]

    cliente = st.text_input("Nombre del Cliente", key="in_cliente")
    
    col1, col2 = st.columns(2)
    with col1: cant_bat = st.number_input("Batata (Docenas)", min_value=0.0, step=0.25, format="%.2f", key="in_bat")
    with col2: cant_mem = st.number_input("Membrillo (Docenas)", min_value=0.0, step=0.25, format="%.2f", key="in_mem")
    
    col_m, col_p = st.columns(2)
    with col_m:
        modalidad = st.selectbox("Modalidad de Entrega", ["Retiro_Local", "Envio_Domicilio"], key="in_mod")
        
        if modalidad == "Envio_Domicilio":
            direccion = st.text_input("Dirección (Solo si es Envío)", placeholder="Calle 123, Ciudad", key="in_dir")
            rango = st.selectbox("Rango Horario", ["08:00-09:00", "09:00-10:00", "10:00-11:00", "11:00-12:00", "12:00-13:00"], key="in_ran")
        else:
            direccion = None
            rango = None
            
    with col_p:
        metodo = st.selectbox("Método de Pago", ["Efectivo", "Transferencia", "N/A"], key="in_met")
        estado_pago = st.selectbox("Estado de Pago", ["Pendiente", "Pagado"], key="in_est")

    if st.button("Guardar Pedido", type="primary"):
        if not cliente.strip():
            st.error("⚠️ El nombre del cliente es obligatorio.")
        elif modalidad == "Envio_Domicilio" and not direccion.strip():
            st.error("⚠️ Error de validación: Para envíos a domicilio, la dirección es obligatoria.")
        else:
            total_dinero = calcular_total(cant_bat, cant_mem, PRECIO_DOCENA, PRECIO_MEDIA)
            lat, lon = obtener_coordenadas(direccion) if modalidad == "Envio_Domicilio" and direccion else (None, None)
            
            if modalidad == "Envio_Domicilio" and (lat is None or lon is None):
                st.warning("⚠️ Advertencia: No se pudieron validar las coordenadas. El pedido se guardará, pero podría no graficarse en el mapa.")
            
            nuevo_pedido = {
                "campana_id": ID_CAMPANA,
                "cliente_nombre": cliente,
                "docenas_batata": float(cant_bat),
                "docenas_membrillo": float(cant_mem),
                "total_calculado": float(total_dinero),
                "estado_pago": estado_pago,
                "metodo_pago": metodo,
                "modalidad_entrega": modalidad,
                "direccion_envio": direccion,
                "rango_horario": rango,
                "latitud": lat,
                "longitud": lon
            }
            supabase.table("pedidos").insert(nuevo_pedido).execute()
            st.success(f"Pedido guardado. Total calculado: ${total_dinero}")
            
            limpiar_formulario()
            st.rerun()

    st.divider()
    pedidos_req = supabase.table("pedidos").select("*").eq("campana_id", ID_CAMPANA).execute()
    
    if pedidos_req.data:
        df_pedidos = pd.DataFrame(pedidos_req.data)
        
        # --- MÓDULO DE PRODUCCIÓN ---
        st.subheader("🧑‍🍳 Resumen de Producción")
        df_pedidos["docenas_batata"] = pd.to_numeric(df_pedidos["docenas_batata"], errors="coerce").fillna(0)
        df_pedidos["docenas_membrillo"] = pd.to_numeric(df_pedidos["docenas_membrillo"], errors="coerce").fillna(0)
        
        total_batata = df_pedidos["docenas_batata"].sum()
        total_membrillo = df_pedidos["docenas_membrillo"].sum()
        gran_total = total_batata + total_membrillo
        
        col_prod1, col_prod2, col_prod3 = st.columns(3)
        col_prod1.metric("Total Batata", decimal_a_fraccion(total_batata))
        col_prod2.metric("Total Membrillo", decimal_a_fraccion(total_membrillo))
        col_prod3.metric("Producción Total", decimal_a_fraccion(gran_total))
        
        st.divider()
        
        # --- VISTA DETALLADA POR CLIENTE Y EDICIÓN ---
        st.subheader("📋 Gestión de Pedidos")
        
        columnas_base = ["id", "cliente_nombre", "docenas_batata", "docenas_membrillo", "estado_pago", "modalidad_entrega", "direccion_envio", "rango_horario", "total_calculado"]
        
        # Control estricto de estructura
        for col in columnas_base:
            if col not in df_pedidos.columns:
                df_pedidos[col] = None
                
        df_pedidos_edicion = df_pedidos[columnas_base].copy()
        df_pedidos_edicion["total_calculado"] = pd.to_numeric(df_pedidos_edicion["total_calculado"], errors="coerce").fillna(0)
        
        st.caption("💡 Para editar: modifica las celdas numéricas o direcciones. Para eliminar un pedido: selecciona la fila izquierda y presiona 'Delete/Supr'.")
        
        editor_pedidos = st.data_editor(
            df_pedidos_edicion,
            column_config={
                "id": None,
                "cliente_nombre": st.column_config.TextColumn("Cliente", required=True),
                "docenas_batata": st.column_config.NumberColumn("Batata", min_value=0.0, step=0.25, required=True),
                "docenas_membrillo": st.column_config.NumberColumn("Membrillo", min_value=0.0, step=0.25, required=True),
                "estado_pago": st.column_config.SelectboxColumn("Pago", options=["Pendiente", "Pagado"], required=True),
                "modalidad_entrega": st.column_config.SelectboxColumn("Entrega", options=["Retiro_Local", "Envio_Domicilio"], required=True),
                "direccion_envio": st.column_config.TextColumn("Dirección"),
                "rango_horario": st.column_config.SelectboxColumn("Horario", options=["08:00-09:00", "09:00-10:00", "10:00-11:00", "11:00-12:00", "12:00-13:00"]),
                "total_calculado": st.column_config.NumberColumn("Total ($)", disabled=True) 
            },
            num_rows="dynamic",
            hide_index=True,
            key="editor_pedidos_v3"
        )
        
        if st.button("💾 Guardar Cambios en Pedidos"):
            estado_pedidos = st.session_state["editor_pedidos_v3"]
            try:
                if estado_pedidos["edited_rows"]:
                    for idx_str, cambios in estado_pedidos["edited_rows"].items():
                        idx = int(idx_str)
                        pedido_id = df_pedidos_edicion.iloc[idx]["id"]
                        
                        batata_actual = float(df_pedidos_edicion.iloc[idx]["docenas_batata"])
                        membrillo_actual = float(df_pedidos_edicion.iloc[idx]["docenas_membrillo"])
                        nueva_batata = float(cambios.get("docenas_batata", batata_actual))
                        nuevo_membrillo = float(cambios.get("docenas_membrillo", membrillo_actual))
                        
                        if "docenas_batata" in cambios or "docenas_membrillo" in cambios:
                            cambios["total_calculado"] = float(calcular_total(nueva_batata, nuevo_membrillo, PRECIO_DOCENA, PRECIO_MEDIA))
                        
                        mod_actual = df_pedidos_edicion.iloc[idx]["modalidad_entrega"]
                        nueva_mod = cambios.get("modalidad_entrega", mod_actual)

                        if nueva_mod == "Retiro_Local":
                            cambios["direccion_envio"] = None
                            cambios["rango_horario"] = None
                            cambios["latitud"] = None
                            cambios["longitud"] = None
                        else:
                            dir_actual = df_pedidos_edicion.iloc[idx]["direccion_envio"]
                            nueva_dir = cambios.get("direccion_envio", dir_actual)
                            
                            if "modalidad_entrega" in cambios or "direccion_envio" in cambios:
                                if pd.notna(nueva_dir) and str(nueva_dir).strip() and str(nueva_dir).strip() != "None":
                                    lat, lon = obtener_coordenadas(nueva_dir)
                                    cambios["latitud"] = lat
                                    cambios["longitud"] = lon
                                else:
                                    cambios["latitud"] = None
                                    cambios["longitud"] = None
                        
                        supabase.table("pedidos").update(cambios).eq("id", pedido_id).execute()

                if estado_pedidos["deleted_rows"]:
                    for idx in estado_pedidos["deleted_rows"]:
                        pedido_id = df_pedidos_edicion.iloc[idx]["id"]
                        supabase.table("pedidos").delete().eq("id", pedido_id).execute()

                st.success("Actualización consolidada en la base de datos.")
                st.rerun()
            except Exception as e:
                st.error(f"Error de ejecución SQL: {e}")
                
        # --- EXPORTACIÓN AL EXCEL ---
        st.divider()
        df_excel = df_pedidos.copy()
        df_excel["Batata"] = df_excel["docenas_batata"].apply(decimal_a_fraccion)
        df_excel["Membrillo"] = df_excel["docenas_membrillo"].apply(decimal_a_fraccion)
        
        excel_data = exportar_excel(df_excel[["cliente_nombre", "Batata", "Membrillo", "total_calculado", "estado_pago", "modalidad_entrega"]])
        st.download_button("📥 Descargar Planilla Excel (Formato A4)", data=excel_data, file_name=f"pedidos_{campana_activa}.xlsx")

        # --- ZONA DE PELIGRO ---
        st.divider()
        with st.expander("⚠️ Zona de Peligro: Eliminar todos los pedidos de la campaña"):
            st.error("Alerta: Esta instrucción ejecutará un DELETE masivo sobre los pedidos vinculados a esta campaña específica.")
            confirmacion = st.checkbox("Comprendo el riesgo. Desbloquear botón de purga.")
            if confirmacion:
                if st.button("🚨 Ejecutar Borrado", type="primary"):
                    supabase.table("pedidos").delete().eq("campana_id", ID_CAMPANA).execute()
                    st.success("Registros eliminados permanentemente.")
                    st.rerun()
    else:
        st.info("No hay pedidos registrados en esta campaña.")

# --- PESTAÑA 2: FINANZAS (Módulo de Rentabilidad) ---
with tab2:
    st.header("📈 Balance Financiero")
    
    if not pedidos_req.data:
        ingresos_totales = 0
    else:
        df_ped = pd.DataFrame(pedidos_req.data)
        df_ped['total_calculado'] = pd.to_numeric(df_ped['total_calculado'], errors="coerce").fillna(0)
        ingresos_totales = df_ped[df_ped['estado_pago'] == 'Pagado']['total_calculado'].sum()

    gastos_req = supabase.table("gastos").select("*").eq("campana_id", ID_CAMPANA).execute()
    df_gastos = pd.DataFrame()
    gastos_totales = 0
    if gastos_req.data:
        df_gastos = pd.DataFrame(gastos_req.data)
        df_gastos['monto'] = pd.to_numeric(df_gastos['monto'], errors="coerce").fillna(0)
        gastos_totales = df_gastos['monto'].sum()
    
    rentabilidad = ingresos_totales - gastos_totales

    col_m1, col_m2, col_m3 = st.columns(3)
    col_m1.metric("Ingresos Efectivos (Pagados)", f"${ingresos_totales:,.2f}")
    col_m2.metric("Gastos Operativos", f"${gastos_totales:,.2f}")
    col_m3.metric("Ganancia Neta", f"${rentabilidad:,.2f}", delta=float(rentabilidad))

    st.divider()

    st.subheader("➕ Registrar Nuevo Gasto")
    with st.form("form_gasto", clear_on_submit=True):
        desc = st.text_input("Descripción del Insumo (Ej: Cajas, Aceite, Harina)")
        monto = st.number_input("Monto total ($)", min_value=0.0, step=100.0, format="%.2f")
        if st.form_submit_button("Registrar Gasto") and desc:
            supabase.table("gastos").insert({
                "campana_id": ID_CAMPANA, 
                "descripcion": desc, 
                "monto": monto, 
                "fecha_registro": str(date.today())
            }).execute()
            st.success("Gasto registrado con éxito.")
            st.rerun()

    st.divider()

    st.subheader("📋 Historial y Edición de Gastos")
    if not df_gastos.empty:
        st.caption("💡 Puedes editar las celdas numéricas/fechas directamente o seleccionar una fila y presionar 'Delete' para eliminarla.")
        
        df_gastos_edicion = df_gastos[["id", "descripcion", "monto", "fecha_registro"]].copy()
        df_gastos_edicion["monto"] = pd.to_numeric(df_gastos_edicion["monto"], errors="coerce")
        df_gastos_edicion["fecha_registro"] = pd.to_datetime(df_gastos_edicion["fecha_registro"], errors="coerce").dt.date
        
        gastos_editados = st.data_editor(
            df_gastos_edicion,
            column_config={
                "id": None, 
                "descripcion": st.column_config.TextColumn("Descripción del Gasto", required=True),
                "monto": st.column_config.NumberColumn("Monto ($)", min_value=0.0, format="$%.2f", required=True),
                "fecha_registro": st.column_config.DateColumn("Fecha de Registro", required=True)
            },
            num_rows="dynamic",
            hide_index=True,
            key="editor_gastos_tabla"
        )
        
        if st.button("💾 Guardar Cambios en Gastos"):
            estado_cambios = st.session_state["editor_gastos_tabla"]
            try:
                if estado_cambios["edited_rows"]:
                    for idx_str, columnas_modificadas in estado_cambios["edited_rows"].items():
                        idx = int(idx_str)
                        gasto_id = df_gastos_edicion.iloc[idx]["id"]
                        if "fecha_registro" in columnas_modificadas and not isinstance(columnas_modificadas["fecha_registro"], str):
                            columnas_modificadas["fecha_registro"] = str(columnas_modificadas["fecha_registro"])
                        supabase.table("gastos").update(columnas_modificadas).eq("id", gasto_id).execute()

                if estado_cambios["deleted_rows"]:
                    for idx in estado_cambios["deleted_rows"]:
                        gasto_id = df_gastos_edicion.iloc[idx]["id"]
                        supabase.table("gastos").delete().eq("id", gasto_id).execute()

                st.success("Base de datos de gastos actualizada correctamente.")
                st.rerun()
            except Exception as e:
                st.error(f"Error crítico durante la persistencia de datos: {e}")
    else:
        st.info("No existen gastos registrados en la campaña activa.")

# --- PESTAÑA 3: REPARTO (Lógica de Enrutamiento y Mapa) ---
with tab3:
    st.header("🚚 Logística y Envíos")
    if pedidos_req.data:
        df_rutas = pd.DataFrame(pedidos_req.data)
        envios_totales = df_rutas[df_rutas['modalidad_entrega'] == 'Envio_Domicilio']
        
        if not envios_totales.empty:
            sin_coord = envios_totales[envios_totales['latitud'].isnull()]
            if not sin_coord.empty:
                st.warning(f"⚠️ Atención: Hay {len(sin_coord)} pedido(s) asignados como 'Envío a Domicilio' que no tienen una dirección o coordenadas válidas. Debes completar su dirección en la Pestaña de Pedidos para que aparezcan en la ruta.")
            
            envios = envios_totales[envios_totales['latitud'].notnull()]
            
            if not envios.empty:
                opciones_rango = ["Todos"] + list(envios['rango_horario'].dropna().unique())
                rango_seleccionado = st.selectbox("Filtrar por Rango Horario", opciones_rango)
                
                if rango_seleccionado == "Todos":
                    pedidos_rango = envios.copy()
                else:
                    pedidos_rango = envios[envios['rango_horario'] == rango_seleccionado].copy()
                
                st.subheader("Borrador de Ruta")
                pedidos_rango["Incluir"] = True
                
                editado = st.data_editor(pedidos_rango[["cliente_nombre", "direccion_envio", "rango_horario", "Incluir"]], hide_index=True)
                
                if st.button("🗺️ Generar Ruta Óptima (VRP)"):
                    pedidos_confirmados = pedidos_rango[editado["Incluir"] == True]
                    if len(pedidos_confirmados) < 2:
                        st.warning("Se necesitan al menos 2 puntos para generar una ruta.")
                    else:
                        with st.spinner("Calculando ruta óptima con OpenRouteService..."):
                            coordenadas = [[float(row['longitud']), float(row['latitud'])] for _, row in pedidos_confirmados.iterrows()]
                            origen = [-55.108986,-27.476643] 
                            jobs = [{"id": i, "location": coord} for i, coord in enumerate(coordenadas)]
                            
                            body = {
                                "vehicles": [{"id": 1, "profile": "driving-car", "start": origen, "end": origen}],
                                "jobs": jobs
                            }
                            headers = {"Authorization": st.secrets["ORS_API_KEY"], "Content-Type": "application/json"}
                            res = requests.post("https://api.openrouteservice.org/optimization", json=body, headers=headers)
                            
                            if res.status_code == 200:
                                st.success("Ruta generada.")
                                data = res.json()
                                m = folium.Map(location=[origen[1], origen[0]], zoom_start=13)
                                folium.Marker([origen[1], origen[0]], popup="LOCAL", icon=folium.Icon(color="red")).add_to(m)
                                
                                for step in data['routes'][0]['steps']:
                                    if step['type'] == 'job':
                                        loc = step['location']
                                        job_id = step['job']
                                        cliente_r = pedidos_confirmados.iloc[job_id]['cliente_nombre']
                                        folium.Marker([loc[1], loc[0]], popup=f"Entrega: {cliente_r}").add_to(m)
                                
                                st_folium(m, width=700, height=500)
                            else:
                                st.error(f"Error en la API de Rutas: {res.text}")
            else:
                st.info("No hay pedidos con envío a domicilio que cuenten con coordenadas válidas listos para rutear.")
        else:
            st.info("No hay pedidos con envío a domicilio en esta campaña.")
            
# --- PESTAÑA 4: CONFIGURACIÓN ---
with tab4:
    st.header("⚙️ Gestión de Campañas")
    with st.form("form_campana", clear_on_submit=True):
        st.subheader("Crear Nueva Campaña")
        n_nombre = st.text_input("Nombre (Ej: Julio 2026)")
        n_fecha = st.date_input("Fecha del Evento")
        n_p_doc = st.number_input("Precio Docena Inicial", value=7000)
        n_p_med = st.number_input("Precio Media Inicial", value=4000)
        
        if st.form_submit_button("Crear Campaña") and n_nombre:
            supabase.table("campanas").insert({
                "nombre_campana": n_nombre,
                "fecha_entrega": str(n_fecha),
                "precio_docena": n_p_doc,
                "precio_media": n_p_med,
                "estado": "Activa"
            }).execute()
            st.success("Campaña creada.")
            st.rerun()
