import streamlit as st
import pandas as pd
import tempfile
import os
from ged4py.parser import GedcomReader
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import folium
from streamlit_folium import st_folium
import chardet

# --- Asetukset ---
st.set_page_config(page_title="Sukututkimuskartta", layout="wide")

st.title("📍 Sukututkimuskartta: Syntymäpaikat")
st.markdown("""
Tämä sovellus lukee GEDCOM-tiedoston, etsii henkilöiden syntymäpaikat ja -vuodet, 
ja piirtää ne kartalle aikajärjestyksessä (uusimmasta vanhimpaan).
""")

# --- Apufunktiot ---

def detect_encoding(file_bytes):
    """Yrittää tunnistaa tiedoston merkistökoodauksen."""
    result = chardet.detect(file_bytes)
    return result['encoding']

def parse_gedcom(file_path):
    """Lukee GEDCOM-tiedoston ja palauttaa listan henkilöistä."""
    data = []
    
    # Avataan gedcom ged4py-kirjastolla
    try:
        with GedcomReader(file_path) as parser:
            # KORJAUS: Iteroidaan suoraan objekteja, ei (id, obj) -pareja
            for indi in parser.records0("INDI"):
                
                # Varmistetaan, että nimi löytyy
                if not indi.name:
                    continue

                # Ged4py:n tapa hakea nimen osat
                try:
                    given = indi.name.given if indi.name.given else ""
                    surname = indi.name.surname if indi.name.surname else ""
                    full_name = f"{given} {surname}".strip()
                except:
                    full_name = "Tuntematon"
                
                # Etsitään syntymätapahtuma (BIRT)
                birt = indi.sub_tag("BIRT")
                if birt:
                    date_val = birt.sub_tag_value("DATE")
                    place_val = birt.sub_tag_value("PLAC")
                    
                    if place_val:
                        # Yritetään kaivaa vuosiluku
                        year = None
                        if date_val:
                            import re
                            years = re.findall(r'\d{4}', str(date_val))
                            if years:
                                year = int(years[-1]) 
                        
                        data.append({
                            "Nimi": full_name,
                            "Vuosi": year if year else 0,
                            "Alkuperäinen_Pvm": str(date_val), # Varmistetaan string-muoto
                            "Paikka": str(place_val)           # Varmistetaan string-muoto
                        })
    except Exception as e:
        st.error(f"Virhe tiedoston lukemisessa: {e}")
        return []
        
    return data

@st.cache_data
def get_coordinates(places_list):
    """Hakee koordinaatit paikannimille. Välimuistitettu suorituskyvyn vuoksi."""
    geolocator = Nominatim(user_agent="sukututkimus_kartta_sovellus")
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1.1) # 1.1s viive sääntöjen mukaan
    
    coords = {}
    total = len(places_list)
    my_bar = st.progress(0, text="Haetaan koordinaatteja...")

    for i, place in enumerate(places_list):
        # Yritetään hakea pelkällä paikalla, lisätään ", Finland" jos ei löydy (optio)
        # Pieni siivous: poistetaan sulut ja numerot jos niitä on
        clean_place = place.split(',')[0] # Usein "Kylä, Pitäjä, Maa" -> otetaan tarkin
        
        try:
            location = geocode(place)
            if location:
                coords[place] = (location.latitude, location.longitude)
            else:
                # Fallback: Yritetään hakea pelkällä ensimmäisellä sanalla/osalla
                location = geocode(clean_place)
                if location:
                     coords[place] = (location.latitude, location.longitude)
                else:
                    coords[place] = (None, None)
        except Exception as e:
            coords[place] = (None, None)
            
        progress_percent = int((i + 1) / total * 100)
        my_bar.progress(progress_percent, text=f"Haetaan: {place} ({i+1}/{total})")
    
    my_bar.empty()
    return coords

# --- Pääohjelma ---

uploaded_file = st.file_uploader("Lataa GEDCOM-tiedosto (.ged)", type=["ged"])

if uploaded_file is not None:
    # 1. Tallennetaan väliaikaistiedosto (ged4py vaatii polun tai seekable stream)
    # Tunnistetaan koodaus ensin, jotta ged4py osaa avata oikein tarvittaessa
    raw_data = uploaded_file.read()
    encoding = detect_encoding(raw_data)
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".ged") as tmp_file:
        tmp_file.write(raw_data)
        tmp_file_path = tmp_file.name

    st.success(f"Tiedosto ladattu. Tunnistettu koodaus: {encoding}")

    # 2. Parsitaan data
    with st.spinner("Luetaan sukupuuta..."):
        parsed_data = parse_gedcom(tmp_file_path)
    
    # Poistetaan väliaikaistiedosto
    os.remove(tmp_file_path)

    if not parsed_data:
        st.warning("Tiedostosta ei löytynyt henkilöitä, joilla on syntymäpaikka.")
    else:
        df = pd.DataFrame(parsed_data)
        
        # 3. Optimointi: Haetaan koordinaatit vain uniikeille paikoille
        unique_places = df['Paikka'].unique().tolist()
        st.info(f"Löydetty {len(df)} syntymätapahtumaa ja {len(unique_places)} uniikkia paikkakuntaa.")
        
        # Varoitus jos paikkoja on paljon
        if len(unique_places) > 50:
            st.warning("Huom: Paikkoja on paljon. Koordinaattien haku kestää hetken (n. 1 sekunti per paikka).")

        if st.button("Hae koordinaatit ja piirrä kartta"):
            coords_dict = get_coordinates(unique_places)
            
            # Yhdistetään koordinaatit DataFrameen
            df['lat'] = df['Paikka'].map(lambda x: coords_dict.get(x, (None, None))[0])
            df['lon'] = df['Paikka'].map(lambda x: coords_dict.get(x, (None, None))[1])
            
            # Poistetaan ne, joille ei löytynyt koordinaatteja
            df_map = df.dropna(subset=['lat', 'lon']).copy()
            
            # 4. Lajittelu: Uusimmasta vanhimpaan
            df_map = df_map.sort_values(by='Vuosi', ascending=False)
            
            not_found_count = len(df) - len(df_map)
            if not_found_count > 0:
                st.warning(f"Koordinaatteja ei löytynyt {not_found_count} paikalle. Tarkista paikannimien kirjoitusasu.")

            # --- Kartan piirto ---
            # Keskitetään Suomeen
            m = folium.Map(location=[64.0, 26.0], zoom_start=5)

            # Lisätään pisteet
            for index, row in df_map.iterrows():
                # Tooltip teksti
                vuosi_str = str(row['Vuosi']) if row['Vuosi'] > 0 else "?"
                tooltip_text = f"{row['Nimi']} ({vuosi_str}), {row['Paikka']}"
                
                folium.CircleMarker(
                    location=[row['lat'], row['lon']],
                    radius=5,
                    popup=tooltip_text,
                    tooltip=tooltip_text,
                    color="blue",
                    fill=True,
                    fill_color="blue",
                    fill_opacity=0.6
                ).add_to(m)

            st_folium(m, width=1000, height=800)
            
            # Näytetään data taulukkona kartan alla
            st.subheader("Löydetyt tiedot")
            st.dataframe(df_map[['Vuosi', 'Nimi', 'Paikka', 'lat', 'lon']])
