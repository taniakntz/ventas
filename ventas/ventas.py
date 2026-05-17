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
            # Guardamos el usuario en una variable que Streamlit no borrará
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
MAPA_FRACCIONES = {"0": 0.0, "1/4": 0.25, "1/2": 0.5, "3/4": 0.75}

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
    # API Gratuita de Nominatim (Requiere User-Agent)
    url = f"https://nominatim.openstreetmap.org/search?q={direccion}&format=json&limit=1"
    headers = {'User-Agent': 'PastelitosApp/1.0'}
    response = requests.get(url, headers=headers)
    if response.status_code == 200 and len(response.json()) > 0:
        data = response.json()[0]
        return float(data['lat']), float(data['lon'])
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
    st.stop() # Frena la ejecución aquí hasta que exista una campaña

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
    with st.form("form_pedido", clear_on_submit=True):
        cliente = st.text_input("Nombre del Cliente")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1: ent_bat = st.number_input("Batata (Enteros)", min_value=0, step=1)
        with col2: frac_bat = st.selectbox("Batata (Fracción)", list(MAPA_FRACCIONES.keys()))
        with col3: ent_mem = st.number_input("Membrillo (Enteros)", min_value=0, step=1)
        with col4: frac_mem = st.selectbox("Membrillo (Fracción)", list(MAPA_FRACCIONES.keys()))
        
        col_m, col_p = st.columns(2)
        with col_m:
            modalidad = st.selectbox("Modalidad de Entrega", ["Retiro_Local", "Envio_Domicilio"])
            direccion = st.text_input("Dirección (Solo si es Envío)", placeholder="Calle 123, Ciudad") if modalidad == "Envio_Domicilio" else ""
            rango = st.selectbox("Rango Horario", ["08:00-09:00", "09:00-10:00", "10:00-11:00", "11:00-12:00", "12:00-13:00"]) if modalidad == "Envio_Domicilio" else ""
        with col_p:
            metodo = st.selectbox("Método de Pago", ["Efectivo", "Transferencia", "N/A"])
            estado_pago = st.selectbox("Estado de Pago", ["Pendiente", "Pagado"])

        submit = st.form_submit_button("Guardar Pedido")
        
        if submit and cliente:
            batata_total = ent_bat + MAPA_FRACCIONES[frac_bat]
            membrillo_total = ent_mem + MAPA_FRACCIONES[frac_mem]
            total_dinero = calcular_total(batata_total, membrillo_total, PRECIO_DOCENA, PRECIO_MEDIA)
            
            lat, lon = obtener_coordenadas(direccion) if modalidad == "Envio_Domicilio" and direccion else (None, None)
            
            nuevo_pedido = {
                "campana_id": ID_CAMPANA,
                "cliente_nombre": cliente,
                "docenas_batata": float(batata_total),
                "docenas_membrillo": float(membrillo_total),
                "total_calculado": float(total_dinero),
                "estado_pago": estado_pago,
                "metodo_pago": metodo,
                "modalidad_entrega": modalidad,
                "direccion_envio": direccion,
                "rango_horario": rango if modalidad == "Envio_Domicilio" else None,
                "latitud": lat,
                "longitud": lon
            }
            supabase.table("pedidos").insert(nuevo_pedido).execute()
            st.success(f"Pedido guardado. Total calculado: ${total_dinero}")
            st.rerun()

    # Vista de Base de Datos
    st.divider()
    st.subheader("📋 Pedidos de la Campaña")
    pedidos_req = supabase.table("pedidos").select("*").eq("campana_id", ID_CAMPANA).execute()
    if pedidos_req.data:
        df_pedidos = pd.DataFrame(pedidos_req.data)
        # Cálculo dinámico para la vista
        df_pedidos["Docenas Totales"] = df_pedidos["docenas_batata"] + df_pedidos["docenas_membrillo"]
        st.dataframe(df_pedidos[["cliente_nombre", "Docenas Totales", "total_calculado", "estado_pago", "modalidad_entrega"]], use_container_width=True)
        
        excel_data = exportar_excel(df_pedidos)
        st.download_button("📥 Descargar Planilla Excel (Formato A4)", data=excel_data, file_name=f"pedidos_{campana_activa}.xlsx")

# --- PESTAÑA 2: FINANZAS (Módulo de Rentabilidad) ---
with tab2:
    st.header("📈 Balance Financiero")
    
    # Obtener ingresos reales (Solo PAGADO)
    if not pedidos_req.data:
        ingresos_totales = 0
    else:
        df_ped = pd.DataFrame(pedidos_req.data)
        ingresos_totales = df_ped[df_ped['estado_pago'] == 'Pagado']['total_calculado'].sum()

    # Obtener gastos
    gastos_req = supabase.table("gastos").select("*").eq("campana_id", ID_CAMPANA).execute()
    gastos_totales = 0
    if gastos_req.data:
        df_gastos = pd.DataFrame(gastos_req.data)
        gastos_totales = df_gastos['monto'].sum()
    
    rentabilidad = ingresos_totales - gastos_totales

    col_m1, col_m2, col_m3 = st.columns(3)
    col_m1.metric("Ingresos Efectivos (Pagados)", f"${ingresos_totales:,.2f}")
    col_m2.metric("Gastos Operativos", f"${gastos_totales:,.2f}")
    col_m3.metric("Ganancia Neta", f"${rentabilidad:,.2f}", delta=float(rentabilidad))

    st.subheader("Añadir Gasto")
    with st.form("form_gasto", clear_on_submit=True):
        desc = st.text_input("Descripción (Ej: Cajas, Aceite)")
        monto = st.number_input("Monto", min_value=0.0, step=100.0)
        if st.form_submit_button("Registrar Gasto") and desc:
            supabase.table("gastos").insert({"campana_id": ID_CAMPANA, "descripcion": desc, "monto": monto, "fecha_registro": str(date.today())}).execute()
            st.success("Gasto registrado")
            st.rerun()

# --- PESTAÑA 3: REPARTO (Lógica de Enrutamiento y Mapa) ---
with tab3:
    st.header("🚚 Logística y Envíos")
    if pedidos_req.data:
        df_rutas = pd.DataFrame(pedidos_req.data)
        envios = df_rutas[(df_rutas['modalidad_entrega'] == 'Envio_Domicilio') & (df_rutas['latitud'].notnull())]
        
        if not envios.empty:
            rango_seleccionado = st.selectbox("Filtrar por Rango Horario", envios['rango_horario'].unique())
            pedidos_rango = envios[envios['rango_horario'] == rango_seleccionado].copy()
            
            st.subheader("Borrador de Ruta")
            # Interfaz para marcar/desmarcar pedidos por stock (True por defecto)
            pedidos_rango["Incluir"] = True
            editado = st.data_editor(pedidos_rango[["cliente_nombre", "direccion_envio", "Incluir"]], hide_index=True)
            
            if st.button("🗺️ Generar Ruta Óptima (VRP)"):
                pedidos_confirmados = pedidos_rango[editado["Incluir"] == True]
                if len(pedidos_confirmados) < 2:
                    st.warning("Se necesitan al menos 2 puntos para generar una ruta.")
                else:
                    with st.spinner("Calculando ruta óptima con OpenRouteService..."):
                        coordenadas = [[row['longitud'], row['latitud']] for _, row in pedidos_confirmados.iterrows()]
                        # Punto de partida
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
                            # Dibujar mapa con Folium
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
            st.info("No hay pedidos con envío a domicilio con coordenadas válidas.")
    else:
        st.info("Aún no hay pedidos en esta campaña.")

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
