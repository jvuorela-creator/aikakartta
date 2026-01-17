import streamlit as st
import pandas as pd
import tempfile
import os
import re
import time
from ged4py.parser import GedcomReader
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
import folium
from folium.plugins import TimestampedGeoJson
from streamlit_folium import st_folium
import chardet

# --- 1. Asetukset ---
st.set_page_config(page_title="Sukututkimuskartta", layout="wide")

st.title("📍 Sukututkimuskartta: Aikajana")
st.markdown("Pisteet ilmestyvät kartalle syntymävuoden mukaan ja jäävät näkyviin.")

# --- 2. Session State ---
if 'processed_data' not in st.session_state:
    st.session_state.processed_data = None
if 'current_file' not in st.session_state:
    st.session_state.current_file = None

# --- 3. Apufunktiot ---

def parse_gedcom(file_path):
    data = []
    try:
        with GedcomReader(file_path) as parser:
            for indi in parser.records0("INDI"):
                if not indi.name:
                    continue
                try:
                    given = indi.name.given if indi.name.given else ""
                    surname = indi.name.surname if indi.name.surname else ""
                    full_name = f"{given} {surname}".strip()
                except:
                    full_name = "Tuntematon"
                
                birt = indi.sub_tag("BIRT")
                if birt:
                    date_val = birt.sub_tag_value("DATE")
                    place_val = birt.sub_tag_value("PLAC")
                    
                    if place_val:
                        year = None
                        if date_val:
                            years = re.findall(r'\d{4}', str(date_val))
                            if years:
                                year = int(years[-1])
                        
                        if year and place_val:
                            data.append({
                                "Nimi": full_name,
                                "Vuosi": year,
                                "Paikka": str(place_val)
                            })
    except Exception as e:
        st.error(f"Virhe tiedoston lukemisessa: {e}")
        return []
    return data

@st.cache_data
def get_coordinates(places_list):
    geolocator = Nominatim(user_agent="aikakartta_fix_v10")
    coords = {}
    total = len(places_list)
    
    status_text = st.empty()
    my_bar = st.progress(0)
    
    arvio = total * 1.1
    aika_str = f"{int(arvio/60)} min {int(arvio%60)} sek"
    status_text.write(f"Haetaan koordinaatteja {total} paikkakunnalle... Arvio: {aika_str}.")

    for i, place in enumerate(places_list):
        clean_place = place.split(',')[0]
        try:
            time.sleep(1.1) 
            location = geolocator.geocode(place, timeout=10)
            if location:
                coords[place] = (location.latitude, location.longitude)
            else:
                location = geolocator.geocode(clean_place, timeout=10)
                if location:
                     coords[place] = (location.latitude, location.longitude)
                else:
                    coords[place] = (None, None)
        except:
            time.sleep(2)
            coords[place] = (None, None)
            
        my_bar.progress(int((i + 1) / total * 100))
        status_text.write(f"Käsitellään: {place} ({i+1}/{total})")
    
    status_text.success("Valmis!")
    time.sleep(1)
    status_text.empty()
    my_bar.empty()
    return coords

def create_geojson_features(df):
    features = []
    for _, row in df.iterrows():
        # TimestampedGeoJson vaatii tarkan päivämäärämuodon
        time_str = f"{row['Vuosi']}-01-01"
        
        feature = {
            'type': 'Feature',
            'geometry': {
                'type': 'Point',
                'coordinates': [row['lon'], row['lat']],
            },
            'properties': {
                'time': time_str,
                # Tärkeää: Icon-tyylit määritellään tässä
                'icon': 'circle',
                'iconstyle': {
                    'fillColor': 'blue',
                    'fillOpacity': 0.8,
                    'stroke': 'false',
                    'radius': 6
                },
                'popup': f"{row['Vuosi']}: {row['Nimi']}, {row['Paikka']}",
            }
        }
        features.append(feature)
    return features

# --- 4. Pääohjelma ---

col1, col2 = st.columns([1, 2])

with col1:
    uploaded_file = st.file_uploader("1. Lataa GEDCOM", type=["ged"])
    st.write("---")
    test_mode = st.checkbox("⚡ Pikatesti (vain 15 paikkaa)", value=True)
    run_btn = st.button("2. Luo kartta")

if uploaded_file is not None:
    if st.session_state.current_file != uploaded_file.name:
        st.session_state.processed_data = None
        st.session_state.current_file = uploaded_file.name

    if run_btn:
        raw_data = uploaded_file.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ged") as tmp_file:
            tmp_file.write(raw_data)
            tmp_file_path = tmp_file.name

        with st.spinner("Luetaan dataa..."):
            parsed_data = parse_gedcom(tmp_file_path)
        os.remove(tmp_file_path)

        if not parsed_data:
            st.error("Ei tietoja.")
        else:
            df = pd.DataFrame(parsed_data)
            unique_places = df['Paikka'].unique().tolist()
            
            if test_mode:
                unique_places = unique_places[:15]
            
            coords_dict = get_coordinates(unique_places)
            
            df['lat'] = df['Paikka'].map(lambda x: coords_dict.get(x, (None, None))[0])
            df['lon'] = df['Paikka'].map(lambda x: coords_dict.get(x, (None, None))[1])
            
            if test_mode:
                df = df[df['Paikka'].isin(coords_dict.keys())]

            df_clean = df.dropna(subset=['lat', 'lon']).copy()
            
            if df_clean.empty:
                st.error("Ei koordinaatteja.")
            else:
                st.session_state.processed_data = df_clean

# --- 5. Tulostus ---

with col2:
    if st.session_state.processed_data is not None:
        df_display = st.session_state.processed_data.sort_values(by='Vuosi', ascending=True)
        
        # 1. Luodaan peruskartta
        avg_lat = df_display['lat'].mean()
        avg_lon = df_display['lon'].mean()
        m = folium.Map(location=[avg_lat, avg_lon], zoom_start=5)
        
        # 2. Luodaan animaatio-objekti
        features = create_geojson_features(df_display)
        
        TimestampedGeoJson(
            {'type': 'FeatureCollection', 'features': features},
            period='P1Y',       # Aikajana liikkuu vuosi kerrallaan
            duration='P500Y',   # Piste pysyy kartalla 500 vuotta (eli käytännössä aina)
            transition_time=200, # Pehmeä siirtymä (ms)
            auto_play=True,
            loop=False,
            max_speed=10,
            loop_button=True,
            date_options='YYYY',
            time_slider_drag_update=True
        ).add_to(m)

        st.success(f"Kartta valmis! ({len(df_display)} tapahtuma
