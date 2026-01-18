import streamlit as st
import pandas as pd
import tempfile
import os
import re
import time
from ged4py.parser import GedcomReader
from geopy.geocoders import Nominatim
import folium
from folium.plugins import TimestampedGeoJson
from streamlit_folium import st_folium

# --- 1. ASETUKSET ---
st.set_page_config(page_title="Sukututkimuskartta", layout="wide")
st.title("Sukututkimuskartta: Korjattu Animaatio")

CACHE_FILE = "tallennetut_paikat.csv"

# --- 2. APUFUNKTIOT ---

def load_local_cache():
    if os.path.exists(CACHE_FILE):
        try:
            df = pd.read_csv(CACHE_FILE, header=None, names=["Paikka", "Lat", "Lon"])
            cache = {}
            for _, row in df.iterrows():
                cache[row['Paikka']] = (row['Lat'], row['Lon'])
            return cache
        except:
            return {}
    return {}

def save_to_cache(place, lat, lon):
    with open(CACHE_FILE, "a", encoding="utf-8") as f:
        f.write(f'"{place}",{lat},{lon}\n')

def parse_gedcom(file_path):
    data_list = []
    try:
        with GedcomReader(file_path) as parser:
            for indi in parser.records0("INDI"):
                if not indi.name: continue
                
                full_name = "Tuntematon"
                try:
                    g = indi.name.given or ""
                    s = indi.name.surname or ""
                    full_name = (g + " " + s).strip()
                except: pass
                
                birt = indi.sub_tag("BIRT")
                if birt:
                    date_val = birt.sub_tag_value("DATE")
                    place_val = birt.sub_tag_value("PLAC")
                    
                    if place_val and date_val:
                        # Etsitään kaikki 4-numeroiset luvut
                        years = re.findall(r'\d{4}', str(date_val))
                        if years:
                            # Otetaan viimeinen (usein tarkin vuosi)
                            y = int(years[-1])
                            # Suodatetaan epärealistiset vuodet pois
                            if 1000 < y < 2100:
                                data_list.append({
                                    "Nimi": full_name,
                                    "Vuosi": y,
                                    "Paikka": str(place_val)
                                })
    except Exception as e:
        st.error(f"Virhe GEDCOM-luvussa: {e}")
        return []
    return data_list

@st.cache_data
def get_coordinates_smart(places_list):
    local_cache = load_local_cache()
    geolocator = Nominatim(user_agent="aikakartta_final_fix_v2")
    coords = {}
    
    to_fetch = []
    for p in places_list:
        if p in local_cache:
            coords[p] = local_cache[p]
        else:
            to_fetch.append(p)
            
    if not to_fetch:
        return coords

    st.info(f"Haetaan verkosta {len(to_fetch)} puuttuvaa paikkaa...")
    bar = st.progress(0)
    status = st.empty()

    for i, place in enumerate(to_fetch):
        lat, lon = None, None
        clean_place = place.split(',')[0]
        
        try:
            time.sleep(1.2)
            loc = geolocator.geocode(place, timeout=10)
            if loc:
                lat, lon = loc.latitude, loc.longitude
            else:
                loc = geolocator.geocode(clean_place, timeout=10)
                if loc:
                    lat, lon = loc.latitude, loc.longitude
        except Exception:
            time.sleep(2)
        
        if lat is not None:
            coords[place] = (lat, lon)
            save_to_cache(place, lat, lon)
        else:
            coords[place] = (None, None)
            
        bar.progress(int((i + 1) / len(to_fetch) * 100))
        status.write(f"Haetaan: {place}")

    status.empty()
    bar.empty()
    return coords

def create_features(df):
    features = []
    for _, row in df.iterrows():
        # PAKOTETAAN AIKA STR-MUOTOON 'YYYY-MM-DD'
        # Tämä on kriittisin kohta animaation toimivuudelle
        time_str = f"{int(row['Vuosi'])}-01-01"
        
        popup_txt = f"{row['Vuosi']}: {row['Nimi']}, {row['Paikka']}"
        
        feat = {
            'type': 'Feature',
            'geometry': {
                'type': 'Point',
                'coordinates': [row['lon'], row['lat']],
            },
            'properties': {
                'time': time_str, # Tämän pitää olla string, ei number
                'popup': popup_txt,
                'icon': 'circle',
                'iconstyle': {
                    'fillColor': 'blue',
                    'fillOpacity': 0.8,
                    'stroke
