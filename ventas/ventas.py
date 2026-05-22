# ========================= IMPORTS =========================
import streamlit as st
import pandas as pd
import requests
import time
import re
import unicodedata
from io import BytesIO
from datetime import date
from supabase import create_client, Client
import folium
from streamlit_folium import st_folium
from openpyxl.styles import Font, PatternFill, Alignment

# ========================= CONFIG =========================
st.set_page_config(
    page_title="Gestión de Pastelitos",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ========================= SUPABASE =========================
@st.cache_resource
def init_connection() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_connection()

# ========================= AUTH =========================
def check_password():
    def password_entered():
        if (
            st.session_state["username"] in st.secrets["passwords"]
            and st.session_state["password"]
            == st.secrets["passwords"][st.session_state["username"]]
        ):
            st.session_state["password_correct"] = True
            st.session_state["usuario_logeado"] = st.session_state["username"]
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.title("🔒 Acceso Restringido")
        st.text_input("Usuario", key="username")
        st.text_input(
            "Contraseña",
            type="password",
            key="password",
            on_change=password_entered
        )
        return False

    elif not st.session_state["password_correct"]:
        st.title("🔒 Acceso Restringido")
        st.text_input("Usuario", key="username")
        st.text_input(
            "Contraseña",
            type="password",
            key="password",
            on_change=password_entered
        )
        st.error("😕 Usuario o contraseña incorrectos")
        return False

    return True

if not check_password():
    st.stop()

# ========================= UTILIDADES =========================
def decimal_a_fraccion(valor):
    if pd.isna(valor) or valor == 0:
        return "0"

    entero = int(valor)
    decimal = round(valor - entero, 2)

    frac = {
        0.25: "1/4",
        0.5: "1/2",
        0.75: "3/4"
    }.get(decimal, "")

    if entero == 0:
        return frac if frac else str(valor)

    return f"{entero} {frac}" if frac else str(entero)

def calcular_total(batata, membrillo, precio_doc, precio_med):
    total_docenas = batata + membrillo

    if total_docenas == 1.0 or (batata == 0.5 and membrillo == 0.5):
        return precio_doc

    total = 0

    for cant in [batata, membrillo]:
        entero = int(cant)
        resto = round(cant % 1, 2)

        total += entero * precio_doc

        total += {
            0.25: precio_med / 2,
            0.5: precio_med,
            0.75: precio_med * 1.5
        }.get(resto, 0)

    return total

def normalizar_texto(txt):
    txt = unicodedata.normalize('NFKD', txt)
    return ''.join(
        c for c in txt
        if not unicodedata.combining(c)
    ).lower()

# ========================= GEOCODING =========================
def obtener_coordenadas(direccion):

    if not direccion:
        return None, None

    texto = str(direccion).strip()

    if texto.upper() == "EMPTY":
        return None, None

    texto_normalizado = normalizar_texto(texto)

    # NORMALIZACIÓN INTELIGENTE
    if "obera" not in texto_normalizado:
        texto = f"{texto}, Oberá, Misiones, Argentina"

    elif "argentina" not in texto_normalizado:
        texto = f"{texto}, Misiones, Argentina"

    url = "https://nominatim.openstreetmap.org/search"

    headers = {
        "User-Agent": "PastelitosLogistica/1.0"
    }

    # DEBUG VISUAL
    st.write(f"🔎 Buscando dirección: {texto}")

    tiempos_espera = [2, 5, 10]

    for espera in tiempos_espera:

        try:
            res = requests.get(
                url,
                params={
                    "q": texto,
                    "format": "json",
                    "limit": 1,
                    "countrycodes": "ar"
                },
                headers=headers,
                timeout=15
            )

            if res.status_code == 200:

                data = res.json()

                st.write("📡 Respuesta API:", data)

                if data:
                    lat = float(data[0]["lat"])
                    lon = float(data[0]["lon"])

                    return lat, lon

                return None, None

            elif res.status_code == 429:

                st.warning(
                    f"⚠️ Nominatim saturado. Reintentando en {espera}s..."
                )

                time.sleep(espera)

            else:
                st.error(
                    f"❌ Error API: HTTP {res.status_code}"
                )
                return None, None

        except Exception as e:

            st.error(f"❌ Error geocoding: {e}")

            time.sleep(espera)

    return None, None

# ========================= EXPORT EXCEL =========================
def exportar_excel(dataframe):

    output = BytesIO()

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        dataframe.to_excel(
            writer,
            index=False,
            sheet_name='Ventas'
        )

    return output.getvalue()

# ========================= CARGA CAMPAÑAS =========================
res_camp = supabase.table("campanas").select("*").execute()

campanas_df = pd.DataFrame(res_camp.data)

if campanas_df.empty:
    st.info("Configura una campaña.")
    st.stop()

campana_activa = st.sidebar.selectbox(
    "Campaña",
    campanas_df['nombre_campana'].tolist()
)

datos_c = campanas_df[
    campanas_df['nombre_campana'] == campana_activa
].iloc[0]

ID_CAMPANA = datos_c['id']
PRECIO_DOCENA = float(datos_c['precio_docena'])
PRECIO_MEDIA = float(datos_c['precio_media'])

# ========================= TABS =========================
tab1, tab2, tab3, tab4 = st.tabs([
    "📦 Pedidos",
    "📈 Finanzas",
    "🚚 Reparto",
    "⚙️ Configuración"
])

# =========================================================
# ======================= PEDIDOS =========================
# =========================================================
with tab1:

    st.header("📝 Nuevo Pedido")

    try:

        c_nom = st.text_input(
            "Nombre del Cliente",
            key="in_nom"
        )

        col1, col2 = st.columns(2)

        with col1:
            c_bat = st.number_input(
                "Docenas Batata",
                0.0,
                step=0.25,
                key="in_bat"
            )

        with col2:
            c_mem = st.number_input(
                "Docenas Membrillo",
                0.0,
                step=0.25,
                key="in_mem"
            )

        col3, col4, col5 = st.columns(3)

        with col3:
            c_mod = st.selectbox(
                "Entrega",
                ["Retiro_Local", "Envio_Domicilio"],
                key="in_mod"
            )

        with col4:
            c_pag = st.selectbox(
                "Estado de Pago",
                ["Pendiente", "Pagado"],
                key="in_pag"
            )

        with col5:
            c_met = st.selectbox(
                "Método de Pago",
                ["N/A", "Efectivo", "MP"],
                key="in_met"
            )

        c_dir = None
        c_ran = None

        if c_mod == "Envio_Domicilio":

            c_dir = st.text_input(
                "Dirección de Envío",
                placeholder="Ej: French 911",
                key="in_dir"
            )

            c_ran = st.selectbox(
                "Rango Horario",
                [
                    "08:00-09:00",
                    "09:00-10:00",
                    "10:00-11:00",
                    "11:00-12:00",
                    "12:00-13:00"
                ],
                key="in_ran"
            )

        if st.button("Guardar Pedido", type="primary"):

            if not c_nom:
                st.error("⚠️ El nombre es obligatorio.")

            else:

                total = calcular_total(
                    c_bat,
                    c_mem,
                    PRECIO_DOCENA,
                    PRECIO_MEDIA
                )

                lat = None
                lon = None

                if c_dir:
                    lat, lon = obtener_coordenadas(c_dir)

                    if lat is None:
                        st.warning(
                            "⚠️ Dirección guardada pero sin coordenadas válidas."
                        )

                supabase.table("pedidos").insert({
                    "campana_id": ID_CAMPANA,
                    "cliente_nombre": c_nom,
                    "docenas_batata": c_bat,
                    "docenas_membrillo": c_mem,
                    "total_calculado": total,
                    "estado_pago": c_pag,
                    "metodo_pago": c_met,
                    "modalidad_entrega": c_mod,
                    "direccion_envio": c_dir,
                    "rango_horario": c_ran,
                    "latitud": lat,
                    "longitud": lon
                }).execute()

                st.success("✅ Pedido guardado.")
                st.rerun()

    except Exception as e:
        st.error(f"Error: {e}")

# =========================================================
# ======================= REPARTO =========================
# =========================================================
with tab3:

    st.header("🚚 Logística")

    try:

        pedidos_req = supabase.table("pedidos") \
            .select("*") \
            .eq("campana_id", ID_CAMPANA) \
            .execute()

        if pedidos_req.data:

            df = pd.DataFrame(pedidos_req.data)

            envios = df[
                df['modalidad_entrega'] == "Envio_Domicilio"
            ].copy()

            if not envios.empty:

                df_log = envios.copy()

                df_log["Incluir"] = True

                st.subheader("📍 Datos de Envío")

                res_log = st.data_editor(
                    df_log[
                        [
                            "id",
                            "cliente_nombre",
                            "direccion_envio",
                            "rango_horario",
                            "latitud",
                            "longitud",
                            "Incluir"
                        ]
                    ],

                    column_config={

                        "id": None,

                        "cliente_nombre":
                            st.column_config.TextColumn(
                                "Cliente",
                                disabled=True
                            ),

                        "latitud":
                            st.column_config.NumberColumn(
                                "Latitud",
                                disabled=True
                            ),

                        "longitud":
                            st.column_config.NumberColumn(
                                "Longitud",
                                disabled=True
                            ),

                        "Incluir":
                            st.column_config.CheckboxColumn(
                                "Incluir",
                                default=True
                            )
                    },

                    hide_index=True,
                    key="log_vfinal"
                )

                if st.button("📍 Actualizar Logística"):

                    st_l = st.session_state["log_vfinal"]

                    if st_l["edited_rows"]:

                        for i_s, mods in st_l["edited_rows"].items():

                            idx = int(i_s)

                            rid = df_log.iloc[idx]["id"]

                            datos_a_guardar = mods.copy()

                            if "Incluir" in datos_a_guardar:
                                del datos_a_guardar["Incluir"]

                            # SI MODIFICÓ DIRECCIÓN
                            if "direccion_envio" in datos_a_guardar:

                                direccion = datos_a_guardar[
                                    "direccion_envio"
                                ]

                                lat, lon = obtener_coordenadas(
                                    direccion
                                )

                                # SI NO PUDO GEOCODIFICAR
                                if lat is None or lon is None:

                                    st.error(
                                        f"""
                                        ❌ No se pudo localizar:
                                        {direccion}
                                        """
                                    )

                                    continue

                                datos_a_guardar.update({
                                    "latitud": lat,
                                    "longitud": lon
                                })

                            supabase.table("pedidos") \
                                .update(datos_a_guardar) \
                                .eq("id", rid) \
                                .execute()

                    # =====================================================
                    # REESCANEO AUTOMÁTICO
                    # =====================================================

                    pendientes = df_log[
                        (
                            df_log['latitud'].isnull()
                        ) |
                        (
                            df_log['longitud'].isnull()
                        )
                    ]

                    if not pendientes.empty:

                        with st.spinner(
                            f"Mapeando {len(pendientes)} direcciones..."
                        ):

                            for _, row in pendientes.iterrows():

                                direccion = row["direccion_envio"]

                                if not direccion:
                                    continue

                                lat, lon = obtener_coordenadas(
                                    direccion
                                )

                                if lat is not None and lon is not None:

                                    supabase.table("pedidos") \
                                        .update({
                                            "latitud": lat,
                                            "longitud": lon
                                        }) \
                                        .eq("id", row["id"]) \
                                        .execute()

                                time.sleep(1.2)

                    st.success("✅ Logística actualizada.")
                    st.rerun()

            else:
                st.info("No hay pedidos con envío.")

    except Exception as e:
        st.error(f"Error logística: {e}")
