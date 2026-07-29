import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from datetime import datetime
import math
from streamlit_gsheets import GSheetsConnection

# --- 1. KONFIGURASI LAYOUT ---
st.set_page_config(page_title="Site Down Monitoring", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
        .block-container { padding-top: 1rem; padding-bottom: 2rem; padding-left: 2rem; padding-right: 2rem; max-width: 100%; }
        header { visibility: hidden; }
        #MainMenu { visibility: hidden; }
        footer { visibility: hidden; }
        .stTabs [data-baseweb="tab-list"] { gap: 10px; }
        .st-emotion-cache-1y4p8pa { padding-top: 0rem; }
    </style>
""", unsafe_allow_html=True)

# --- 2. KONFIGURASI MASTER SPREADSHEET URL ---
# Link otomatis gue masukin sesuai yang lo kasih
MASTER_SHEET_URL = "https://docs.google.com/spreadsheets/d/11pp1YavJsR6wnYcvs0Z6B94KM75clu7FQgRy7sdEQ4g"

# Buka koneksi ke GSheets
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 3. FUNGSI JARAK (HAVERSINE) ---
def get_nearest_up_sites(lat, lon, df_up, k=2):
    if pd.isna(lat) or pd.isna(lon) or df_up.empty:
        return [], []
    def calc_dist(row):
        if pd.isna(row['LAT']) or pd.isna(row['LONG']): return float('inf')
        lat1, lon1, lat2, lon2 = map(math.radians, [lat, lon, row['LAT'], row['LONG']])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        return 6371 * c
    
    distances = df_up.apply(calc_dist, axis=1)
    closest_idx = distances.nsmallest(k).index
    closest = df_up.loc[closest_idx]
    return closest['Site_ID'].tolist(), closest['NE_CLEAN'].tolist()

# --- 4. SIDEBAR UNTUK UPLOAD & UPDATE DATA ---
with st.sidebar:
    st.header("⚙️ Update Data UME")
    st.markdown("Upload file UME terbaru di sini. Data akan disimpan utuh ke Google Sheets pada tab **All_Alarm**.")
    ume_file = st.file_uploader("Pilih file UME (Excel/CSV)", type=['xlsx', 'csv'])
    
    if ume_file:
        with st.spinner("⏳ Menyimpan seluruh data ke tab All_Alarm..."):
            try:
                if ume_file.name.endswith('.csv'):
                    df_new = pd.read_csv(ume_file)
                else:
                    df_new = pd.read_excel(ume_file)
                    
                if 'Occurrence Time' in df_new.columns:
                    df_new['Occurrence Time'] = df_new['Occurrence Time'].astype(str)
                
                conn.update(spreadsheet=MASTER_SHEET_URL, worksheet="All_Alarm", data=df_new)
                st.success("✅ Data berhasil disimpan utuh ke Google Sheets!")
                st.cache_data.clear() 
                st.rerun()
            except Exception as e:
                st.error(f"Gagal update data: {e}")

# --- 5. HEADER & LOAD DATA DARI KEDUA TAB ---
st.title("🗺️ Site Down Monitoring")
st.markdown("Monitoring status Site (Up/Down) berdasarkan alarm UME.")

with st.spinner('⏳ Sedang menyinkronkan data dari Google Sheets...'):
    try:
        # FIX ERROR SPASI: Pakai GID angka (432343053) pengganti nama "Data Site"
        df_dapot = conn.read(spreadsheet=MASTER_SHEET_URL, worksheet=432343053, ttl=600)
    except Exception as e:
        st.error(f"Gagal menarik tab Data Site: {e}")
        df_dapot = None
        
    try:
        # Nama "All_Alarm" nggak ada spasinya, jadi aman pakai string
        df_ume = conn.read(spreadsheet=MASTER_SHEET_URL, worksheet="All_Alarm", ttl=600)
    except Exception as e:
        df_ume = pd.DataFrame()

# --- 6. PROSES DATA DENGAN LOGIC DINAMIS ---
if df_dapot is not None:
    if df_ume.empty or len(df_ume) == 0:
        st.warning("⚠️ Database UME di tab 'All_Alarm' masih kosong. Silakan upload file terbaru melalui menu di sebelah kiri.")
    else:
        try:
            if 'Occurrence Time' in df_ume.columns:
                latest_time = pd.to_datetime(df_ume['Occurrence Time'], errors='coerce').max()
                last_update_str = latest_time.strftime("%d-%m-%Y %H:%M:%S") if pd.notnull(latest_time) else "Tidak diketahui"
            else:
                last_update_str = "Tidak diketahui"
                
            st.info(f"🕒 **Data Update Terakhir (Berdasarkan Alarm):** {last_update_str}")
            
            def clean_id(text):
                val = str(text).strip()
                return val[:-2] if val.endswith('.0') else val

            def get_6digit_id(text):
                try:
                    val = str(text).strip()
                    if val.endswith('.0'): val = val[:-2]
                    if val.upper().startswith('C_') or val.upper().startswith('N_'):
                        return val[2:8].upper()
                    else:
                        return val[:6].upper()
                except:
                    return str(text)

            if 'ME ID' in df_ume.columns:
                df_ume['ME_CLEAN'] = df_ume['ME ID'].apply(clean_id)
            elif 'Site Name(Office)' in df_ume.columns:
                df_ume['ME_CLEAN'] = df_ume['Site Name(Office)'].apply(get_6digit_id)
            else:
                st.error("Kolom 'ME ID' atau 'Site Name(Office)' tidak ditemukan di tab All_Alarm!")
                st.stop()
                
            if 'NE ID' in df_dapot.columns:
                df_dapot['NE_CLEAN'] = df_dapot['NE ID'].apply(clean_id)
            elif 'Site_ID' in df_dapot.columns:
                df_dapot['NE_CLEAN'] = df_dapot['Site_ID'].apply(clean_id)
            else:
                st.error("Kolom 'NE ID' atau 'Site_ID' tidak ditemukan di tab Data Site!")
                st.stop()

            if 'LAT' in df_dapot.columns and 'LONG' in df_dapot.columns:
                df_dapot['LAT'] = df_dapot['LAT'].astype(str).str.replace(',', '.').astype(float)
                df_dapot['LONG'] = df_dapot['LONG'].astype(str).str.replace(',', '.').astype(float)

            for col in ['Kota/Kab', 'Kecamatan']:
                if col in df_dapot.columns:
                    df_dapot[col] = df_dapot[col].apply(lambda x: str(x).title() if pd.notnull(x) else x)
            if 'Hub site' in df_dapot.columns:
                df_dapot['Hub site'] = df_dapot['Hub site'].fillna('Non Hub')

            if 'Occurrence Time' in df_ume.columns and 'Alarm Code Name' in df_ume.columns:
                df_ume['Alarm_Detail'] = "• " + df_ume['Alarm Code Name'].astype(str) + " (" + df_ume['Occurrence Time'].astype(str) + ")"
            elif 'Alarm Code Name' in df_ume.columns:
                df_ume['Alarm_Detail'] = "• " + df_ume['Alarm Code Name'].astype(str)
            else:
                df_ume['Alarm_Detail'] = "• Unknown Alarm"
            
            all_alarm_dict = df_ume.groupby('ME_CLEAN')['Alarm_Detail'].apply(lambda x: "<br>".join(x)).to_dict()

            if 'Position' in df_ume.columns and 'Specific Problem' in df_ume.columns:
                cond_power = (df_ume['Alarm Code Name'].str.contains('Input power-off', case=False, na=False)) & \
                             (df_ume['Position'].astype(str).str.strip() == 'Equipment=1')
                cond_link1 = (df_ume['Specific Problem'].str.contains('The link between the server and the ME is broken', case=False, na=False)) | \
                             (df_ume['Alarm Code Name'].str.contains('The link between the server and the ME is broken', case=False, na=False))
                cond_link2 = (df_ume['Specific Problem'].str.contains('Site Abis control link broken', case=False, na=False)) | \
                             (df_ume['Alarm Code Name'].str.contains('Site Abis control link broken', case=False, na=False))
            else:
                cond_power = df_ume['Alarm Code Name'].str.contains('Input power-off', case=False, na=False)
                cond_link1 = df_ume['Alarm Code Name'].str.contains('The link between the server and the ME is broken', case=False, na=False)
                cond_link2 = df_ume['Alarm Code Name'].str.contains('Site Abis control link broken', case=False, na=False)
            
            df_down = df_ume[cond_power | cond_link1 | cond_link2].copy()
            
            if 'Occurrence Time' in df_down.columns:
                df_down['Occurrence_DT'] = pd.to_datetime(df_down['Occurrence Time'], errors='coerce')
                min_occurrence = df_down.groupby('ME_CLEAN')['Occurrence_DT'].min()
            else:
                min_occurrence = pd.Series(dtype='datetime64[ns]')

            site_down_list = df_down['ME_CLEAN'].dropna().unique()
            df_dapot['Status'] = df_dapot['NE_CLEAN'].apply(lambda x: 'Down' if x in site_down_list else 'Up')

            df_up_all = df_dapot[(df_dapot['Status'] == 'Up') & df_dapot['LAT'].notna() & df_dapot['LONG'].notna()]
            suggestion_site_ids = {}
            suggested_up_ids = set()
            
            for idx, row in df_dapot[df_dapot['Status'] == 'Down'].iterrows():
                site_ids, ne_cleans = get_nearest_up_sites(row['LAT'], row['LONG'], df_up_all, k=2)
                suggestion_site_ids[row['NE_CLEAN']] = site_ids if site_ids else ["-"]
                suggested_up_ids.update(ne_cleans)

            def format_durasi(start_time):
                if pd.isnull(start_time): return "-"
                now_wib = pd.Timestamp.now(tz='Asia/Jakarta').tz_localize(None)
                delta = now_wib - start_time
                total_seconds = int(delta.total_seconds())
                if total_seconds < 0: return "0m"
                days, remainder = divmod(total_seconds, 86400)
                hours, remainder = divmod(remainder, 3600)
                minutes, _ = divmod(remainder, 60)
                res = []
                if days > 0: res.append(f"{days}h")
                if hours > 0: res.append(f"{hours}j")
                res.append(f"{minutes}m")
                return " ".join(res)
                
            def get_summary_table(col_name):
                if col_name not in df_dapot.columns: return pd.DataFrame()
                summary = pd.crosstab(df_dapot[col_name], df_dapot['Status']).reset_index()
                for s in ['Up', 'Down']:
                    if s not in summary.columns: summary[s] = 0
                summary = summary.rename(columns={'Down': 'Jumlah Down', 'Up': 'Jumlah Up'})
                summary['Total'] = summary['Jumlah Down'] + summary['Jumlah Up']
                summary['% Down'] = (summary['Jumlah Down'] / summary['Total'] * 100).round(1).astype(str) + '%'
                summary['% Up'] = (summary['Jumlah Up'] / summary['Total'] * 100).round(1).astype(str) + '%'
                return summary.sort_values('Jumlah Down', ascending=False).set_index(col_name)[['Jumlah Down', 'Jumlah Up', '% Down', '% Up', 'Total']]

            # ==========================================
            # LAYOUT: STATS (KIRI) & MAPS (KANAN)
            # ==========================================
            col_stats, col_map = st.columns([1.5, 2.5]) 
            
            filter_col = None
            filter_val = None
            
            with col_stats:
                col_stat_text, col_stat_toggle1, col_stat_toggle2 = st.columns([2, 1, 1])
                col_stat_text.subheader("📊 Summary")
                show_labels = col_stat_toggle1.toggle("Show Site ID", value=False)
                show_legend = col_stat_toggle2.toggle("Show Legend", value=True)
                
                up_count = len(df_dapot[df_dapot['Status'] == 'Up'])
                down_count = len(df_dapot[df_dapot['Status'] == 'Down'])
                
                c1, c2 = st.columns(2)
                c1.success(f"✅ **Up:** {up_count}")
                c2.error(f"🚨 **Down:** {down_count}")
                
                tab1, tab2, tab3 = st.tabs(["Kabupaten", "Kecamatan", "Hub/Non Hubsite"])
                
                with tab1:
                    kab_df = get_summary_table('Kota/Kab')
                    event_kab = st.dataframe(kab_df, height=300, use_container_width=True, on_select="rerun", selection_mode="single-row")
                    if len(event_kab.selection.rows) > 0:
                        filter_col = 'Kota/Kab'
                        filter_val = kab_df.index[event_kab.selection.rows[0]]
                        
                with tab2:
                    kec_df = get_summary_table('Kecamatan')
                    event_kec = st.dataframe(kec_df, height=300, use_container_width=True, on_select="rerun", selection_mode="single-row")
                    if len(event_kec.selection.rows) > 0:
                        filter_col = 'Kecamatan'
                        filter_val = kec_df.index[event_kec.selection.rows[0]]
                        
                with tab3:
                    hub_df = get_summary_table('Hub site')
                    event_hub = st.dataframe(hub_df, height=300, use_container_width=True, on_select="rerun", selection_mode="single-row")
                    if len(event_hub.selection.rows) > 0:
                        filter_col = 'Hub site'
                        filter_val = hub_df.index[event_hub.selection.rows[0]]

            with col_map:
                df_map = df_dapot.copy()
                if filter_col and filter_val:
                    df_map = df_map[df_map[filter_col] == filter_val]
                    st.info(f"📍 Menampilkan Area **{filter_col}: {filter_val}**")
                else:
                    st.write("") 
                
                if 'LAT' in df_map.columns and 'LONG' in df_map.columns:
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
                        
                        if show_legend:
                            legend_html = '''
                            <div style="position: fixed; 
                                        bottom: 20px; left: 20px; width: 190px; height: 120px; 
                                        border:2px solid grey; z-index:9999; font-size:12px; color:black;
                                        background-color:white; padding: 10px; border-radius: 5px; opacity: 0.95;">
                            <b style="color:black;">Map Legend</b><br>
                            <i style="background:#e60000; width: 12px; height: 12px; float: left; margin-right: 8px; margin-top: 3px; border-radius: 50%;"></i> <span style="color:black;">Down</span><br>
                            <i style="background:#00802b; width: 12px; height: 12px; float: left; margin-right: 8px; margin-top: 3px; border-radius: 50%;"></i> <span style="color:black;">Up</span><br>
                            <i style="background:#0066ff; width: 12px; height: 12px; float: left; margin-right: 8px; margin-top: 3px; border-radius: 50%;"></i> <span style="color:black;">Neighbour to optim</span><br>
                            <div style="color:#444; font-size:16px; float:left; margin-right:7px; margin-top:-3px; margin-left:-2px;">★</div> <span style="color:black;">Hub site</span><br>
                            </div>
                            '''
                            m.get_root().html.add_child(folium.Element(legend_html))
                        
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
                            
                            if status == 'Down':
                                color_hex = '#e60000'
                                status_label = '<b style="color:red;">Down</b>'
                            else:
                                if ne_id in suggested_up_ids:
                                    color_hex = '#0066ff'
                                    status_label = '<b style="color:#0066ff;">Up (Suggested to Optim)</b>'
                                else:
                                    color_hex = '#00802b'
                                    status_label = '<b style="color:green;">Up</b>'

                            alarms_terkait = all_alarm_dict.get(ne_id, "<i style='color:gray;'>Tidak ada alarm aktif</i>")
                            start_dt = min_occurrence.get(ne_id) if status == 'Down' else None
                            durasi_str = f" (Durasi: {format_durasi(start_dt)})" if status == 'Down' else ""
                            
                            html_detail = f"""
                            <div style="width: 250px; font-size:12px; color:black; white-space: normal; line-height: 1.4;">
                                <b style="font-size:14px;">{site_name}</b> <br>
                                Site ID: <b>{site_id}</b><br>
                                Status: {status_label}{durasi_str}<br>
                                <b>Class:</b> {site_class} | <b>Tipe:</b> {hub_status}<br>
                                <b>Power:</b> {power_type} | <b>Grid:</b> {grid_type}
                                <hr style="margin: 5px 0;">
                                <b style="font-size:11px;">Daftar Alarm Terdeteksi:</b><br>
                                <div style="font-size:10px; max-height:120px; overflow-y:auto; background-color:#f1f1f1; padding:5px; border-radius:4px;">
                                    {alarms_terkait}
                                </div>
                            </div>
                            """
                            
                            if is_hub:
                                shape_html = f'<div style="color:{color_hex}; font-size:18px; margin-top:-4px; margin-left:-2px; text-shadow: -1px -1px 0 #FFF, 1px -1px 0 #FFF, -1px 1px 0 #FFF, 1px 1px 0 #FFF, 0px 0px 4px rgba(0,0,0,0.6);">★</div>'
                            else:
                                shape_html = f'<div style="width:12px; height:12px; background-color:{color_hex}; border:2px solid white; border-radius:50%; box-shadow:0px 0px 3px rgba(0,0,0,0.6);"></div>'
                                
                            if show_labels:
                                label_html = f'<div class="site-label" style="position:absolute; left:14px; top:-2px; pointer-events:none; font-size:10px; font-weight:bold; color:{color_hex}; text-shadow: -1px -1px 0 #FFF, 1px -1px 0 #FFF, -1px 1px 0 #FFF, 1px 1px 0 #FFF, 0px 0px 3px #FFF; white-space:nowrap;">{site_id}</div>'
                            else:
                                label_html = ""
                                
                            combined_html = f'<div style="position:relative; width:12px; height:12px; cursor:pointer;">{shape_html}{label_html}</div>'

                            folium.Marker(
                                location=[lat, lon],
                                icon=folium.DivIcon(html=combined_html, icon_size=(12, 12), icon_anchor=(6, 6)),
                                tooltip=folium.Tooltip(html_detail)
                            ).add_to(m)
                        
                        folium.LayerControl(position='topright').add_to(m)
                        st_folium(m, use_container_width=True, height=520, returned_objects=[])
                    else:
                        st.warning("Tidak ada data site (Up/Down) di area yang dipilih.")

            # ==========================================
            # LAYOUT BAWAH: TABEL DETAIL SITE
            # ==========================================
            st.divider()
            st.subheader("📋 Detail Site Down")
            
            df_dapot_down = df_dapot[df_dapot['Status'] == 'Down'].copy()
            
            if filter_col and filter_val:
                df_dapot_down = df_dapot_down[df_dapot_down[filter_col] == filter_val]
            
            if not df_dapot_down.empty:
                df_dapot_down['Occurrence_Time'] = df_dapot_down['NE_CLEAN'].map(min_occurrence)
                df_dapot_down = df_dapot_down.sort_values(by='Occurrence_Time', ascending=True, na_position='last')
                df_dapot_down['Durasi Down'] = df_dapot_down['Occurrence_Time'].apply(format_durasi)
                
                df_dapot_down['Suggestion (Nearest Up)'] = df_dapot_down['NE_CLEAN'].map(suggestion_site_ids)
                df_dapot_down = df_dapot_down.explode('Suggestion (Nearest Up)')
                
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
                    'Durasi Down': 'Durasi Down',
                    'Suggestion (Nearest Up)': 'Suggestion'
                }
                
                kolom_ada = [k for k in kolom_detail.keys() if k in df_dapot_down.columns]
                df_detail_final = df_dapot_down[kolom_ada].rename(columns=kolom_detail)
                
                if 'Site ID' in df_detail_final.columns:
                    df_detail_final = df_detail_final.set_index('Site ID')
                    
                st.dataframe(df_detail_final, height=350, use_container_width=True)
            else:
                st.info("🎉 Keren! Tidak ada site yang Down saat ini.")
                    
        except Exception as e:
            st.error(f"Terdapat kesalahan saat memproses data UME: {e}")
