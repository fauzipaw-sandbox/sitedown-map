import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="Site Down/Up Mapping", layout="wide")
st.title("🗺️ Mapping Status Site (Up/Down)")
st.markdown("Dashboard ini narik data Dapot langsung dari Google Sheets dan mencocokkannya dengan file UME. **[Responsive Mode]**")

SHEET_URL = "https://docs.google.com/spreadsheets/d/11pp1YavJsR6wnYcvs0Z6B94KM75clu7FQgRy7sdEQ4g/export?format=csv&gid=0"

@st.cache_data(ttl=600)
def load_dapot():
    try:
        df = pd.read_csv(SHEET_URL)
        return df
    except Exception as e:
        st.error(f"Gagal narik data Dapot. Pastiin akses link 'Anyone with the link can view'. Error: {e}")
        return None

with st.spinner('Lagi narik data Dapot...'):
    df_dapot = load_dapot()

if df_dapot is not None:
    st.success("✅ Data Dapot ditarik!")
    
    st.subheader("Upload Data UME (fm-active)")
    ume_file = st.file_uploader("Upload UME Alarm Monitor (Excel)", type=['xlsx'])

    if ume_file:
        try:
            df_ume = pd.read_excel(ume_file)
            
            # --- LOGIC: Match ME ID (UME) ke NE ID (Dapot) ---
            def clean_id(text):
                val = str(text).strip()
                if val.endswith('.0'):
                    return val[:-2]
                return val

            if 'ME ID' in df_ume.columns:
                df_ume['ME_CLEAN'] = df_ume['ME ID'].apply(clean_id)
            else:
                st.error("Kolom 'ME ID' tidak ditemukan di file UME!")
                st.stop()
                
            if 'NE ID' in df_dapot.columns:
                df_dapot['NE_CLEAN'] = df_dapot['NE ID'].apply(clean_id)
            else:
                st.error("Kolom 'NE ID' tidak ditemukan di file Dapot!")
                st.stop()

            # --- RULE FILTERING ALARM DOWN ---
            cond_power = (df_ume['Alarm Code Name'].str.contains('Input power-off', case=False, na=False)) & \
                         (df_ume['Position'].astype(str).str.contains('Equipment=1', case=False, na=False))
            
            cond_link1 = (df_ume['Specific Problem'].str.contains('The link between the server and the ME is broken', case=False, na=False)) | \
                         (df_ume['Alarm Code Name'].str.contains('The link between the server and the ME is broken', case=False, na=False))
            
            cond_link2 = (df_ume['Specific Problem'].str.contains('Site Abis control link broken', case=False, na=False)) | \
                         (df_ume['Alarm Code Name'].str.contains('Site Abis control link broken', case=False, na=False))
            
            df_down = df_ume[cond_power | cond_link1 | cond_link2].copy()
            
            # --- BIKIN DICTIONARY ALARM BUAT POPUP ---
            # Menggabungkan nama alarm dan waktunya
            if 'Occurrence Time' in df_down.columns:
                df_down['Alarm_Detail'] = "• " + df_down['Alarm Code Name'].astype(str) + " (" + df_down['Occurrence Time'].astype(str) + ")"
            else:
                df_down['Alarm_Detail'] = "• " + df_down['Alarm Code Name'].astype(str)
            
            # Grouping alarm berdasarkan ME ID biar kalau 1 site ada 3 alarm, kerangkum semua
            alarm_dict = df_down.groupby('ME_CLEAN')['Alarm_Detail'].apply(lambda x: "<br>".join(x)).to_dict()
                             
            site_down_list = df_down['ME_CLEAN'].dropna().unique()
            
            # Tentukan Status
            df_dapot['Status'] = df_dapot['NE_CLEAN'].apply(lambda x: 'Down' if x in site_down_list else 'Up')
            
            st.divider()
            
            # --- RESPONSIVE LAYOUT SUMMARY ---
            st.subheader("📊 Summary Status Site")
            col_up, col_down = st.columns(2)
            up_count = len(df_dapot[df_dapot['Status'] == 'Up'])
            down_count = len(df_dapot[df_dapot['Status'] == 'Down'])
            
            col_up.success(f"✅ **Total Site Up:** {up_count}")
            col_down.error(f"🚨 **Total Site Down:** {down_count}")
            
            # Menampilkan breakdown breakdown dengan Tabs biar responsif dan nggak menuhin layar
            if down_count > 0:
                df_dapot_down = df_dapot[df_dapot['Status'] == 'Down']
                
                tab1, tab2, tab3, tab4 = st.tabs(["🏙️ By Kabupaten", "🏘️ By Kecamatan", "📡 By Hub Site", "📋 Detail All Data"])
                
                with tab1:
                    if 'Kota/Kab' in df_dapot_down.columns:
                        st.dataframe(df_dapot_down['Kota/Kab'].value_counts().reset_index().rename(columns={'count':'Jumlah Down', 'Kota/Kab':'Kabupaten'}), use_container_width=True)
                
                with tab2:
                    if 'Kecamatan' in df_dapot_down.columns:
                        st.dataframe(df_dapot_down['Kecamatan'].value_counts().reset_index().rename(columns={'count':'Jumlah Down'}), use_container_width=True)
                        
                with tab3:
                    if 'Hub site' in df_dapot_down.columns:
                        # Isi yang kosong dengan 'Non Hub'
                        hub_counts = df_dapot_down['Hub site'].fillna('Non Hub').value_counts().reset_index().rename(columns={'count':'Jumlah Down'})
                        st.dataframe(hub_counts, use_container_width=True)
                        
                with tab4:
                    st.dataframe(df_dapot_down[['Site_ID', 'NE ID', 'Site_Name', 'Kota/Kab', 'Kecamatan', 'Hub site', 'LAT', 'LONG']], use_container_width=True)

            st.divider()
            st.subheader("📍 Peta Persebaran Site")
            
            if 'LAT' in df_dapot.columns and 'LONG' in df_dapot.columns:
                df_dapot['LAT'] = df_dapot['LAT'].astype(str).str.replace(',', '.').astype(float)
                df_dapot['LONG'] = df_dapot['LONG'].astype(str).str.replace(',', '.').astype(float)
                df_dapot = df_dapot.dropna(subset=['LAT', 'LONG'])
                
                center_lat = df_dapot['LAT'].mean()
                center_lon = df_dapot['LONG'].mean()
                
                m = folium.Map(location=[center_lat, center_lon], zoom_start=11)
                
                for idx, row in df_dapot.iterrows():
                    lat = row['LAT']
                    lon = row['LONG']
                    site_name = row.get('Site_Name', 'Unknown')
                    site_id = row.get('Site_ID', 'Unknown')
                    ne_id = row.get('NE_CLEAN', 'Unknown')
                    status = row['Status']
                    
                    color = 'red' if status == 'Down' else 'green'
                    
                    # Konfigurasi Popup Maps Custom
                    if status == 'Down':
                        alarms_terkait = alarm_dict.get(ne_id, "Data alarm tidak terbaca")
                        popup_html = f"""
                        <div style="min-width: 250px;">
                            <b>Site ID: {site_id}</b><br>
                            NE ID: {ne_id}<br>
                            {site_name}<br>
                            Status: <b style="color:red;">{status}</b>
                            <hr style="margin: 5px 0;">
                            <b style="font-size:12px;">Daftar Alarm:</b><br>
                            <div style="font-size:11px; max-height:120px; overflow-y:auto; background-color:#f9f9f9; padding:5px; border-radius:4px;">
                                {alarms_terkait}
                            </div>
                        </div>
                        """
                    else:
                        popup_html = f"<b>Site ID: {site_id}</b><br>NE ID: {ne_id}<br>{site_name}<br>Status: <b style='color:green;'>{status}</b>"
                    
                    folium.CircleMarker(
                        location=[lat, lon],
                        radius=4,
                        color=color,
                        weight=1,
                        fill=True,
                        fill_color=color,
                        fill_opacity=0.8,
                        popup=folium.Popup(popup_html, max_width=400),
                        tooltip=f"{site_id}" 
                    ).add_to(m)
                
                # use_container_width=True bikin maps otomatis nyesuain lebar layar hp/laptop
                st_folium(m, use_container_width=True, height=600, returned_objects=[])
                
            else:
                st.error("Kolom 'LAT' dan 'LONG' wajib ada di Dapot!")
                
        except Exception as e:
            st.error(f"Error pas narik/proses: {e}")
