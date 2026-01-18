import streamlit as st
import pandas as pd
import tempfile
import os
import re
import time

# Tuodaan kirjastot turvallisesti
try:
    from ged4py.parser import GedcomReader
    from geopy.geocoders import Nominatim
    import folium
    from folium.plugins import TimestampedGeoJson
    from streamlit_folium import st_folium
except ImportError:
    st.error("Asenna puuttuvat kirjastot: pip install ged4py geopy folium streamlit-folium")
    st.stop()

# --- 1. SIVUN ASETUKSET ---
st.set_page_config(page_title="Sukututkimuskartta", layout="wide")
st.title("Sukututkimuskartta")

# --- 2. ALUSTETAAN MUISTI (Session State) ---
# TAMA ESTAA KARTAN KATOAMISEN
if 'data_ready' not in st.session_state:
    st.session_state.data_ready = False
if 'map_df' not in st.session_state:
    st.session_state.map_df = None

# --- 3. APUFUNKTIOT ---

def parse_gedcom_safe(file_path):
    results = []
    try:
        with GedcomReader(file_path) as parser:
            for indi in parser.records0("INDI"):
                if not indi.name: continue
                
                # Nimi
                full_name = "Tuntematon"
                try:
                    g = indi.name.given or ""
                    s = indi.name.surname or ""
                    full_name = str(g) + " " + str(s)
                except: pass

                # Syntymä
                birt = indi.sub_tag("BIRT")
                if birt:
                    date_val = birt.sub_tag_value("DATE")
                    place_val = birt.sub_tag_value("PLAC")
                    
                    # Muutetaan tekstiksi
                    raw_date = str(date_val) if date_val else ""
                    raw_place = str(place_val) if place_val else ""
                    
                    # Etsitään vuosi
                    found_year = 0
                    years = re.findall(r'\d{4}', raw_date)
                    if years:
                        found_year = int(years[-1])
                    
                    # Hyväksytään vain jos vuosi on järkevä ja paikka löytyy
                    if found_year > 1000 and raw_place != "":
                        item = {}
                        item["Nimi"] = full_name
                        item["Vuosi"] = found_year
                        item["Paikka"] = raw_place
                        results.append(item)
                        
    except Exception as e:
        st.error("Virhe tiedoston luvussa: " + str(e))
        return []
    return results

def get_coordinates_safe(places):
    geolocator = Nominatim(user_agent="aikakartta_fix_final")
    coords = {}
    
    # UI
    text_box = st.empty()
    bar = st.progress(0)
    total = len(places)
    
    text_box.write("Haetaan koordinaatteja...")
    
    for i, p in enumerate(places):
        try:
            # Hidastus on pakollinen
            time.sleep(1.1)
            loc = geolocator.geocode(p, timeout=5)
            if loc:
                coords[p] = (loc.latitude, loc.longitude)
            else:
                # Kokeillaan lyhyempää nimeä (ennen pilkkua)
                short_p = p.split(',')[0]
                loc2 = geolocator.geocode(short_p, timeout=5)
                if loc2:
                    coords[p] = (loc2.latitude, loc2.longitude)
        except:
            pass
            
        # Palkki
        percent = int((i + 1) / total * 100)
        bar.progress(percent)
        text_box.write("Käsitellään: " + str(i+1) + "/" + str(total))
        
    text_box.success("Valmis!")
    time.sleep(1)
    text_box.empty()
    bar.empty()
    return coords

def create_geojson_features(df):
    features = []
    for _, row in df.iterrows():
        y = row['Vuosi']
        time_str = str(y) + "-01-01"
        popup = str(y) + ": " + row['Nimi'] + " (" + row['Paikka'] + ")"
        
        # Tyylit
        style = {}
        style['fillColor'] = 'blue'
        style['fillOpacity'] = 0.8
        style['radius'] = 5
        style['stroke'] = 'false'
        
        # Ominaisuudet
        props = {}
        props['time'] = time_str
        props['popup'] = popup
        props['icon'] = 'circle'
        props['iconstyle'] = style
        
        # Sijainti
        geom = {}
        geom['type'] = 'Point'
        geom['coordinates'] = [row['lon'], row['lat']]
        
        # Feature
        feat = {}
        feat['type'] = 'Feature'
        feat['geometry'] = geom
        feat['properties'] = props
        
        features.append(feat)
    return features

# --- 4. KÄYTTÖLIITTYMÄ ---

uploaded = st.file_uploader("1. Lataa GEDCOM", type=["ged"])
test_mode = st.checkbox("Pikatesti (vain 10 paikkaa)", value=True)
btn = st.button("2. Analysoi ja Piirrä")

# --- 5. LOGIIKKA (Suoritetaan kun nappia painetaan) ---

if uploaded and btn:
    # Luetaan tiedosto
    raw = uploaded.read()
    tf = tempfile.NamedTemporaryFile(delete=False, suffix=".ged")
    tf.write(raw)
    tf.close()
    
    with st.spinner("Luetaan GEDCOM-tiedostoa..."):
        data = parse_gedcom_safe(tf.name)
    
    if os.path.exists(tf.name):
        os.remove(tf.name)
        
    if not data:
        st.error("Ei tietoja löytynyt.")
    else:
        df = pd.DataFrame(data)
        
        # Otetaan uniikit paikat
        places = df['Paikka'].unique().tolist()
        
        if test_mode:
            places = places[:10]
            st.warning("Pikatesti: Haetaan vain 10 ensimmäistä paikkaa.")
            
        # Haetaan koordinaatit
        coords = get_coordinates_safe(places)
        
        # Yhdistetään
        df['lat'] = df['Paikka'].map(lambda x: coords.get(x, (None, None))[0])
        df['lon'] = df['Paikka'].map(lambda x: coords.get(x, (None, None))[1])
        
        # Jos pikatesti, karsitaan data
        if test_mode:
            df = df[df['Paikka'].isin(coords.keys())]
            
        # Poistetaan tyhjät
        final_df = df.dropna(subset=['lat', 'lon']).copy()
        
        if final_df.empty:
            st.error("Ei koordinaatteja löytynyt.")
        else:
            # TALLENNETAAN MUISTIIN (TÄMÄ ON KORJAUS VILKKUMISEEN)
            st.session_state.map_df = final_df.sort_values(by='Vuosi')
            st.session_state.data_ready = True

# --- 6. KARTAN PIIRTO (Tämä on napin ulkopuolella!) ---

if st.session_state.data_ready and st.session_state.map_df is not None:
    st.write("---")
    df_show = st.session_state.map_df
    
    st.success("Kartta valmis! " + str(len(df_show)) + " kohdetta.")
    st.info("Paina Play-nappia kartan vasemmassa alakulmassa.")
    
    # Kartta
    start_lat = df_show['lat'].mean()
    start_lon = df_show['lon'].mean()
    m = folium.Map(location=[start_lat, start_lon], zoom_start=5)
    
    # Luodaan animaatio
    feats = create_geojson_features(df_show)
    
    TimestampedGeoJson(
        {'type': 'FeatureCollection', 'features': feats},
        period='P1Y',
        duration='P100Y',
        auto_play=True,
        loop=False,
        max_speed=10,
        loop_button=True,
        date_options='YYYY',
        time_slider_drag_update=True
    ).add_to(m)
    
    # Piirretään Streamlitiin
    st_folium(m, width=900, height=600)
    
    # Taulukko
    with st.expander("Näytä data"):
        st.dataframe(df_show[['Vuosi', 'Nimi', 'Paikka']])
