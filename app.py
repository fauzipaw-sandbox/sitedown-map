import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="Site Down/Up Mapping", layout="wide")
st.title("🗺️ Mapping Status Site (Up/Down)")
st.markdown("Dashboard ini mencocokkan data Dapot dengan file UME (fm-active) untuk memetakan site mana yang Down (Merah) dan Up (Hijau).")

col1, col2 = st.columns(2)
with col1:
    st.subheader("1. Upload Data Dapot")
    dapot_file = st.file_uploader("Upload Dapot (Wajib ada kolom: Site ID, Site Name, Latitude, Longitude)", type=['xlsx', 'csv'])

with col2:
    st.subheader("2. Upload Data UME (fm-active)")
    ume_file = st.file_uploader("Upload UME Alarm Monitor (Excel)", type=['xlsx'])

if dapot_file and ume_file:
    try:
        # Baca Dapot
        if dapot_file.name.endswith('.csv'):
            df_dapot = pd.read_csv(dapot_file)
        else:
            df_dapot = pd.read_excel(dapot_file)
            
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
            
        if 'Site ID' in df_dapot.columns:
            df_dapot['Site ID Clean'] = df_dapot['Site ID'].apply(clean_id)
        else:
            st.error("Kolom 'Site ID' tidak ditemukan di file Dapot!")
            st.stop()

        # Rule Down 2G dan 4G
        # 199087337 -> Site Abis control link broken (2G down)
        # 1014 -> The link between the server and the ME is broken (4G down)
        target_codes = [199087337, 1014]
        target_names = ['Site Abis control link broken', 'The link between the server and the ME is broken']
        
        # Filter ume yang down
        df_down = df_ume[(df_ume['Alarm Code'].isin(target_codes)) | 
                         (df_ume['Specific Problem'].isin(target_names)) | 
                         (df_ume['Alarm Code Name'].isin(target_names))]
                         
        site_down_list = df_down['ME ID Clean'].dropna().unique()
        
        # Tentukan Status
        df_dapot['Status'] = df_dapot['Site ID Clean'].apply(lambda x: 'Down' if x in site_down_list else 'Up')
        
        st.divider()
        st.subheader("📍 Peta Persebaran Site")
        
        # Bikin Map
        if 'Latitude' in df_dapot.columns and 'Longitude' in df_dapot.columns:
            # Konversi comma jadi titik kalau format lat/longnya pake koma Indo, lalu casting ke float
            df_dapot['Latitude'] = df_dapot['Latitude'].astype(str).str.replace(',', '.').astype(float)
            df_dapot['Longitude'] = df_dapot['Longitude'].astype(str).str.replace(',', '.').astype(float)
            
            center_lat = df_dapot['Latitude'].mean()
            center_lon = df_dapot['Longitude'].mean()
            
            m = folium.Map(location=[center_lat, center_lon], zoom_start=10)
            
            for idx, row in df_dapot.iterrows():
                lat = row['Latitude']
                lon = row['Longitude']
                site_name = row.get('Site Name', 'Unknown')
                site_id = row['Site ID']
                status = row['Status']
                
                if status == 'Down':
                    color = 'red'
                    icon = 'remove-sign'
                else:
                    color = 'green'
                    icon = 'ok-sign'
                    
                popup_text = f"<b>Site Name:</b> {site_name}<br><b>Site ID:</b> {site_id}<br><b>Status:</b> {status}"
                folium.Marker(
                    location=[lat, lon],
                    popup=folium.Popup(popup_text, max_width=300),
                    icon=folium.Icon(color=color, icon=icon)
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
                st.dataframe(df_dapot[df_dapot['Status'] == 'Down'][['Site ID', 'Site Name', 'Latitude', 'Longitude']], use_container_width=True)
        else:
            st.error("Kolom 'Latitude' dan 'Longitude' wajib ada di file Dapot!")
            
    except Exception as e:
        st.error(f"Terjadi error pas narik data: {e}")
