import streamlit as st
import pandas as pd
import tempfile
import os
import datetime
import re
from ged4py.parser import GedcomReader
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import folium
from folium.plugins import TimestampedGeoJson
from streamlit_folium import st_folium
import chardet

# --- Asetukset ---
st.set_page_config(page_title="Sukututkimuskartta", layout="wide")

st.title("📍 Sukututkimuskartta: Syntymäpaikat")
st.markdown("""
Tämä sovellus animoi sukupuun syntymäpaikat kartalle.
Pisteet ilmestyvät kartalle aikajärjestyksessä.
""")

# --- Alustetaan session_state ---
if 'processed_data' not in st.session_state:
    st.session_state.processed_data = None
if 'current_file' not in st.session_state:
    st.session_state.current_file = None

# --- Apufunktiot ---

def detect_encoding(file_bytes):
    result = chardet.detect(file_bytes)
    return result['encoding']

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
    geolocator = Nominatim(user_agent="sukututkimus_kartta_app_v5")
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1.1)
    
    coords = {}
    total = len(places_list)
    
    if total > 0:
        my_bar = st.progress(0, text="Haetaan koordinaatteja...")
    
    for i, place in enumerate(places_list):
        clean_place = place.split(',')[0]
        try:
            location = geocode(place)
            if location:
                coords[place] = (location.latitude, location.longitude)
            else:
                location = geocode(clean_place)
                if location:
                     coords[place] = (location.latitude, location.longitude)
                else:
                    coords[place] = (None, None)
        except:
            coords[place] = (None, None)
            
        if total > 0:
            my_bar.progress(int((i + 1) / total * 100), text=f"Haetaan: {place}")
    
    if total > 0:
        my_bar.empty()
    return coords

def create_geojson_features(df):
    features = []
    for _, row in df.iterrows():
        time_str = f"{row['Vuosi']}-01-01"
        feature = {
            'type': 'Feature',
            'geometry': {
                'type': 'Point',
                'coordinates': [row['lon'], row['lat']],
            },
            'properties': {
                'time': time_str,
                'style': {'color': 'blue'},
                'icon': 'circle',
                'iconstyle': {
                    'fillColor': 'blue',
                    'fillOpacity': 0.8,
                    'stroke': 'false',
                    'radius': 6
                },
                'popup': f"{row['Nimi']} ({row['Vuosi']})<br>{row['Paikka']}",
            }
        }
        features.append(feature)
    return features

# --- Pääohjelma ---

uploaded_file = st.file_uploader("Lataa GEDCOM-tiedosto (.ged)", type=["ged"])

if uploaded_file is not None:
    # Tarkistetaan onko tiedosto vaihtunut. TÄMÄ ON NYT KORJATTU.
    if st.session_state.current_file != uploaded_file.name:
        st.session_state.processed_data = None
        st.session_state.current_file = uploaded_file.name

    # Analysointinappi
    if st.button("Hae koordinaatit ja luo animaatio"):
        
        # Luetaan tiedosto tavuina
        raw_data = uploaded_file.read()
        
        # Kirjoitetaan väliaikaistiedostoon
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ged") as tmp_file:
            tmp_file.write(raw_data)
            tmp_file_path = tmp_file.name

        with st.spinner("Luetaan sukupuuta..."):
            parsed_data = parse_gedcom(tmp_file_path)
        
        # Siivotaan
        if os.path.exists(tmp_file_path):
            os.remove(tmp_file_path)

        if not parsed_data:
            st.warning("Tiedostosta ei löytynyt sopivia tietoja.")
        else:
            df = pd.DataFrame(parsed_data)
            unique_places = df['Paikka'].unique().tolist()
            
            # Haetaan koordinaatit
            coords_dict = get_coordinates(unique_places)
            
            df['lat'] = df['Paikka'].map(lambda x: coords_dict.get(x, (None, None))[0])
            df['lon'] = df['Paikka'].map(lambda x: coords_dict.get(x, (None, None))[1])
            
            df_clean = df.dropna(subset=['lat', 'lon']).copy()
            
            if df_clean.empty:
                st.error("Ei koordinaatteja.")
            else:
                # Tallennetaan valmis data sessioon
                st.session_state.processed_data = df_clean

# --- Näytetään tulokset ---

if st.session_state.processed_data is not None:
    df_display = st.session_state.processed_data.sort_values(by='Vuosi', ascending=False)
    
    st.success(f"Kartta luotu! Näytetään {len(df_display)} tapahtumaa.")

    # Kartta
    m = folium.Map(location=[64.0, 26.0], zoom_start=5)
    
    features = create_geojson_features(df_display)
    
    TimestampedGeoJson(
        {'type': 'FeatureCollection', 'features': features},
        period='P1Y',
        add_last_point=True,
        auto_play=True,
        loop=False,
        max_speed=10,
        loop_button=True,
        date_options='YYYY',
        time_slider_drag_update=True,
        duration='P100Y'
    ).add_to(m)

    st_folium(m, width=1000, height=800)
    
    st.subheader("Löydetyt ja paikannetut tiedot")
    st.dataframe(df_display[['Vuosi', 'Nimi', 'Paikka']])
