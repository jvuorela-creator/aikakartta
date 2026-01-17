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

# --- Asetukset ---
st.set_page_config(page_title="Sukututkimuskartta", layout="wide")

st.title("📍 Sukututkimuskartta: Aikajana")

# --- Session State ---
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
            # Käydään läpi kaikki henkilöt
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
    """Hakee koordinaatit. Sisältää pakollisen hidastuksen."""
    geolocator = Nominatim(user_agent="sukututkimus_testi_v1")
    coords = {}
    total = len(places_list)
    
    # Luodaan tilaa statusviesteille
    status_text = st.empty()
    my_bar = st.progress(0)
    
    # Arvioitu kesto (1.1s per haku)
    arvio = total * 1.1
    if arvio > 60:
        aika_str = f"{int(arvio/60)} min {int(arvio%60)} sek"
    else:
        aika_str = f"{int(arvio)} sek"

    status_text.write(f"Haetaan koordinaatteja {total} paikkakunnalle... Arvioitu kesto: {aika_str}. Älä sulje selainta.")

    for i, place in enumerate(places_list):
        clean_place = place.split(',')[0]
        
        # PÄIVITYS: Manuaalinen hidastus ja virheensieto
        try:
            time.sleep(1.1) # Pakollinen tauko (Nominatim säännöt)
            
            location = geolocator.geocode(place, timeout=10)
            if location:
                coords[place] = (location.latitude, location.longitude)
            else:
                # Fallback: pelkkä kunta/kylä
                location = geolocator.geocode(clean_place, timeout=10)
                if location:
                     coords[place] = (location.latitude, location.longitude)
                else:
                    coords[place] = (None, None)
        except (GeocoderTimedOut, GeocoderServiceError):
            time.sleep(2) # Odotetaan pidempään jos virhe
            coords[place] = (None, None)
        except Exception:
            coords[place] = (None, None)
            
        # Päivitetään palkkia
        prosentti = int((i + 1) / total * 100)
        my_bar.progress(prosentti)
        status_text.write(f"Käsitellään: {place} ({i+1}/{total})")
    
    status_text.success("Koordinaatit haettu!")
    time.sleep(1)
    status_text.empty()
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
                    'radius': 5
                },
                'popup': f"{row['Vuosi']}: {row['Nimi']}, {row['Paikka']}",
            }
        }
        features.append(feature)
    return features

# --- Pääohjelma ---

col1, col2 = st.columns([1, 2])

with col1:
    uploaded_file = st.file_uploader("1. Lataa GEDCOM", type=["ged"])
    
    st.write("---")
    st.write("### Asetukset")
    # TÄSSÄ ON NOPEUTUS-VALINTA
    test_mode = st.checkbox("⚡ Pikatesti (vain 15 paikkaa)", value=True, help="Valitse tämä nähdäksesi toimiiko kartta heti. Jos otat pois, haku kestää n. 1 sekunti per paikkakunta.")

    run_btn = st.button("2. Luo kartta")

if uploaded_file is not None:
    # Nollataan data jos tiedosto vaihtuu
    if st.session_state.current_file != uploaded_file.name:
        st.session_state.processed_data = None
        st.session_state.current_file = uploaded_file.name

    if run_btn:
        raw_data = uploaded_file.read()
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ged") as tmp_file:
            tmp_file.write(raw_data)
            tmp_file_path = tmp_file.name

        with st.spinner("Luetaan GEDCOM-tiedostoa..."):
            parsed_data = parse_
