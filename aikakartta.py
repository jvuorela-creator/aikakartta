import streamlit as st

# 1. ASETUKSET (Nämä pitää olla ensimmäisenä)
st.set_page_config(page_title="Sukututkimuskartta", layout="wide")
st.title("Sukututkimuskartta: Aikajana")

# 2. PIIRRETÄÄN UI HETI (Jotta se näkyy varmasti)
st.write("---")
uploaded_file = st.file_uploader("1. Lataa GEDCOM-tiedosto (.ged)", type=["ged"])
test_mode = st.checkbox("Pikatesti (vain 15 paikkaa)", value=True)
run_btn = st.button("2. Luo kartta")
st.write("---")

# 3. TUODAAN KIRJASTOT JA NÄYTETÄÄN VIRHE JOS PUUTTUU
try:
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
    import chardet
except ImportError as e:
    st.error("VIRHE: Jokin kirjasto puuttuu!")
    st.code("pip install pandas ged4py geopy folium streamlit-folium chardet")
    st.error("Tarkka virhe: " + str(e))
    st.stop()

# 4. ALUSTUKSET
if 'processed_data' not in st.session_state:
    st.session_state.processed_data = None
if 'current_file' not in st.session_state:
    st.session_state.current_file = None

# 5. APUFUNKTIOT
def parse_gedcom_simple(file_path):
    # Yksinkertainen jäsennin
    results = []
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
                        # Etsi vuosi
                        years = re.findall(r'\d{4}', str(date_val))
                        if years:
                            obj = {
                                "Nimi": full_name,
                                "Vuosi": int(years[-1]),
                                "Paikka": str(place_val)
                            }
                            results.append(obj)
    except Exception as e:
        st.error("Virhe tiedoston sisällössä: " + str(e))
        return []
    return results

@st.cache_data
def get_coordinates_simple(places_list):
    geolocator = Nominatim(user_agent="aikakartta_v2025")
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
            time.sleep(1.1) # Pakollinen hidastus
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
        
        # Palkin päivitys
        prc = int((i + 1) / total * 100)
        if prc > 100: prc = 100
        bar.progress(prc)
        status.write("Etsitään: " + str(i+1) + " / " + str(total))
        
    status.success("Valmis!")
    time.sleep(1)
    status.empty()
    bar.empty()
    return coords

def create_features_simple(df):
    features = []
    for idx, row in df.iterrows():
        time_str = str(row['Vuosi']) + "-01-01"
        txt = str(row['Vuosi']) + ": " + row['Nimi'] + ", " + row['Paikka']
        
        feat = {
            'type': 'Feature',
            'geometry': {
                'type': 'Point',
                'coordinates': [row['lon'], row['lat']],
            },
            'properties': {
                'time': time_str,
                'popup': txt,
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

# 6. LOGIIKKA (Tapahtuu kun nappia painetaan)

if uploaded_file is not None:
    # Nollataan vanha data jos tiedosto vaihtui
    if st.session_state.current_file != uploaded_file.name:
        st.session_state.processed_data = None
        st.session_state.current_file = uploaded_file.name

    if run_btn:
        # Luetaan tiedosto
        bytes_data = uploaded_file.read()
        
        # Väliaikaistiedosto
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ged") as tf:
            tf.write(bytes_data)
            tf_path = tf.name

        with st.spinner("Luetaan GEDCOM-tiedostoa..."):
            parsed_list = parse_gedcom_simple(tf_path)
        
        if os.path.exists(tf_path):
            os.remove(tf_path)

        if not parsed_list:
            st.error("Tiedostosta ei löytynyt sopivia tietoja.")
        else:
            df = pd.DataFrame(parsed_list)
            places = df['Paikka'].unique().tolist()
            
            st.info("Löydettiin " + str(len(places)) + " paikkakuntaa.")
            
            if test_mode:
                places = places[:15]
                st.warning("Pikatesti päällä: Vain 15 paikkaa haetaan.")
            
            coords_map = get_coordinates_simple(places)
            
            df['lat'] = df['Paikka'].map(lambda x: coords_map.get(x, (None, None))[0])
            df['lon'] = df['Paikka'].map(lambda x: coords_map.get(x, (None, None))[1])
            
            if test_mode:
                df = df[df['Paikka'].isin(coords_map.keys())]

            df_clean = df.dropna(subset=['lat', 'lon']).copy()
            
            if df_clean.empty:
                st.error("Ei koordinaatteja.")
            else:
                st.session_state.processed_data = df_clean

# 7. TULOSTUS

if st.session_state.processed_data is not None:
    st.subheader("Kartta")
    
    final_df = st.session_state.processed_data.sort_values(by='Vuosi', ascending=True)
    
    center_lat = final_df['lat'].mean()
    center_lon = final_df['lon'].mean()
    m = folium.Map(location=[center_lat, center_lon], zoom_start=5)
    
    geo_data = create_features_simple(final_df)
    
    TimestampedGeoJson(
        {'type': 'FeatureCollection', 'features': geo_data},
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

    st.success("Valmis! " + str(len(final_df)) + " kohdetta.")
    st_folium(m, width=900, height=600)
    
    with st.expander("Näytä tiedot"):
        st.dataframe(final_df[['Vuosi', 'Nimi', 'Paikka']])
