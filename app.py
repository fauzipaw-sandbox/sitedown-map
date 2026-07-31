import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from datetime import datetime
import math
from streamlit_gsheets import GSheetsConnection

# --- 1. KONFIGURASI LAYOUT ---
st.set_page_config(page_title="Site Down Monitoring Kalimantan (ZTE Only)", layout="wide", initial_sidebar_state="collapsed")

# Inisialisasi Session State untuk Filter Status Tombol
if 'status_filter' not in st.session_state:
    st.session_state.status_filter = 'All'

def set_status(status):
    if st.session_state.status_filter == status:
        st.session_state.status_filter = 'All'
    else:
        st.session_state.status_filter = status

# CSS untuk menyembunyikan tulisan loading (stStatusWidget) agar klik terasa instan
st.markdown("""
    <style>
        .block-container { padding-top: 1.5rem; padding-bottom: 2rem; padding-left: 2rem; padding-right: 2rem; max-width: 100%; }
        header { visibility: hidden; }
        #MainMenu { visibility: hidden; }
        footer { visibility: hidden; }
        .stTabs [data-baseweb="tab-list"] { gap: 8px; }
        .st-emotion-cache-1y4p8pa { padding-top: 0rem; }
        .update-info { text-align: right; font-size: 13px; color: #555; margin-bottom: 8px; margin-top: -5px;}
        [data-testid="stStatusWidget"] {visibility: hidden;} 
    </style>
""", unsafe_allow_html=True)

# --- 2. KONFIGURASI SPREADSHEET ---
MASTER_SHEET_URL = "https://docs.google.com/spreadsheets/d/11pp1YavJsR6wnYcvs0Z6B94KM75clu7FQgRy7sdEQ4g"
KOLOM_MASTER = ['Alarm ID', 'ME ID', 'Site Name(Office)', 'Alarm Code Name', 'Occurrence Time', 'Position', 'Specific Problem', 'Location']

# --- 3. FUNGSI UTILITIES ---
def get_nearest_up_sites(lat, lon, df_up, k=2):
    if pd.isna(lat) or pd.isna(lon) or df_up.empty: return [], []
    def calc_dist(row):
        if pd.isna(row['LAT']) or pd.isna(row['LONG']): return float('inf')
        lat1, lon1, lat2, lon2 = map(math.radians, [lat, lon, row['LAT'], row['LONG']])
        a = max(0.0, min(1.0, math.sin((lat2 - lat1)/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1)/2)**2))
        return 6371 * (2 * math.asin(math.sqrt(a)))
    distances = df_up.apply(calc_dist, axis=1)
    closest = df_up.loc[distances.nsmallest(k).index]
    return closest['Site_ID'].tolist(), closest['NE_CLEAN'].tolist()

def find_col(df, possible_names):
    df_cols_clean = {c.strip().lower(): c for c in df.columns}
    for name in possible_names:
        if name.strip().lower() in df_cols_clean: return df_cols_clean[name.strip().lower()]
    return None

def clean_id(text):
    if pd.isna(text): return ""
    val = str(text).strip()
    return "" if val.lower() in ['nan', 'none', 'null', ''] else (val[:-2] if val.endswith('.0') else val)

def get_6digit_id(text):
    if pd.isna(text): return ""
    try:
        val = str(text).strip()
        if val.lower() in ['nan', 'none', 'null', '']: return ""
        if val.endswith('.0'): val = val[:-2]
        return val[2:8].upper() if val.upper().startswith(('C_', 'N_')) else val[:6].upper()
    except: return str(text)

conn = st.connection("gsheets", type=GSheetsConnection)

# --- 4. TARIK DATA DARI DATABASE (Tanpa Spinner agar Instan saat Rerun) ---
try: df_dapot = conn.read(spreadsheet=MASTER_SHEET_URL, worksheet=1, sql="SELECT *", ttl=300)
except Exception as e: st.error(f"Gagal menarik data site: {e}"); df_dapot = None
    
try: df_ume = conn.read(spreadsheet=MASTER_SHEET_URL, worksheet=0, sql="SELECT *", ttl=300)
except Exception as e: st.error(f"Gagal menarik data alarm: {e}"); df_ume = pd.DataFrame()

if df_ume is not None and not df_ume.empty and 'Occurrence Time' in df_ume.columns:
    latest_time = pd.to_datetime(df_ume['Occurrence Time'], errors='coerce').max()
    last_update_str = latest_time.strftime("%d-%m-%Y %H:%M:%S") if pd.notnull(latest_time) else "Tidak diketahui"
else: last_update_str = "Belum Ada Data"

# --- 5. HEADER & TOOLBAR UPLOAD & FILTER SPESIFIK ---
col_title, col_header_right = st.columns([2.2, 1.8])
with col_title: st.title("🗺️ Site Down Monitoring Kalimantan (ZTE Only)")
with col_header_right:
    st.markdown(f"<div class='update-info'>Pembaruan Data Terakhir: <b style='color:#1a73e8;'>{last_update_str}</b></div>", unsafe_allow_html=True)
    c_f, c_u = st.columns(2)
    
    with c_f:
        with st.popover("🔍 Filter Spesifik", use_container_width=True):
            st.markdown("**Site dengan Alarm:**")
            f_s1 = st.checkbox("S1-GTPU / S1 Link Broken")
            f_cell = st.checkbox("Cell Down (Outage/Shutdown/Interruption)")
            f_vswr = st.checkbox("VSWR (Antenna Standing)")
            f_temp = st.checkbox("High Temp")
            
    with c_u:
        with st.popover("⚙️ Update Data", use_container_width=True):
            st.markdown("""
            **Cara Update Data:**
            1. Login UME ZTE ([Klik Disini](https://10.40.48.9:28001/uportal/framework/default.html#/home))
            2. **Alarm Management > Active Alarm > Alarm Monitor > Export All**
            3. Drag n Drop filenya di bawah ini:
            """)
            ume_file_top = st.file_uploader("Pilih file (Excel/CSV)", type=['xlsx', 'csv'], label_visibility="collapsed")
            if st.button("🔄 Reload / Clear Cache", use_container_width=True, type="primary"):
                st.cache_data.clear(); conn.reset(); st.rerun()
                
            if ume_file_top:
                if "last_uploaded" not in st.session_state or st.session_state["last_uploaded"] != ume_file_top.name:
                    with st.spinner("Menyimpan..."):
                        try:
                            df_new = pd.read_csv(ume_file_top) if ume_file_top.name.endswith('.csv') else pd.read_excel(ume_file_top)
                            valid_cols = [c for c in KOLOM_MASTER if c in df_new.columns]
                            if valid_cols: df_new = df_new[valid_cols]
                            df_new = df_new.dropna(how='all')
                            if 'Occurrence Time' in df_new.columns: df_new['Occurrence Time'] = df_new['Occurrence Time'].astype(str)
                            conn.update(spreadsheet=MASTER_SHEET_URL, worksheet=0, data=df_new)
                            st.cache_data.clear(); conn.reset() 
                            st.session_state["last_uploaded"] = ume_file_top.name
                            st.success("✅ Berhasil. Klik Reload.")
                        except Exception as e: st.error(f"Gagal: {e}")

st.markdown("<hr style='margin: 0px 0px 15px 0px;'/>", unsafe_allow_html=True)

# --- 6. PROSES DATA ---
if df_dapot is not None:
    if df_ume.empty or len(df_ume) == 0:
        st.warning("⚠️ **Database alarm masih kosong atau belum dimuat!**")
    else:
        try:
            if 'Occurrence Time' in df_ume.columns and 'Alarm Code Name' in df_ume.columns:
                df_ume['Alarm_Detail'] = "• " + df_ume['Alarm Code Name'].astype(str) + " (" + df_ume['Occurrence Time'].astype(str) + ")"
            elif 'Alarm Code Name' in df_ume.columns: df_ume['Alarm_Detail'] = "• " + df_ume['Alarm Code Name'].astype(str)
            else: df_ume['Alarm_Detail'] = "• Unknown Alarm"
            
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
            cond_pot = pd.Series(False, index=df_ume.index)
            
            # Mask untuk Filter Alarm Spesifik
            s1_mask = pd.Series(False, index=df_ume.index)
            cell_mask = pd.Series(False, index=df_ume.index)
            vswr_mask = pd.Series(False, index=df_ume.index)
            temp_mask = pd.Series(False, index=df_ume.index)
            
            if 'Alarm Code Name' in df_ume.columns:
                cond_pow = df_ume['Alarm Code Name'].astype(str).str.contains('Input power-off', case=False, na=False)
                if 'Position' in df_ume.columns: cond_pow = cond_pow & (df_ume['Position'].astype(str).str.strip() == 'Equipment=1')
                cond_l1 = df_ume['Alarm Code Name'].astype(str).str.contains('The link between the server and the ME is broken', case=False, na=False)
                cond_l2 = df_ume['Alarm Code Name'].astype(str).str.contains('Site Abis control link broken', case=False, na=False)
                cond_pot = df_ume['Alarm Code Name'].astype(str).str.contains('mains|ac fail|battery|low batt', case=False, na=False)
                
                s1_mask = df_ume['Alarm Code Name'].str.contains('s1 link|s1-gtpu', case=False, na=False)
                cell_mask = df_ume['Alarm Code Name'].str.contains('cell outage|cell shutdown|cell inter', case=False, na=False)
                vswr_mask = df_ume['Alarm Code Name'].str.contains('vswr|antenna standing', case=False, na=False)
                temp_mask = df_ume['Alarm Code Name'].str.contains('high temp', case=False, na=False)

            if 'Specific Problem' in df_ume.columns:
                cond_l1 = cond_l1 | df_ume['Specific Problem'].astype(str).str.contains('The link between the server and the ME is broken', case=False, na=False)
                cond_l2 = cond_l2 | df_ume['Specific Problem'].astype(str).str.contains('Site Abis control link broken', case=False, na=False)
                cond_pot = cond_pot | df_ume['Specific Problem'].astype(str).str.contains('mains|ac fail|battery|low batt', case=False, na=False)
                
                s1_mask = s1_mask | df_ume['Specific Problem'].str.contains('s1 link|s1-gtpu', case=False, na=False)
                cell_mask = cell_mask | df_ume['Specific Problem'].str.contains('cell outage|cell shutdown|cell inter', case=False, na=False)
                vswr_mask = vswr_mask | df_ume['Specific Problem'].str.contains('vswr|antenna standing', case=False, na=False)
                temp_mask = temp_mask | df_ume['Specific Problem'].str.contains('high temp', case=False, na=False)

            # Ekstrak ID untuk Filter Spesifik
            def get_ids_by_mask(mask):
                res = set()
                if 'V1' in df_ume.columns: res.update(df_ume.loc[mask, 'V1'].dropna())
                if 'V2' in df_ume.columns: res.update(df_ume.loc[mask, 'V2'].dropna())
                return {str(x).strip() for x in res if pd.notnull(x) and str(x).strip() != ''}
                
            ids_s1 = get_ids_by_mask(s1_mask)
            ids_cell = get_ids_by_mask(cell_mask)
            ids_vswr = get_ids_by_mask(vswr_mask)
            ids_temp = get_ids_by_mask(temp_mask)

            df_down = df_ume[cond_pow | cond_l1 | cond_l2].copy()
            df_pot_raw = df_ume[cond_pot & ~(cond_pow | cond_l1 | cond_l2)].copy()

            now_wib = pd.Timestamp.now(tz='Asia/Jakarta').tz_localize(None)
            if 'Occurrence Time' in df_pot_raw.columns:
                df_pot_raw['Occ_DT'] = pd.to_datetime(df_pot_raw['Occurrence Time'], errors='coerce')
                df_pot_raw['Hours_Diff'] = (now_wib - df_pot_raw['Occ_DT']).dt.total_seconds() / 3600
                df_pot = df_pot_raw[df_pot_raw['Hours_Diff'] < 18].copy()
            else:
                df_pot = df_pot_raw.copy()

            def extract_ids_and_time(df_source):
                ids_raw = set(); min_occ = {}
                if 'Occurrence Time' in df_source.columns:
                    df_source['Occurrence_DT'] = pd.to_datetime(df_source['Occurrence Time'], errors='coerce')
                    min1, min2 = {}, {}
                    if 'V1' in df_source.columns:
                        v1 = df_source.dropna(subset=['Occurrence_DT', 'V1'])
                        min1 = v1.groupby('V1')['Occurrence_DT'].min().to_dict(); ids_raw.update(v1['V1'].unique())
                    if 'V2' in df_source.columns:
                        v2 = df_source.dropna(subset=['Occurrence_DT', 'V2'])
                        min2 = v2.groupby('V2')['Occurrence_DT'].min().to_dict(); ids_raw.update(v2['V2'].unique())
                    for k in set(min1.keys()).union(set(min2.keys())):
                        if k and str(k).strip() != '' and str(k).lower() not in ['nan', 'none']:
                            t1, t2 = min1.get(k, pd.NaT), min2.get(k, pd.NaT)
                            if pd.notnull(t1) and pd.notnull(t2): min_occ[k] = min(t1, t2)
                            elif pd.notnull(t1): min_occ[k] = t1
                            elif pd.notnull(t2): min_occ[k] = t2
                clean_ids = {str(k).strip() for k in ids_raw if pd.notnull(k) and str(k).strip() != '' and str(k).strip().lower() not in ['nan', 'none']}
                return clean_ids, min_occ

            down_ids, min_occ_down = extract_ids_and_time(df_down)
            pot_ids, min_occ_pot = extract_ids_and_time(df_pot)
            min_occurrence = {**min_occ_pot, **min_occ_down}

            if 'LAT' in df_dapot.columns and 'LONG' in df_dapot.columns:
                df_dapot['LAT'] = df_dapot['LAT'].astype(str).str.replace(',', '.').astype(float)
                df_dapot['LONG'] = df_dapot['LONG'].astype(str).str.replace(',', '.').astype(float)

            for col in ['Kota/Kab', 'Kecamatan']:
                if col in df_dapot.columns: df_dapot[col] = df_dapot[col].apply(lambda x: str(x).title() if pd.notnull(x) else x)
            if 'NOP' in df_dapot.columns:
                df_dapot['NOP'] = df_dapot['NOP'].apply(lambda x: str(x).upper().replace('NOP', 'NOP') if pd.notnull(x) else x)

            if 'Hub site' in df_dapot.columns: df_dapot['Hub site'] = df_dapot['Hub site'].fillna('Non Hub')
            col_class = find_col(df_dapot, ['SITE CLASS', 'Site_Class', 'Site Class', 'Class'])
            df_dapot['Site Class'] = df_dapot[col_class].fillna('-') if col_class else '-'

            df_dapot['C1'] = df_dapot['NE ID'].apply(clean_id) if 'NE ID' in df_dapot.columns else pd.Series([""] * len(df_dapot))
            df_dapot['C2'] = df_dapot['Site_ID'].astype(str).apply(get_6digit_id) if 'Site_ID' in df_dapot.columns else pd.Series([""] * len(df_dapot))
            df_dapot['C3'] = df_dapot['Site_Name'].astype(str).apply(get_6digit_id) if 'Site_Name' in df_dapot.columns else pd.Series([""] * len(df_dapot))
            
            df_dapot['NE_CLEAN'] = df_dapot.apply(lambda row: row.get('C2') or row.get('C3') or row.get('C1') or "", axis=1)
            
            df_dapot['Status'] = 'Up'
            c_pot = df_dapot['C2'].isin(pot_ids) | df_dapot['C3'].isin(pot_ids) | df_dapot['C1'].isin(pot_ids)
            df_dapot.loc[c_pot, 'Status'] = 'Potential Down'
            c_down = df_dapot['C2'].isin(down_ids) | df_dapot['C3'].isin(down_ids) | df_dapot['C1'].isin(down_ids)
            df_dapot.loc[c_down, 'Status'] = 'Down'

            def format_durasi(start_time):
                if pd.isnull(start_time): return "-"
                delta = pd.Timestamp.now(tz='Asia/Jakarta').tz_localize(None) - start_time
                t_sec = int(delta.total_seconds())
                if t_sec < 0: return "0m"
                d, rem = divmod(t_sec, 86400); h, rem = divmod(rem, 3600); m, _ = divmod(rem, 60)
                res = []
                if d > 0: res.append(f"{d}h")
                if h > 0: res.append(f"{h}j")
                res.append(f"{m}m")
                return " ".join(res)
                
            def get_summary_table(df_source, col_name):
                if col_name not in df_source.columns: return pd.DataFrame()
                summary = pd.crosstab(df_source[col_name], df_source['Status']).reset_index()
                for s in ['Up', 'Down', 'Potential Down']:
                    if s not in summary.columns: summary[s] = 0
                summary = summary.rename(columns={'Down': 'Jumlah Down', 'Up': 'Jumlah Up', 'Potential Down': 'Jumlah Potential'})
                summary['Total'] = summary['Jumlah Down'] + summary['Jumlah Up'] + summary['Jumlah Potential']
                summary['% Down'] = (summary['Jumlah Down'] / summary['Total'] * 100).round(1).astype(str) + '%'
                return summary.sort_values('Jumlah Down', ascending=False).set_index(col_name)[['Jumlah Down', 'Jumlah Potential', 'Jumlah Up', '% Down', 'Total']]

            # --- LAYOUT DUA KOLOM ---
            col_stats, col_map = st.columns([1.5, 2.5]) 
            
            with col_stats:
                list_nop = sorted([str(x) for x in df_dapot['NOP'].dropna().unique() if str(x).strip() != ''])
                idx_pal = next((i for i, v in enumerate(list_nop) if 'palangka' in str(v).lower()), 0)
                selected_nop = st.selectbox("📌 Filter NOP", list_nop, index=idx_pal)
                
                df_active_base = df_dapot[df_dapot['NOP'] == selected_nop].copy()
                
                # Integrasi Filter Spesifik ke DataFrame Active
                active_spesifik_ids = set()
                is_spesifik_filtered = False
                if f_s1: active_spesifik_ids.update(ids_s1); is_spesifik_filtered = True
                if f_cell: active_spesifik_ids.update(ids_cell); is_spesifik_filtered = True
                if f_vswr: active_spesifik_ids.update(ids_vswr); is_spesifik_filtered = True
                if f_temp: active_spesifik_ids.update(ids_temp); is_spesifik_filtered = True

                if is_spesifik_filtered:
                    mask_sp = df_active_base['C1'].isin(active_spesifik_ids) | df_active_base['C2'].isin(active_spesifik_ids) | df_active_base['C3'].isin(active_spesifik_ids)
                    df_active_base = df_active_base[mask_sp]
                
                up_cnt = len(df_active_base[df_active_base['Status'] == 'Up'])
                pot_cnt = len(df_active_base[df_active_base['Status'] == 'Potential Down'])
                down_cnt = len(df_active_base[df_active_base['Status'] == 'Down'])
                
                c1, c2, c3 = st.columns(3)
                with c1:
                    btn_up = st.button(f"✅ Up: {up_cnt}", type="primary" if st.session_state.status_filter == 'Up' else "secondary", use_container_width=True, on_click=set_status, args=('Up',))
                with c2:
                    btn_pot = st.button(f"⚠️ Potential Down: {pot_cnt}", type="primary" if st.session_state.status_filter == 'Potential Down' else "secondary", use_container_width=True, on_click=set_status, args=('Potential Down',))
                with c3:
                    btn_dwn = st.button(f"🚨 Down: {down_cnt}", type="primary" if st.session_state.status_filter == 'Down' else "secondary", use_container_width=True, on_click=set_status, args=('Down',))
                
                if st.session_state.status_filter != 'All':
                    df_active = df_active_base[df_active_base['Status'] == st.session_state.status_filter]
                else:
                    df_active = df_active_base

                st.write("") 
                
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
            if len(event_kab.selection.rows) > 0: filter_col, filter_val = 'Kota/Kab', kab_df.index[event_kab.selection.rows[0]]
            elif len(event_kec.selection.rows) > 0: filter_col, filter_val = 'Kecamatan', kec_df.index[event_kec.selection.rows[0]]
            elif len(event_cls.selection.rows) > 0: filter_col, filter_val = 'Site Class', cls_df.index[event_cls.selection.rows[0]]
            elif len(event_hub.selection.rows) > 0: filter_col, filter_val = 'Hub site', hub_df.index[event_hub.selection.rows[0]]

            with col_map:
                df_map = df_active.copy()
                if filter_col and filter_val:
                    df_map = df_map[df_map[filter_col] == filter_val]
                    st.info(f"📍 Area **{selected_nop}** - Filter: **{filter_col} ({filter_val})** (Tombol 🗂️ di peta untuk Legend & Toggles)")
                else:
                    status_text = f" ({st.session_state.status_filter})" if st.session_state.status_filter != 'All' else ""
                    sp_text = " (Filter Spesifik Aktif)" if is_spesifik_filtered else ""
                    st.info(f"📍 Seluruh Area **{selected_nop}**{status_text}{sp_text} (Tombol 🗂️ di peta untuk Legend)")
                
                suggestion_site_ids, suggested_up_ids = {}, set()
                df_up_strict = df_dapot[(df_dapot['Status'] == 'Up') & df_dapot['LAT'].notna() & df_dapot['LONG'].notna()]
                
                for idx, row in df_map[df_map['Status'] == 'Down'].iterrows():
                    site_ids, ne_cleans = get_nearest_up_sites(row['LAT'], row['LONG'], df_up_strict, k=2)
                    suggestion_site_ids[idx] = site_ids if site_ids else ["-"]
                    for ne in ne_cleans:
                        val = str(ne).strip()
                        if val and val.lower() not in ['nan', 'none', 'unknown', '']: suggested_up_ids.add(val)

                if 'LAT' in df_map.columns and 'LONG' in df_map.columns:
                    df_map = df_map.dropna(subset=['LAT', 'LONG'])
                    
                    if not df_map.empty:
                        m = folium.Map(location=[df_map['LAT'].mean(), df_map['LONG'].mean()], zoom_start=10, control_scale=True)
                        folium.TileLayer(tiles='https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}', attr='Google', name='Google Satellite').add_to(m)
                        
                        fg_down = folium.FeatureGroup(name="<span style='color:#e60000; font-size:12px;'>🔴</span> <b>Down</b>", show=True)
                        fg_pot = folium.FeatureGroup(name="<span style='color:#ff9900; font-size:12px;'>🟠</span> <b>Potential Down (<18h)</b>", show=True)
                        fg_up = folium.FeatureGroup(name="<span style='color:#00802b; font-size:12px;'>🟢</span> <b>Up</b>", show=True)
                        fg_rec = folium.FeatureGroup(name="<span style='color:#0066ff; font-size:12px;'>🔵</span> <b>Recommend to Optim</b>", show=False)
                        fg_id = folium.FeatureGroup(name="<span style='color:black; font-size:12px;'>🏷️</span> <b>Tampilkan ID Map</b>", show=False)
                        fg_hub = folium.FeatureGroup(name="<span style='color:#444; font-size:16px;'>★</span> <b>Penanda Hub Site</b>", show=True)
                        
                        if (filter_col and filter_val) or st.session_state.status_filter != 'All' or is_spesifik_filtered:
                            min_lat, max_lat, min_lon, max_lon = df_map['LAT'].min(), df_map['LAT'].max(), df_map['LONG'].min(), df_map['LONG'].max()
                            if min_lat == max_lat: min_lat -= 0.02; max_lat += 0.02
                            if min_lon == max_lon: min_lon -= 0.02; max_lon += 0.02
                            m.fit_bounds([[min_lat, min_lon], [max_lat, max_lon]])

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
                            col_simpul_telkom = find_col(df_dapot, ['SIMPUL TELKOM', 'Simpul Telkom', 'simpul telkom', 'SIMPUL_TELKOM'])
                            col_jml_anakan = find_col(df_dapot, ['JUMLAH SITE ANAKAN', 'Jumlah anakan', 'Jumlah Anakan', 'Jml Anakan'])
                            col_id_anakan = find_col(df_dapot, ['SITE ID ANAKAN', 'Site id anakan', 'Site ID Anakan', 'ID Anakan'])
                            
                            transport_type = row[col_transport] if col_transport and pd.notnull(row[col_transport]) else '-'
                            simpul_4g = row[col_simpul] if col_simpul and pd.notnull(row[col_simpul]) else '-'
                            simpul_telkom = row[col_simpul_telkom] if col_simpul_telkom and pd.notnull(row[col_simpul_telkom]) else '-'
                            
                            try: jumlah_anakan = int(float(row[col_jml_anakan])) if col_jml_anakan and pd.notnull(row[col_jml_anakan]) else 0
                            except: jumlah_anakan = 0
                            site_id_anakan = row[col_id_anakan] if col_id_anakan and pd.notnull(row[col_id_anakan]) else '-'
                            route_link = row.get('Route', row.get('Link_Route', ''))
                            
                            if status == 'Down':
                                color_hex, status_label, target_layer = '#e60000', '<b style="color:red;">Down</b>', fg_down
                            elif status == 'Potential Down':
                                color_hex, status_label, target_layer = '#ff9900', '<b style="color:orange;">Potential Down (Mains/Batt <18h)</b>', fg_pot
                            else:
                                color_hex, status_label, target_layer = '#00802b', '<b style="color:green;">Up</b>', fg_up

                            alarms_terkait = "<i style='color:gray;'>Tidak ada alarm aktif</i>"
                            start_dt = None
                            for c_k in [row['C2'], row['C3'], row['C1']]:
                                if c_k and c_k in all_alarm_dict: alarms_terkait = all_alarm_dict[c_k]; break
                            for c_k in [row['C2'], row['C3'], row['C1']]:
                                if c_k and c_k in min_occurrence: start_dt = min_occurrence[c_k]; break

                            durasi_str = f" (Durasi: {format_durasi(start_dt)})" if (status in ['Down', 'Potential Down'] and start_dt) else ""
                            
                            route_html_button = f'<hr style="margin: 4px 0;"><a href="{route_link}" target="_blank" style="display:block; text-align:center; background:#1a73e8; color:white; padding:4px; text-decoration:none; border-radius:4px; font-weight:bold; font-size:10px;">🔗 Buka Link Route</a>' if (pd.notnull(route_link) and str(route_link).strip() != "" and str(route_link).lower() != "nan") else ""

                            html_detail = f"""
                            <div style="width: 260px; font-size:11px; color:black; white-space: normal; line-height: 1.3;">
                                <b style="font-size:13px;">{site_name}</b> <br>Site ID: <b>{site_id}</b><br>
                                Status: {status_label}{durasi_str}<br><b>Class:</b> {site_class} | <b>Tipe:</b> {hub_status}<br>
                                <b>Power:</b> {power_type} | <b>Grid:</b> {grid_type}<br><b>Transport:</b> {transport_type}<br>
                                <b>Simpul 4G:</b> {simpul_4g}<br><b>Simpul Telkom:</b> {simpul_telkom}<br><b>Jumlah Anakan:</b> {jumlah_anakan} site<br>
                                <b>Site ID Anakan:</b> <span style="word-break: break-all;">{site_id_anakan}</span>
                                <hr style="margin: 4px 0;"><b style="font-size:10px;">Daftar Alarm:</b><br>
                                <div style="font-size:9.5px; line-height:1.2; background:#f1f1f1; padding:4px; border-radius:4px;">
                                    {alarms_terkait}</div>{route_html_button}
                            </div>
                            """
                            
                            if is_hub: shape_html = f'<div style="color:{color_hex}; font-size:18px; margin-top:-4px; margin-left:-2px; text-shadow: -1px -1px 0 #FFF, 1px -1px 0 #FFF, -1px 1px 0 #FFF, 1px 1px 0 #FFF, 0px 0px 4px rgba(0,0,0,0.6);">★</div>'
                            else: shape_html = f'<div style="width:12px; height:12px; background-color:{color_hex}; border:2px solid white; border-radius:50%; box-shadow:0px 0px 3px rgba(0,0,0,0.6);"></div>'
                            
                            folium.Marker(
                                location=[lat, lon],
                                icon=folium.DivIcon(html=f'<div style="position:relative; width:12px; height:12px;">{shape_html}</div>', icon_size=(12, 12), icon_anchor=(6, 6)),
                                tooltip=folium.Tooltip(html_detail)
                            ).add_to(target_layer)
                            
                            if ne_id in suggested_up_ids and status == 'Up' and ne_id.lower() not in ['', 'nan']:
                                rec_html = f'<div style="position:relative; width:16px; height:16px; margin-top:-2px; margin-left:-2px;"><div style="width:16px; height:16px; background-color:#0066ff; border:2px solid white; border-radius:50%; box-shadow:0px 0px 4px rgba(0,0,0,0.8);"></div></div>'
                                folium.Marker(
                                    location=[lat, lon], 
                                    icon=folium.DivIcon(html=rec_html), 
                                    tooltip=folium.Tooltip(html_detail)
                                ).add_to(fg_rec)
                            
                            label_html = f'<div style="position:absolute; left:14px; top:-2px; font-size:10px; font-weight:bold; color:{color_hex}; text-shadow:-1px -1px 0 #FFF,1px -1px 0 #FFF,-1px 1px 0 #FFF,1px 1px 0 #FFF,0px 0px 3px #FFF; white-space:nowrap;">{site_id}</div>'
                            folium.Marker(location=[lat, lon], icon=folium.DivIcon(html=f'<div style="position:relative; width:12px; height:12px;">{label_html}</div>', icon_size=(12, 12), icon_anchor=(6, 6))).add_to(fg_id)

                        m.add_child(fg_down)
                        m.add_child(fg_pot)
                        m.add_child(fg_up)
                        m.add_child(fg_rec)
                        m.add_child(fg_id)
                        m.add_child(fg_hub)
                        
                        folium.LayerControl(position='topright', collapsed=True).add_to(m)
                        
                        st_folium(m, use_container_width=True, height=520, returned_objects=[])
                    else:
                        st.warning("Tidak ada data site pada area yang dipilih.")

            st.divider()
            
            if st.session_state.status_filter == 'All':
                df_followup = df_map[df_map['Status'].isin(['Down', 'Potential Down'])].copy()
                st.subheader("📋 Detail Site (Follow Up: Down & Potential Down)")
            elif st.session_state.status_filter == 'Up':
                df_followup = df_map[df_map['Status'] == 'Up'].copy()
                st.subheader("📋 Detail Site (Status Up)")
            else:
                df_followup = df_map[df_map['Status'] == st.session_state.status_filter].copy()
                st.subheader(f"📋 Detail Site (Status {st.session_state.status_filter})")

            if not df_followup.empty:
                def get_down_time(row):
                    for c in [row['C2'], row['C3'], row['C1']]:
                        if c in min_occurrence: return min_occurrence[c]
                    return pd.NaT

                df_followup['Occurrence_Time'] = df_followup.apply(get_down_time, axis=1)
                df_followup = df_followup.sort_values(by='Occurrence_Time', ascending=True, na_position='last')
                df_followup['Durasi Alarm'] = df_followup['Occurrence_Time'].apply(format_durasi)
                df_followup['Suggestion (Nearest Up)'] = df_followup.index.map(suggestion_site_ids)
                df_followup = df_followup.explode('Suggestion (Nearest Up)')
                
                kolom_detail = {
                    'Site_ID': 'Site ID', 'Site_Name': 'Site Name', 'Status': 'Status', 'Site Class': 'Site Class',
                    'Kota/Kab': 'Kabupaten', 'Kecamatan': 'Kecamatan', 'POWER TYPE': 'Tipe Power',
                    'Grid Category New': 'Grid', 'Hub site': 'Hub/Non Hub', 'Simpul 4G': 'Simpul 4G',
                    'Durasi Alarm': 'Durasi Alarm', 'Suggestion (Nearest Up)': 'Recommend to Optim crowd'
                }
                
                df_detail_final = df_followup[[k for k in kolom_detail.keys() if k in df_followup.columns]].rename(columns=kolom_detail)
                if 'Site ID' in df_detail_final.columns: df_detail_final = df_detail_final.set_index('Site ID')
                st.dataframe(df_detail_final, height=350, use_container_width=True)
            else:
                st.info("🎉 Tidak ada data site yang perlu di-follow up pada filter saat ini.")
                    
        except Exception as e:
            st.error(f"🚨 Terjadi kesalahan saat memproses data: {e}")
            st.exception(e)

# --- FOOTER CUSTOM ---
st.markdown("<hr style='margin: 3rem 0 1rem 0;'/><p style='text-align: center; color: #888; font-size: 14px;'>© 2026 | Created with ❤️ by Fauzi Ramdani - 97122</p>", unsafe_allow_html=True)
