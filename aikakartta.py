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
    geolocator = Nominatim(user_agent="aikakartta_v11_final")
    coords = {}
    total = len(places_list)
    
    status_text = st.empty()
    my_bar = st.progress(0)
    
    # Arvioitu kesto
    arvio = total * 1.1
    minuutit = int(arvio / 60)
    sekunnit = int(arvio % 60)
    aika_str = f"{minuutit} min {sekunnit} sek"
    
    status_text.write(f"Haetaan koordinaatteja {total} paikk
