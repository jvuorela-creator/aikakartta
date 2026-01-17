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

# --- 2. Session State (Välimuisti) ---
if 'processed_data' not in st.session_state:
    st.session_state.processed_data = None
if 'current_file' not in st.session_state:
    st.session_state.current_file = None

# --- 3. Apufunktiot ---

def detect_encoding(file_bytes):
    """Tunnistaa tiedoston merkistökoodauksen (UTF-8, ANSEL, yms)."""
    result = chardet.detect(file_bytes)
    return result['encoding']

def parse_gedcom(file_path):
    """Lukee GEDCOM-tiedoston ja etsii syntymätiedot."""
    data = []
    try:
        with GedcomReader(file_path) as parser:
            # Iteroidaan kaikki henkilöt (INDI)
            for indi in parser.records0("INDI"):
                if not indi.name:
                    continue

                # Nimen haku turvallisesti
                try:
                    given = indi.name.given if indi.name.given else ""
                    surname = indi.name.surname if indi.name.surname else ""
                    full_name = f"{given} {surname}".strip()
                except:
                    full_name = "Tuntematon"
                
                # Etsitään syntymätapahtuma (BIRT)
                birt = indi.sub_tag("BIRT")
                if birt:
                    date_val = birt.sub_tag_value("DATE")
                    place_val = birt.sub_tag_value("PLAC")
                    
                    if place_val:
                        year = None
                        if date_val:
                            # Etsitään vuosiluku (4 numeroa)
                            years = re.findall(r'\d{4}', str(date_val))
                            if years:
                                year = int(years[-1])
                        
                        # Lisätään listaan vain jos vuosi ja paikka löytyvät
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
    """Hakee koordinaatit Nominatim-palvelusta viiveellä."""
    # User-agent on pakollinen
    geolocator = Nominatim(user_agent="sukututkimus_kartta_final_fix")
    coords = {}
    total = len(places_list)
    
    # UI-elementit edistymiselle
    status_text = st.empty()
    my_bar = st.progress(0)
    
    # Lasketaan arvioitu kesto
    arvio_sekunnit = total * 1.1
    
    # VIRHEEN KORJAUS: Lasketaan aika selkeästi erikseen
    minuutit = int(arvio_sekunnit / 60)
    sekunnit = int(arvio_sekunnit % 60)
    
    if minuutit > 0:
        aika_str = f"{minuutit} min {sekunnit} sek"
    else:
        aika_str = f"{sekunnit} sek"

    status_text.write(f"Haetaan koordinaatteja {total} paikkakunnalle... Arvioitu kesto: {aika_str}. Älä sulje selainta.")

    for i, place in enumerate(places_list):
        clean_place = place.split(',')[0] # Otetaan vain ensimmäinen osa (esim. "Turku" tekstistä "Turku, Finland")
        
        try:
            # Pakollinen viive palvelun ehtojen mukaan (min 1 sek)
            time.sleep(1.1) 
            
            # 1. Haku koko nimellä
            location = geolocator.geocode(place, timeout=10)
            
            if location:
                coords[place] = (location.latitude, location.longitude)
            else:
                # 2. Fallback: Haku pelkällä paikkakunnalla
                location = geolocator.geocode(clean_place, timeout=10)
                if location:
                     coords[place] = (location.latitude, location.longitude)
                else:
                    coords[place] = (None, None)
                    
        except (GeocoderTimedOut, GeocoderServiceError):
            time.sleep(2) # Odotetaan pidempään virhetilanteessa
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
    """Luo GeoJSON-datan aikajana-animaatiota varten."""
    features = []
    for _, row in df.iterrows():
        # Aikaleima ISO-muodossa
        time_str = f"{row['Vuosi']}-01-01"
        
        feature = {
            'type': 'Feature',
            'geometry': {
                'type': 'Point',
                'coordinates': [row['lon'], row['lat']], # GeoJSON: lon, lat
            },
            'properties': {
                '
