import matplotlib.pyplot as plt
import collections
import re
import datetime

# Luetaan GEDCOM-tiedosto
file_path = 'sukupuu.ged.ged'

individuals = []
current_ind = {}
reading_birth = False
reading_death = False

with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
    for line in f:
        line = line.strip()
        parts = line.split(' ', 2)
        level = parts[0]
        tag = parts[1] if len(parts) > 1 else ''
        value = parts[2] if len(parts) > 2 else ''

        if level == '0' and value == 'INDI':
            if current_ind:
                individuals.append(current_ind)
            current_ind = {'name': '', 'birth_date': '', 'death_date': '', 'sex': ''}
            reading_birth = False
            reading_death = False
        
        if not current_ind:
            continue
            
        if level == '1' and tag == 'NAME':
            current_ind['name'] = value.replace('/', '').strip()
        
        elif level == '1' and tag == 'SEX':
            current_ind['sex'] = value
            
        elif level == '1' and tag == 'BIRT':
            reading_birth = True
            reading_death = False
            
        elif level == '1' and tag == 'DEAT':
            reading_death = True
            reading_birth = False
            
        elif level == '2' and tag == 'DATE':
            if reading_birth:
                current_ind['birth_date'] = value
            elif reading_death:
                current_ind['death_date'] = value

    if current_ind:
        individuals.append(current_ind)

# --- Datan käsittely ---

first_names = []
birth_months = []
lifespans = [] # (syntymävuosi, ikä)

months_map = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
}

def extract_year(date_str):
    match = re.search(r'\d{4}', date_str)
    if match:
        return int(match.group(0))
    return None

def extract_month(date_str):
    for m_str, m_int in months_map.items():
        if m_str in date_str.upper():
            return m_int
    return None

for ind in individuals:
    # 1. Nimet
    full_name = ind.get('name', '')
    if full_name:
        parts = full_name.split()
        if parts:
            first_names.append(parts[0]) # Otetaan ensimmäinen nimi
            
    # 2. Kuukaudet
    b_date = ind.get('birth_date', '')
    if b_date:
        m = extract_month(b_date)
        if m:
            birth_months.append(m)
            
    # 3. Elinikä
    d_date = ind.get('death_date', '')
    if b_date and d_date:
        b_year = extract_year(b_date)
        d_year = extract_year(d_date)
        if b_year and d_year and d_year > b_year:
            age = d_year - b_year
            if age < 110: # Suodatetaan virheelliset datat
                lifespans.append((b_year, age))

# --- Grafiikka 1: Suosituimmat etunimet ---
name_counts = collections.Counter(first_names).most_common(10)
names, counts = zip(*name_counts) if name_counts else ([], [])

plt.figure(figsize=(10, 6))
plt.barh(names[::-1], counts[::-1], color='#69b3a2')
plt.title('Suvun 10 suosituinta etunimeä', fontsize=16)
plt.xlabel('Lukumäärä')
plt.grid(axis='x', linestyle='--', alpha=0.7)
plt.tight_layout()
plt.savefig('grafiikka1_nimet.png')
plt.close()

# --- Grafiikka 2: Syntymäkuukaudet ---
month_counts = collections.Counter(birth_months)
sorted_months = [month_counts.get(i, 0) for i in range(1, 13)]
month_names = ['Tammi', 'Helmi', 'Maalis', 'Huhti', 'Touko', 'Kesä', 
               'Heinä', 'Elo', 'Syys', 'Loka', 'Marras', 'Joulu']

plt.figure(figsize=(10, 6))
colors = plt.cm.viridis([i/12 for i in range(12)])
plt.bar(month_names, sorted_months, color=colors)
plt.title('Missä kuussa sukuun synnytään?', fontsize=16)
plt.ylabel('Syntyneiden määrä')
plt.xticks(rotation=45)
plt.grid(axis='y', linestyle='--', alpha=0.5)
plt.tight_layout()
plt.savefig('grafiikka2_kuukaudet.png')
plt.close()

# --- Grafiikka 3: Elinikä ja historia ---
if lifespans:
    b_years, ages = zip(*lifespans)
    plt.figure(figsize=(10, 6))
    plt.scatter(b_years, ages, alpha=0.6, c=ages, cmap='coolwarm', edgecolors='grey')
    plt.title('Elinikä syntymävuoden mukaan', fontsize=16)
    plt.xlabel('Syntymävuosi')
    plt.ylabel('Ikä kuollessa')
    plt.grid(True, linestyle='--', alpha=0.5)
    
    # Trendiviiva (yksinkertainen)
    if len(b_years) > 1:
        import numpy as np
        z = np.polyfit(b_years, ages, 1)
        p = np.poly1d(z)
        plt.plot(b_years, p(b_years), "r--", label='Trendi')
        plt.legend()
        
    plt.tight_layout()
    plt.savefig('grafiikka3_elinika.png')
    plt.close()
