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

# --- Apufunktiot ---

def detect_encoding(file_bytes):
    """Tunnistaa tiedoston merkistön."""
    result = chardet.detect(file_bytes)
    return result['encoding']

def parse_gedcom(file_path):
    """Lukee GEDCOM-tiedoston ja etsii henkilöt, vuodet ja paikat."""
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
                            # Etsitään vuosiluku (4 numeroa)
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
    """Hakee koordinaatit välimuistia hyödyntäen."""
    geolocator = Nominatim(user_agent="sukututkimus_kartta_app_v3")
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1.1)
    
    coords = {}
    total = len(places_list)
    my_bar = st.progress(0, text="Haetaan koordinaatteja...")

    for i, place in enumerate(places_list):
        clean_place = place.split(',')[0] # Ensimmäinen osa ennen pilkkua
        try:
            # 1. Haku koko nimellä
            location = geocode(place)
            if location:
                coords[place] = (location.latitude, location.longitude)
            else:
                # 2. Haku pelkällä paikkakunnalla (fallback)
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
    
    for _, row in df.iterrows():
        time_str = f"{row['Vuosi']}-01-01"
        
        # TÄSSÄ OLI AIEMMIN VIRHE: 'style' -rivin lainausmerkit ovat nyt korjattu
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

if uploaded_file is not None:
    raw_data = uploaded_file.read()
    encoding = detect_encoding(raw_data)
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".ged") as tmp_file:
        tmp_file.write(raw_data)
        tmp_file_path = tmp_file.name

    with st.spinner("Luetaan sukupuuta..."):
        parsed_data = parse_gedcom(tmp_file_path)
    
    # Poistetaan väliaikaistiedosto
    os.remove(tmp_file_path)

    if not parsed_data:
        st.warning("Tiedostosta ei löytynyt sopivia tietoja (Henkilöitä, joilla on Vuosi + Paikka).")
    else:
        df = pd.DataFrame(parsed_data)
        
        unique_places = df['Paikka'].unique().tolist()
        st.info(f"Löydetty {len(df)} henkilöä ja {len(unique_places)} eri paikkakuntaa.")
        
        if st.button("Hae koordinaatit ja luo animaatio"):
            coords_dict = get_coordinates(unique_places)
            
            # Lisätään koordinaatit
            df['lat'] = df['Paikka'].map(lambda x: coords_dict.get(x, (None, None))[0])
            df['lon'] = df['Paikka'].map(lambda x: coords_dict.get(x, (None, None))[1])
            
            # Poistetaan rivit ilman koordinaatteja
            df_clean = df.dropna(subset=['lat', 'lon']).copy()
            
            dropped = len(df) - len(df_clean)
            if dropped > 0:
                st.warning(f"Ohitettiin {dropped} tapahtumaa, koska paikkaa ei löytynyt kartalta.")
            
            if df_clean.empty:
                st.error("Yhdellekään paikalle ei löytynyt koordinaatteja. Tarkista aineisto.")
            else:
                # Näytettävä taulukko
                df_display = df_clean.sort_values(by='Vuosi', ascending=False)
                
                # Kartta
                m = folium.Map(location=[64.0, 26.0], zoom_start=5)
                
                features = create_geojson_features(df_clean)
                
                TimestampedGeoJson(
                    {'type': 'FeatureCollection', 'features': features},
                    period='P1Y',
                    add_last_point=True,
                    auto_play=True,
                    loop=False,
                    max_speed=10,
                    loop_button=True,
                    date_options='YYYY',
                    time_slider_drag_update=True,
                    duration='P100Y' # Piste pysyy kartalla 100 vuotta
                ).add_to(m)

                st_folium(m, width=1000, height=800)
                
                st.subheader("Löydetyt ja paikannetut tiedot")
                st.dataframe(df_display[['Vuosi', 'Nimi', 'Paikka']])
