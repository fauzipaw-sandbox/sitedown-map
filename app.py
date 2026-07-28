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
        /* Buang semua ruang kosong, header, dan footer biar nge-fit 1 layar */
        .block-container { padding-top: 1rem; padding-bottom: 0rem; padding-left: 2rem; padding-right: 2rem; max-width: 100%; }
        header { visibility: hidden; }
        #MainMenu { visibility: hidden; }
        footer { visibility: hidden; }
        /* Rapikan jarak antar elemen */
        .stTabs [data-baseweb="tab-list"] { gap: 10px; }
        .st-emotion-cache-1y4p8pa { padding-top: 0rem; }
    </style>
""", unsafe_allow_html=True)

# --- 2. DIALOG POPUP UNTUK KLIK TABEL ---
@st.dialog("📋 Detail Site Down")
def show_detail_popup(kategori, nilai, df_down):
    st.markdown(f"Berikut adalah daftar site yang down pada **{kategori}: {nilai}**")
    detail_df = df_down[df_down[kategori] == nilai][['Site_ID', 'Site_Name', 'LAT', 'LONG']]
    st.dataframe(detail_df, use_container_width=True, hide_index=True)

# --- 3. FUNGSI TARIK DATA ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/11pp1YavJsR6wnYcvs0Z6B94KM75clu7FQgRy7sdEQ4g/export?format=csv&gid=0"

@st.cache_data(ttl=600)
def load_dapot():
    try:
        return pd.read_csv(SHEET_URL)
    except Exception as e:
        st.error(f"Gagal narik Dapot. Error: {e}")
        return None

# --- 4. JS MACRO UNTUK ZOOM LABEL ---
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

# --- 5. HEADER & UPLOAD SECTION (Dibuat sebaris) ---
col_title, col_upload = st.columns([2, 1])
with col_title:
    st.title("🗺️ Site Down Monitoring")
    st.markdown("Monitoring status Site (Up/Down) berdasarkan alarm UME.")
with col_upload:
    ume_file = st.file_uploader("Upload UME (fm-active.xlsx)", type=['xlsx'], label_visibility="collapsed")

with st.spinner('Menyiapkan data...'):
    df_dapot = load_dapot()

# --- 6. PROSES DATA & RENDER ---
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

        # ==========================================
        # SPLIT SCREEN DASHBOARD (KIRI & KANAN)
        # ==========================================
        col_stats, col_map = st.columns([1.5, 2.5]) 
        
        # --- KOLOM KIRI (SUMMARY & TABEL KLIKABLE) ---
        with col_stats:
            up_count = len(df_dapot[df_dapot['Status'] == 'Up'])
            down_count = len(df_dapot[df_dapot['Status'] == 'Down'])
            
            c1, c2 = st.columns(2)
            c1.success(f"✅ **Up:** {up_count}")
            c2.error(f"🚨 **Down:** {down_count}")
            
            if down_count > 0:
                df_dapot_down = df_dapot[df_dapot['Status'] == 'Down'].copy()
                df_dapot_down['Hub site'] = df_dapot_down['Hub site'].fillna('Non Hub')
                
                tab1, tab2, tab3 = st.tabs(["Kabupaten", "Kecamatan", "Hub Site"])
                st.caption("💡 *Klik baris pada tabel untuk melihat popup detail site.*")
                
                with tab1:
                    kab_df = df_dapot_down.groupby('Kota/Kab').size().reset_index(name='Jumlah Down')
                    # on_select="rerun" bikin tabel ini bisa diklik!
                    event_kab = st.dataframe(kab_df, height=350, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")
                    if len(event_kab.selection.rows) > 0:
                        selected_val = kab_df.iloc[event_kab.selection.rows[0]]['Kota/Kab']
                        show_detail_popup('Kota/Kab', selected_val, df_dapot_down)
                        
                with tab2:
                    kec_df = df_dapot_down.groupby('Kecamatan').size().reset_index(name='Jumlah Down')
                    event_kec = st.dataframe(kec_df, height=350, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")
                    if len(event_kec.selection.rows) > 0:
                        selected_val = kec_df.iloc[event_kec.selection.rows[0]]['Kecamatan']
                        show_detail_popup('Kecamatan', selected_val, df_dapot_down)
                        
                with tab3:
                    hub_df = df_dapot_down.groupby('Hub site').size().reset_index(name='Jumlah Down')
                    event_hub = st.dataframe(hub_df, height=350, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")
                    if len(event_hub.selection.rows) > 0:
                        selected_val = hub_df.iloc[event_hub.selection.rows[0]]['Hub site']
                        show_detail_popup('Hub site', selected_val, df_dapot_down)

        # --- KOLOM KANAN (MAPS) ---
        with col_map:
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
                    
                    # LABEL ZOOM-IN (Desain Pill/Badge Solid biar sangat mudah dibaca)
                    label_html = f'<div class="site-label" style="display:none; font-size:10px; font-weight:bold; color:#000; background-color:rgba(255,255,255,0.95); border:2px solid {color}; border-radius:5px; padding:2px 5px; box-shadow: 0px 2px 4px rgba(0,0,0,0.4); white-space:nowrap; margin-left:10px; margin-top:-8px;">{site_id}</div>'
                    
                    folium.Marker(
                        location=[lat, lon],
                        icon=folium.DivIcon(html=label_html)
                    ).add_to(m)

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
                
                # Height disesuaikan biar nggak melewati batas bawah layar laptop
                st_folium(m, use_container_width=True, height=520, returned_objects=[])
                
            else:
                st.error("Kolom 'LAT' dan 'LONG' tidak valid!")
                
    except Exception as e:
        st.error(f"Terdapat kesalahan saat memproses data: {e}")
