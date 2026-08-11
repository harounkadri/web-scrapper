import requests
import pandas as pd
import re
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup


# ======================================
# 1. CONFIGURATION
# ======================================

URL = "https://en.wikipedia.org/wiki/List_of_countries_by_GDP_(nominal)"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


# ======================================
# 2. FETCH PAGE
# ======================================

print(f"🌐 Fetching: {URL}")

session = requests.Session()

retry = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[500, 502, 503, 504],
    allowed_methods=["GET"],
)

adapter = HTTPAdapter(max_retries=retry)

session.mount("http://", adapter)
session.mount("https://", adapter)


try:
    response = session.get(
        URL,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    print("✅ Page fetched successfully!")

except requests.exceptions.Timeout:
    print("❌ Connection timed out.")
    raise SystemExit

except requests.exceptions.RequestException as e:
    print(f"❌ Error fetching page: {e}")
    raise SystemExit


# ======================================
# 3. PARSE HTML
# ======================================

soup = BeautifulSoup(
    response.content,
    "html.parser"
)

tables = soup.find_all(
    "table",
    class_="wikitable"
)

print(f"📋 Found {len(tables)} wikitable(s).")


# ======================================
# 4. FIND GDP TABLE
# ======================================

target_table = None

for index, table in enumerate(tables):

    header_row = table.find("tr")

    if not header_row:
        continue

    headers = [
        th.get_text(" ", strip=True)
        for th in header_row.find_all("th")
    ]

    print(
        f"   Table {index + 1} headers: "
        f"{headers[:5]}"
    )

    headers_lower = [
        header.lower()
        for header in headers
    ]

    # We are looking specifically for:
    # Country/Territory
    # AND
    # IMF / World Bank / GDP

    has_country = any(
        "country" in header
        or "territory" in header
        for header in headers_lower
    )

    has_gdp_source = any(
        "imf" in header
        or "world bank" in header
        or "gdp" in header
        for header in headers_lower
    )

    if has_country and has_gdp_source:

        target_table = table

        print(
            f"✅ GDP table found: Table {index + 1}"
        )

        break


if target_table is None:

    raise ValueError(
        "❌ Could not find the GDP table."
    )


# ======================================
# 5. EXTRACT TABLE HEADERS
# ======================================

header_row = target_table.find("tr")

headers = []

for th in header_row.find_all("th"):

    text = th.get_text(
        " ",
        strip=True
    )

    # Remove Wikipedia citations [1], [2], etc.
    text = re.sub(
        r"\[\d+\]",
        "",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    headers.append(
        text.strip()
    )


print(f"\n📊 Final Headers: {headers}")


# ======================================
# 6. EXTRACT ROWS
# ======================================

data_rows = []

for tr in target_table.find_all("tr")[1:]:

    cells = tr.find_all(
        ["td", "th"]
    )

    if not cells:
        continue

    row = []

    for cell in cells:

        text = cell.get_text(
            " ",
            strip=True
        )

        # Remove citations
        text = re.sub(
            r"\[\d+\]",
            "",
            text
        )

        # Remove excessive spaces
        text = re.sub(
            r"\s+",
            " ",
            text
        )

        row.append(
            text.strip()
        )

    # Only keep rows with enough columns
    if len(row) >= len(headers):

        row = row[:len(headers)]

        data_rows.append(row)


print(
    f"📋 Extracted {len(data_rows)} rows of data."
)


# ======================================
# 7. CREATE DATAFRAME
# ======================================

df = pd.DataFrame(
    data_rows,
    columns=headers
)

print(
    f"📊 DataFrame created with "
    f"{df.shape[0]} rows and "
    f"{df.shape[1]} columns."
)


# ======================================
# 8. IDENTIFY COUNTRY COLUMN
# ======================================

country_col = None

for column in df.columns:

    column_lower = column.lower()

    if (
        "country" in column_lower
        or "territory" in column_lower
    ):

        country_col = column
        break


if country_col is None:

    raise ValueError(
        "❌ Country/Territory column not found."
    )


# ======================================
# 9. IDENTIFY GDP COLUMN
# ======================================

# We will use IMF GDP because it is the
# first GDP estimate on the Wikipedia table.

gdp_col = None

for column in df.columns:

    column_lower = column.lower()

    if "imf" in column_lower:

        gdp_col = column
        break


# Fallback to World Bank
if gdp_col is None:

    for column in df.columns:

        column_lower = column.lower()

        if "world bank" in column_lower:

            gdp_col = column
            break


if gdp_col is None:

    raise ValueError(
        "❌ Could not find a GDP column."
    )


print(
    f"   Country column: {country_col}"
)

print(
    f"   GDP column: {gdp_col}"
)


# ======================================
# 10. RENAME COLUMNS
# ======================================

df = df.rename(
    columns={
        country_col: "Country",
        gdp_col: "GDP_Nominal"
    }
)


# ======================================
# 11. CLEAN COUNTRY NAMES
# ======================================

df["Country"] = (
    df["Country"]
    .astype(str)
    .str.strip()
)


# ======================================
# 12. CLEAN GDP
# ======================================

def clean_gdp(value):

    if pd.isna(value):
        return None

    value = str(value)

    # Remove Wikipedia references
    value = re.sub(
        r"\[\d+\]",
        "",
        value
    )

    # Extract first number
    match = re.search(
        r"[\d,]+(?:\.\d+)?",
        value
    )

    if not match:
        return None

    number = match.group(0)

    number = number.replace(
        ",",
        ""
    )

    try:

        return float(number)

    except ValueError:

        return None


df["GDP_Nominal"] = (
    df["GDP_Nominal"]
    .apply(clean_gdp)
)


# ======================================
# 13. REMOVE INVALID GDP ROWS
# ======================================

before = len(df)

df = df.dropna(
    subset=["GDP_Nominal"]
)

removed = before - len(df)

print(
    f"   Dropped {removed} rows "
    f"with invalid GDP."
)


# ======================================
# 14. ADD RANK
# ======================================

df = df.reset_index(
    drop=True
)

df["Rank"] = (
    df["GDP_Nominal"]
    .rank(
        ascending=False,
        method="min"
    )
    .astype(int)
)


# ======================================
# 15. SORT BY GDP
# ======================================

df = df.sort_values(
    "GDP_Nominal",
    ascending=False
).reset_index(
    drop=True
)


# Recalculate rank after sorting
df["Rank"] = range(
    1,
    len(df) + 1
)


# ======================================
# 16. ROUND GDP
# ======================================

df["GDP_Billions"] = (
    df["GDP_Nominal"]
    .round(2)
)


# ======================================
# 17. ADD YEAR
# ======================================

df["Year"] = "2026"


# ======================================
# 18. REORDER COLUMNS
# ======================================

df = df[
    [
        "Rank",
        "Country",
        "GDP_Nominal",
        "GDP_Billions",
        "Year"
    ]
]


# ======================================
# 19. SUMMARY
# ======================================

summary = pd.DataFrame({

    "Metric": [
        "Total Countries",
        "Average GDP (Billions)",
        "Median GDP (Billions)",
        "Minimum GDP (Billions)",
        "Maximum GDP (Billions)",
        "Total GDP (Billions)"
    ],

    "Value": [

        len(df),

        round(
            df["GDP_Billions"].mean(),
            2
        ),

        round(
            df["GDP_Billions"].median(),
            2
        ),

        round(
            df["GDP_Billions"].min(),
            2
        ),

        round(
            df["GDP_Billions"].max(),
            2
        ),

        round(
            df["GDP_Billions"].sum(),
            2
        )
    ]
})


# ======================================
# 20. SAVE CSV
# ======================================

csv_file = "gdp_data.csv"

df.to_csv(
    csv_file,
    index=False
)

print(
    f"✅ CSV saved: {csv_file}"
)


# ======================================
# 21. SAVE EXCEL
# ======================================

excel_file = "gdp_report.xlsx"

with pd.ExcelWriter(
    excel_file,
    engine="openpyxl"
) as writer:

    df.to_excel(
        writer,
        sheet_name="GDP_Data",
        index=False
    )

    summary.to_excel(
        writer,
        sheet_name="Summary",
        index=False
    )


print(
    f"✅ Excel saved: {excel_file}"
)


# ======================================
# 22. PREVIEW
# ======================================

print("\n📊 TOP 10 COUNTRIES:")

print(
    df.head(10).to_string(
        index=False
    )
)


print("\n📊 SUMMARY:")

print(
    summary.to_string(
        index=False
    )
)


# ======================================
# 23. FINISHED
# ======================================

print(
    f"\n✅ Scraping complete!"
)

print(
    f"   {len(df)} countries extracted."
)

print(
    "   Files created:"
)

print(
    "   📄 gdp_data.csv"
)

print(
    "   📊 gdp_report.xlsx"
)