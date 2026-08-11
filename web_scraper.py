import requests
import pandas as pd
import re
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

# ======================================
# 1. FETCH WITH RETRIES & TIMEOUT
# ======================================
url = "https://en.wikipedia.org/wiki/List_of_countries_by_GDP_(nominal)"
print(f"🌐 Fetching: {url}")

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# Session with retry logic
session = requests.Session()
retry = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
adapter = HTTPAdapter(max_retries=retry)
session.mount('http://', adapter)
session.mount('https://', adapter)

try:
    response = session.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    print("✅ Page fetched successfully!")
except requests.exceptions.Timeout:
    print("❌ Connection timed out. Please check your internet or try using a VPN.")
    exit()
except requests.exceptions.RequestException as e:
    print(f"❌ Error fetching page: {e}")
    exit()

# ======================================
# 2. PARSE AND FIND THE CORRECT TABLE
# ======================================
soup = BeautifulSoup(response.content, 'html.parser')

tables = soup.find_all('table', class_='wikitable')
print(f"📋 Found {len(tables)} wikitable(s).")

target_table = None

for idx, tbl in enumerate(tables):
    header_row = tbl.find('tr')
    if not header_row:
        continue
    
    headers_text = [th.get_text(strip=True) for th in header_row.find_all('th')]
    print(f"   Table {idx+1} headers: {headers_text[:5]}...")
    
    # Check for GDP ranking table: has 'Rank' or (country + gdp/billion)
    has_rank = any('rank' in h.lower() for h in headers_text)
    has_country = any('country' in h.lower() or 'territory' in h.lower() for h in headers_text)
    has_gdp = any('gdp' in h.lower() or 'billion' in h.lower() or 'us$' in h.lower() for h in headers_text)
    
    if has_rank or (has_country and has_gdp):
        # Verify first column has numeric values (rank)
        data_rows = tbl.find_all('tr')[1:6]
        numeric_counts = 0
        for tr in data_rows:
            first_td = tr.find('td')
            if first_td:
                text = first_td.get_text(strip=True)
                text = re.sub(r'\[\d+\]', '', text)
                if text.replace(',', '').replace('.', '').isdigit():
                    numeric_counts += 1
        if numeric_counts >= 3:
            target_table = tbl
            print(f"✅ Found GDP ranking table (Table {idx+1})")
            break

# Fallback: if not found, try using the second table (commonly the GDP table)
if not target_table and len(tables) >= 2:
    target_table = tables[1]
    print("⚠️  Using fallback: Table 2 (likely the GDP ranking table)")
elif not target_table:
    raise ValueError("❌ Could not find the GDP ranking table.")

table = target_table

# ======================================
# 3. EXTRACT HEADERS
# ======================================
header_row = table.find('tr')
headers = []
for th in header_row.find_all('th'):
    text = th.get_text(strip=True)
    text = re.sub(r'\[\d+\]', '', text)
    headers.append(text.strip())

print(f"\n📊 Final Headers: {headers}")

# ======================================
# 4. EXTRACT DATA ROWS
# ======================================
data_rows = []
for tr in table.find_all('tr')[1:]:
    cells = tr.find_all(['td', 'th'])
    if not cells:
        continue
    
    row = []
    for cell in cells:
        text = cell.get_text(strip=True)
        text = re.sub(r'\[\d+\]', '', text)
        row.append(text.strip())
    
    if row and len(row) >= 3:
        first_val = row[0].replace(',', '').replace('.', '').strip()
        if first_val.isdigit() or first_val == '—':
            data_rows.append(row)

print(f"📋 Extracted {len(data_rows)} rows of data.")

# ======================================
# 5. CREATE DATAFRAME
# ======================================
df = pd.DataFrame(data_rows, columns=headers)
print(f"📊 DataFrame created with {df.shape[0]} rows and {df.shape[1]} columns.")

# ======================================
# 6. CLEAN DATA
# ======================================
print("\n🔄 Cleaning data...")

# Identify key columns
rank_col = headers[0]
country_col = None
gdp_col = None
year_col = None

for col in df.columns:
    col_lower = col.lower()
    if 'country' in col_lower or 'territory' in col_lower or 'economy' in col_lower:
        country_col = col
    elif 'gdp' in col_lower or 'billion' in col_lower or 'us$' in col_lower:
        gdp_col = col
    elif 'year' in col_lower or 'date' in col_lower:
        year_col = col

if not country_col:
    country_col = headers[1] if len(headers) > 1 else 'Country'
if not gdp_col:
    gdp_col = headers[2] if len(headers) > 2 else 'GDP'

print(f"   Using: Rank='{rank_col}', Country='{country_col}', GDP='{gdp_col}'")

# Rename to standard names
df = df.rename(columns={
    rank_col: 'Rank',
    country_col: 'Country',
    gdp_col: 'GDP_Nominal'
})
if year_col:
    df = df.rename(columns={year_col: 'Year'})

# Clean GDP
def clean_gdp(value):
    if isinstance(value, str):
        cleaned = re.sub(r'[^0-9.]', '', value)
        try:
            return float(cleaned)
        except:
            return None
    return value

df['GDP_Nominal'] = df['GDP_Nominal'].apply(clean_gdp)
before = len(df)
df = df.dropna(subset=['GDP_Nominal'])
print(f"   Dropped {before - len(df)} rows with invalid GDP.")

# Clean Rank
df['Rank'] = df['Rank'].apply(lambda x: 999 if x == '—' else x)
df['Rank'] = pd.to_numeric(df['Rank'], errors='coerce').fillna(999).astype(int)
df = df.sort_values('Rank').reset_index(drop=True)

# Add GDP_Billions
df['GDP_Billions'] = df['GDP_Nominal'].round(2)

# Add Year if missing
if 'Year' not in df.columns:
    df['Year'] = '2025'  # default

# ======================================
# 7. SUMMARY
# ======================================
summary = pd.DataFrame({
    'Metric': ['Total Countries', 'Average GDP (Billions)', 'Median GDP (Billions)',
               'Min GDP (Billions)', 'Max GDP (Billions)', 'Total GDP (Billions)'],
    'Value': [
        len(df),
        round(df['GDP_Nominal'].mean(), 2),
        round(df['GDP_Nominal'].median(), 2),
        round(df['GDP_Nominal'].min(), 2),
        round(df['GDP_Nominal'].max(), 2),
        round(df['GDP_Nominal'].sum(), 2)
    ]
})

# ======================================
# 8. EXPORT
# ======================================
csv_file = "gdp_data.csv"
df.to_csv(csv_file, index=False)
print(f"✅ CSV saved: {csv_file}")

excel_file = "gdp_report.xlsx"
with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
    df.to_excel(writer, sheet_name='GDP_Data', index=False)
    summary.to_excel(writer, sheet_name='Summary', index=False)
print(f"✅ Excel saved: {excel_file}")

# ======================================
# 9. PREVIEW
# ======================================
print("\n📊 Data Preview:")
print(df.head(10).to_string())

print("\n📊 Summary Statistics:")
print(summary.to_string(index=False))

print(f"\n✅ Scraping complete! {len(df)} countries extracted.")
print("   Files created: gdp_data.csv, gdp_report.xlsx")