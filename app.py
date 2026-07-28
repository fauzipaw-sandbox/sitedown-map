import streamlit as st
import pandas as pd
import folium
from folium import MacroElement
from jinja2 import Template
from streamlit_folium import st_folium

# --- 1. KONFIGURASI LAYOUT 1 HALAMAN (NO SCROLL) ---
st.set_page_config(page_title="Site Down Monitoring", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
    <style>
        .block-container { padding-top: 1rem; padding-bottom: 0rem; padding-left: 2rem; padding-right: 2rem; max-width: 100%; }
        header { visibility: hidden; }
        #MainMenu { visibility: hidden; }
        footer { visibility: hidden; }
        .stTabs [data-baseweb="tab-list"] { gap: 10px; }
        .st-emotion-cache-1y4p8pa { padding-top: 0rem; }
        /* Memastikan class leaflet label kebal terhadap klik mouse */
        .leaflet-marker-icon.site-label-container { pointer-events: none !important; }
    </style>
""", unsafe_allow_html=True)

# --- 2. FUNGSI TARIK DATA ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/11pp1YavJsR6wnYcvs0Z6B94KM75clu7FQgRy7sdEQ4g/export?format=csv&gid=0"

@st.cache_data(ttl=600)
def load_dapot():
    try:
        return pd.read_csv(SHEET_URL)
    except Exception as e:
        st.error(f"Gagal narik Dapot. Error: {e}")
        return None

# --- 3. JS MACRO UNTUK ZOOM LABEL ---
class ZoomLabel(MacroElement):
    _template = Template("""
    {% macro script(this, kwargs) %}
    var map = {{ this._parent.get_name() }};
    map.on('zoomend', function() {
        var currentZoom = map.getZoom();
        var labels = document.getElementsByClassName('site-label');
        for (var i = 0; i < labels.length; i++) {
            if (currentZoom >= 13) {
                labels[i].style.display = 'block';
            } else {
                labels[i].style.display = 'none';
            }
        }
    });
    map.fire('zoomend');
    {% endmacro %}
    """)

# --- 4. HEADER & UPLOAD SECTION ---
col_title, col_upload = st.columns([2, 1])
with col_title:
    st.title("🗺️ Site Down Monitoring")
    st.markdown("Monitoring status Site (Up/Down) berdasarkan alarm UME.")
with col_upload:
    ume_file = st.file_uploader("Upload UME (fm-active.xlsx)", type=['xlsx'], label_visibility="collapsed")

with st.spinner('Menyiapkan data...'):
    df_dapot = load_dapot()

# --- 5. PROSES DATA & RENDER ---
if df_dapot is not None and ume_file:
    try:
        df_ume = pd.read_excel(ume_file)
        
        def clean_id(text):
            val = str(text).strip()
            return val[:-2] if val.endswith('.0') else val

        df_ume['ME_CLEAN'] = df_ume['ME ID'].apply(clean_id) if 'ME ID' in df_ume.columns else st.stop()
        df_dapot['NE_CLEAN'] = df_dapot['NE ID'].apply(clean_id) if 'NE ID' in df_dapot.columns else st.stop()

        # Normalisasi Case Kabupaten dan Kecamatan (Biar nyatu)
        if 'Kota/Kab' in df_dapot.columns:
            df_dapot['Kota/Kab'] = df_dapot['Kota/Kab'].apply(lambda x: str(x).title() if pd.notnull(x) else x)
        if 'Kecamatan' in df_dapot.columns:
            df_dapot['Kecamatan'] = df_dapot['Kecamatan'].apply(lambda x: str(x).title() if pd.notnull(x) else x)

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

        # ==========================================
        # SPLIT SCREEN DASHBOARD (KIRI & KANAN)
        # ==========================================
        col_stats, col_map = st.columns([1.5, 2.5]) 
        
        filter_col = None
        filter_val = None
        
        # --- KOLOM KIRI (SUMMARY & TABEL KLIKABLE) ---
        with col_stats:
            col_stat_text, col_stat_toggle = st.columns([2, 1])
            col_stat_text.subheader("📊 Summary Status")
            show_labels = col_stat_toggle.toggle("Show Site ID", value=True)
            
            up_count = len(df_dapot[df_dapot['Status'] == 'Up'])
            down_count = len(df_dapot[df_dapot['Status'] == 'Down'])
            
            c1, c2 = st.columns(2)
            c1.success(f"✅ **Up:** {up_count}")
            c2.error(f"🚨 **Down:** {down_count}")
            
            if down_count > 0:
                df_dapot_down = df_dapot[df_dapot['Status'] == 'Down'].copy()
                df_dapot_down['Hub site'] = df_dapot_down['Hub site'].fillna('Non Hub')
                
                tab1, tab2, tab3 = st.tabs(["Kabupaten", "Kecamatan", "Hub Site"])
                st.caption("💡 *Klik baris pada tabel untuk memfilter Map.*")
                
                with tab1:
                    kab_df = df_dapot_down.groupby('Kota/Kab').size().reset_index(name='Jumlah Down')
                    event_kab = st.dataframe(kab_df, height=300, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")
                    if len(event_kab.selection.rows) > 0:
                        filter_col = 'Kota/Kab'
                        filter_val = kab_df.iloc[event_kab.selection.rows[0]]['Kota/Kab']
                        
                with tab2:
                    kec_df = df_dapot_down.groupby('Kecamatan').size().reset_index(name='Jumlah Down')
                    event_kec = st.dataframe(kec_df, height=300, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")
                    if len(event_kec.selection.rows) > 0:
                        filter_col = 'Kecamatan'
                        filter_val = kec_df.iloc[event_kec.selection.rows[0]]['Kecamatan']
                        
                with tab3:
                    hub_df = df_dapot_down.groupby('Hub site').size().reset_index(name='Jumlah Down')
                    event_hub = st.dataframe(hub_df, height=300, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")
                    if len(event_hub.selection.rows) > 0:
                        filter_col = 'Hub site'
                        filter_val = hub_df.iloc[event_hub.selection.rows[0]]['Hub site']

        # --- KOLOM KANAN (MAPS) ---
        with col_map:
            # Terapkan Filter Peta kalau ada row yang diklik
            df_map = df_dapot.copy()
            if filter_col and filter_val:
                # Normalisasi data Hub site buat filter (mengubah NaN jadi 'Non Hub')
                if filter_col == 'Hub site':
                    df_map['Hub site'] = df_map['Hub site'].fillna('Non Hub')
                
                df_map = df_map[df_map[filter_col] == filter_val]
                st.info(f"📍 Menampilkan Peta Area **{filter_col}: {filter_val}** (Menampilkan Up & Down)")
            else:
                st.write("") # Spacer
            
            if 'LAT' in df_map.columns and 'LONG' in df_map.columns:
                df_map['LAT'] = df_map['LAT'].astype(str).str.replace(',', '.').astype(float)
                df_map['LONG'] = df_map['LONG'].astype(str).str.replace(',', '.').astype(float)
                df_map = df_map.dropna(subset=['LAT', 'LONG'])
                
                if not df_map.empty:
                    m = folium.Map(location=[df_map['LAT'].mean(), df_map['LONG'].mean()], zoom_start=10 if (filter_col and filter_val) else 9)
                    
                    folium.TileLayer(
                        tiles='https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
                        attr='Google',
                        name='Google Satellite',
                        overlay=False,
                        control=True
                    ).add_to(m)
                    
                    if show_labels:
                        m.add_child(ZoomLabel())
                    
                    for idx, row in df_map.iterrows():
                        lat, lon = row['LAT'], row['LONG']
                        site_id = row.get('Site_ID', 'Unknown')
                        ne_id = row.get('NE_CLEAN', 'Unknown')
                        site_name = row.get('Site_Name', 'Unknown')
                        site_class = row.get('SITE CLASS', row.get('Site_Class', '-'))
                        status = row['Status']
                        
                        grid_type = row.get('Grid Category New', '-')
                        power_type = row.get('POWER TYPE', '-')
                        hub_val = str(row.get('Hub site', '')).strip()
                        hub_status = 'Non Hub' if not hub_val or hub_val.lower() == 'nan' else hub_val
                        is_hub = 'hub' in hub_status.lower() and 'non' not in hub_status.lower()
                        
                        color = '#ff3333' if status == 'Down' else '#00cc44'
                        
                        if status == 'Down':
                            alarms_terkait = alarm_dict.get(ne_id, "Tidak ada data historis")
                            popup_html = f"""
                            <div style="min-width: 250px; font-size:12px;">
                                <b style="font-size:14px;">{site_name}</b> <br>
                                Site ID: <b>{site_id}</b><br>
                                Status: <b style="color:red;">{status}</b><br>
                                <b>Class:</b> {site_class} | <b>Tipe:</b> {hub_status}<br>
                                <b>Power:</b> {power_type} | <b>Grid:</b> {grid_type}
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
                                <b>Class:</b> {site_class} | <b>Tipe:</b> {hub_status}<br>
                                <b>Power:</b> {power_type} | <b>Grid:</b> {grid_type}
                            </div>
                            """
                        
                        tooltip_text = f"{site_name} ({site_id})"
                        
                        # LOGIC ICON CUSTOM (Garis Tepi Putih Tebal biar pop up di map satelit, gampang diklik!)
                        if is_hub:
                            icon_html = f'<div style="color:{color}; font-size:16px; text-shadow: -1px -1px 0 #FFF, 1px -1px 0 #FFF, -1px 1px 0 #FFF, 1px 1px 0 #FFF, 0px 0px 4px rgba(0,0,0,0.6);">★</div>'
                            folium.Marker(
                                location=[lat, lon],
                                icon=folium.DivIcon(html=icon_html, icon_size=(16, 16), icon_anchor=(8, 10)),
                                popup=folium.Popup(popup_html, max_width=400),
                                tooltip=tooltip_text
                            ).add_to(m)
                        else:
                            icon_html = f'<div style="width:10px; height:10px; background-color:{color}; border:2px solid white; border-radius:50%; box-shadow:0px 0px 3px rgba(0,0,0,0.6);"></div>'
                            folium.Marker(
                                location=[lat, lon],
                                icon=folium.DivIcon(html=icon_html, icon_size=(10, 10), icon_anchor=(5, 5)),
                                popup=folium.Popup(popup_html, max_width=400),
                                tooltip=tooltip_text
                            ).add_to(m)

                        # LABEL ZOOM-IN (Unbold, Kecil, ClassName ditambahin biar ga bentrok klik)
                        if show_labels:
                            label_html = f'<div class="site-label" style="display:none; font-size:9.5px; font-weight:normal; color:{color}; text-shadow: -1px -1px 0 #FFF, 1px -1px 0 #FFF, -1px 1px 0 #FFF, 1px 1px 0 #FFF, 0px 0px 3px #FFF; white-space:nowrap; margin-left:12px; margin-top:-5px;">{site_id}</div>'
                            folium.Marker(
                                location=[lat, lon],
                                icon=folium.DivIcon(html=label_html, class_name='site-label-container')
                            ).add_to(m)
                    
                    folium.LayerControl(position='topright').add_to(m)
                    
                    # Height disesuaikan
                    st_folium(m, use_container_width=True, height=520, returned_objects=[])
                else:
                    st.warning("Tidak ada data site (Up/Down) di area yang dipilih.")
            else:
                st.error("Kolom 'LAT' dan 'LONG' tidak valid!")
                
    except Exception as e:
        st.error(f"Terdapat kesalahan saat memproses data: {e}")
