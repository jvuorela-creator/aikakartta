import streamlit as st
import pandas as pd
import tempfile
import os
import datetime
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
Pisteet ilmestyvät kartalle aikajärjestyksessä ja jäävät näkyviin.
""")

# --- Apufunktiot ---

def detect_encoding(file_bytes):
    result = chardet.detect(file_bytes)
    return result['encoding']

def parse_gedcom(file_path):
    data = []
    try:
        with GedcomReader(file_path) as parser:
            # KORJAUS: Iteroidaan suoraan objekteja
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
                            import re
                            years = re.findall(r'\d{4}', str(date_val))
                            if years:
                                year = int(years[-1])
                        
                        # Otetaan mukaan vain jos vuosi ja paikka löytyy
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
    geolocator = Nominatim(user_agent="sukututkimus_kartta_v2")
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1.1)
    
    coords = {}
    total = len(places_list)
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
            
        my_bar.progress(int((i + 1) / total * 100), text=f"Haetaan: {place}")
    
    my_bar.empty()
    return coords

def create_geojson_features(df):
    """Luo GeoJSON-datan animaatiota varten."""
    features = []
    current_year = datetime.datetime.now().year + 10 # Pisteet pysyvät näkyvissä tulevaisuuteen asti
    
    for _, row in df.iterrows():
        # Muutetaan vuosi päivämäärästringiksi (esim. 1850-01-01)
        time_str = f"{row['Vuosi']}-01-01"
        # Asetetaan kesto nykypäivään asti, jotta piste ei katoa
        # TimestampedGeoJson ei tue suoraan "endless" kestoa täydellisesti, 
        # mutta kikkailemalla 'times'-listalla tai periodilla se onnistuu.
        # Yksinkertaisin tapa 'jäädä näkyviin' on antaa pisteelle pitkä duration tai käyttää 'add_last_point' logiikkaa
        
        feature = {
            'type': 'Feature',
            'geometry': {
                'type': 'Point',
                'coordinates': [row['lon'], row['lat']],
            },
            'properties': {
                'time': time_str,
                'style': {'color': 'blue
