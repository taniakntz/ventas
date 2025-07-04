import streamlit as st
import pandas as pd
from io import BytesIO
from datetime import date
import os

st.set_page_config(page_title="Ventas de Pastelitos", layout="centered")
st.title("📦 Registro de ventas de pastelitos")

# --- CONFIGURACIÓN DE PRECIOS ---
st.sidebar.header("💲 Precios")
precio_docena = st.sidebar.number_input("Precio por docena", value=6000, step=500)
precio_media = st.sidebar.number_input("Precio por media docena", value=3500, step=250)

# --- ARCHIVO DE GUARDADO ---
data_file = "ventas_guardadas.xlsx"

# --- CARGAR DATOS EXISTENTES ---
if os.path.exists(data_file):
    df = pd.read_excel(data_file)
else:
    df = pd.DataFrame(columns=["Cliente", "Batata", "Membrillo", "Total ($)"])

# --- FUNCION CALCULO TOTAL ---
def calcular_total(batata, membrillo):
    total = 0
    for cantidad in [batata, membrillo]:
        if cantidad == 0.5:
            total += precio_media
        elif cantidad == 0.25:
            total += precio_media / 2
        elif cantidad == 0.75:
            total += precio_media + (precio_media / 2)
        elif cantidad >= 1:
            total += int(cantidad) * precio_docena
            if cantidad % 1 == 0.5:
                total += precio_media
            elif cantidad % 1 == 0.25:
                total += precio_media / 2
            elif cantidad % 1 == 0.75:
                total += precio_media + (precio_media / 2)
    return total

# --- AGREGAR NUEVA VENTA ---
st.subheader("📝 Agregar cliente")
with st.form("form_venta"):
    nombre = st.text_input("Nombre del cliente")
    batata = st.number_input("Docenas de batata", min_value=0.0, step=0.25)
    membrillo = st.number_input("Docenas de membrillo", min_value=0.0, step=0.25)
    submitted = st.form_submit_button("Agregar")

    if submitted and nombre:
        total = calcular_total(batata, membrillo)
        nueva_venta = pd.DataFrame([{"Cliente": nombre, "Batata": batata, "Membrillo": membrillo, "Total ($)": total}])
        df = pd.concat([df, nueva_venta], ignore_index=True)
        df.to_excel(data_file, index=False)
        st.success(f"Venta agregada para {nombre} por ${total}")

# --- MOSTRAR TABLA Y ACCIONES ---
if not df.empty:
    st.subheader("📋 Lista de ventas")
    st.dataframe(df, use_container_width=True)

    # --- BORRAR O EDITAR CLIENTE ---
    st.subheader("✏️ Modificar o eliminar una venta")
    cliente_seleccionado = st.selectbox("Seleccionar cliente", df["Cliente"].unique())
    accion = st.radio("Acción", ["Modificar", "Eliminar"])

    if accion == "Modificar":
        idx = df[df["Cliente"] == cliente_seleccionado].index[0]
        nuevo_batata = st.number_input("Nueva cantidad batata", value=float(df.at[idx, "Batata"]), step=0.25)
        nuevo_membrillo = st.number_input("Nueva cantidad membrillo", value=float(df.at[idx, "Membrillo"]), step=0.25)
        if st.button("Guardar cambios"):
            total = calcular_total(nuevo_batata, nuevo_membrillo)
            df.at[idx, "Batata"] = nuevo_batata
            df.at[idx, "Membrillo"] = nuevo_membrillo
            df.at[idx, "Total ($)"] = total
            df.to_excel(data_file, index=False)
            st.success("Venta actualizada correctamente.")

    elif accion == "Eliminar":
        if st.button("Eliminar venta"):
            df = df[df["Cliente"] != cliente_seleccionado]
            df.to_excel(data_file, index=False)
            st.success("Venta eliminada correctamente.")

    # --- RESUMEN ---
    total_batata = df["Batata"].sum()
    total_membrillo = df["Membrillo"].sum()
    total_cobrado = df["Total ($)"].sum()

    st.markdown("---")
    st.subheader("📊 Resumen")
    st.write(f"**Total docenas de batata:** {total_batata}")
    st.write(f"**Total docenas de membrillo:** {total_membrillo}")
    st.write(f"**Total recaudado:** ${total_cobrado}")

    # --- EXPORTAR ---
    def exportar_excel(dataframe):
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            dataframe.to_excel(writer, index=False, sheet_name='Ventas')
        return output.getvalue()

    excel_data = exportar_excel(df)
    st.download_button(
        label="📥 Descargar como Excel",
        data=excel_data,
        file_name=f"ventas_{date.today()}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    # --- ELIMINAR TODO ---
    if st.button("🗑️ Borrar todas las ventas"):
        df = pd.DataFrame(columns=["Cliente", "Batata", "Membrillo", "Total ($)"])
        if os.path.exists(data_file):
            os.remove(data_file)
        st.success("Todas las ventas fueron eliminadas.")
else:
    st.info("Todavía no se ingresaron ventas.")
