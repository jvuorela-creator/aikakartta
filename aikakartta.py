import streamlit as st
import pandas as pd
import tempfile
import os
import re
from ged4py.parser import GedcomReader
import folium
from folium.plugins import TimestampedGeoJson
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
import time

# --- ASETUKSET ---
st.set_page_config(page_title="Päivämäärä-testeri", layout="wide")
st.title("🕵️ Sukututkimuskartta: Päivämäärä-testeri")

st.markdown("""
**Ongelman syy:** Ohjelma todennäköisesti hylkää suurimman osan päivämääristä, koska ne ovat erikoisessa muodossa.
Tämä työkalu näyttää listan kaikista luetuista riveistä, jotta näemme miltä päivämäärät näyttävät.
""")

# --- APUFUNKTIOT ---

def parse_gedcom_debug(file_path):
    # Tallennetaan kaikki löydökset, myös epäonnistuneet
    results = []
    
    try:
        with GedcomReader(file_path) as parser:
            # Käydään läpi INDI (henkilöt)
            for indi in parser.records0("INDI"):
                
                # Nimi
                full_name = "Tuntematon"
                try:
                    if indi.name:
                        g = indi.name.given or ""
                        s = indi.name.surname or ""
                        full_name = (g + " " + s).strip()
                except:
                    pass

                # Syntymä
                birt = indi.sub_tag("BIRT")
                if birt:
                    date_val = birt.sub_tag_value("DATE")
                    place_val = birt.sub_tag_value("PLAC")
                    
                    # Muutetaan stringiksi varmuuden vuoksi
                    raw_date = str(date_val) if date_val else ""
                    raw_place = str(place_val) if place_val else ""
                    
                    # Yritetään etsiä vuosiluku
                    found_year = 0
                    years = re.findall(r'\d{4}', raw_date)
                    if years:
                        found_year = int(years[-1])
                    
                    # Tallennetaan debug-tieto
                    item = {
                        "Nimi": full_name,
                        "Raaka_Pvm": raw_date,   # Tämä on se mitä GEDCOMissa lukee oikeasti
                        "Tulkittu_Vuosi": found_year,
                        "Paikka": raw_place,
                        "Status": "OK" if (found_year > 0 and raw_place != "") else "HYLÄTTY"
                    }
                    results.append(item)
                    
    except Exception as e:
        st.error("Virhe tiedoston luvussa: " + str(e))
        return []
        
    return results

@st.cache_data
def get_coords_simple(places):
    # Yksinkertainen geokoodaus ilman välimuistia tässä testissä
    geolocator = Nominatim(user_agent="aikakartta_debug_run")
    coords = {}
    
    # Otetaan vain 10 ensimmäistä uniikkia paikkaa testiksi, ettei mene jumiin
    test_places = places[:10]
    
    if len(places) > 0:
        st.info("Haetaan koordinaatteja vain 10 ensimmäiselle paikalle testiksi...")
    
    for p in test_places:
        try:
            time.sleep(1.1)
            loc = geolocator.geocode(p, timeout=5)
            if loc:
                coords[p] = (loc.latitude, loc.longitude)
        except:
            pass
    return coords

def create_features(df):
    feats = []
    for _, row in df.iterrows():
        y = row['Tulkittu_Vuosi']
        time_str = str(y) + "-01-01"
        popup = str(y) + ": " + row['Nimi']
        
        # Tyylit erikseen
        istyle = {
            'fillColor': 'blue',
            'fillOpacity': 0.8,
            'stroke': 'false',
            'radius': 6
        }
        
        props = {
            'time': time_str,
            'popup': popup,
            'icon': 'circle',
            'iconstyle': istyle,
            'style': {'color': 'blue'}
        }
        
        geo = {
            'type': 'Point',
            'coordinates': [row['lon'], row['lat']]
        }
        
        f = {
            'type': 'Feature',
            'geometry': geo,
            'properties': props
        }
        feats.append(f)
    return feats

# --- PÄÄOHJELMA ---

uploaded = st.file_uploader("Lataa GEDCOM", type=["ged"])
btn = st.button("Analysoi tiedosto")

if uploaded and btn:
    # 1. Lue tiedosto
    bytes_data = uploaded.read()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".ged") as tf:
        tf.write(bytes_data)
        tf_path = tf.name
    
    # 2. Parsitaan
    data = parse_gedcom_debug(tf_path)
    os.remove(tf_path)
    
    if not data:
        st.error("Ei dataa löytynyt.")
    else:
        df = pd.DataFrame(data)
        
        # 3. NÄYTETÄÄN TAULUKKO (TÄMÄ ON TÄRKEIN KOHTA)
        st.subheader("Analyysin tulos")
        
        col1, col2 = st.columns(2)
        with col1:
            ok_count = len(df[df['Status'] == 'OK'])
            fail_count = len(df[df['Status'] == 'HYLÄTTY'])
            st.metric("Kelvolliset rivit", ok_count)
            st.metric("Hylätyt rivit", fail_count)
        
        with col2:
            st.write("Esimerkki hylätyistä riveistä (Miksi nämä eivät toimi?):")
            st.dataframe(df[df['Status'] == 'HYLÄTTY'].head(10))

        st.write("Esimerkki hyväksytyistä riveistä:")
        st.dataframe(df[df['Status'] == 'OK'].head(
