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
import unicodedata

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

def normalizar_texto(txt):
    txt = unicodedata.normalize('NFKD', txt)
    return ''.join(c for c in txt if not unicodedata.combining(c)).lower()
    
def obtener_coordenadas(direccion):
    if not direccion: return None, None
    texto_original = str(direccion).strip()
    if texto_original.upper() == "EMPTY": return None, None

    # 1. INTERCEPTOR MANUAL (Bypass total para evitar la API si pasás coordenadas limpias)
    match_coords = re.search(r'(-?\d{1,2}\.\d+)[,\s]+(-?\d{1,3}\.\d+)', texto_original)
    if match_coords:
        return float(match_coords.group(1)), float(match_coords.group(2))

    # 2. PARCHE LÉXICO (Intersecciones)
    if " y " in texto_original.lower():
        texto = re.split(r'\s+y\s+', texto_original, flags=re.IGNORECASE)[0].strip()
    else:
        texto = texto_original

    # 3. PHOTON API
    texto_normalizado = normalizar_texto(texto)
    if "obera" not in texto_normalizado: texto = f"{texto}, Oberá, Misiones, Argentina"
    elif "argentina" not in texto_normalizado: texto = f"{texto}, Misiones, Argentina"

    url = "https://photon.komoot.io/api/"
    params = {"q": texto, "limit": 5}
    headers = {'User-Agent': 'PastelitosApp_Obera/1.0 (contacto: admin@obera.com)'}

    try:
        res = requests.get(url, params=params, headers=headers, timeout=15)
        if res.status_code != 200: return None, None
        
        features = res.json().get("features", [])
        if not features: return None, None

        for f in features:
            coords = f["geometry"]["coordinates"]
            props = f.get("properties", {})
            ciudad = props.get("city", "") or props.get("county", "") or props.get("state", "")
            if "obera" in normalizar_texto(ciudad):
                return coords[1], coords[0] # lat, lon

        return None, None

    except Exception:
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

campana_activa = st.sidebar.selectbox("Campaña", campanas_df['nombre_campana'].tolist(), index=len(campanas_df) - 1)
datos_c = campanas_df[campanas_df['nombre_campana'] == campana_activa].iloc[0]
ID_CAMPANA, PRECIO_DOCENA, PRECIO_MEDIA = datos_c['id'], float(datos_c['precio_docena']), float(datos_c['precio_media'])

tab1, tab2, tab3, tab4 = st.tabs(["📦 Pedidos", "📈 Finanzas", "🚚 Reparto", "⚙️ Configuración"])

# --- PESTAÑA 1: PEDIDOS ---
with tab1:
    st.header("📝 Nuevo Pedido")

    try:
        col_n1, col_n2 = st.columns(2)
        with col_n1: c_nom = st.text_input("Nombre del Cliente", key="in_nom")
        with col_n2: c_tel = st.text_input("WhatsApp (Solo números. Ej: 3755123456)", key="in_tel")
        
        col1, col2 = st.columns(2)
        with col1: c_bat = st.number_input("Docenas Batata", 0.0, step=0.25, key="in_bat")
        with col2: c_mem = st.number_input("Docenas Membrillo", 0.0, step=0.25, key="in_mem")      

        col3, col4, col5 = st.columns(3)
        with col3: c_mod = st.selectbox("Entrega", ["Retiro_Local", "Envio_Domicilio"], key="in_mod")
        with col4: c_pag = st.selectbox("Estado de Pago", ["Pendiente", "Pagado"], key="in_pag")
        with col5: c_met = st.selectbox("Método de Pago", ["N/A", "Efectivo", "MP"], key="in_met")        

        c_dir, c_ran = None, None
        if c_mod == "Envio_Domicilio":
            c_dir = st.text_input("Dirección de Envío", placeholder="Calle, Ciudad o Coordenadas (-27.12, -55.12)", key="in_dir")
            # NUEVO RANGO HORARIO AGREGADO ACÁ
            c_ran = st.selectbox("Rango Horario", ["07:00-08:00", "08:00-09:00", "09:00-10:00", "10:00-11:00", "11:00-12:00", "12:00-13:00"], key="in_ran")   

        if st.button("Guardar Pedido", type="primary"):
            if not c_nom: 
                st.error("⚠️ El nombre es obligatorio.")
            else:
                total = calcular_total(c_bat, c_mem, PRECIO_DOCENA, PRECIO_MEDIA)
                lat, lon = obtener_coordenadas(c_dir) if c_dir else (None, None)
                # Limpieza de caracteres en el teléfono por si el usuario puso espacios o guiones
                telefono_limpio = re.sub(r'\D', '', c_tel) if c_tel else None
                
                supabase.table("pedidos").insert({
                    "campana_id": ID_CAMPANA, "cliente_nombre": c_nom, "telefono": telefono_limpio, 
                    "docenas_batata": c_bat, "docenas_membrillo": c_mem, "total_calculado": total, 
                    "estado_pago": c_pag, "metodo_pago": c_met, "modalidad_entrega": c_mod, 
                    "direccion_envio": c_dir, "rango_horario": c_ran, "latitud": lat, "longitud": lon
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
            
            # Generar URL de WhatsApp al vuelo para la tabla
            if "telefono" in df.columns:
                df["WhatsApp"] = df["telefono"].apply(lambda x: f"https://wa.me/549{x}" if pd.notnull(x) and x != "" else None)
            else:
                df["WhatsApp"] = None

            df_ed = df[["id", "cliente_nombre", "WhatsApp", "docenas_batata", "docenas_membrillo", "estado_pago", "metodo_pago", "modalidad_entrega", "total_calculado"]].copy()            

            df_ed["estado_pago"] = df_ed["estado_pago"].replace([None, "", "nan"], "Pendiente")
            df_ed["metodo_pago"] = df_ed["metodo_pago"].replace([None, "", "nan"], "N/A")
            df_ed["modalidad_entrega"] = df_ed["modalidad_entrega"].replace([None, "", "nan"], "Retiro_Local")
            df_ed["total_calculado"] = pd.to_numeric(df_ed["total_calculado"]).fillna(0)            

            res_ed = st.data_editor(
                df_ed, 
                column_config={
                    "id": None, 
                    "WhatsApp": st.column_config.LinkColumn("WhatsApp", display_text="💬 Enviar Mensaje"),
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
                        
                        # No intentamos guardar la columna virtual de WhatsApp en DB
                        if "WhatsApp" in mods:
                            del mods["WhatsApp"]
                            
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
            excel_data = exportar_excel(df_excel[["cliente_nombre", "telefono", "Batata", "Membrillo", "total_calculado", "estado_pago", "modalidad_entrega"]])

            st.download_button("📥 Descargar Planilla Excel", data=excel_data, file_name=f"pedidos_{campana_activa}.xlsx")

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
        if "datos_ruta_cache" not in st.session_state:
            st.session_state.datos_ruta_cache = None

        if "ids_en_ruta" not in st.session_state:
            st.session_state.ids_en_ruta = []

        if pedidos_req.data:
            envios = df[df['modalidad_entrega'] == "Envio_Domicilio"].copy()

            if not envios.empty:
                filt = st.selectbox(
                    "Filtro Horario",
                    ["Todos"] + sorted(list(envios['rango_horario'].dropna().unique()))
                )

                df_log = envios if filt == "Todos" else envios[envios['rango_horario'] == filt]
                df_log["Incluir"] = True

                st.subheader("📍 Datos de Envío")

                res_log = st.data_editor(
                    df_log[["id", "cliente_nombre", "direccion_envio", "rango_horario", "Incluir"]],
                    column_config={
                        "id": None,
                        "cliente_nombre": st.column_config.TextColumn("Cliente", disabled=True),
                        "Incluir": st.column_config.CheckboxColumn("Incluir", default=True),
                        "rango_horario": st.column_config.SelectboxColumn(
                            "Horario",
                            # NUEVO RANGO HORARIO AGREGADO ACÁ TAMBIÉN
                            options=["07:00-08:00", "08:00-09:00", "09:00-10:00", "10:00-11:00", "11:00-12:00", "12:00-13:00"]
                        )
                    },
                    hide_index=True,
                    key="log_vfinal"
                )

                col_l1, col_l2 = st.columns(2)

                # =====================================
                # ACTUALIZAR LOGISTICA (BOTÓN INTELIGENTE)
                # =====================================
                if col_l1.button("📍 Actualizar Logística"):
                    hubo_cambios = False
                    for idx, row in res_log.iterrows():
                        rid = row["id"]
                        direccion_nueva = row["direccion_envio"]
                        rango = row["rango_horario"]

                        # Chequea la DB para no reprocesar filas que no fueron modificadas
                        pedido_db = next((p for p in pedidos_req.data if p["id"] == rid), None)
                        if pedido_db:
                            dir_vieja = pedido_db.get("direccion_envio")
                            lat_vieja = pedido_db.get("latitud")
                            if direccion_nueva == dir_vieja and lat_vieja is not None:
                                continue # Ignora esta fila, ahorra tiempo y bloqueos de API

                        datos_update = {
                            "direccion_envio": direccion_nueva,
                            "rango_horario": rango
                        }

                        if direccion_nueva:
                            lat, lon = obtener_coordenadas(direccion_nueva)
                            
                            if lat is not None and lon is not None:
                                datos_update.update({"latitud": lat, "longitud": lon})
                                st.toast(f"✅ Ok: {direccion_nueva}")
                            else:
                                st.warning(f"⚠️ Falló: {direccion_nueva}")

                            # Solo hace pausa si procesó un texto real. Si pegaste coordenadas a mano, saltea la espera.
                            if not re.search(r'(-?\d{1,2}\.\d+)[,\s]+(-?\d{1,3}\.\d+)', str(direccion_nueva)):
                                time.sleep(1.5)

                        # Limpieza estricta de NaN
                        datos_update = {k: (None if pd.isna(v) else v) for k, v in datos_update.items()}
                        supabase.table("pedidos").update(datos_update).eq("id", rid).execute()
                        hubo_cambios = True

                    if hubo_cambios:
                        st.session_state.datos_ruta_cache = None
                        st.success("✅ Logística actualizada (Solo se procesaron los cambios)")
                        st.rerun()
                    else:
                        st.info("No detecté modificaciones. Nada que actualizar.")

                # =====================================
                # GENERAR RUTA OPTIMA
                # =====================================
                if col_l2.button("🗺️ Generar/Ver Ruta Óptima"):
                    try:
                        pedidos_ruta = []
                        for _, row in res_log.iterrows():
                            if row["Incluir"]:
                                pedido_db = next((p for p in pedidos_req.data if p["id"] == row["id"]), None)
                                if pedido_db and pedido_db.get("latitud") is not None and pedido_db.get("longitud") is not None:
                                    pedidos_ruta.append({
                                        "id": pedido_db["id"],
                                        "nombre": pedido_db["cliente_nombre"],
                                        "lat": float(pedido_db["latitud"]),
                                        "lon": float(pedido_db["longitud"])
                                    })

                        if not pedidos_ruta:
                            st.warning("No hay pedidos con coordenadas válidas.")
                        else:
                            ORIGEN_LAT = -27.476740
                            ORIGEN_LON = -55.108945

                            coords_ors = [[ORIGEN_LON, ORIGEN_LAT]]
                            for p in pedidos_ruta:
                                coords_ors.append([p["lon"], p["lat"]])

                            url_dir = "https://api.openrouteservice.org/v2/directions/driving-car/geojson"
                            headers = {
                                "Authorization": st.secrets["ORS_API_KEY"],
                                "Content-Type": "application/json"
                            }
                            
                            body_dir = {
                                "coordinates": coords_ors,
                                "radiuses": [1500] * len(coords_ors)
                            }

                            res_dir = requests.post(url_dir, json=body_dir, headers=headers, timeout=30)

                            if res_dir.status_code == 200:
                                geojson = res_dir.json()
                                st.session_state.datos_ruta_cache = {
                                    "origen": [ORIGEN_LAT, ORIGEN_LON],
                                    "clientes": pedidos_ruta,
                                    "geojson": geojson
                                }
                                st.success("✅ Ruta generada correctamente")
                                st.rerun()
                            else:
                                st.error(f"❌ Error al generar ruta. HTTP: {res_dir.status_code}\n{res_dir.text}")

                    except Exception as e:
                        st.error(f"Error generando ruta: {e}")

                # =====================================
                # RENDERIZADO DEL MAPA 
                # =====================================
                if st.session_state.datos_ruta_cache:
                    cache = st.session_state.datos_ruta_cache
                    m = folium.Map(location=cache["origen"], zoom_start=14)
                    
                    folium.Marker(
                        cache["origen"], 
                        popup="LOCAL", 
                        icon=folium.Icon(color="green", icon="home")
                    ).add_to(m)

                    for c in cache["clientes"]:
                        folium.Marker(
                            [c["lat"], c["lon"]], 
                            popup=f"Cliente: {c['nombre']}", 
                            icon=folium.Icon(color="red")
                        ).add_to(m)

                    folium.GeoJson(
                        cache["geojson"],
                        style_function=lambda x: {"color": "blue", "weight": 5, "opacity": 0.8}
                    ).add_to(m)

                    st_folium(m, width=800, height=500, key="mapa_reparto")

            else:
                st.info("No hay pedidos con envío a domicilio.")

    except Exception as e:
        st.error(f"ERROR TAB3: {e}")
        import traceback
        st.code(traceback.format_exc())
                    
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
