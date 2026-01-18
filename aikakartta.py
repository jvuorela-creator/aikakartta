import streamlit as st
import pandas as pd
import tempfile
import os
import re
import time
# Tuodaan kirjastot varovasti
try:
    from ged4py.parser import GedcomReader
    from geopy.geocoders import Nominatim
    from geopy.exc import GeocoderTimedOut, GeocoderServiceError
    import folium
    from folium.plugins import TimestampedGeoJson
    from streamlit_folium import st_folium
    import chardet
except ImportError as e:
    st.error("Jokin kirjasto puuttuu! Asenna ne komennolla: pip install -r requirements.txt")
    st.stop()

# --- 1. SIVUN ALUSTUS ---
st.set_page_config(page_title="Sukututkimuskartta", layout="wide")
st.title("Sukututkimuskartta: Aikajana")

# Tulostetaan teksti heti, jotta tiedetaan etta koodi pyorii
st.write("Sovellus kaynnistynyt. Lataa GEDCOM-tiedosto alta.")

# --- 2. SESSION STATE ---
if 'processed_data' not in st.session_state:
    st.session_state.processed_data = None
if 'current_file' not in st.session_state:
    st.session_state.current_file = None

# --- 3. APUFUNKTIOT ---

def parse_gedcom_safe(file_path):
    # Lukee GEDCOM-tiedoston ilman monimutkaisia rakenteita
    results = []
    try:
        with GedcomReader(file_path) as parser:
            # Iteroidaan INDI-tietueet
            for indi in parser.records0("INDI"):
                if not indi.name:
                    continue
                
                # Nimi talteen
                full_name = "Tuntematon"
                try:
                    g = indi.name.given or ""
                    s = indi.name.surname or ""
                    full_name = (g + " " + s).strip()
                except:
                    pass
                
                # Syntyma talteen
                birt = indi.sub_tag("BIRT")
                if birt:
                    date_val = birt.sub_tag_value("DATE")
                    place_val = birt.sub_tag_value("PLAC")
                    
                    # Jos paikka ja aika loytyy
                    if place_val and date_val:
                        # Etsitaan vuosiluku (4 numeroa)
                        years = re.findall(r'\d{4}', str(date_val))
                        if years:
                            # Otetaan viimeinen loytynyt vuosiluku
                            the_year = int(years[-1])
                            
                            # Lisataan listaan
                            obj = {
                                "Nimi": full_name,
                                "Vuosi": the_year,
                                "Paikka": str(place_val)
                            }
                            results.append(obj)
    except Exception as e:
        st.error("Virhe GEDCOM-luvussa: " + str(e))
        return []
    return results

@st.cache_data
def get_coordinates_safe(places_list):
    # Alustetaan geokoodaaja
    geolocator = Nominatim(user_agent="aikakartta_final_v99")
    coords = {}
    total = len(places_list)
    
    # UI elementit
    status_msg = st.empty()
    progress_bar = st.progress(0)
    
    status_msg.write("Haetaan koordinaatteja " + str(total) + " paikkakunnalle...")

    for i, place in enumerate(places_list):
        # Otetaan pelkka kunta (ennen pilkkua)
        clean_place = place.split(',')[0]
        lat = None
        lon = None
        
        try:
            # Hidastus (pakollinen)
            time.sleep(1.1)
            
            # Haku 1: Koko nimi
            loc = geolocator.geocode(place, timeout=10)
            if loc:
                lat = loc.latitude
                lon = loc.longitude
            else:
                # Haku 2: Pelkka kunta
                loc = geolocator.geocode(clean_place, timeout=10)
                if loc:
                    lat = loc.latitude
                    lon = loc.longitude
        except:
            # Jos virhe, odotetaan hetki ja jatketaan
            time.sleep(2)
        
        # Tallennetaan tulos
        coords[place] = (lat, lon)
        
        # Paivitetaan palkki
        percent = int((i + 1) / total * 100)
        if percent > 100: percent = 100
        progress_bar.progress(percent)
