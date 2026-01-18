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
st.title("Sukututkimuskartta: Toimiva animaatio")

# Välimuistitiedoston nimi
CACHE_FILE = "tallennetut_paikat.csv"

# --- 2. APUFUNKTIOT ---

def load_local_cache():
    """Lataa vanhat koordinaatit levyltä, jotta vältetään IP-estot."""
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
    """Tallentaa uuden koordinaatin levylle."""
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
        st.error(f"Virhe GEDCOM-luvussa: {e}")
        return []
    return data_list

@st.cache_data
def get_coordinates_smart(places_list):
    local_cache = load_local_cache()
    geolocator = Nominatim(user_agent="aikakartta_fixed_anim_v1")
    coords = {}
    
    # Erotellaan haettavat
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
        # Aikaleima on kriittinen animaatiolle
        time_str = f"{row['Vuosi']}-01-01"
        popup_txt = f"{row['Vuosi']}: {row['Nimi']}, {row['Paikka']}"
        
        feat = {
            'type': 'Feature',
            'geometry': {
                'type': 'Point',
                'coordinates': [row['lon'], row['lat']], # Lon, Lat järjestys
            },
            'properties': {
                'time': time_str,
                'popup': popup_txt,
                'icon': 'circle',
                'iconstyle': {
                    'fillColor': '#0000FF', # Sininen
                    'fillOpacity': 0.8,
                    'stroke': 'false',
                    'radius': 6
                },
                'style': {'color': 'blue'}
            }
        }
        features.append(feat)
    return features

# --- 3. PÄÄOHJELMA ---

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

    with st.spinner("Analysoidaan..."):
        data = parse_gedcom(tf_path)
    os.remove(tf_path)

    if not data:
        st.error("Ei dataa.")
    else:
        df = pd.DataFrame(data)
        places = df['Paikka'].unique().tolist()
        coords_map = get_coordinates_smart(places)
        
        df['lat'] = df['Paikka'].map(lambda x: coords_map.get(x, (None, None))[0])
        df['lon'] = df['Paikka'].map(lambda x: coords_map.get(x, (None, None))[1])
        
        df_clean = df.dropna(subset=['lat', 'lon']).copy()
        
        if df_clean.empty:
            st.error("Ei koordinaatteja. (IP-esto voi olla päällä)")
        else:
            st.session_state.processed_data = df_clean

# --- 4. TULOSTUS JA ANIMAATIO ---

if st.session_state.processed_data is not None:
    final_df = st.session_state.processed_data.sort_values(by='Vuosi', ascending=True)
    
    st.success(f"Valmis! {len(final_df)} pistettä.")
    st.info("Paina kartan vasemmassa alakulmassa olevaa 'Play'-nappia.")
    
    m = folium.Map(location=[64.0, 26.0], zoom_start=5)
    
    features = create_features(final_df)
    
    TimestampedGeoJson(
        {'type': 'FeatureCollection', 'features': features},
        period='P1Y',        # 1 vuosi kerrallaan
        duration='P500Y',    # Piste jää näkyviin (500 vuotta)
        add_last_point=False, # TÄMÄ ON TÄRKEÄ: Estää viivojen piirtymisen pisteiden välille
        auto_play=True,
        loop=False,
        max_speed=10,
        loop_button=True,
        date_options='YYYY',
        time_slider_drag_update=True
    ).add_to(m)

    st_folium(m, width=900, height=600)
    
    with st.expander("Näytä data"):
        st.dataframe(final_df[['Vuosi', 'Nimi', 'Paikka']])
