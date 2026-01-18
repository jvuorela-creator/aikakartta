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

# --- 1. ASETUKSET ---
st.set_page_config(page_title="Sukututkimuskartta", layout="wide")
st.title("Sukututkimuskartta: Debug-versio")
st.write("Tämä versio näyttää tarkasti, toimiiko karttapalvelu vai onko IP-osoite estetty.")

# --- 2. APUFUNKTIOT ---

def parse_gedcom(file_path):
    # Lukee GEDCOM-tiedoston
    data_list = []
    try:
        with GedcomReader(file_path) as parser:
            for indi in parser.records0("INDI"):
                if not indi.name:
                    continue
                
                # Nimi
                full_name = "Tuntematon"
                try:
                    g = indi.name.given or ""
                    s = indi.name.surname or ""
                    full_name = (g + " " + s).strip()
                except:
                    pass
                
                # Syntymäaika ja paikka
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
        st.error(f"Virhe GEDCOM-luvussa: {e}")
        return []
    return data_list

@st.cache_data
def get_coordinates_debug(places_list):
    # Käytetään uutta tunnistetta eston välttämiseksi
    user_agent_str = "sukututkimus_debug_v2026_fixed"
    geolocator = Nominatim(user_agent=user_agent_str)
    
    coords = {}
    total = len(places_list)
    
    # UI-elementit
    status_box = st.empty()
    bar = st.progress(0)
    log_box = st.expander("Näytä haun lokitiedot (Debug)", expanded=True)
    
    status_box.write(f"Aloitetaan haku {total} paikkakunnalle...")

    found_count = 0
    
    with log_box:
        for i, place in enumerate(places_list):
            clean_place = place.split(',')[0]
            lat = None
            lon = None
            
            try:
                # Hidastus on pakollinen
                time.sleep(1.2)
                
                # Yritetään hakea
                location = geolocator.geocode(place, timeout=10)
                
                if location:
                    lat = location.latitude
                    lon = location.longitude
                    st.write(f"✅ OK: {place} -> {lat}, {lon}")
                    found_count += 1
                else:
                    # Yritetään lyhyemmällä nimellä
                    st.write(f"⚠️ Ei löytynyt: {place}. Kokeillaan: {clean_place}")
                    time.sleep(1.2)
                    location = geolocator.geocode(clean_place, timeout=10)
                    if location:
                        lat = location.latitude
                        lon = location.longitude
                        st.write(f"✅ OK (lyhyt): {clean_place} -> {lat}, {lon}")
                        found_count += 1
                    else:
                        st.write(f"❌ Epäonnistui: {place}")

            except Exception as e:
                st.write(f"🔥 VIRHE ({place}): {e}")
                # Jos tulee 403 tai 429 virhe, se tarkoittaa IP-estoa
                if "403" in str(e) or "429" in str(e):
                    st.error("KRIITTINEN VIRHE: Karttapalvelu on estänyt pyynnöt liian tiheän käytön vuoksi. Odota 10-15 minuuttia.")
                    break
            
            coords[place] = (lat, lon)
            
            # Päivitetään palkki
            prog = int((i + 1) / total * 100)
            if prog > 100: prog = 100
            bar.progress(prog)
            status_box.write(f"Käsitellään {i+1}/{total}: {place}")

    status_box.success(f"Haku valmis. Löytyi {found_count}/{total} koordinaatit.")
    return coords

def create_features(df):
    features = []
    for _, row in df.iterrows():
        time_str = f"{row['Vuosi']}-01-01"
        popup = f"{row['Vuosi']}: {row['Nimi']}, {row['Paikka']}"
        
        feat = {
            'type': 'Feature',
            'geometry': {
                'type': 'Point',
                'coordinates': [row['lon'], row['lat']],
            },
            'properties': {
                'time': time_str,
                'popup': popup,
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

# --- 3. PÄÄOHJELMA ---

# Session state alustus
if 'processed_data' not in st.session_state:
    st.session_state.processed_data = None
if 'current_file' not in st.session_state:
    st.session_state.current_file = None

uploaded_file = st.file_uploader("Lataa GEDCOM-tiedosto", type=["ged"])
test_mode = st.checkbox("Pikatesti (vain 5 paikkaa)", value=True, help="Käytä tätä testaukseen, ettei IP mene lukkoon.")
run_btn = st.button("Hae tiedot ja piirrä kartta")

if uploaded_file is not None and run_btn:
    # 1. Luetaan tiedosto
    bytes_data = uploaded_file.read()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".ged") as tf:
        tf.write(bytes_data)
        tf_path = tf.name
    
    with st.spinner("Luetaan GEDCOM..."):
        parsed_data = parse_gedcom(tf_path)
    os.remove(tf_path)

    if not parsed_data:
        st.error("Tiedostosta ei löytynyt henkilöitä, joilla on syntymävuosi ja paikka.")
    else:
        # 2. Käsitellään data
        df = pd.DataFrame(parsed_data)
        unique_places = df['Paikka'].unique().tolist()
        
        st.info(f"Tiedostosta löytyi {len(df)} tapahtumaa ja {len(unique_places)} eri paikkakuntaa.")

        if test_mode:
            unique_places = unique_places[:5]
            st.warning("Pikatesti: Haetaan vain 5 ensimmäistä paikkaa.")
        
        # 3. Haetaan koordinaatit
        coords_map = get_coordinates_debug(unique_places)
        
        # Yhdistetään
        df['lat'] = df['Paikka'].map(lambda x: coords_map.get(x, (None, None))[0])
        df['lon'] = df['Paikka'].map(lambda x: coords_map.get(x, (None, None))[1])
        
        if test_mode:
            # Pikatestissä rajataan data vain haettuihin
            df = df[df['Paikka'].isin(coords_map.keys())]

        df_clean = df.dropna(subset=['lat', 'lon']).copy()
        
        if df_clean.empty:
            st.error("Yhdellekään paikalle ei saatu koordinaatteja. Katso yllä olevaa lokia syyn selvittämiseksi.")
        else:
            st.session_state.processed_data = df_clean
            st.success(f"Onnistui! {len(df_clean)} pistettä valmiina kartalle.")

# --- 4. TULOSTUS ---

if st.session_state.processed_data is not None:
    st.write("---")
    
    final_df = st.session_state.processed_data.sort_values(by='Vuosi', ascending=True)
    
    # Kartan keskitys
    avg_lat = final_df['lat'].mean()
    avg_lon = final_df['lon'].mean()
    
    m = folium.Map(location=[avg_lat, avg_lon], zoom_start=5)
    
    geo_features = create_features(final_df)
    
    TimestampedGeoJson(
        {'type': 'FeatureCollection', 'features': geo_features},
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

    st_folium(m, width=900, height=600)
    
    with st.expander("Näytä datataulukko"):
        st.dataframe(final_df[['Vuosi', 'Nimi', 'Paikka']])
