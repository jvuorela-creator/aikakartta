import streamlit as st
import pandas as pd
import tempfile
import os
import re
import time
from ged4py.parser import GedcomReader
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
import folium
from folium.plugins import TimestampedGeoJson
from streamlit_folium import st_folium

# --- ASETUKSET ---
st.set_page_config(page_title="Sukututkimuskartta Pro", layout="wide")
st.title("Sukututkimuskartta: Älykäs versio")
st.markdown("""
Tämä versio tallentaa haetut koordinaatit tiedostoon (`tallennetut_paikat.csv`).
Ensimmäinen ajo on hidas, mutta seuraavat ovat nopeita, koska tietoja ei tarvitse hakea uudelleen.
""")

CACHE_FILE = "tallennetut_paikat.csv"

# --- APUFUNKTIOT ---

def load_local_cache():
    """Lataa tallennetut koordinaatit CSV-tiedostosta muistiin."""
    if os.path.exists(CACHE_FILE):
        try:
            # Luetaan CSV: Sarake 0 = Paikka, Sarake 1 = Lat, Sarake 2 = Lon
            df = pd.read_csv(CACHE_FILE, header=None, names=["Paikka", "Lat", "Lon"])
            # Muutetaan sanakirjaksi: {"Turku": (60.45, 22.25)}
            cache = {}
            for _, row in df.iterrows():
                cache[row['Paikka']] = (row['Lat'], row['Lon'])
            return cache
        except:
            return {}
    return {}

def save_to_cache(place, lat, lon):
    """Lisää uuden paikan CSV-tiedostoon."""
    # Avataan tiedosto append-tilassa ('a'), jotta vanhat eivät katoa
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
                        years = re.findall(r'\d{4}', str(date_val))
                        if years:
                            data_list.append({
                                "Nimi": full_name,
                                "Vuosi": int(years[-1]),
                                "Paikka": str(place_val)
                            })
    except Exception as e:
        st.error(f"Virhe luvussa: {e}")
        return []
    return data_list

@st.cache_data
def get_coordinates_smart(places_list):
    # 1. Ladataan vanhat muistista
    local_cache = load_local_cache()
    
    # Alustetaan geokoodaaja
    geolocator = Nominatim(user_agent="aikakartta_pro_v1")
    coords = {}
    
    # UI
    status = st.empty()
    bar = st.progress(0)
    total = len(places_list)
    
    # Logiikka: Erotellaan ne, jotka on jo haettu, ja ne jotka pitää hakea
    to_fetch = []
    for p in places_list:
        if p in local_cache:
            coords[p] = local_cache[p]
        else:
            to_fetch.append(p)
            
    if not to_fetch:
        status.success("Kaikki paikat löytyivät välimuistista! Ei tarvita verkkohakua.")
        bar.progress(100)
        return coords

    st.info(f"Löytyi {len(coords)} paikkaa muistista. Haetaan verkosta {len(to_fetch)} uutta paikkaa...")

    # Haetaan vain puuttuvat
    for i, place in enumerate(to_fetch):
        lat, lon = None, None
        clean_place = place.split(',')[0]
        
        try:
            time.sleep(1.2) # Hidastus
            loc = geolocator.geocode(place, timeout=10)
            if loc:
                lat, lon = loc.latitude, loc.longitude
            else:
                loc = geolocator.geocode(clean_place, timeout=10)
                if loc:
                    lat, lon = loc.latitude, loc.longitude
        except Exception as e:
            if "403" in str(e) or "429" in str(e):
                st.error("Karttapalvelu esti yhteyden. Odota hetki.")
                break
            time.sleep(2)
        
        # Jos löytyi, lisätään listaan JA tallennetaan tiedostoon
        if lat is not None:
            coords[place] = (lat, lon)
            save_to_cache(place, lat, lon)
        else:
            coords[place] = (None, None)
            
        # Päivitys
        prc = int((i + 1) / len(to_fetch) * 100)
        bar.progress(prc)
        status.write(f"Haetaan verkosta: {place}")

    status.success("Haku valmis!")
    time.sleep(1)
    status.empty()
    bar.empty()
    return coords

def create_features(df):
    features = []
    for _, row in df.iterrows():
        feat = {
            'type': 'Feature',
            'geometry': {
                'type': 'Point',
                'coordinates': [row['lon'], row['lat']],
            },
            'properties': {
                'time': f"{row['Vuosi']}-01-01",
                'popup': f"{row['Vuosi']}: {row['Nimi']}, {row['Paikka']}",
                'icon': 'circle',
                'iconstyle': {
                    'fillColor': 'blue', 'fillOpacity': 0.8,
                    'stroke': 'false', 'radius': 6
                },
                'style': {'color': 'blue'}
            }
        }
        features.append(feat)
    return features

# --- PÄÄOHJELMA ---

if 'processed_data' not in st.session_state:
    st.session_state.processed_data = None
if 'current_file' not in st.session_state:
    st.session_state.current_file = None

uploaded_file = st.file_uploader("Lataa GEDCOM", type=["ged"])
run_btn = st.button("Luo kartta")

if uploaded_file and run_btn:
    if st.session_state.current_file != uploaded_file.name:
        st.session_state.processed_data = None
        st.session_state.current_file = uploaded_file.name

    bytes_data = uploaded_file.read()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".ged") as tf:
        tf.write(bytes_data)
        tf_path = tf.name

    with st.spinner("Luetaan dataa..."):
        data = parse_gedcom(tf_path)
    os.remove(tf_path)

    if not data:
        st.error("Ei tietoja.")
    else:
        df = pd.DataFrame(data)
        places = df['Paikka'].unique().tolist()
        
        # Haetaan koordinaatit (käyttäen välimuistia)
        coords_map = get_coordinates_smart(places)
        
        df['lat'] = df['Paikka'].map(lambda x: coords_map.get(x, (None, None))[0])
        df['lon'] = df['Paikka'].map(lambda x: coords_map.get(x, (None, None))[1])
        
        df_clean = df.dropna(subset=['lat', 'lon']).copy()
        
        if df_clean.empty:
            st.warning("Ei koordinaatteja. Jos IP on estetty, kokeile myöhemmin uudestaan.")
        else:
            st.session_state.processed_data = df_clean

if st.session_state.processed_data is not None:
    final_df = st.session_state.processed_data.sort_values(by='Vuosi', ascending=True)
    
    m = folium.Map(location=[final_df['lat'].mean(), final_df['lon'].mean()], zoom_start=5)
    
    TimestampedGeoJson(
        {'type': 'FeatureCollection', 'features': create_features(final_df)},
        period='P1Y',
        duration='P500Y',
        transition_time=200,
        auto_play=True,
        loop=False,
        max_speed=10,
        loop_button=True,
        date_options='YYYY',
        time_slider_drag_update=True
    ).add_to(m)

    st.success(f"Valmis! {len(final_df)} pistettä.")
    st_folium(m, width=900, height=600)
    
    with st.expander("Näytä data"):
        st.dataframe(final_df[['Vuosi', 'Nimi', 'Paikka']])
