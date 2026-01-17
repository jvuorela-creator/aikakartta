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

# 1. ASETUKSET
st.set_page_config(page_title="Sukututkimuskartta", layout="wide")
st.title("Sukututkimuskartta: Aikajana")
st.write("Lataa GEDCOM-tiedosto nähdäksesi syntymäpaikat kartalla aikajärjestyksessä.")

# 2. ALUSTUKSET
if 'processed_data' not in st.session_state:
    st.session_state.processed_data = None
if 'current_file' not in st.session_state:
    st.session_state.current_file = None

# 3. APUFUNKTIOT

def parse_gedcom(file_path):
    # Lukee GEDCOM-tiedoston ja palauttaa listan syntymatapahtumista
    data_list = []
    try:
        with GedcomReader(file_path) as parser:
            for indi in parser.records0("INDI"):
                if not indi.name:
                    continue
                
                # Nimen haku
                full_name = "Tuntematon"
                try:
                    g = indi.name.given or ""
                    s = indi.name.surname or ""
                    full_name = (g + " " + s).strip()
                except:
                    pass
                
                # Syntyman haku
                birt = indi.sub_tag("BIRT")
                if birt:
                    date_val = birt.sub_tag_value("DATE")
                    place_val = birt.sub_tag_value("PLAC")
                    
                    if place_val and date_val:
                        # Etsi vuosiluku
                        years = re.findall(r'\d{4}', str(date_val))
                        if years:
                            # Lisataan listaan
                            item = {
                                "Nimi": full_name,
                                "Vuosi": int(years[-1]),
                                "Paikka": str(place_val)
                            }
                            data_list.append(item)
    except Exception as e:
        st.error("Virhe tiedoston lukemisessa: " + str(e))
        return []
    return data_list

@st.cache_data
def get_coordinates(places_list):
    # Hakee koordinaatit
    geolocator = Nominatim(user_agent="aikakartta_simple_v1")
    coords = {}
    total = len(places_list)
    
    status = st.empty()
    bar = st.progress(0)
    
    status.write("Haetaan koordinaatteja " + str(total) + " paikkakunnalle...")

    for i, place in enumerate(places_list):
        clean = place.split(',')[0]
        lat = None
        lon = None
        
        try:
            time.sleep(1.1)
            loc = geolocator.geocode(place, timeout=10)
            if loc:
                lat = loc.latitude
                lon = loc.longitude
            else:
                loc = geolocator.geocode(clean, timeout=10)
                if loc:
                    lat = loc.latitude
                    lon = loc.longitude
        except:
            time.sleep(2)
        
        coords[place] = (lat, lon)
        
        # Paivita palkki
        prog = int((i + 1) / total * 100)
        if prog > 100:
            prog = 100
        bar.progress(prog)
        status.write("Kasitellaan: " + str(i+1) + "/" + str(total))
        
    status.success("Valmis!")
    time.sleep(1)
    status.empty()
    bar.empty()
    return coords

def create_features(df):
    # Luo GeoJSON feature-listan
    features = []
    for index, row in df.iterrows():
        # Aikaleima
        time_str = str(row['Vuosi']) + "-01-01"
        popup_txt = str(row['Vuosi']) + ": " + row['Nimi'] + ", " + row['Paikka']
        
        feat = {
            'type': 'Feature',
            'geometry': {
                'type': 'Point',
                'coordinates': [row['lon'], row['lat']],
            },
            'properties': {
                'time': time_str,
                'popup': popup_txt,
                'icon': 'circle',
                'iconstyle': {
                    'fillColor': 'blue',
                    'fillOpacity': 0.8,
                    'stroke': 'false',
                    'radius': 6
                },
                'style': {'color': 'blue'}
            }
        }
        features.append(feat)
    return features

# 4. PAAOHJELMA

upload = st.file_uploader("Lataa GEDCOM (.ged)", type=["ged"])
st.write("---")
do_test = st.checkbox("Pikatesti (vain 15 paikkaa)", value=True)
btn = st.button("Luo kartta")

if upload is not None:
    # Tiedosto vaihtui?
