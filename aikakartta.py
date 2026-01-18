import streamlit as st
import pandas as pd
import tempfile
import os
import re
import time
# Tuodaan kirjastot try-except lohkon sisällä
try:
    from ged4py.parser import GedcomReader
    from geopy.geocoders import Nominatim
    import folium
    from folium.plugins import TimestampedGeoJson
    from streamlit_folium import st_folium
except ImportError:
    st.error("Jokin kirjasto puuttuu.")
    st.stop()

# --- ASETUKSET ---
st.set_page_config(page_title="Sukututkimus Debugger", layout="wide")
st.title("Sukututkimus Debugger")
st.write("Tämä työkalu näyttää miksi päivämäärät eivät toimi.")

# --- APUFUNKTIOT ---

def parse_gedcom_simple(file_path):
    # Tallennetaan tulokset tähän listaan
    results = []
    
    try:
        # Avataan tiedosto
        with GedcomReader(file_path) as parser:
            # Käydään läpi henkilöt
            for indi in parser.records0("INDI"):
                
                # Nimen haku varovasti
                full_name = "Tuntematon"
                try:
                    if indi.name:
                        g = indi.name.given or ""
                        s = indi.name.surname or ""
                        full_name = str(g) + " " + str(s)
                except:
                    pass

                # Haetaan syntymätiedot
                birt = indi.sub_tag("BIRT")
                if birt:
                    date_val = birt.sub_tag_value("DATE")
                    place_val = birt.sub_tag_value("PLAC")
                    
                    # Muutetaan tekstiksi
                    raw_date = str(date_val)
                    if date_val is None:
                        raw_date = ""
                        
                    raw_place = str(place_val)
                    if place_val is None:
                        raw_place = ""
                    
                    # Yritetään löytää vuosiluku (4 numeroa)
                    found_year = 0
                    years = re.findall(r'\d{4}', raw_date)
                    
                    if years:
                        # Otetaan viimeinen löydetty luku
                        found_year = int(years[-1])
                    
                    # Määritellään tila
                    status = "HYLÄTTY"
                    if found_year > 0:
                        status = "OK"
                    if raw_place == "":
                        status = "EI PAIKKAA"

                    # Lisätään listaan
                    item = {}
                    item["Nimi"] = full_name
                    item["Raaka_Pvm"] = raw_date
                    item["Tulkittu_Vuosi"] = found_year
                    item["Paikka"] = raw_place
                    item["Status"] = status
                    
                    results.append(item)
                    
    except Exception as e:
        st.error("Virhe: " + str(e))
        return []
        
    return results

def create_map_features(df):
    features = []
    for index, row in df.iterrows():
        y = row['Tulkittu_Vuosi']
        
        # Aikaleima
        time_str = str(y) + "-01-01"
        
        # Popup teksti
        popup_text = str(y) + ": " + str(row['Nimi'])
        
        # Tyylit
        style_opts = {}
        style_opts['fillColor'] = 'blue'
        style_opts['fillOpacity'] = 0.8
        style_opts['radius'] = 6
        style_opts['stroke'] = 'false'
        
        # GeoJSON properties
        props = {}
        props['time'] = time_str
        props['popup'] = popup_text
        props['icon'] = 'circle'
        props['iconstyle'] = style_opts
        
        # GeoJSON geometry
        geom = {}
        geom['type'] = 'Point'
        geom['coordinates'] = [row['lon'], row['lat']]
        
        # Koko feature
        feat = {}
        feat['type'] = 'Feature'
        feat['geometry'] = geom
        feat['properties'] = props
        
        features.append(feat)
        
    return features

# --- PÄÄOHJELMA ---

uploaded = st.file_uploader("Lataa GEDCOM", type=["ged"])
btn = st.button("Analysoi")

if uploaded and btn:
    # 1. Tallennetaan tiedosto levylle
    raw_bytes = uploaded.read()
    
    tf = tempfile.NamedTemporaryFile(delete=False, suffix=".ged")
    tf.write(raw_bytes)
    tf.close()
    
    tf_path = tf.name
    
    # 2. Parsitaan
    data = parse_gedcom_simple(tf_path)
    
    # Poistetaan väliaikaistiedosto
    if os.path.exists(tf_path):
        os.remove(tf_path)
    
    # 3. Näytetään tulokset
    if not data:
        st.error("Ei dataa.")
    else:
        df = pd.DataFrame(data)
        
        # --- DIAGNOSTIIKKA ---
        st.subheader("Analyysi")
        
        # Lasketaan määrät
        ok_mask = df['Status'] == 'OK'
        ok_df = df[ok_mask]
        
        fail_mask = df['Status'] == 'HYLÄTTY'
        fail_df = df[fail_mask]
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.info("Onnistuneet rivit: " + str(len(ok_df)))
            if not ok_df.empty:
                st.dataframe(ok_df.head(10))
                
        with col2:
            st.error("Hylätyt rivit: " + str(len(fail_df)))
            st.write("Tässä näet miksi päivämäärät eivät kelpaa:")
            if not fail_df.empty:
                # Näytetään vain relevantit sarakkeet
                show_cols = ['Raaka_Pvm', 'Paikka', 'Nimi']
                st.dataframe(fail_df[show_cols].head(10))

        # --- KARTTA TESTI ---
        # Piirretään kartta vain jos on onnistuneita rivejä
        if not ok_df.empty:
            st.write("---")
            st.subheader("Testikartta (10 ensimmäistä)")
            
            # Otetaan vain 10 ensimmäistä testiin
            test_set = ok_df.head(10).copy()
            places = test_set['Paikka'].unique().tolist()
            
            # Haetaan koordinaatit
            geolocator = Nominatim(user_agent="aikakartta_debug_safe")
            coords = {}
            
            st.write("Haetaan koordinaatteja...")
            
            for p in places:
                try:
                    time.sleep(1.1)
                    loc = geolocator.geocode(p, timeout=5)
                    if loc:
                        coords[p] = (loc.latitude, loc.longitude)
                except:
                    pass
            
            # Mapataan
            test_set['lat'] = test_set['Paikka'].map(lambda x: coords.get(x, (None, None))[0])
            test_set['lon'] = test_set['Paikka'].map(lambda x: coords.get(x, (None, None))[1])
            
            # Poistetaan tyhjät
            map_df = test_set.dropna(subset=['lat', 'lon'])
            
            if not map_df.empty:
                # Lajitellaan
                map_df = map_df.sort_values(by='Tulkittu_Vuosi')
                
                # Kartta
                m = folium.Map(location=[64, 26], zoom_start=4)
                
                features = create_map_features(map_df)
                
                TimestampedGeoJson(
                    {'type': 'FeatureCollection', 'features': features},
                    period='P1Y',
                    duration='P100Y',
                    auto_play=True,
                    loop=False
                ).add_to(m)
                
                st_folium(m, width=800, height=500)
            else:
                st.warning("Koordinaatteja ei löytynyt testiryhmälle.")
