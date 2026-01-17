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
    geolocator = Nominatim(user_agent="sukututkimus_kartta_app_v4")
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1.1)
    
    coords = {}
    total = len(places_list)
    
    # Progress bar luodaan tässä, mutta käytetään vain jos lista on pitkä
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

# Jos uusi tiedosto ladataan, nollataan vanha data
if uploaded_file is not None:
    # Tarkistetaan onko tiedosto vaihtunut (yksinkertainen tarkistus)
    if 'current_file' not in st.session_state or st.session_state.current_file != uploaded_file.name:
