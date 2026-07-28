import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium

# Layout WIDE dan sidebar disembunyiin biar kerasa kayak Dashboard beneran
st.set_page_config(page_title="Site Down/Up Mapping", layout="wide", initial_sidebar_state="collapsed")

# Styling biar padding atas gak terlalu lebar
st.markdown("<style> .block-container { padding-top: 1rem; padding-bottom: 0rem; } </style>", unsafe_allow_html=True)

st.title("🗺️ Network Ops Command Center")
st.markdown("Monitoring status Site (Up/Down) berdasarkan Dapot Google Sheets & Data UME.")

SHEET_URL = "https://docs.google.com/spreadsheets/d/11pp1YavJsR6wnYcvs0Z6B94KM75clu7FQgRy7sdEQ4g/export?format=csv&gid=0"

@st.cache_data(ttl=600)
def load_dapot():
    try:
        df = pd.read_csv(SHEET_URL)
        return df
    except Exception as e:
        st.error(f"Gagal narik data Dapot. Error: {e}")
        return None

# --- UPLOAD SECTION (Dibuat ringkas) ---
col_up1, col_up2 = st.columns([1, 2])
with col_up1:
    ume_file = st.file_uploader("Upload Data UME (fm-active.xlsx)", type=['xlsx'], label_visibility="collapsed")

with st.spinner('Menyiapkan data...'):
    df_dapot = load_dapot()

if df_dapot is not None and ume_file:
    try:
        df_ume = pd.read_excel(ume_file)
        
        # --- LOGIC MATCHING ---
        def clean_id(text):
            val = str(text).strip()
            return val[:-2] if val.endswith('.0') else val

        df_ume['ME_CLEAN'] = df_ume['ME ID'].apply(clean_id) if 'ME ID' in df_ume.columns else st.stop()
        df_dapot['NE_CLEAN'] = df_dapot['NE ID'].apply(clean_id) if 'NE ID' in df_dapot.columns else st.stop()

        # Rule Down
        cond_power = (df_ume['Alarm Code Name'].str.contains('Input power-off', case=False, na=False)) & \
                     (df_ume['Position'].astype(str).str.contains('Equipment=1', case=False, na=False))
        cond_link1 = (df_ume['Specific Problem'].str.contains('The link between the server and the ME is broken', case=False, na=False)) | \
                     (df_ume['Alarm Code Name'].str.contains('The link between the server and the ME is broken', case=False, na=False))
        cond_link2 = (df_ume['Specific Problem'].str.contains('Site Abis control link broken', case=False, na=False)) | \
                     (df_ume['Alarm Code Name'].str.contains('Site Abis control link broken', case=False, na=False))
        
        df_down = df_ume[cond_power | cond_link1 | cond_link2].copy()
        
        # Bikin Dictionary Alarm buat Popup
        if 'Occurrence Time' in df_down.columns:
            df_down['Alarm_Detail'] = "• " + df_down['Alarm Code Name'].astype(str) + " (" + df_down['Occurrence Time'].astype(str) + ")"
        else:
            df_down['Alarm_Detail'] = "• " + df_down['Alarm Code Name'].astype(str)
        
        alarm_dict = df_down.groupby('ME_CLEAN')['Alarm_Detail'].apply(lambda x: "<br>".join(x)).to_dict()
        site_down_list = df_down['ME_CLEAN'].dropna().unique()
        
        df_dapot['Status'] = df_dapot['NE_CLEAN'].apply(lambda x: 'Down' if x in site_down_list else 'Up')
        
        st.divider()

        # ==========================================
        # SPLIT SCREEN DASHBOARD (KIRI: STATS, KANAN: MAP)
        # ==========================================
        col_stats, col_map = st.columns([1.2, 2.8])
        
        # --- KOLOM KIRI (SUMMARY & TABEL) ---
        with col_stats:
            st.subheader("📊 Summary Status")
            up_count = len(df_dapot[df_dapot['Status'] == 'Up'])
            down_count = len(df_dapot[df_dapot['Status'] == 'Down'])
            
            c1, c2 = st.columns(2)
            c1.success(f"✅ **Up:** {up_count}")
            c2.error(f"🚨 **Down:** {down_count}")
            
            if down_count > 0:
                df_dapot_down = df_dapot[df_dapot['Status'] == 'Down'].copy()
                # Bersihin kolom Hub site dari NaN
                df_dapot_down['Hub site'] = df_dapot_down['Hub site'].fillna('Non Hub')
                
                # Tab untuk filter biar 1 halaman tetep ringkas
                tab1, tab2, tab3, tab4 = st.tabs(["Kabupaten", "Kecamatan", "Hub Site", "Data Lengkap"])
                
                with tab1:
                    st.dataframe(df_dapot_down['Kota/Kab'].value_counts().reset_index().rename(columns={'count':'Down'}), height=450, use_container_width=True)
                with tab2:
                    st.dataframe(df_dapot_down['Kecamatan'].value_counts().reset_index().rename(columns={'count':'Down'}), height=450, use_container_width=True)
                with tab3:
                    st.dataframe(df_dapot_down['Hub site'].value_counts().reset_index().rename(columns={'count':'Down'}), height=450, use_container_width=True)
                with tab4:
                    st.dataframe(df_dapot_down[['Site_ID', 'Hub site', 'Site_Name', 'LAT', 'LONG']], height=450, use_container_width=True)

        # --- KOLOM KANAN (MAPS) ---
        with col_map:
            st.subheader("📍 Peta Interaktif")
            
            if 'LAT' in df_dapot.columns and 'LONG' in df_dapot.columns:
                df_dapot['LAT'] = df_dapot['LAT'].astype(str).str.replace(',', '.').astype(float)
                df_dapot['LONG'] = df_dapot['LONG'].astype(str).str.replace(',', '.').astype(float)
                df_dapot = df_dapot.dropna(subset=['LAT', 'LONG'])
                
                m = folium.Map(location=[df_dapot['LAT'].mean(), df_dapot['LONG'].mean()], zoom_start=11)
                
                # Tambahin Base Map Satelit (Bisa di toggle lewat LayerControl)
                folium.TileLayer(
                    tiles='https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
                    attr='Google',
                    name='Google Satellite',
                    overlay=False,
                    control=True
                ).add_to(m)
                
                for idx, row in df_dapot.iterrows():
                    lat, lon = row['LAT'], row['LONG']
                    site_id = row.get('Site_ID', 'Unknown')
                    ne_id = row.get('NE_CLEAN', 'Unknown')
                    site_name = row.get('Site_Name', 'Unknown')
                    status = row['Status']
                    
                    # Ekstrak Info Tambahan
                    grid_type = row.get('Grid Category New', '-')
                    power_type = row.get('POWER TYPE', '-')
                    hub_val = str(row.get('Hub site', '')).strip()
                    hub_status = 'Non Hub' if not hub_val or hub_val.lower() == 'nan' else hub_val
                    is_hub = 'hub' in hub_status.lower() and 'non' not in hub_status.lower()
                    
                    color = 'red' if status == 'Down' else 'green'
                    
                    # Render Isi Popup Custom
                    if status == 'Down':
                        alarms_terkait = alarm_dict.get(ne_id, "Tidak ada data historis")
                        popup_html = f"""
                        <div style="min-width: 250px; font-size:12px;">
                            <b>Site ID: {site_id}</b> <br>
                            NE ID: {ne_id}<br>
                            {site_name}<br>
                            Status: <b style="color:red;">{status}</b><br>
                            <b>Tipe:</b> {hub_status} | <b>Power:</b> {power_type} | <b>Grid:</b> {grid_type}
                            <hr style="margin: 5px 0;">
                            <b style="font-size:11px;">Daftar Alarm Terdeteksi:</b><br>
                            <div style="font-size:10px; max-height:120px; overflow-y:auto; background-color:#f1f1f1; padding:5px; border-radius:4px;">
                                {alarms_terkait}
                            </div>
                        </div>
                        """
                    else:
                        popup_html = f"""
                        <div style="min-width: 200px; font-size:12px;">
                            <b>Site ID: {site_id}</b><br>
                            NE ID: {ne_id}<br>
                            {site_name}<br>
                            Status: <b style="color:green;">{status}</b><br>
                            <b>Tipe:</b> {hub_status} | <b>Power:</b> {power_type} | <b>Grid:</b> {grid_type}
                        </div>
                        """
                    
                    tooltip_text = f"{site_id} (Hub)" if is_hub else site_id
                    
                    # Logic Icon: Bintang Pin buat HUB, Titik Bulat buat NON-HUB
                    if is_hub:
                        folium.Marker(
                            location=[lat, lon],
                            icon=folium.Icon(color=color, icon='star', prefix='fa'),
                            popup=folium.Popup(popup_html, max_width=400),
                            tooltip=tooltip_text
                        ).add_to(m)
                    else:
                        folium.CircleMarker(
                            location=[lat, lon],
                            radius=4,
                            color=color,
                            weight=1,
                            fill=True,
                            fill_color=color,
                            fill_opacity=0.9,
                            popup=folium.Popup(popup_html, max_width=400),
                            tooltip=tooltip_text
                        ).add_to(m)
                
                # Menambahkan tombol Layer Control biar bisa switch ke mode Satelit
                folium.LayerControl(position='topright').add_to(m)
                
                st_folium(m, use_container_width=True, height=600, returned_objects=[])
                
            else:
                st.error("Kolom 'LAT' dan 'LONG' tidak valid!")
                
    except Exception as e:
        st.error(f"Terdapat kesalahan saat memproses data: {e}")
