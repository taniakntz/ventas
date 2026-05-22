import streamlit as st
import pandas as pd
import requests
import time
import re
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

# --- 3. SISTEMA DE AUTENTICACIÓN ---
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

# --- 4. UTILIDADES ---
def decimal_a_fraccion(valor):
    if pd.isna(valor) or valor == 0: return "0"
    entero, decimal = int(valor), round(valor - int(valor), 2)
    frac = {0.25: "1/4", 0.5: "1/2", 0.75: "3/4"}.get(decimal, "")
    if entero == 0: return frac if frac else str(valor)
    return f"{entero} {frac}" if frac else str(entero)

def calcular_total(batata, membrillo, precio_doc, precio_med):
    total_docenas = batata + membrillo
    if total_docenas == 1.0 or (batata == 0.5 and membrillo == 0.5): return precio_doc
    total = 0
    for cant in [batata, membrillo]:
        entero, resto = int(cant), round(cant % 1, 2)
        total += entero * precio_doc
        total += {0.25: precio_med/2, 0.5: precio_med, 0.75: precio_med*1.5}.get(resto, 0)
    return total

def obtener_coordenadas(direccion):
    if not direccion or str(direccion).strip().upper() == "EMPTY": 
        return None, None
        
    texto = str(direccion).strip().replace("&", "y")
    if "Oberá" not in texto: texto = f"{texto}, Oberá"
    
    # URL de Nominatim (OpenStreetMap)
    url = "https://nominatim.openstreetmap.org/search"
    headers = {'User-Agent': 'PastelitosLogistica_Debug/1.0 (admin@obera.com)'}
    params = {'q': texto, 'format': 'json', 'limit': 1}
    
    try:
        # Hacemos la consulta
        res = requests.get(url, params=params, headers=headers, timeout=10)
        
        # AQUÍ ESTÁ LA CLAVE: Si falla, te avisamos por qué
        if res.status_code != 200:
            st.error(f"Error de servidor OSM: Código {res.status_code}")
            return None, None
            
        data = res.json()
        if not data:
            st.warning(f"La API no encontró resultados para: '{texto}'")
            return None, None
            
        lat = data[0]['lat']
        lon = data[0]['lon']
        return float(lat), float(lon)
            
    except Exception as e:
        st.error(f"Fallo de conexión: {e}")
        return None, None
    
def exportar_excel(dataframe):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        dataframe.to_excel(writer, index=False, sheet_name='Ventas')
    return output.getvalue()

# --- 5. LÓGICA DE DATOS ---
res_camp = supabase.table("campanas").select("*").execute()
campanas_df = pd.DataFrame(res_camp.data)

if campanas_df.empty:
    st.info("Configura una campaña en la última pestaña.")
    st.stop()

campana_activa = st.sidebar.selectbox("Campaña", campanas_df['nombre_campana'].tolist())
datos_c = campanas_df[campanas_df['nombre_campana'] == campana_activa].iloc[0]
ID_CAMPANA, PRECIO_DOCENA, PRECIO_MEDIA = datos_c['id'], float(datos_c['precio_docena']), float(datos_c['precio_media'])

tab1, tab2, tab3, tab4 = st.tabs(["📦 Pedidos", "📈 Finanzas", "🚚 Reparto", "⚙️ Configuración"])

# --- PESTAÑA 1: PEDIDOS ---
with tab1:
    st.header("📝 Nuevo Pedido")

    try:
        c_nom = st.text_input("Nombre del Cliente", key="in_nom")
        col1, col2 = st.columns(2)
        with col1: c_bat = st.number_input("Docenas Batata", 0.0, step=0.25, key="in_bat")
        with col2: c_mem = st.number_input("Docenas Membrillo", 0.0, step=0.25, key="in_mem")      

        col3, col4, col5 = st.columns(3)
        with col3: c_mod = st.selectbox("Entrega", ["Retiro_Local", "Envio_Domicilio"], key="in_mod")
        with col4: c_pag = st.selectbox("Estado de Pago", ["Pendiente", "Pagado"], key="in_pag")
        with col5: c_met = st.selectbox("Método de Pago", ["N/A", "Efectivo", "MP"], key="in_met")        

        c_dir, c_ran = None, None
        if c_mod == "Envio_Domicilio":
            c_dir = st.text_input("Dirección de Envío", placeholder="Calle, Ciudad", key="in_dir")
            c_ran = st.selectbox("Rango Horario", ["08:00-09:00", "09:00-10:00", "10:00-11:00", "11:00-12:00", "12:00-13:00"], key="in_ran")   

        if st.button("Guardar Pedido", type="primary"):
            if not c_nom: 
                st.error("⚠️ El nombre es obligatorio.")
            else:
                total = calcular_total(c_bat, c_mem, PRECIO_DOCENA, PRECIO_MEDIA)
                lat, lon = obtener_coordenadas(c_dir) if c_dir else (None, None)
                supabase.table("pedidos").insert({
                    "campana_id": ID_CAMPANA, "cliente_nombre": c_nom, "docenas_batata": c_bat,
                    "docenas_membrillo": c_mem, "total_calculado": total, "estado_pago": c_pag,
                    "metodo_pago": c_met, "modalidad_entrega": c_mod, "direccion_envio": c_dir, "rango_horario": c_ran,
                    "latitud": lat, "longitud": lon
                }).execute()
                st.rerun()   

        st.divider()
        pedidos_req = supabase.table("pedidos").select("*").eq("campana_id", ID_CAMPANA).execute()
        if pedidos_req.data:
            df = pd.DataFrame(pedidos_req.data)
            
            st.subheader("🧑‍🍳 Resumen Producción")
            df["docenas_batata"] = pd.to_numeric(df["docenas_batata"], errors="coerce").fillna(0)
            df["docenas_membrillo"] = pd.to_numeric(df["docenas_membrillo"], errors="coerce").fillna(0)
            b_t, m_t = df["docenas_batata"].sum(), df["docenas_membrillo"].sum()
            c1, c2, c3 = st.columns(3)
            c1.metric("Batata", decimal_a_fraccion(b_t))
            c2.metric("Membrillo", decimal_a_fraccion(m_t))
            c3.metric("Total", decimal_a_fraccion(b_t + m_t))    

            st.subheader("📋 Gestión de Pedidos")
            # Vista limpia: Excluye explícitamente direccion_envio y rango_horario para evitar ruido visual
            df_ed = df[["id", "cliente_nombre", "docenas_batata", "docenas_membrillo", "estado_pago", "metodo_pago", "modalidad_entrega", "total_calculado"]].copy()            

            df_ed["estado_pago"] = df_ed["estado_pago"].replace([None, "", "nan"], "Pendiente")
            df_ed["metodo_pago"] = df_ed["metodo_pago"].replace([None, "", "nan"], "N/A")
            df_ed["modalidad_entrega"] = df_ed["modalidad_entrega"].replace([None, "", "nan"], "Retiro_Local")
            df_ed["total_calculado"] = pd.to_numeric(df_ed["total_calculado"]).fillna(0)            

            res_ed = st.data_editor(
                df_ed, 
                column_config={
                    "id": None, 
                    "total_calculado": st.column_config.NumberColumn("Total ($)", disabled=True),
                    "modalidad_entrega": st.column_config.SelectboxColumn("Entrega", options=["Retiro_Local", "Envio_Domicilio"], required=True),
                    "estado_pago": st.column_config.SelectboxColumn("Pago", options=["Pendiente", "Pagado"], required=True),
                    "metodo_pago": st.column_config.SelectboxColumn("Método", options=["N/A", "Efectivo", "MP"], required=True)
                }, 
                num_rows="dynamic", hide_index=True, key="p_v_final_strict"
            )   

            if st.button("💾 Guardar Cambios"):
                state = st.session_state["p_v_final_strict"]
                if state["edited_rows"]:
                    for idx_str, mods in state["edited_rows"].items():
                        idx = int(idx_str)
                        rid = df_ed.iloc[idx]["id"]
                        if mods.get("modalidad_entrega") == "Retiro_Local":
                            mods.update({"direccion_envio": None, "rango_horario": None, "latitud": None, "longitud": None})
                        if "docenas_batata" in mods or "docenas_membrillo" in mods:
                            nb = mods.get("docenas_batata", df_ed.iloc[idx]["docenas_batata"])
                            nm = mods.get("docenas_membrillo", df_ed.iloc[idx]["docenas_membrillo"])
                            mods["total_calculado"] = calcular_total(nb, nm, PRECIO_DOCENA, PRECIO_MEDIA)
                        supabase.table("pedidos").update(mods).eq("id", rid).execute()
                if state["deleted_rows"]:
                    for idx in state["deleted_rows"]:
                        rid = df_ed.iloc[idx]["id"]
                        supabase.table("pedidos").delete().eq("id", rid).execute()
                st.rerun()
                
            st.divider()
            df_excel = df.copy()
            df_excel["Batata"] = df_excel["docenas_batata"].apply(decimal_a_fraccion)
            df_excel["Membrillo"] = df_excel["docenas_membrillo"].apply(decimal_a_fraccion)
            excel_data = exportar_excel(df_excel[["cliente_nombre", "Batata", "Membrillo", "total_calculado", "estado_pago", "modalidad_entrega"]])

            st.download_button("📥 Descargar Planilla Excel (Formato A4)", data=excel_data, file_name=f"pedidos_{campana_activa}.xlsx")

            st.divider()
            with st.expander("⚠️ Zona de Peligro: Eliminar todos los pedidos"):
                st.error("Alerta: Esta acción eliminará permanentemente todos los pedidos de la campaña activa.")
                confirm = st.checkbox("Confirmar eliminación masiva")

                if confirm:
                    if st.button("🚨 Ejecutar Borrado Total", type="primary"):
                        supabase.table("pedidos").delete().eq("campana_id", ID_CAMPANA).execute()
                        st.success("Pedidos eliminados.")
                        st.rerun()
        else:
            st.info("No hay pedidos registrados en esta campaña.")

    except Exception as e:
        st.error(f"Error en Pedidos: {e}")
        st.info("Podés seguir usando las otras pestañas normalmente.")
        
# --- PESTAÑA 2: FINANZAS ---
with tab2:
    st.header("📈 Balance")
    try:
        if pedidos_req.data:
            ing = df[df['estado_pago'] == 'Pagado']['total_calculado'].sum()
            gas_res = supabase.table("gastos").select("*").eq("campana_id", ID_CAMPANA).execute()
            df_gastos = pd.DataFrame(gas_res.data) if gas_res.data else pd.DataFrame()
            gas_tot = df_gastos['monto'].sum() if not df_gastos.empty else 0
            c1, c2, c3 = st.columns(3)
            c1.metric("Ingresos", f"${ing:,.2f}")
            c2.metric("Gastos", f"${gas_tot:,.2f}")
            c3.metric("Neto", f"${ing - gas_tot:,.2f}")
    
            st.divider()
            st.subheader("➕ Nuevo Gasto")
            with st.form("g_form", clear_on_submit=True):
                g_desc = st.text_input("Descripción")
                g_mont = st.number_input("Monto", 0.0, step=100.0)
                if st.form_submit_button("Registrar"):
                    supabase.table("gastos").insert({"campana_id": ID_CAMPANA, "descripcion": g_desc, "monto": g_mont, "fecha_registro": str(date.today())}).execute()
                    st.rerun()
            
            if not df_gastos.empty:
                st.subheader("📋 Detalle de Gastos")
                df_gastos["monto"] = pd.to_numeric(df_gastos["monto"])
                df_gastos["fecha_registro"] = pd.to_datetime(df_gastos["fecha_registro"]).dt.date
                ed_g = st.data_editor(df_gastos[["id", "descripcion", "monto", "fecha_registro"]], column_config={"id": None}, num_rows="dynamic", hide_index=True, key="g_ed")
                if st.button("💾 Guardar Gastos"):
                    st_g = st.session_state["g_ed"]
                    for i_s, m in st_g["edited_rows"].items():
                        rid = df_gastos.iloc[int(i_s)]["id"]
                        if "fecha_registro" in m: m["fecha_registro"] = str(m["fecha_registro"])
                        supabase.table("gastos").update(m).eq("id", rid).execute()
                    for i in st_g["deleted_rows"]:
                        supabase.table("gastos").delete().eq("id", df_gastos.iloc[i]["id"]).execute()
                    st.rerun()
                    
    except Exception as e:
        st.error(f"Error en Balance: {e}")
        st.info("Podés seguir usando las otras pestañas normalmente.")

# --- PESTAÑA 3: REPARTO ---
with tab3:
    st.header("🚚 Logística")

    try:
        if "datos_ruta_cache" not in st.session_state: st.session_state.datos_ruta_cache = None
        if "ids_en_ruta" not in st.session_state: st.session_state.ids_en_ruta = []
    
        if pedidos_req.data:
            envios = df[df['modalidad_entrega'] == "Envio_Domicilio"].copy()
            if not envios.empty:
                filt = st.selectbox("Filtro Horario", ["Todos"] + sorted(list(envios['rango_horario'].dropna().unique())))
                df_log = envios if filt == "Todos" else envios[envios['rango_horario'] == filt]
                df_log["Incluir"] = True
                
                st.subheader("📍 Datos de Envío")
                res_log = st.data_editor(df_log[["id", "cliente_nombre", "direccion_envio", "rango_horario", "Incluir"]], 
                                         column_config={
                                             "id":None, "cliente_nombre":st.column_config.TextColumn("Cliente", disabled=True),
                                             "Incluir": st.column_config.CheckboxColumn("Incluir", default=True),
                                             "rango_horario":st.column_config.SelectboxColumn("Horario", options=["08:00-09:00", "09:00-10:00", "10:00-11:00", "11:00-12:00", "12:00-13:00"])
                                         }, hide_index=True, key="log_vfinal")
                
                col_l1, col_l2 = st.columns(2)
                
                if col_l1.button("📍 Actualizar Logística"):
                    st_l = st.session_state["log_vfinal"]
                    hubo_cambios = False
                    
                    # FASE 1: Guardar modificaciones directas hechas en la tabla
                    if st_l["edited_rows"]:
                        for i_s, m in st_l["edited_rows"].items():
                            rid = df_log.iloc[int(i_s)]["id"]
                            datos_a_guardar = m.copy()
                            
                            if "Incluir" in datos_a_guardar:
                                del datos_a_guardar["Incluir"]
                            
                            if datos_a_guardar:
                                if "direccion_envio" in datos_a_guardar:
                                    lat, lon = obtener_coordenadas(datos_a_guardar["direccion_envio"])
                                    if lat is not None and lon is not None:
                                        datos_a_guardar.update({"latitud": lat, "longitud": lon})
                                
                                supabase.table("pedidos").update(datos_a_guardar).eq("id", rid).execute()
                                hubo_cambios = True

                    # FASE 2: Escaneo y conversión automática de registros vacíos/EMPTY
                    pendientes = df_log[df_log['latitud'].isnull() | df_log['longitud'].isnull()]
                    
                    if not pendientes.empty:
                        with st.spinner(f"Mapeando {len(pendientes)} direcciones en segundo plano..."):
                            for idx, row in pendientes.iterrows():
                                if str(idx) not in st_l["edited_rows"]:
                                    lat, lon = obtener_coordenadas(row["direccion_envio"])
                                    if lat is not None and lon is not None:
                                        supabase.table("pedidos").update({"latitud": lat, "longitud": lon}).eq("id", row["id"]).execute()
                                        hubo_cambios = True
                                    time.sleep(1.2) 

                    if hubo_cambios:
                        st.session_state.datos_ruta_cache = None 
                        st.rerun()
                    elif not pendientes.empty:
                        st.warning("⚠️ El motor cartográfico no logró decodificar las nuevas direcciones. Comprobá que no contengan abreviaturas o formatos inválidos.")
    
                if col_l2.button("🗺️ Generar/Ver Ruta Óptima"):
                    ready_ids = res_log[res_log['Incluir'] == True]['id'].tolist()
                    
                    if st.session_state.datos_ruta_cache is None or ready_ids != st.session_state.ids_en_ruta:
                        with st.spinner("Calculando ruta real con OpenRouteService..."):
                            ready_coords = df_log[(df_log['id'].isin(ready_ids)) & (df_log['latitud'].notnull())]
                            
                            if len(ready_coords) < 1:
                                st.error("❌ No hay coordenadas asignadas en la base de datos para generar la ruta.")
                            else:
                                origen = [-55.1089, -27.4766] 
                                
                                jobs_list = []
                                map_nombres = {}
                                for i, (_, row) in enumerate(ready_coords.iterrows()):
                                    j_id = i + 1
                                    map_nombres[j_id] = row['cliente_nombre']
                                    jobs_list.append({
                                        "id": j_id, 
                                        "location": [float(row['longitud']), float(row['latitud'])]
                                    })
                                
                                body_vrp = {
                                    "vehicles": [{"id": 1, "profile": "driving-car", "start": origen, "end": origen}],
                                    "jobs": jobs_list
                                }
                                
                                api_key = st.secrets.get("ORS_API_KEY", "")
                                if not api_key:
                                    st.error("🚨 Error Crítico: No se encontró 'ORS_API_KEY' en los secretos.")
                                else:
                                    headers = {"Authorization": api_key, "Content-Type": "application/json"}
                                    res_vrp = requests.post("https://api.openrouteservice.org/optimization", json=body_vrp, headers=headers)
                                    
                                    if res_vrp.status_code == 200:
                                        data_vrp = res_vrp.json()
                                        orden_coords = [origen]
                                        info_clientes = []

                                        rutas = data_vrp.get('routes', [])
                                        if rutas:
                                            for step in rutas[0]['steps']:
                                                lon_s, lat_s = step['location']
                                                orden_coords.append([lon_s, lat_s])
                                                if step['type'] == 'job':
                                                    c_n = map_nombres.get(step['job'], "Desconocido")
                                                    info_clientes.append({"lat": lat_s, "lon": lon_s, "nombre": c_n})

                                            body_dir = {"coordinates": orden_coords}
                                            res_dir = requests.post("https://api.openrouteservice.org/v2/directions/driving-car/geojson", json=body_dir, headers=headers)
                                            
                                            if res_dir.status_code == 200:
                                                st.session_state.datos_ruta_cache = {
                                                    "geojson": res_dir.json(),
                                                    "clientes": info_clientes,
                                                    "origen": [origen[1], origen[0]] 
                                                }
                                                st.session_state.ids_en_ruta = ready_ids
                                                st.rerun() 
                                            else:
                                                st.error(f"❌ Error al trazar calles (HTTP {res_dir.status_code}): {res_dir.text}")
                                        else:
                                            st.error("⚠️ La API de optimización no pudo trazar un trayecto coherente con esos puntos.")
                                    else:
                                        st.error(f"❌ Error de OpenRouteService (HTTP {res_vrp.status_code}): {res_vrp.text}")
    
                if st.session_state.datos_ruta_cache:
                    cache = st.session_state.datos_ruta_cache
                    m = folium.Map(location=cache["origen"], zoom_start=14)
                    folium.Marker(cache["origen"], popup="LOCAL", icon=folium.Icon(color="green", icon="home")).add_to(m)
                    
                    for c in cache["clientes"]:
                        folium.Marker([c["lat"], c["lon"]], popup=f"Cliente: {c['nombre']}", icon=folium.Icon(color="red")).add_to(m)
                    
                    folium.GeoJson(cache["geojson"], style_function=lambda x: {'color': 'blue', 'weight': 5, 'opacity': 0.7}).add_to(m)
                    st_folium(m, width=800, height=500, key="mapa_reparto")
            else:
                st.info("No hay pedidos con envío a domicilio.")
    except Exception as e:
        st.error(f"Error en Reparto: {e}")
        st.info("Podés seguir usando las otras pestañas normalmente.")
        
# --- PESTAÑA 4: CONFIGURACIÓN ---
with tab4:
    st.header("⚙️ Gestión de Campañas")

    try:
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

    except Exception as e:
        st.error(f"Error en Configuracion: {e}")
        st.info("Podés seguir usando las otras pestañas normalmente.")
