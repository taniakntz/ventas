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
    entero, decimal = int(valor), valor - int(valor)
    frac = {0.25: "1/4", 0.5: "1/2", 0.75: "3/4"}.get(decimal, "")
    if entero == 0: return frac if frac else str(valor)
    return f"{entero} {frac}" if frac else str(entero)

def calcular_total(batata, membrillo, precio_doc, precio_med):
    total_docenas = batata + membrillo
    if total_docenas == 1.0 or (batata == 0.5 and membrillo == 0.5): return precio_doc
    total = 0
    for cant in [batata, membrillo]:
        entero, resto = int(cant), cant % 1
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
    with st.container():
        c_nom = st.text_input("Cliente", key="n_cli")
        col1, col2 = st.columns(2)
        c_bat = col1.number_input("Batata", 0.0, step=0.25, key="n_bat")
        c_mem = col2.number_input("Membrillo", 0.0, step=0.25, key="n_mem")
        col3, col4 = st.columns(2)
        c_mod = col3.selectbox("Entrega", ["Retiro_Local", "Envio_Domicilio"], key="n_mod")
        c_pag = col4.selectbox("Pago", ["Pendiente", "Pagado"], key="n_pag")
        
        if st.button("Guardar", type="primary"):
            if c_nom:
                total = calcular_total(c_bat, c_mem, PRECIO_DOCENA, PRECIO_MEDIA)
                supabase.table("pedidos").insert({
                    "campana_id": ID_CAMPANA, "cliente_nombre": c_nom, "docenas_batata": c_bat,
                    "docenas_membrillo": c_mem, "total_calculado": total, "estado_pago": c_pag,
                    "modalidad_entrega": c_mod
                }).execute()
                st.rerun()

    st.divider()
    pedidos_req = supabase.table("pedidos").select("*").eq("campana_id", ID_CAMPANA).execute()
    if pedidos_req.data:
        df = pd.DataFrame(pedidos_req.data)
        
        # Resumen Producción
        st.subheader("🧑‍🍳 Producción")
        b_t, m_t = df["docenas_batata"].sum(), df["docenas_membrillo"].sum()
        c1, c2, c3 = st.columns(3)
        c1.metric("Batata", decimal_a_fraccion(b_t))
        c2.metric("Membrillo", decimal_a_fraccion(m_t))
        c3.metric("Total", decimal_a_fraccion(b_t + m_t))

        # Editor de Pedidos (SIMPLIFICADO PARA EVITAR ERRORES)
        st.subheader("📋 Lista de Pedidos")
        cols_edit = ["id", "cliente_nombre", "docenas_batata", "docenas_membrillo", "estado_pago", "modalidad_entrega", "total_calculado"]
        df_ed = df[cols_edit].copy()
        
        res_ed = st.data_editor(df_ed, column_config={
            "id": None, "total_calculado": st.column_config.NumberColumn("Total", disabled=True),
            "modalidad_entrega": st.column_config.SelectboxColumn("Entrega", options=["Retiro_Local", "Envio_Domicilio"])
        }, num_rows="dynamic", hide_index=True, key="p_v4")

        if st.button("💾 Guardar Cambios"):
            state = st.session_state["p_v4"]
            for idx_str, mods in state["edited_rows"].items():
                idx = int(idx_str)
                row_id = df_ed.iloc[idx]["id"]
                # Si cambia a Retiro_Local, borramos basura logística en DB
                if mods.get("modalidad_entrega") == "Retiro_Local":
                    mods.update({"direccion_envio": None, "rango_horario": None, "latitud": None, "longitud": None})
                # Recalcular total si cambian cantidades
                if "docenas_batata" in mods or "docenas_membrillo" in mods:
                    nb = mods.get("docenas_batata", df_ed.iloc[idx]["docenas_batata"])
                    nm = mods.get("docenas_membrillo", df_ed.iloc[idx]["docenas_membrillo"])
                    mods["total_calculado"] = calcular_total(nb, nm, PRECIO_DOCENA, PRECIO_MEDIA)
                supabase.table("pedidos").update(mods).eq("id", row_id).execute()
            for idx in state["deleted_rows"]:
                supabase.table("pedidos").delete().eq("id", df_ed.iloc[idx]["id"]).execute()
            st.rerun()

# --- PESTAÑA 2: FINANZAS ---
with tab2:
    st.header("📈 Finanzas")
    if pedidos_req.data:
        ing = df[df['estado_pago'] == 'Pagado']['total_calculado'].sum()
        gas_res = supabase.table("gastos").select("*").eq("campana_id", ID_CAMPANA).execute()
        gas = sum(g['monto'] for g in gas_res.data) if gas_res.data else 0
        c1, c2, c3 = st.columns(3)
        c1.metric("Ingresos", f"${ing:,.2f}")
        c2.metric("Gastos", f"${gas:,.2f}")
        c3.metric("Neto", f"${ing-gas:,.2f}")

# --- PESTAÑA 3: REPARTO (LOGÍSTICA) ---
with tab3:
    st.header("🚚 Logística")
    if pedidos_req.data:
        envios = df[df['modalidad_entrega'] == "Envio_Domicilio"].copy()
        if not envios.empty:
            filt = st.selectbox("Filtro", ["Todos"] + list(envios['rango_horario'].dropna().unique()))
            df_log = envios if filt == "Todos" else envios[envios['rango_horario'] == filt]
            
            st.subheader("📍 Completar Datos de Envío")
            # AQUÍ ES DONDE EDITAS DIRECCIONES Y HORARIOS
            res_log = st.data_editor(df_log[["id", "cliente_nombre", "direccion_envio", "rango_horario"]], 
                                     column_config={"id":None, "cliente_nombre":st.column_config.TextColumn(disabled=True),
                                                    "rango_horario":st.column_config.SelectboxColumn("Horario", options=["08:00-09:00", "09:00-10:00", "10:00-11:00", "11:00-12:00", "12:00-13:00"])},
                                     hide_index=True, key="log_v1")
            
            if st.button("📍 Actualizar Direcciones/Horarios"):
                state_l = st.session_state["log_v1"]
                for idx_str, mods in state_l["edited_rows"].items():
                    idx = int(idx_str)
                    rid = df_log.iloc[idx]["id"]
                    if "direccion_envio" in mods:
                        lat, lon = obtener_coordenadas(mods["direccion_envio"])
                        mods.update({"latitud": lat, "longitud": lon})
                    supabase.table("pedidos").update(mods).eq("id", rid).execute()
                st.rerun()

            if st.button("🗺️ Generar Mapa"):
                ready = df_log[df_log['latitud'].notnull()]
                if not ready.empty:
                    m = folium.Map(location=[-27.4766, -55.1089], zoom_start=13)
                    for _, r in ready.iterrows():
                        folium.Marker([r['latitud'], r['longitud']], popup=r['cliente_nombre']).add_to(m)
                    st_folium(m, width=700)

# --- PESTAÑA 4: CONFIGURACIÓN ---
with tab4:
    st.header("⚙️ Configuración")
    with st.form("new_camp"):
        n = st.text_input("Nombre")
        p_d = st.number_input("Precio Docena", value=7000)
        p_m = st.number_input("Precio Media", value=4000)
        if st.form_submit_button("Crear"):
            supabase.table("campanas").insert({"nombre_campana":n, "precio_docena":p_d, "precio_media":p_m, "estado":"Activa"}).execute()
            st.rerun()
