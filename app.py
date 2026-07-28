import streamlit as st
import pandas as pd
import folium
import re
from streamlit_folium import st_folium

st.set_page_config(page_title="Site Down/Up Mapping", layout="wide")
st.title("🗺️ Mapping Status Site (Up/Down)")
st.markdown("Dashboard ini narik data Dapot langsung dari Google Sheets dan mencocokkannya dengan file UME.")

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
            
            # --- FIX LOGIC: EXTRACT ID NUMBER ONLY ---
            # Karena ME ID di UME itu "287021" dan di Dapot itu "MRB021", kita ekstrak angkanya
            def get_number_only(text):
                try:
                    text_str = str(text)
                    # Hapus .0 kalau format float
                    if text_str.endswith('.0'):
                        text_str = text_str[:-2]
                    # Ambil digit angka aja dari text
                    numbers = re.findall(r'\d+', text_str)
                    return numbers[0] if numbers else text_str
                except:
                    return str(text)

            if 'ME ID' in df_ume.columns:
                df_ume['ME_NUM'] = df_ume['ME ID'].apply(get_number_only)
            else:
                st.error("Kolom 'ME ID' ga ada!")
                st.stop()
                
            if 'Site_ID' in df_dapot.columns:
                df_dapot['SITE_NUM'] = df_dapot['Site_ID'].apply(get_number_only)
            else:
                st.error("Kolom 'Site_ID' ga ada!")
                st.stop()

            # Rule Filter Down
            cond_power = (df_ume['Alarm Code Name'].str.contains('Input power-off', case=False, na=False)) & \
                         (df_ume['Position'].astype(str).str.contains('Equipment=1', case=False, na=False))
            
            cond_link1 = (df_ume['Specific Problem'].str.contains('The link between the server and the ME is broken', case=False, na=False)) | \
                         (df_ume['Alarm Code Name'].str.contains('The link between the server and the ME is broken', case=False, na=False))
            
            cond_link2 = (df_ume['Specific Problem'].str.contains('Site Abis control link broken', case=False, na=False)) | \
                         (df_ume['Alarm Code Name'].str.contains('Site Abis control link broken', case=False, na=False))
            
            df_down = df_ume[cond_power | cond_link1 | cond_link2]
                             
            site_down_list = df_down['ME_NUM'].dropna().unique()
            
            # Tentukan Status
            df_dapot['Status'] = df_dapot['SITE_NUM'].apply(lambda x: 'Down' if x in site_down_list else 'Up')
            
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
                    site_id = row['Site_ID']
                    status = row['Status']
                    
                    color = 'red' if status == 'Down' else 'green'
                    
                    popup_html = f"<b>{site_id}</b><br>{site_name}<br>Status: {status}"
                    
                    # Tooltip muncul pas di-hover (efek seperti zoom reveal teks)
                    # Marker dibikin lingkaran kecil bersih
                    folium.CircleMarker(
                        location=[lat, lon],
                        radius=4,
                        color=color,
                        weight=1,
                        fill=True,
                        fill_color=color,
                        fill_opacity=0.8,
                        popup=folium.Popup(popup_html, max_width=300),
                        tooltip=f"{site_id}" # Munculin teks ID pas kursor diarahkan!
                    ).add_to(m)
                
                st_folium(m, width=1200, height=600)
                
                col_up, col_down = st.columns(2)
                up_count = len(df_dapot[df_dapot['Status'] == 'Up'])
                down_count = len(df_dapot[df_dapot['Status'] == 'Down'])
                
                col_up.success(f"✅ Total Site Up: {up_count}")
                col_down.error(f"🚨 Total Site Down: {down_count}")
                
                if down_count > 0:
                    st.write("**Detail Site Down:**")
                    st.dataframe(df_dapot[df_dapot['Status'] == 'Down'][['Site_ID', 'Site_Name', 'LAT', 'LONG']], use_container_width=True)
            else:
                st.error("Kolom 'LAT' dan 'LONG' wajib ada!")
                
        except Exception as e:
            st.error(f"Error pas narik/proses: {e}")
