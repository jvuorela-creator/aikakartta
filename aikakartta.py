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
st.title("Sukututkimuskartta")

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
    try:
        with open(CACHE_FILE, "a", encoding="utf-8") as f:
            f.write(f'"{place}",{lat},{lon}\n')
    except:
        pass

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
                            y = int(years[-1])
                            # Suodatetaan selkeat virheet
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
    geolocator = Nominatim(user_agent="aikakartta_final_v3")
    coords = {}
    
    to_fetch = []
    for p in places_list:
        if p in local_cache:
            coords[p] = local_cache[p]
        else:
            to_fetch.append(p)
            
    if not to_fetch:
        return coords

    st.info(f"Haetaan verkosta {len(to_fetch)} paikkaa...")
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
        # Luodaan muuttujat erikseen syntaksivirheiden välttämiseksi
        v = row['Vuosi']
        time_str = f"{int(v)}-01-01"
        popup_txt = f"{v}: {row['Nimi']}, {row['Paikka']}"
        
        # Määritellään tyylit erikseen sanakirjoina
        # TÄMÄ ESTÄÄ RIVIN KATKEAMISVIRHEET
        icon_style_dict = {}
        icon_style_dict['fillColor'] = 'blue'
        icon_style_dict['fillOpacity'] = 0.8
        icon_style_dict['stroke'] = 'false'
        icon_style_dict['radius'] = 6

        props = {}
        props['time'] = time_str
        props['popup'] = popup_txt
        props['icon'] = 'circle'
        props['iconstyle'] = icon_style_dict
        props['style'] = {'color': 'blue'}

        geometry = {}
        geometry['type'] = 'Point'
        geometry['coordinates'] = [row['lon'], row['lat']]

        feature = {}
        feature['type'] = 'Feature'
        feature['geometry'] = geometry
        feature['properties'] = props
        
        features.append(feature)
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

    with st.spinner("Luetaan dataa..."):
        data = parse_gedcom(tf_path)
    os.remove(tf_path)

    if not data:
        st.error("Ei dataa. Tarkista tiedosto.")
    else:
        df = pd.DataFrame(data)
        
        places = df['Paikka'].unique().tolist()
        coords_map = get_coordinates_smart(places)
        
        df['lat'] = df['Paikka'].map(lambda x: coords_map.get(x, (None, None))[0])
        df['lon'] = df['Paikka'].map(lambda x: coords_map.get(x, (None, None))[1])
        
        df_clean = df.dropna(subset=['lat', 'lon']).copy()
        
        if df_clean.empty:
            st.error("Ei koordinaatteja.")
        else:
            st.session_state.processed_data = df_clean

# --- 4. TULOSTUS ---

if st.session_state.processed_data is not None:
    # Järjestys on kriittinen animaatiolle
    final_df = st.session_state.processed_data.sort_values(by='Vuosi', ascending=True)
    
    st.success(f"Valmis! {len(final_df)} tapahtumaa.")
    st.info("Käynnistä animaatio kartan vasemmasta alakulmasta (Play-nappi).")
    
    m = folium.Map(location=[64.0, 26.0], zoom_start=5)
    
    feats = create_features(final_df)
    
    TimestampedGeoJson(
        {'type': 'FeatureCollection', 'features': feats},
        period='P1Y',
        duration='P500Y', 
        add_last_point=False,
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
