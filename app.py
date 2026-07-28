import streamlit as st
import pandas as pd
import folium
from folium import MacroElement
from jinja2 import Template
from streamlit_folium import st_folium

# Layout WIDE dan sidebar disembunyiin
st.set_page_config(page_title="Site Down Monitoring", layout="wide", initial_sidebar_state="collapsed")

# Styling biar padding atas gak terlalu lebar
st.markdown("<style> .block-container { padding-top: 1rem; padding-bottom: 0rem; } </style>", unsafe_allow_html=True)

st.title("🗺️ Site Down Monitoring")
st.markdown("Monitoring status Site (Up/Down) berdasarkan alarm UME.")

SHEET_URL = "https://docs.google.com/spreadsheets/d/11pp1YavJsR6wnYcvs0Z6B94KM75clu7FQgRy7sdEQ4g/export?format=csv&gid=0"

@st.cache_data(ttl=600)
def load_dapot():
    try:
        df = pd.read_csv(SHEET_URL)
        return df
    except Exception as e:
        st.error(f"Gagal narik data Dapot. Error: {e}")
        return None

# --- SCRIPT CUSTOM UNTUK TAMPILIN TEKS SAAT ZOOM IN ---
class ZoomLabel(MacroElement):
    _template = Template("""
    {% macro script(this, kwargs) %}
    var map = {{ this._parent.get_name() }};
    map.on('zoomend', function() {
        var currentZoom = map.getZoom();
        var labels = document.getElementsByClassName('site-label');
        for (var i = 0; i < labels.length; i++) {
            // Teks muncul kalau level zoom 13 atau lebih dekat
            if (currentZoom >= 13) {
                labels[i].style.display = 'block';
            } else {
                labels[i].style.display = 'none';
            }
        }
    });
    // Trigger event saat pertama kali map diload
    map.fire('zoomend');
    {% endmacro %}
    """)

# --- UPLOAD SECTION ---
col_up1, col_up2 = st.columns([1, 2])
with col_up1:
    ume_file = st.file_uploader("Upload Data UME (fm-active.xlsx)", type=['xlsx'], label_visibility="collapsed")

with st.spinner('Menyiapkan data...'):
    df_dapot = load_dapot()

if df_dapot is not None and ume_file:
    try:
        df_ume = pd.read_excel(ume_file)
        
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
        
        # Dictionary Alarm
        if 'Occurrence Time' in df_down.columns:
            df_down['Alarm_Detail'] = "• " + df_down['Alarm Code Name'].astype(str) + " (" + df_down['Occurrence Time'].astype(str) + ")"
        else:
            df_down['Alarm_Detail'] = "• " + df_down['Alarm Code Name'].astype(str)
        
        alarm_dict = df_down.groupby('ME_CLEAN')['Alarm_Detail'].apply(lambda x: "<br>".join(x)).to_dict()
        site_down_list = df_down['ME_CLEAN'].dropna().unique()
        
        df_dapot['Status'] = df_dapot['NE_CLEAN'].apply(lambda x: 'Down' if x in site_down_list else 'Up')
        
        st.divider()

        # ==========================================
        # SPLIT SCREEN DASHBOARD
        # ==========================================
        col_stats, col_map = st.columns([1.5, 2.5]) # Porsi lebar disesuaikan biar tabelnya kebaca jelas
        
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
                df_dapot_down['Hub site'] = df_dapot_down['Hub site'].fillna('Non Hub')
                
                tab1, tab2, tab3, tab4 = st.tabs(["Kabupaten", "Kecamatan", "Hub Site", "Data Lengkap"])
                
                # Fungsi agregasi buat nampilin list site ID di tabel langsung
                with tab1:
                    kab_df = df_dapot_down.groupby('Kota/Kab').agg(Jumlah_Down=('Site_ID', 'count'), List_Site_ID=('Site_ID', lambda x: ', '.join(x))).reset_index()
                    st.dataframe(kab_df, height=450, use_container_width=True)
                with tab2:
                    kec_df = df_dapot_down.groupby('Kecamatan').agg(Jumlah_Down=('Site_ID', 'count'), List_Site_ID=('Site_ID', lambda x: ', '.join(x))).reset_index()
                    st.dataframe(kec_df, height=450, use_container_width=True)
                with tab3:
                    hub_df = df_dapot_down.groupby('Hub site').agg(Jumlah_Down=('Site_ID', 'count'), List_Site_ID=('Site_ID', lambda x: ', '.join(x))).reset_index()
                    st.dataframe(hub_df, height=450, use_container_width=True)
                with tab4:
                    st.dataframe(df_dapot_down[['Site_ID', 'Hub site', 'Site_Name', 'Kota/Kab', 'Kecamatan', 'LAT', 'LONG']], height=450, use_container_width=True)

        # --- KOLOM KANAN (MAPS) ---
        with col_map:
            st.subheader("📍 Peta Interaktif")
            
            if 'LAT' in df_dapot.columns and 'LONG' in df_dapot.columns:
                df_dapot['LAT'] = df_dapot['LAT'].astype(str).str.replace(',', '.').astype(float)
                df_dapot['LONG'] = df_dapot['LONG'].astype(str).str.replace(',', '.').astype(float)
                df_dapot = df_dapot.dropna(subset=['LAT', 'LONG'])
                
                m = folium.Map(location=[df_dapot['LAT'].mean(), df_dapot['LONG'].mean()], zoom_start=11)
                
                # Base Map Satelit
                folium.TileLayer(
                    tiles='https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
                    attr='Google',
                    name='Google Satellite',
                    overlay=False,
                    control=True
                ).add_to(m)
                
                # Eksekusi Macro JavaScript buat zoom teks
                m.add_child(ZoomLabel())
                
                for idx, row in df_dapot.iterrows():
                    lat, lon = row['LAT'], row['LONG']
                    site_id = row.get('Site_ID', 'Unknown')
                    ne_id = row.get('NE_CLEAN', 'Unknown')
                    site_name = row.get('Site_Name', 'Unknown')
                    status = row['Status']
                    
                    grid_type = row.get('Grid Category New', '-')
                    power_type = row.get('POWER TYPE', '-')
                    hub_val = str(row.get('Hub site', '')).strip()
                    hub_status = 'Non Hub' if not hub_val or hub_val.lower() == 'nan' else hub_val
                    is_hub = 'hub' in hub_status.lower() and 'non' not in hub_status.lower()
                    
                    color = 'red' if status == 'Down' else 'green'
                    
                    # Popup Custom (NE ID dihapus, Site Name di atas)
                    if status == 'Down':
                        alarms_terkait = alarm_dict.get(ne_id, "Tidak ada data historis")
                        popup_html = f"""
                        <div style="min-width: 250px; font-size:12px;">
                            <b style="font-size:14px;">{site_name}</b> <br>
                            Site ID: <b>{site_id}</b><br>
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
                            <b style="font-size:14px;">{site_name}</b><br>
                            Site ID: <b>{site_id}</b><br>
                            Status: <b style="color:green;">{status}</b><br>
                            <b>Tipe:</b> {hub_status} | <b>Power:</b> {power_type} | <b>Grid:</b> {grid_type}
                        </div>
                        """
                    
                    tooltip_text = f"{site_name} ({site_id})"
                    
                    # Tambah label gaib (class site-label) di kordinat yang sama, dikontrol oleh JS dari class ZoomLabel
                    label_html = f'<div class="site-label" style="display:none; font-size:9pt; font-weight:bold; color:{color}; text-shadow:1px 1px 2px white; white-space:nowrap; margin-left:12px; margin-top:-5px;">{site_id}</div>'
                    folium.Marker(
                        location=[lat, lon],
                        icon=folium.DivIcon(html=label_html)
                    ).add_to(m)

                    # Logic Hub = Bintang, Non-Hub = Bulat
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
                
                folium.LayerControl(position='topright').add_to(m)
                st_folium(m, use_container_width=True, height=600, returned_objects=[])
                
            else:
                st.error("Kolom 'LAT' dan 'LONG' tidak valid!")
                
    except Exception as e:
        st.error(f"Terdapat kesalahan saat memproses data: {e}")
