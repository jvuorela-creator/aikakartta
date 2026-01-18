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

st.set_page_config(page_title="Sukututkimuskartta", layout="wide")
st.title("Sukututkimuskartta: Aikajana")

if 'processed_data' not in st.session_state:
    st.session_state.processed_data = None
if 'current_file' not in st.session_state:
    st.session_state.current_file = None

def parse_gedcom(file_path):
    data_list = []
    try:
        with GedcomReader(file_path) as parser:
            for indi in parser.records0("INDI"):
                if not indi.name:
                    continue
                
                full_name = "Tuntematon"
                try:
                    g = indi.name.given or ""
                    s = indi.name.surname or ""
                    full_name = (g + " " + s).strip()
                except:
                    pass
                
                birt = indi.sub_tag("BIRT")
                if birt:
                    date_val = birt.sub_tag_value("DATE")
                    place_val = birt.sub_tag_value("PLAC")
                    
                    if place_val and date_val:
                        years = re.findall(r'\d{4}', str(date_val))
                        if years:
                            item = {
                                "Nimi": full_name,
                                "Vuosi": int(years[-1]),
                                "Paikka": str(place_val)
                            }
                            data_list.append(item)
    except Exception as e:
        return []
    return data_list

@st.cache_data
def get_coordinates(places_list):
    geolocator = Nominatim(user_agent="aikakartta_simple_v2")
    coords = {}
    total = len(places_list)
    
    status = st.empty()
    bar = st.progress(0)
    
    status.write("Haetaan koordinaatteja...")

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
        
        prog = int((i + 1) / total * 100)
        if prog > 100:
            prog = 100
        bar.progress(prog)
        status.write(str(i+1) + "/" + str(total))
        
    status.empty()
    bar.empty()
    return coords

def create_features(df):
    features = []
    for index, row in df.iterrows():
        time_str
