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
    url = f"https://nominatim.openstreetmap.org/search?q={direccion}&format=json&limit=1"
    headers = {'User-Agent': 'PastelitosApp/1.0'}
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200 and len(res.json()) > 0:
            return float(res.json()[0]['lat']), float(res.json()[0]['lon'])
    except: pass
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
    
    c_nom = st.text_input("Nombre del Cliente", key="in_nom")
    col1, col2 = st.columns(2)
    with col1: c_bat = st.number_input("Batata (Docenas)", 0.0, step=0.25, key="in_bat")
    with col2: c_mem = st.number_input("Membrillo (Docenas)", 0.0, step=0.25, key="in_mem")
    
    col3, col4 = st.columns(2)
    with col3: c_mod = st.selectbox("Entrega", ["Retiro_Local", "Envio_Domicilio"], key="in_mod")
    with col4: c_pag = st.selectbox("Estado de Pago", ["Pendiente", "Pagado"], key="in_pag")
    
    c_dir, c_ran = None, None
    if c_mod == "Envio_Domicilio":
        c_dir = st.text_input("Dirección de Envío", placeholder="Calle 123, Ciudad", key="in_dir")
        c_ran = st.selectbox("Rango Horario", ["08:00-09:00", "09:00-10:00", "10:00-11:00", "11:00-12:00", "12:00-13:00"], key="in_ran")

    if st.button("Guardar Pedido", type="primary"):
        if not c_nom.strip():
            st.error("⚠️ El nombre es obligatorio.")
        elif c_mod == "Envio_Domicilio" and not c_dir:
            st.error("⚠️ Falta la dirección para el envío.")
        else:
            total = calcular_total(c_bat, c_mem, PRECIO_DOCENA, PRECIO_MEDIA)
            lat, lon = obtener_coordenadas(c_dir) if c_dir else (None, None)
            
            supabase.table("pedidos").insert({
                "campana_id": ID_CAMPANA, "cliente_nombre": c_nom, "docenas_batata": c_bat,
                "docenas_membrillo": c_mem, "total_calculado": total, "estado_pago": c_pag,
                "modalidad_entrega": c_mod, "direccion_envio": c_dir, "rango_horario": c_ran,
                "latitud": lat, "longitud": lon
            }).execute()
            st.success("Pedido guardado!")
            st.rerun()

    st.divider()
    pedidos_req = supabase.table("pedidos").select("*").eq("campana_id", ID_CAMPANA).execute()
    if pedidos_req.data:
        df = pd.DataFrame(pedidos_req.data)
        
        # Resumen Producción
        st.subheader("🧑‍🍳 Producción")
        df["docenas_batata"] = pd.to_numeric(df["docenas_batata"], errors="coerce").fillna(0)
        df["docenas_membrillo"] = pd.to_numeric(df["docenas_membrillo"], errors="coerce").fillna(0)
        b_t, m_t = df["docenas_batata"].sum(), df["docenas_membrillo"].sum()
        c1, c2, c3 = st.columns(3)
        c1.metric("Batata", decimal_a_fraccion(b_t))
        c2.metric("Membrillo", decimal_a_fraccion(m_t))
        c3.metric("Total", decimal_a_fraccion(b_t + m_t))

        st.subheader("📋 Gestión de Pedidos")
        df_ed = df[["id", "cliente_nombre", "docenas_batata", "docenas_membrillo", "estado_pago", "modalidad_entrega", "total_calculado"]].copy()
        df_ed["total_calculado"] = pd.to_numeric(df_ed["total_calculado"]).fillna(0)
        
        res_ed = st.data_editor(df_ed, column_config={
            "id": None, 
            "total_calculado": st.column_config.NumberColumn("Total", disabled=True),
            "modalidad_entrega": st.column_config.SelectboxColumn("Entrega", options=["Retiro_Local", "Envio_Domicilio"]),
            "estado_pago": st.column_config.SelectboxColumn("Pago", options=["Pendiente", "Pagado"]) # <-- MODIFICACIÓN AQUÍ
        }, num_rows="dynamic", hide_index=True, key="p_v_final_pago")

        if st.button("💾 Guardar Cambios"):
            state = st.session_state["p_v_final_pago"]
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
            for idx in state["deleted_rows"]:
                supabase.table("pedidos").delete().eq("id", df_ed.iloc[idx]["id"]).execute()
            st.rerun()

# --- PESTAÑA 2: FINANZAS ---
with tab2:
    st.header("📈 Balance")
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

# --- PESTAÑA 3: REPARTO ---
with tab3:
    st.header("🚚 Logística")
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
                                         "id":None, "cliente_nombre":st.column_config.TextColumn(disabled=True),
                                         "Incluir": st.column_config.CheckboxColumn("Incluir", default=True),
                                         "rango_horario":st.column_config.SelectboxColumn("Horario", options=["08:00-09:00", "09:00-10:00", "10:00-11:00", "11:00-12:00", "12:00-13:00"])
                                     }, hide_index=True, key="log_vfinal")
            
            col_l1, col_l2 = st.columns(2)
            if col_l1.button("📍 Actualizar Logística"):
                st_l = st.session_state["log_vfinal"]
                for i_s, m in st_l["edited_rows"].items():
                    rid = df_log.iloc[int(i_s)]["id"]
                    if "direccion_envio" in m:
                        lat, lon = obtener_coordenadas(m["direccion_envio"])
                        m.update({"latitud": lat, "longitud": lon})
                    supabase.table("pedidos").update(m).eq("id", rid).execute()
                st.session_state.datos_ruta_cache = None 
                st.rerun()

            if col_l2.button("🗺️ Generar/Ver Ruta Óptima"):
                ready_ids = res_log[res_log['Incluir'] == True]['id'].tolist()
                
                if st.session_state.datos_ruta_cache is None or ready_ids != st.session_state.ids_en_ruta:
                    with st.spinner("Calculando ruta real..."):
                        ready_coords = df_log[(df_log['id'].isin(ready_ids)) & (df_log['latitud'].notnull())]
                        
                        if len(ready_coords) >= 1:
                            origen = [-55.1089, -27.4766] 
                            
                            body_vrp = {
                                "vehicles": [{"id": 1, "profile": "driving-car", "start": origen, "end": origen}],
                                "jobs": [{"id": i, "location": [row['longitud'], row['latitud']]} for i, (_, row) in enumerate(ready_coords.iterrows())]
                            }
                            headers = {"Authorization": st.secrets["ORS_API_KEY"], "Content-Type": "application/json"}
                            res_vrp = requests.post("https://api.openrouteservice.org/optimization", json=body_vrp, headers=headers)
                            
                            if res_vrp.status_code == 200:
                                data_vrp = res_vrp.json()
                                orden_coords = [origen]
                                info_clientes = []

                                for step in data_vrp['routes'][0]['steps']:
                                    lon_s, lat_s = step['location']
                                    orden_coords.append([lon_s, lat_s])
                                    if step['type'] == 'job':
                                        c_n = ready_coords.iloc[step['job']]['cliente_nombre']
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
