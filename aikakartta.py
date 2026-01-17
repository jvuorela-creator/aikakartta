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
    geolocator = Nominatim(user_agent="sukututkimus_testi_korjattu")
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
        aika_str = f"{int(ar
