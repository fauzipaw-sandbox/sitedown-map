import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="Site Down/Up Mapping", layout="wide")
st.title("🗺️ Mapping Status Site (Up/Down)")
st.markdown("Dashboard ini narik data Dapot langsung dari Google Sheets (Sheet: Data Site) dan mencocokkannya dengan file UME (fm-active) yang lo upload.")

# URL Export CSV dari Google Sheets berdasarkan link yang dikasih
SHEET_URL = "https://docs.google.com/spreadsheets/d/11pp1YavJsR6wnYcvs0Z6B94KM75clu7FQgRy7sdEQ4g/export?format=csv&gid=0"

@st.cache_data(ttl=600) # Cache data 10 menit biar gak lemot narik terus
def load_dapot():
    try:
        df = pd.read_csv(SHEET_URL)
        return df
    except Exception as e:
        st.error(f"Gagal narik data Dapot dari Google Sheets. Pastiin akses link-nya udah diset 'Anyone with the link can view'. Error: {e}")
        return None

# Load Dapot
with st.spinner('Lagi narik data Dapot dari Google Sheets...'):
    df_dapot = load_dapot()

if df_dapot is not None:
    st.success("✅ Data Dapot berhasil ditarik dari Google Sheets!")
    
    st.subheader("Upload Data UME (fm-active)")
    ume_file = st.file_uploader("Upload UME Alarm Monitor (Excel)", type=['xlsx'])

    if ume_file:
        try:
            # Baca UME
            df_ume = pd.read_excel(ume_file)
            
            # Cleaning ID biar gampang dicocokin (hilangkan .0 kalau ada)
            def clean_id(x):
                val = str(x).strip()
                return val[:-2] if val.endswith('.0') else val

            # Ambil kolom ME ID dari UME
            if 'ME ID' in df_ume.columns:
                df_ume['ME ID Clean'] = df_ume['ME ID'].apply(clean_id)
            else:
                st.error("Kolom 'ME ID' tidak ditemukan di file UME!")
                st.stop()
                
            # PENYESUAIAN NAMA KOLOM DAPOT: Site_ID
            if 'Site_ID' in df_dapot.columns:
                df_dapot['Site ID Clean'] = df_dapot['Site_ID'].apply(clean_id)
            else:
                st.error("Kolom 'Site_ID' tidak ditemukan di file Dapot!")
                st.stop()

            # --- RULE FILTERING ALARM DOWN ---
            # 1. Input power-off & Position mengandung 'Equipment=1'
            cond_power = (df_ume['Alarm Code Name'].str.contains('Input power-off', case=False, na=False)) & \
                         (df_ume['Position'].astype(str).str.contains('Equipment=1', case=False, na=False))
            
            # 2. The link between the server and the ME is broken
            cond_link1 = (df_ume['Specific Problem'].str.contains('The link between the server and the ME is broken', case=False, na=False)) | \
                         (df_ume['Alarm Code Name'].str.contains('The link between the server and the ME is broken', case=False, na=False))
            
            # 3. Site Abis control link broken
            cond_link2 = (df_ume['Specific Problem'].str.contains('Site Abis control link broken', case=False, na=False)) | \
                         (df_ume['Alarm Code Name'].str.contains('Site Abis control link broken', case=False, na=False))
            
            # Gabungkan semua kondisi
            df_down = df_ume[cond_power | cond_link1 | cond_link2]
                             
            site_down_list = df_down['ME ID Clean'].dropna().unique()
            
            # Tentukan Status
            df_dapot['Status'] = df_dapot['Site ID Clean'].apply(lambda x: 'Down' if x in site_down_list else 'Up')
            
            st.divider()
            st.subheader("📍 Peta Persebaran Site")
            
            # PENYESUAIAN NAMA KOLOM DAPOT: LAT dan LONG
            if 'LAT' in df_dapot.columns and 'LONG' in df_dapot.columns:
                # Konversi comma jadi titik kalau format lat/longnya pake koma Indo, lalu casting ke float
                df_dapot['LAT'] = df_dapot['LAT'].astype(str).str.replace(',', '.').astype(float)
                df_dapot['LONG'] = df_dapot['LONG'].astype(str).str.replace(',', '.').astype(float)
                
                # Drop baris yang Latitude atau Longitudenya kosong/NaN biar folium ga error
                df_dapot = df_dapot.dropna(subset=['LAT', 'LONG'])
                
                center_lat = df_dapot['LAT'].mean()
                center_lon = df_dapot['LONG'].mean()
                
                m = folium.Map(location=[center_lat, center_lon], zoom_start=10)
                
                for idx, row in df_dapot.iterrows():
                    lat = row['LAT']
                    lon = row['LONG']
                    site_name = row.get('Site_Name', 'Unknown')
                    site_id = row['Site_ID']
                    status = row['Status']
                    
                    if status == 'Down':
                        color = 'red'
                    else:
                        color = 'green'
                        
                    popup_text = f"<b>Site Name:</b> {site_name}<br><b>Site ID:</b> {site_id}<br><b>Status:</b> {status}"
                    
                    # Buat titik (mark) kecil
                    folium.CircleMarker(
                        location=[lat, lon],
                        radius=4, # Ukuran titik
                        color=color,
                        fill=True,
                        fill_color=color,
                        fill_opacity=0.9,
                        popup=folium.Popup(popup_text, max_width=300)
                    ).add_to(m)

                    # Buat label teks Site ID di sebelah titik
                    folium.Marker(
                        location=[lat, lon],
                        icon=folium.DivIcon(
                            icon_size=(150, 36),
                            icon_anchor=(0, 0),
                            html=f'<div style="font-size: 8pt; font-weight: bold; color: {color}; margin-left: 8px; text-shadow: 1px 1px 2px white;">{site_id}</div>'
                        )
                    ).add_to(m)
                
                st_folium(m, width=1200, height=600)
                
                # Summary
                st.subheader("📊 Summary Status")
                col_up, col_down = st.columns(2)
                up_count = len(df_dapot[df_dapot['Status'] == 'Up'])
                down_count = len(df_dapot[df_dapot['Status'] == 'Down'])
                
                col_up.success(f"✅ Total Site Up: {up_count}")
                col_down.error(f"🚨 Total Site Down: {down_count}")
                
                # Tampilkan tabel yang down biar gampang laporannya
                if down_count > 0:
                    st.write("**Detail Site Down:**")
                    st.dataframe(df_dapot[df_dapot['Status'] == 'Down'][['Site_ID', 'Site_Name', 'LAT', 'LONG']], use_container_width=True)
            else:
                st.error("Kolom 'LAT' dan 'LONG' wajib ada di file Dapot!")
                
        except Exception as e:
            st.error(f"Terjadi error pas narik/proses data: {e}")
