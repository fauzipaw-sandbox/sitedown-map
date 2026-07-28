import streamlit as st
import pandas as pd
import folium
from folium import MacroElement
from jinja2 import Template
from streamlit_folium import st_folium
from datetime import datetime

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

        if 'Kota/Kab' in df_dapot.columns:
            df_dapot['Kota/Kab'] = df_dapot['Kota/Kab'].apply(lambda x: str(x).title() if pd.notnull(x) else x)
        if 'Kecamatan' in df_dapot.columns:
            df_dapot['Kecamatan'] = df_dapot['Kecamatan'].apply(lambda x: str(x).title() if pd.notnull(x) else x)
            
        if 'Hub site' in df_dapot.columns:
            df_dapot['Hub site'] = df_dapot['Hub site'].fillna('Non Hub')

        # Rule Down Strict
        cond_power = (df_ume['Alarm Code Name'].str.contains('Input power-off', case=False, na=False)) & \
                     (df_ume['Position'].astype(str).str.strip() == 'Equipment=1')
                     
        cond_link1 = (df_ume['Specific Problem'].str.contains('The link between the server and the ME is broken', case=False, na=False)) | \
                     (df_ume['Alarm Code Name'].str.contains('The link between the server and the ME is broken', case=False, na=False))
        
        cond_link2 = (df_ume['Specific Problem'].str.contains('Site Abis control link broken', case=False, na=False)) | \
                     (df_ume['Alarm Code Name'].str.contains('Site Abis control link broken', case=False, na=False))
        
        df_down = df_ume[cond_power | cond_link1 | cond_link2].copy()
        
        # Konversi ke Datetime
        if 'Occurrence Time' in df_down.columns:
            df_down['Occurrence_DT'] = pd.to_datetime(df_down['Occurrence Time'], errors='coerce')
            min_occurrence = df_down.groupby('ME_CLEAN')['Occurrence_DT'].min()
        else:
            min_occurrence = pd.Series(dtype='datetime64[ns]')

        if 'Occurrence Time' in df_down.columns:
            df_down['Alarm_Detail'] = "• " + df_down['Alarm Code Name'].astype(str) + " (" + df_down['Occurrence Time'].astype(str) + ")"
        else:
            df_down['Alarm_Detail'] = "• " + df_down['Alarm Code Name'].astype(str)
        
        alarm_dict = df_down.groupby('ME_CLEAN')['Alarm_Detail'].apply(lambda x: "<br>".join(x)).to_dict()
        site_down_list = df_down['ME_CLEAN'].dropna().unique()
        
        df_dapot['Status'] = df_dapot['NE_CLEAN'].apply(lambda x: 'Down' if x in site_down_list else 'Up')

        # --- FIX: Durasi ditarik pakai Timezone WIB biar ga minus kalau server UTC ---
        def format_durasi(start_time):
            if pd.isnull(start_time):
                return "-"
            # Paksa waktu sekarang pakai WIB (Asia/Jakarta) terus hapus info timezone-nya biar sejalan sama data Excel
            now_wib = pd.Timestamp.now(tz='Asia/Jakarta').tz_localize(None)
            delta = now_wib - start_time
            total_seconds = int(delta.total_seconds())
            
            if total_seconds < 0: return "0m" # Kalau masih aneh, tetep diamankan
            
            days, remainder = divmod(total_seconds, 86400)
            hours, remainder = divmod(remainder, 3600)
            minutes, _ = divmod(remainder, 60)
            
            res = []
            if days > 0: res.append(f"{days}h")
            if hours > 0: res.append(f"{hours}j")
            res.append(f"{minutes}m")
            return " ".join(res)
            
        # --- FIX: Ditambah presentase dan Total di tabel summary ---
        def get_summary_table(col_name):
            if col_name not in df_dapot.columns: return pd.DataFrame()
            summary = pd.crosstab(df_dapot[col_name], df_dapot['Status']).reset_index()
            for s in ['Up', 'Down']:
                if s not in summary.columns: summary[s] = 0
            summary = summary.rename(columns={'Down': 'Jumlah Down', 'Up': 'Jumlah Up'})
            
            # Hitung Total dan Persentase
            summary['Total'] = summary['Jumlah Down'] + summary['Jumlah Up']
            summary['% Down'] = (summary['Jumlah Down'] / summary['Total'] * 100).round(1).astype(str) + '%'
            summary['% Up'] = (summary['Jumlah Up'] / summary['Total'] * 100).round(1).astype(str) + '%'
            
            # Urutkan berdasarkan Jumlah Down terbanyak
            return summary.sort_values('Jumlah Down', ascending=False)[[col_name, 'Jumlah Down', 'Jumlah Up', '% Down', '% Up', 'Total']]

        # ==========================================
        # SPLIT SCREEN DASHBOARD
        # ==========================================
        col_stats, col_map = st.columns([1.5, 2.5]) 
        
        filter_col = None
        filter_val = None
        
        # --- KOLOM KIRI (SUMMARY & TABEL) ---
        with col_stats:
            col_stat_text, col_stat_toggle = st.columns([2, 1])
            col_stat_text.subheader("📊 Summary Status")
            show_labels = col_stat_toggle.toggle("Show Site ID", value=True)
            
            up_count = len(df_dapot[df_dapot['Status'] == 'Up'])
            down_count = len(df_dapot[df_dapot['Status'] == 'Down'])
            
            c1, c2 = st.columns(2)
            c1.success(f"✅ **Up:** {up_count}")
            c2.error(f"🚨 **Down:** {down_count}")
            
            tab1, tab2, tab3, tab4 = st.tabs(["Kabupaten", "Kecamatan", "Hub/Non Hubsite", "Sites"])
            
            with tab1:
                kab_df = get_summary_table('Kota/Kab')
                event_kab = st.dataframe(kab_df, height=300, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")
                if len(event_kab.selection.rows) > 0:
                    filter_col = 'Kota/Kab'
                    filter_val = kab_df.iloc[event_kab.selection.rows[0]]['Kota/Kab']
                    
            with tab2:
                kec_df = get_summary_table('Kecamatan')
                event_kec = st.dataframe(kec_df, height=300, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")
                if len(event_kec.selection.rows) > 0:
                    filter_col = 'Kecamatan'
                    filter_val = kec_df.iloc[event_kec.selection.rows[0]]['Kecamatan']
                    
            with tab3:
                hub_df = get_summary_table('Hub site')
                event_hub = st.dataframe(hub_df, height=300, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")
                if len(event_hub.selection.rows) > 0:
                    filter_col = 'Hub site'
                    filter_val = hub_df.iloc[event_hub.selection.rows[0]]['Hub site']
            
            with tab4:
                df_dapot_down = df_dapot[df_dapot['Status'] == 'Down'].copy()
                
                if not df_dapot_down.empty:
                    df_dapot_down['Occurrence_Time'] = df_dapot_down['NE_CLEAN'].map(min_occurrence)
                    df_dapot_down = df_dapot_down.sort_values(by='Occurrence_Time', ascending=True, na_position='last')
                    df_dapot_down['Durasi Down'] = df_dapot_down['Occurrence_Time'].apply(format_durasi)
                    
                    kolom_detail = {
                        'Site_ID': 'Site ID',
                        'Site_Name': 'Site Name',
                        'SITE CLASS': 'Site Class',
                        'Kota/Kab': 'Kabupaten',
                        'Kecamatan': 'Kecamatan',
                        'POWER TYPE': 'Tipe Power',
                        'Grid Category New': 'Grid',
                        'Hub site': 'Hub/Non Hub',
                        'Simpul 4G': 'Simpul 4G',
                        'Durasi Down': 'Durasi Down'
                    }
                    
                    kolom_ada = [k for k in kolom_detail.keys() if k in df_dapot_down.columns]
                    df_detail_final = df_dapot_down[kolom_ada].rename(columns=kolom_detail)
                    st.dataframe(df_detail_final, height=300, use_container_width=True, hide_index=True)
                else:
                    st.info("🎉 Keren! Tidak ada site yang Down saat ini.")

        # --- KOLOM KANAN (MAPS) ---
        with col_map:
            df_map = df_dapot.copy()
            if filter_col and filter_val:
                df_map = df_map[df_map[filter_col] == filter_val]
                st.info(f"📍 Menampilkan Area **{filter_col}: {filter_val}** (Up & Down)")
            else:
                st.write("") 
            
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
                        
                        color_hex = '#e60000' if status == 'Down' else '#00802b'
                        
                        if status == 'Down':
                            alarms_terkait = alarm_dict.get(ne_id, "Tidak ada data historis")
                            start_dt = min_occurrence.get(ne_id)
                            durasi_str = format_durasi(start_dt)
                            
                            popup_html = f"""
                            <div style="min-width: 250px; font-size:12px;">
                                <b style="font-size:14px;">{site_name}</b> <br>
                                Site ID: <b>{site_id}</b><br>
                                Status: <b style="color:red;">{status}</b> (Durasi: {durasi_str})<br>
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
                        
                        if is_hub:
                            shape_html = f'<div style="color:{color_hex}; font-size:18px; margin-top:-4px; margin-left:-2px; text-shadow: -1px -1px 0 #FFF, 1px -1px 0 #FFF, -1px 1px 0 #FFF, 1px 1px 0 #FFF, 0px 0px 4px rgba(0,0,0,0.6);">★</div>'
                        else:
                            shape_html = f'<div style="width:12px; height:12px; background-color:{color_hex}; border:2px solid white; border-radius:50%; box-shadow:0px 0px 3px rgba(0,0,0,0.6);"></div>'
                            
                        if show_labels:
                            label_html = f'<div class="site-label" style="display:none; position:absolute; left:14px; top:-2px; pointer-events:none; font-size:10px; font-weight:normal; color:{color_hex}; text-shadow: -1px -1px 0 #FFF, 1px -1px 0 #FFF, -1px 1px 0 #FFF, 1px 1px 0 #FFF, 0px 0px 3px #FFF; white-space:nowrap;">{site_id}</div>'
                        else:
                            label_html = ""
                            
                        combined_html = f'<div style="position:relative; width:12px; height:12px; cursor:pointer;">{shape_html}{label_html}</div>'

                        folium.Marker(
                            location=[lat, lon],
                            icon=folium.DivIcon(html=combined_html, icon_size=(12, 12), icon_anchor=(6, 6)),
                            popup=folium.Popup(popup_html, max_width=400),
                            tooltip=tooltip_text
                        ).add_to(m)
                    
                    folium.LayerControl(position='topright').add_to(m)
                    st_folium(m, use_container_width=True, height=520, returned_objects=[])
                else:
                    st.warning("Tidak ada data site (Up/Down) di area yang dipilih.")
            else:
                st.error("Kolom 'LAT' dan 'LONG' tidak valid!")
                
    except Exception as e:
        st.error(f"Terdapat kesalahan saat memproses data: {e}")
