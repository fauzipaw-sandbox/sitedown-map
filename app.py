import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from datetime import datetime
import math
from streamlit_gsheets import GSheetsConnection

# --- 1. KONFIGURASI LAYOUT ---
st.set_page_config(page_title="Site Down Monitoring Kalimantan (ZTE Only)", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
    <style>
        .block-container { padding-top: 1.5rem; padding-bottom: 2rem; padding-left: 2rem; padding-right: 2rem; max-width: 100%; }
        header { visibility: hidden; }
        #MainMenu { visibility: hidden; }
        footer { visibility: hidden; }
        .stTabs [data-baseweb="tab-list"] { gap: 8px; }
        .st-emotion-cache-1y4p8pa { padding-top: 0rem; }
        .update-info { text-align: right; font-size: 13px; color: #555; margin-bottom: 8px; }
    </style>
""", unsafe_allow_html=True)

# --- 2. KONFIGURASI MASTER SPREADSHEET URL ---
MASTER_SHEET_URL = "https://docs.google.com/spreadsheets/d/11pp1YavJsR6wnYcvs0Z6B94KM75clu7FQgRy7sdEQ4g"

# --- 3. MASTER KOLOM UME ---
KOLOM_MASTER = [
    'Alarm ID', 'ME ID', 'Site Name(Office)', 'Alarm Code Name', 
    'Occurrence Time', 'Position', 'Specific Problem', 'Location'
]

# --- 4. FUNGSI UTILITIES & KALKULASI ---
def get_nearest_up_sites(lat, lon, df_up, k=2):
    if pd.isna(lat) or pd.isna(lon) or df_up.empty:
        return [], []
    def calc_dist(row):
        if pd.isna(row['LAT']) or pd.isna(row['LONG']): return float('inf')
        lat1, lon1, lat2, lon2 = map(math.radians, [lat, lon, row['LAT'], row['LONG']])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        a = max(0.0, min(1.0, a))
        c = 2 * math.asin(math.sqrt(a))
        return 6371 * c
    
    distances = df_up.apply(calc_dist, axis=1)
    closest_idx = distances.nsmallest(k).index
    closest = df_up.loc[closest_idx]
    return closest['Site_ID'].tolist(), closest['NE_CLEAN'].tolist()

def find_col(df, possible_names):
    df_cols_clean = {c.strip().lower(): c for c in df.columns}
    for name in possible_names:
        clean_name = name.strip().lower()
        if clean_name in df_cols_clean:
            return df_cols_clean[clean_name]
    return None

def clean_id(text):
    if pd.isna(text): return ""
    val = str(text).strip()
    if val.lower() in ['nan', 'none', 'null', '']: return ""
    return val[:-2] if val.endswith('.0') else val

def get_6digit_id(text):
    if pd.isna(text): return ""
    try:
        val = str(text).strip()
        if val.lower() in ['nan', 'none', 'null', '']: return ""
        if val.endswith('.0'): val = val[:-2]
        if val.upper().startswith('C_') or val.upper().startswith('N_'):
            return val[2:8].upper()
        else:
            return val[:6].upper()
    except:
        return str(text)

conn = st.connection("gsheets", type=GSheetsConnection)

# --- 5. TARIK DATA DARI DATABASE ---
with st.spinner('⏳ Sedang menyinkronkan data dengan sistem...'):
    try:
        df_dapot = conn.read(spreadsheet=MASTER_SHEET_URL, worksheet=1, sql="SELECT *", ttl=300)
    except Exception as e:
        st.error(f"Gagal menarik data site: {e}")
        df_dapot = None
        
    try:
        df_ume = conn.read(spreadsheet=MASTER_SHEET_URL, worksheet=0, sql="SELECT *", ttl=300)
    except Exception as e:
        st.error(f"Gagal menarik data alarm: {e}")
        df_ume = pd.DataFrame()

if df_ume is not None and not df_ume.empty and 'Occurrence Time' in df_ume.columns:
    latest_time = pd.to_datetime(df_ume['Occurrence Time'], errors='coerce').max()
    last_update_str = latest_time.strftime("%d-%m-%Y %H:%M:%S") if pd.notnull(latest_time) else "Tidak diketahui"
else:
    last_update_str = "Belum Ada Data"

# --- 6. HEADER & EXPANDER UPDATE UTAMA ---
col_title, col_header_right = st.columns([2.5, 1])

with col_title:
    st.title("🗺️ Site Down Monitoring Kalimantan (ZTE Only)")

with col_header_right:
    st.markdown(f"<div class='update-info'>Pembaruan Data Terakhir:<br><b style='color:#1a73e8;'>{last_update_str}</b></div>", unsafe_allow_html=True)
    with st.popover("⚙️ KLIK DI SINI UNTUK UPDATE DATA", use_container_width=True):
        st.markdown("""
        **Cara Update Data Alarm:**
        1. Login ke UME ZTE ([klik di sini](https://10.40.48.9:28001/uportal/framework/default.html#/home))
        2. Pilih menu **Alarm Management > Active Alarm > Alarm Monitor > Klik Export > Export All**
        3. Drag n Drop isi filenya di sini, dan tunggu beberapa saat
        """)
        ume_file_top = st.file_uploader("Pilih file (Excel/CSV)", type=['xlsx', 'csv'], label_visibility="collapsed")
        
        if st.button("🔄 Reload Data / Clear Cache", use_container_width=True, type="primary"):
            st.cache_data.clear()
            conn.reset()
            st.rerun()
            
        if ume_file_top:
            if "last_uploaded" not in st.session_state or st.session_state["last_uploaded"] != ume_file_top.name:
                with st.spinner("Menyimpan data..."):
                    try:
                        df_new = pd.read_csv(ume_file_top) if ume_file_top.name.endswith('.csv') else pd.read_excel(ume_file_top)
                        valid_cols = [c for c in KOLOM_MASTER if c in df_new.columns]
                        if valid_cols: df_new = df_new[valid_cols]
                        df_new = df_new.dropna(how='all')
                        if 'Occurrence Time' in df_new.columns:
                            df_new['Occurrence Time'] = df_new['Occurrence Time'].astype(str)
                        conn.update(spreadsheet=MASTER_SHEET_URL, worksheet=0, data=df_new)
                        st.cache_data.clear()
                        conn.reset() 
                        st.session_state["last_uploaded"] = ume_file_top.name
                        st.success("✅ Berhasil. Klik Reload Data.")
                    except Exception as e:
                        st.error(f"Gagal: {e}")

st.markdown("<hr style='margin: 0px 0px 15px 0px;'/>", unsafe_allow_html=True)

# --- 7. PROSES DATA & RENDER DASHBOARD ---
if df_dapot is not None:
    if df_ume.empty or len(df_ume) == 0:
        st.warning("⚠️ **Database alarm masih kosong atau belum dimuat!** Silakan unggah data alarm pada menu di pojok kanan atas.")
    else:
        try:
            if 'Occurrence Time' in df_ume.columns and 'Alarm Code Name' in df_ume.columns:
                df_ume['Alarm_Detail'] = "• " + df_ume['Alarm Code Name'].astype(str) + " (" + df_ume['Occurrence Time'].astype(str) + ")"
            elif 'Alarm Code Name' in df_ume.columns:
                df_ume['Alarm_Detail'] = "• " + df_ume['Alarm Code Name'].astype(str)
            else:
                df_ume['Alarm_Detail'] = "• Unknown Alarm"
            
            dict1, dict2 = {}, {}
            if 'ME ID' in df_ume.columns:
                df_ume['V1'] = df_ume['ME ID'].apply(clean_id)
                m1 = (df_ume['V1'] != '') & (df_ume['V1'].notna())
                dict1 = df_ume[m1].groupby('V1')['Alarm_Detail'].apply(lambda x: "<br>".join(x.unique())).to_dict()
                
            if 'Site Name(Office)' in df_ume.columns:
                df_ume['V2'] = df_ume['Site Name(Office)'].apply(get_6digit_id)
                m2 = (df_ume['V2'] != '') & (df_ume['V2'].notna())
                dict2 = df_ume[m2].groupby('V2')['Alarm_Detail'].apply(lambda x: "<br>".join(x.unique())).to_dict()
                
            all_alarm_dict = {}
            for k in set(dict1.keys()).union(set(dict2.keys())):
                if k and str(k).lower() not in ['nan', 'none', '']:
                    items = []
                    if k in dict1: items.extend(dict1[k].split('<br>'))
                    if k in dict2: items.extend(dict2[k].split('<br>'))
                    all_alarm_dict[k] = "<br>".join(list(dict.fromkeys(items)))

            cond_pow, cond_l1, cond_l2 = pd.Series(False, index=df_ume.index), pd.Series(False, index=df_ume.index), pd.Series(False, index=df_ume.index)
            
            if 'Alarm Code Name' in df_ume.columns:
                cond_pow = df_ume['Alarm Code Name'].astype(str).str.contains('Input power-off', case=False, na=False)
                if 'Position' in df_ume.columns:
                    cond_pow = cond_pow & (df_ume['Position'].astype(str).str.strip() == 'Equipment=1')
                cond_l1 = df_ume['Alarm Code Name'].astype(str).str.contains('The link between the server and the ME is broken', case=False, na=False)
                cond_l2 = df_ume['Alarm Code Name'].astype(str).str.contains('Site Abis control link broken', case=False, na=False)
                
            if 'Specific Problem' in df_ume.columns:
                cond_l1 = cond_l1 | df_ume['Specific Problem'].astype(str).str.contains('The link between the server and the ME is broken', case=False, na=False)
                cond_l2 = cond_l2 | df_ume['Specific Problem'].astype(str).str.contains('Site Abis control link broken', case=False, na=False)

            df_down = df_ume[cond_pow | cond_l1 | cond_l2].copy()
            
            down_ids_raw = set()
            min_occurrence = {}
            if 'Occurrence Time' in df_down.columns:
                df_down['Occurrence_DT'] = pd.to_datetime(df_down['Occurrence Time'], errors='coerce')
                min1, min2 = {}, {}
                if 'V1' in df_down.columns:
                    val_v1 = df_down.dropna(subset=['Occurrence_DT', 'V1'])
                    min1 = val_v1.groupby('V1')['Occurrence_DT'].min().to_dict()
                    down_ids_raw.update(val_v1['V1'].unique())
                if 'V2' in df_down.columns:
                    val_v2 = df_down.dropna(subset=['Occurrence_DT', 'V2'])
                    min2 = val_v2.groupby('V2')['Occurrence_DT'].min().to_dict()
                    down_ids_raw.update(val_v2['V2'].unique())
                    
                for k in set(min1.keys()).union(set(min2.keys())):
                    if k and str(k).strip() != '' and str(k).lower() not in ['nan', 'none']:
                        t1, t2 = min1.get(k, pd.NaT), min2.get(k, pd.NaT)
                        if pd.notnull(t1) and pd.notnull(t2): min_occurrence[k] = min(t1, t2)
                        elif pd.notnull(t1): min_occurrence[k] = t1
                        elif pd.notnull(t2): min_occurrence[k] = t2

            down_ids = {str(k).strip() for k in down_ids_raw if pd.notnull(k) and str(k).strip() != '' and str(k).strip().lower() not in ['nan', 'none']}

            if 'LAT' in df_dapot.columns and 'LONG' in df_dapot.columns:
                df_dapot['LAT'] = df_dapot['LAT'].astype(str).str.replace(',', '.').astype(float)
                df_dapot['LONG'] = df_dapot['LONG'].astype(str).str.replace(',', '.').astype(float)

            # Memastikan text NOP menggunakan Full Kapital dan wilayah lain Title Case
            for col in ['Kota/Kab', 'Kecamatan']:
                if col in df_dapot.columns:
                    df_dapot[col] = df_dapot[col].apply(lambda x: str(x).title() if pd.notnull(x) else x)
            if 'NOP' in df_dapot.columns:
                df_dapot['NOP'] = df_dapot['NOP'].apply(lambda x: str(x).title().replace('Nop', 'NOP') if pd.notnull(x) else x)

            if 'Hub site' in df_dapot.columns:
                df_dapot['Hub site'] = df_dapot['Hub site'].fillna('Non Hub')
                
            col_class = find_col(df_dapot, ['SITE CLASS', 'Site_Class', 'Site Class', 'Class'])
            df_dapot['Site Class'] = df_dapot[col_class].fillna('-') if col_class else '-'

            df_dapot['C1'] = df_dapot['NE ID'].apply(clean_id) if 'NE ID' in df_dapot.columns else pd.Series([""] * len(df_dapot))
            df_dapot['C2'] = df_dapot['Site_ID'].astype(str).apply(get_6digit_id) if 'Site_ID' in df_dapot.columns else pd.Series([""] * len(df_dapot))
            df_dapot['C3'] = df_dapot['Site_Name'].astype(str).apply(get_6digit_id) if 'Site_Name' in df_dapot.columns else pd.Series([""] * len(df_dapot))
            
            def get_valid_ne(row): return row.get('C2') or row.get('C3') or row.get('C1') or ""
            df_dapot['NE_CLEAN'] = df_dapot.apply(get_valid_ne, axis=1)
            
            cond_status = df_dapot['C2'].isin(down_ids) | df_dapot['C3'].isin(down_ids) | df_dapot['C1'].isin(down_ids)
            df_dapot['Status'] = 'Up'
            df_dapot.loc[cond_status, 'Status'] = 'Down'

            def format_durasi(start_time):
                if pd.isnull(start_time): return "-"
                delta = pd.Timestamp.now(tz='Asia/Jakarta').tz_localize(None) - start_time
                total_sec = int(delta.total_seconds())
                if total_sec < 0: return "0m"
                days, rem = divmod(total_sec, 86400)
                hours, rem = divmod(rem, 3600)
                mins, _ = divmod(rem, 60)
                res = []
                if days > 0: res.append(f"{days}h")
                if hours > 0: res.append(f"{hours}j")
                res.append(f"{mins}m")
                return " ".join(res)
                
            def get_summary_table(df_source, col_name):
                if col_name not in df_source.columns: return pd.DataFrame()
                summary = pd.crosstab(df_source[col_name], df_source['Status']).reset_index()
                for s in ['Up', 'Down']:
                    if s not in summary.columns: summary[s] = 0
                summary = summary.rename(columns={'Down': 'Jumlah Down', 'Up': 'Jumlah Up'})
                summary['Total'] = summary['Jumlah Down'] + summary['Jumlah Up']
                summary['% Down'] = (summary['Jumlah Down'] / summary['Total'] * 100).round(1).astype(str) + '%'
                summary['% Up'] = (summary['Jumlah Up'] / summary['Total'] * 100).round(1).astype(str) + '%'
                return summary.sort_values('Jumlah Down', ascending=False).set_index(col_name)[['Jumlah Down', 'Jumlah Up', '% Down', '% Up', 'Total']]

            col_stats, col_map = st.columns([1.5, 2.5]) 
            
            with col_stats:
                list_nop = sorted([str(x) for x in df_dapot['NOP'].dropna().unique() if str(x).strip() != ''])
                idx_pal = next((i for i, v in enumerate(list_nop) if 'palangka' in str(v).lower()), 0)
                
                c_nop, c_tog1, c_tog2 = st.columns([2.5, 1, 1])
                with c_nop:
                    selected_nop = st.selectbox("NOP", list_nop, index=idx_pal, label_visibility="collapsed")
                with c_tog1:
                    show_labels = st.toggle("ID Map", value=False)
                with c_tog2:
                    show_legend = st.toggle("Legenda", value=True)
                
                df_active = df_dapot[df_dapot['NOP'] == selected_nop].copy()
                st.write("") 
                
                up_cnt, down_cnt = len(df_active[df_active['Status'] == 'Up']), len(df_active[df_active['Status'] == 'Down'])
                c1, c2 = st.columns(2)
                c1.success(f"✅ **Total Up:** {up_cnt}")
                c2.error(f"🚨 **Total Down:** {down_cnt}")
                
                tab1, tab2, tab3, tab4 = st.tabs(["Kabupaten", "Kecamatan", "Site Class", "Hub/Non Hub"])
                
                kab_df = get_summary_table(df_active, 'Kota/Kab')
                kec_df = get_summary_table(df_active, 'Kecamatan')
                cls_df = get_summary_table(df_active, 'Site Class')
                hub_df = get_summary_table(df_active, 'Hub site')
                
                with tab1: event_kab = st.dataframe(kab_df, height=250, use_container_width=True, on_select="rerun", selection_mode="single-row")
                with tab2: event_kec = st.dataframe(kec_df, height=250, use_container_width=True, on_select="rerun", selection_mode="single-row")
                with tab3: event_cls = st.dataframe(cls_df, height=250, use_container_width=True, on_select="rerun", selection_mode="single-row")
                with tab4: event_hub = st.dataframe(hub_df, height=250, use_container_width=True, on_select="rerun", selection_mode="single-row")
                    
            filter_col, filter_val = None, None
            
            if len(event_kab.selection.rows) > 0:
                filter_col, filter_val = 'Kota/Kab', kab_df.index[event_kab.selection.rows[0]]
            elif len(event_kec.selection.rows) > 0:
                filter_col, filter_val = 'Kecamatan', kec_df.index[event_kec.selection.rows[0]]
            elif len(event_cls.selection.rows) > 0:
                filter_col, filter_val = 'Site Class', cls_df.index[event_cls.selection.rows[0]]
            elif len(event_hub.selection.rows) > 0:
                filter_col, filter_val = 'Hub site', hub_df.index[event_hub.selection.rows[0]]

            with col_map:
                df_map = df_active.copy()
                if filter_col and filter_val:
                    df_map = df_map[df_map[filter_col] == filter_val]
                    st.info(f"📍 Menampilkan Area **{selected_nop}** - Filter: **{filter_col} ({filter_val})**")
                else:
                    st.info(f"📍 Menampilkan Seluruh Area **{selected_nop}**")
                
                suggestion_site_ids, suggested_up_ids = {}, set()
                df_up_all = df_dapot[(df_dapot['Status'] == 'Up') & df_dapot['LAT'].notna() & df_dapot['LONG'].notna()]
                
                for idx, row in df_map[df_map['Status'] == 'Down'].iterrows():
                    site_ids, ne_cleans = get_nearest_up_sites(row['LAT'], row['LONG'], df_up_all, k=2)
                    suggestion_site_ids[row['NE_CLEAN']] = site_ids if site_ids else ["-"]
                    for ne in ne_cleans:
                        val = str(ne).strip()
                        if val and val.lower() not in ['nan', 'none', 'unknown', '']:
                            suggested_up_ids.add(val)

                if 'LAT' in df_map.columns and 'LONG' in df_map.columns:
                    df_map = df_map.dropna(subset=['LAT', 'LONG'])
                    
                    if not df_map.empty:
                        m = folium.Map(location=[df_map['LAT'].mean(), df_map['LONG'].mean()], zoom_start=10)
                        folium.TileLayer(tiles='https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}', attr='Google', name='Google Satellite').add_to(m)
                        
                        if filter_col in ['Kota/Kab', 'Kecamatan'] and filter_val:
                            min_lat, max_lat = df_map['LAT'].min(), df_map['LAT'].max()
                            min_lon, max_lon = df_map['LONG'].min(), df_map['LONG'].max()
                            
                            if min_lat == max_lat: min_lat -= 0.02; max_lat += 0.02
                            if min_lon == max_lon: min_lon -= 0.02; max_lon += 0.02
                            
                            bounds = [[min_lat, min_lon], [max_lat, max_lon]]
                            m.fit_bounds(bounds)

                        if show_legend:
                            legend_html = '''
                            <div style="position: fixed; bottom: 20px; left: 20px; width: 195px; height: 120px; 
                                        border:2px solid grey; z-index:9999; font-size:12px; color:black;
                                        background-color:white; padding: 10px; border-radius: 5px; opacity: 0.95;">
                            <b style="color:black;">Legenda Peta</b><br>
                            <i style="background:#e60000; width: 12px; height: 12px; float: left; margin-right: 8px; margin-top: 3px; border-radius: 50%;"></i> <span style="color:black;">Down</span><br>
                            <i style="background:#00802b; width: 12px; height: 12px; float: left; margin-right: 8px; margin-top: 3px; border-radius: 50%;"></i> <span style="color:black;">Up</span><br>
                            <i style="background:#0066ff; width: 12px; height: 12px; float: left; margin-right: 8px; margin-top: 3px; border-radius: 50%;"></i> <span style="color:black;">Recommend to Optim crowd</span><br>
                            <div style="color:#444; font-size:16px; float:left; margin-right:7px; margin-top:-3px; margin-left:-2px;">★</div> <span style="color:black;">Hub site</span><br>
                            </div>
                            '''
                            m.get_root().html.add_child(folium.Element(legend_html))
                        
                        for idx, row in df_map.iterrows():
                            lat, lon = row['LAT'], row['LONG']
                            site_id = row.get('Site_ID', 'Unknown')
                            ne_id = str(row.get('NE_CLEAN', 'Unknown')).strip()
                            site_name = row.get('Site_Name', 'Unknown')
                            site_class = row.get('Site Class', '-')
                            status = row['Status']
                            
                            grid_type = row.get('Grid Category New', '-')
                            power_type = row.get('POWER TYPE', '-')
                            hub_status = str(row.get('Hub site', 'Non Hub')).strip()
                            is_hub = 'hub' in hub_status.lower() and 'non' not in hub_status.lower()
                            
                            col_transport = find_col(df_dapot, ['Transport Type', 'Transport', 'Transport_Type'])
                            col_simpul = find_col(df_dapot, ['Simpul 4G/Hub Simpul', 'Simpul 4G', 'Hub Simpul'])
                            col_jml_anakan = find_col(df_dapot, ['JUMLAH SITE ANAKAN', 'Jumlah anakan', 'Jumlah Anakan', 'Jml Anakan'])
                            col_id_anakan = find_col(df_dapot, ['SITE ID ANAKAN', 'Site id anakan', 'Site ID Anakan', 'ID Anakan'])
                            
                            transport_type = row[col_transport] if col_transport and pd.notnull(row[col_transport]) else '-'
                            simpul_4g = row[col_simpul] if col_simpul and pd.notnull(row[col_simpul]) else '-'
                            
                            raw_jml = row[col_jml_anakan] if col_jml_anakan and pd.notnull(row[col_jml_anakan]) else 0
                            try: jumlah_anakan = int(float(raw_jml))
                            except: jumlah_anakan = 0

                            site_id_anakan = row[col_id_anakan] if col_id_anakan and pd.notnull(row[col_id_anakan]) else '-'
                            route_link = row.get('Route', row.get('Link_Route', ''))
                            
                            if status == 'Down':
                                color_hex, status_label = '#e60000', '<b style="color:red;">Down</b>'
                            else:
                                if ne_id in suggested_up_ids and ne_id.lower() not in ['', 'nan', 'none', 'unknown']:
                                    color_hex, status_label = '#0066ff', '<b style="color:#0066ff;">Up (Recommend to Optim crowd)</b>'
                                else:
                                    color_hex, status_label = '#00802b', '<b style="color:green;">Up</b>'

                            alarms_terkait = "<i style='color:gray;'>Tidak ada alarm aktif</i>"
                            start_dt = None
                            for c_k in [row['C2'], row['C3'], row['C1']]:
                                if c_k and c_k in all_alarm_dict: alarms_terkait = all_alarm_dict[c_k]; break
                            for c_k in [row['C2'], row['C3'], row['C1']]:
                                if c_k and c_k in min_occurrence: start_dt = min_occurrence[c_k]; break

                            durasi_str = f" (Durasi: {format_durasi(start_dt)})" if (status == 'Down' and start_dt) else ""
                            
                            route_html_button = f'<hr style="margin: 4px 0;"><a href="{route_link}" target="_blank" style="display:block; text-align:center; background:#1a73e8; color:white; padding:4px; text-decoration:none; border-radius:4px; font-weight:bold; font-size:10px;">🔗 Buka Link Route</a>' if (pd.notnull(route_link) and str(route_link).strip() != "" and str(route_link).lower() != "nan") else ""

                            html_detail = f"""
                            <div style="width: 260px; font-size:11px; color:black; white-space: normal; line-height: 1.4;">
                                <b style="font-size:13px;">{site_name}</b> <br>Site ID: <b>{site_id}</b><br>
                                Status: {status_label}{durasi_str}<br><b>Class:</b> {site_class} | <b>Tipe:</b> {hub_status}<br>
                                <b>Power:</b> {power_type} | <b>Grid:</b> {grid_type}<br><b>Transport:</b> {transport_type}<br>
                                <b>Simpul 4G:</b> {simpul_4g}<br><b>Jumlah Anakan:</b> {jumlah_anakan} site<br>
                                <b>Site ID Anakan:</b> <span style="word-break: break-all;">{site_id_anakan}</span>
                                <hr style="margin: 4px 0;"><b style="font-size:10px;">Daftar Alarm:</b><br>
                                <div style="font-size:10px; max-height:85px; overflow-y:auto; background:#f1f1f1; padding:4px; border-radius:4px;">
                                    {alarms_terkait}</div>{route_html_button}
                            </div>
                            """
                            
                            if is_hub: shape_html = f'<div style="color:{color_hex}; font-size:18px; margin-top:-4px; margin-left:-2px; text-shadow: -1px -1px 0 #FFF, 1px -1px 0 #FFF, -1px 1px 0 #FFF, 1px 1px 0 #FFF, 0px 0px 4px rgba(0,0,0,0.6);">★</div>'
                            else: shape_html = f'<div style="width:12px; height:12px; background-color:{color_hex}; border:2px solid white; border-radius:50%; box-shadow:0px 0px 3px rgba(0,0,0,0.6);"></div>'
                            label_html = f'<div style="position:absolute; left:14px; top:-2px; pointer-events:none; font-size:10px; font-weight:bold; color:{color_hex}; text-shadow:-1px -1px 0 #FFF,1px -1px 0 #FFF,-1px 1px 0 #FFF,1px 1px 0 #FFF,0px 0px 3px #FFF; white-space:nowrap;">{site_id}</div>' if show_labels else ""
                            
                            folium.Marker(
                                location=[lat, lon],
                                icon=folium.DivIcon(html=f'<div style="position:relative; width:12px; height:12px;">{shape_html}{label_html}</div>', icon_size=(12, 12), icon_anchor=(6, 6)),
                                tooltip=folium.Tooltip(html_detail)
                            ).add_to(m)
                        
                        folium.LayerControl(position='topright').add_to(m)
                        st_folium(m, use_container_width=True, height=500, returned_objects=[])
                    else:
                        st.warning("Tidak ada data site pada area yang dipilih.")

            st.divider()
            st.subheader("📋 Detail Site Down")
            
            df_dapot_down = df_map[df_map['Status'] == 'Down'].copy()
            if not df_dapot_down.empty:
                def get_down_time(row):
                    for c in [row['C2'], row['C3'], row['C1']]:
                        if c in min_occurrence: return min_occurrence[c]
                    return pd.NaT

                df_dapot_down['Occurrence_Time'] = df_dapot_down.apply(get_down_time, axis=1)
                df_dapot_down = df_dapot_down.sort_values(by='Occurrence_Time', ascending=True, na_position='last')
                df_dapot_down['Durasi Down'] = df_dapot_down['Occurrence_Time'].apply(format_durasi)
                df_dapot_down['Suggestion (Nearest Up)'] = df_dapot_down['NE_CLEAN'].map(suggestion_site_ids)
                df_dapot_down = df_dapot_down.explode('Suggestion (Nearest Up)')
                
                kolom_detail = {
                    'Site_ID': 'Site ID', 'Site_Name': 'Site Name', 'Site Class': 'Site Class',
                    'Kota/Kab': 'Kabupaten', 'Kecamatan': 'Kecamatan', 'POWER TYPE': 'Tipe Power',
                    'Grid Category New': 'Grid', 'Hub site': 'Hub/Non Hub', 'Simpul 4G': 'Simpul 4G',
                    'Durasi Down': 'Durasi Down', 'Suggestion (Nearest Up)': 'Recommend to Optim crowd'
                }
                
                df_detail_final = df_dapot_down[[k for k in kolom_detail.keys() if k in df_dapot_down.columns]].rename(columns=kolom_detail)
                if 'Site ID' in df_detail_final.columns: df_detail_final = df_detail_final.set_index('Site ID')
                st.dataframe(df_detail_final, height=350, use_container_width=True)
            else:
                st.info("🎉 Sistem normal. Tidak ada site yang berstatus Down saat ini pada filter yang dipilih.")
                    
        except Exception as e:
            st.error(f"🚨 Terjadi kesalahan saat memproses data: {e}")
            st.exception(e)

# --- FOOTER CUSTOM ---
st.markdown("<hr style='margin-top: 3rem; margin-bottom: 1rem;'/><p style='text-align: center; color: #888; font-size: 14px;'>© 2026 | Created with ❤️ by Fauzi Ramdani - 97122</p>", unsafe_allow_html=True)
