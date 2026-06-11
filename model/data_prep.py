import pandas as pd
import numpy as np
from pathlib import Path
from datetime import date

DATA_DIR = Path(__file__).parent.parent / "data"
TODAY = date.today()

NAME_ALIASES = {
    "Bosnia & Herzegovina": "Bosnia and Herzegovina",
    "USA": "United States",
}

# Confederation membership — used to split WCQ weights into strong/weak tiers.
# UEFA and CONMEBOL qualifiers are the most competitive → 0.85
# CAF, CONCACAF, AFC, OFC qualifiers → 0.60
# Covers all 300 teams fitted by the model (all nations in intl_results 2014+).
CONFEDERATION = {
    # ── UEFA ────────────────────────────────────────────────────────────────
    "Albania": "UEFA", "Andorra": "UEFA", "Armenia": "UEFA",
    "Austria": "UEFA", "Azerbaijan": "UEFA", "Belarus": "UEFA",
    "Belgium": "UEFA", "Bosnia and Herzegovina": "UEFA", "Bulgaria": "UEFA",
    "Croatia": "UEFA", "Cyprus": "UEFA", "Czech Republic": "UEFA",
    "Denmark": "UEFA", "England": "UEFA", "Estonia": "UEFA",
    "Faroe Islands": "UEFA", "Finland": "UEFA", "France": "UEFA",
    "Georgia": "UEFA", "Germany": "UEFA", "Gibraltar": "UEFA",
    "Greece": "UEFA", "Hungary": "UEFA", "Iceland": "UEFA",
    "Ireland": "UEFA", "Israel": "UEFA", "Italy": "UEFA",
    "Kazakhstan": "UEFA", "Kosovo": "UEFA", "Latvia": "UEFA",
    "Liechtenstein": "UEFA", "Lithuania": "UEFA", "Luxembourg": "UEFA",
    "Malta": "UEFA", "Moldova": "UEFA", "Montenegro": "UEFA",
    "Netherlands": "UEFA", "North Macedonia": "UEFA", "Northern Ireland": "UEFA",
    "Norway": "UEFA", "Poland": "UEFA", "Portugal": "UEFA",
    "Romania": "UEFA", "Russia": "UEFA", "San Marino": "UEFA",
    "Scotland": "UEFA", "Serbia": "UEFA", "Slovakia": "UEFA",
    "Slovenia": "UEFA", "Spain": "UEFA", "Sweden": "UEFA",
    "Switzerland": "UEFA", "Turkey": "UEFA", "Ukraine": "UEFA",
    "Wales": "UEFA",
    # ── CONMEBOL ────────────────────────────────────────────────────────────
    "Argentina": "CONMEBOL", "Bolivia": "CONMEBOL", "Brazil": "CONMEBOL",
    "Chile": "CONMEBOL", "Colombia": "CONMEBOL", "Ecuador": "CONMEBOL",
    "Paraguay": "CONMEBOL", "Peru": "CONMEBOL", "Uruguay": "CONMEBOL",
    "Venezuela": "CONMEBOL",
    # ── CAF ─────────────────────────────────────────────────────────────────
    "Algeria": "CAF", "Angola": "CAF", "Benin": "CAF",
    "Botswana": "CAF", "Burkina Faso": "CAF", "Burundi": "CAF",
    "Cameroon": "CAF", "Cape Verde": "CAF", "Central African Republic": "CAF",
    "Chad": "CAF", "Comoros": "CAF", "Congo": "CAF",
    "DR Congo": "CAF", "Djibouti": "CAF", "Egypt": "CAF",
    "Equatorial Guinea": "CAF", "Eritrea": "CAF", "Eswatini": "CAF",
    "Ethiopia": "CAF", "Gabon": "CAF", "Gambia": "CAF",
    "Ghana": "CAF", "Guinea": "CAF", "Guinea-Bissau": "CAF",
    "Ivory Coast": "CAF", "Kenya": "CAF", "Lesotho": "CAF",
    "Liberia": "CAF", "Libya": "CAF", "Madagascar": "CAF",
    "Malawi": "CAF", "Mali": "CAF", "Mauritania": "CAF",
    "Mauritius": "CAF", "Morocco": "CAF", "Mozambique": "CAF",
    "Namibia": "CAF", "Niger": "CAF", "Nigeria": "CAF",
    "Rwanda": "CAF", "São Tomé and Príncipe": "CAF", "Senegal": "CAF",
    "Seychelles": "CAF", "Sierra Leone": "CAF", "Somalia": "CAF",
    "South Africa": "CAF", "South Sudan": "CAF", "Sudan": "CAF",
    "Tanzania": "CAF", "Togo": "CAF", "Tunisia": "CAF",
    "Uganda": "CAF", "Zambia": "CAF", "Zimbabwe": "CAF",
    # ── CONCACAF ────────────────────────────────────────────────────────────
    "Antigua and Barbuda": "CONCACAF", "Aruba": "CONCACAF",
    "Bahamas": "CONCACAF", "Barbados": "CONCACAF", "Belize": "CONCACAF",
    "Bermuda": "CONCACAF", "Canada": "CONCACAF", "Cayman Islands": "CONCACAF",
    "Costa Rica": "CONCACAF", "Cuba": "CONCACAF", "Curaçao": "CONCACAF",
    "Dominica": "CONCACAF", "Dominican Republic": "CONCACAF",
    "El Salvador": "CONCACAF", "French Guiana": "CONCACAF",
    "Grenada": "CONCACAF", "Guadeloupe": "CONCACAF", "Guatemala": "CONCACAF",
    "Guyana": "CONCACAF", "Haiti": "CONCACAF", "Honduras": "CONCACAF",
    "Jamaica": "CONCACAF", "Martinique": "CONCACAF", "Mexico": "CONCACAF",
    "Montserrat": "CONCACAF", "Nicaragua": "CONCACAF", "Panama": "CONCACAF",
    "Puerto Rico": "CONCACAF", "Saint Kitts and Nevis": "CONCACAF",
    "Saint Lucia": "CONCACAF", "Saint Vincent and the Grenadines": "CONCACAF",
    "Suriname": "CONCACAF", "Trinidad and Tobago": "CONCACAF",
    "Turks and Caicos Islands": "CONCACAF", "United States": "CONCACAF",
    "US Virgin Islands": "CONCACAF",
    # ── AFC ─────────────────────────────────────────────────────────────────
    "Afghanistan": "AFC", "Australia": "AFC", "Bahrain": "AFC",
    "Bangladesh": "AFC", "Bhutan": "AFC", "Cambodia": "AFC",
    "China": "AFC", "Chinese Taipei": "AFC", "Guam": "AFC",
    "Hong Kong": "AFC", "India": "AFC", "Indonesia": "AFC",
    "Iran": "AFC", "Iraq": "AFC", "Japan": "AFC",
    "Jordan": "AFC", "Kuwait": "AFC", "Kyrgyzstan": "AFC",
    "Laos": "AFC", "Lebanon": "AFC", "Macau": "AFC",
    "Malaysia": "AFC", "Maldives": "AFC", "Mongolia": "AFC",
    "Myanmar": "AFC", "Nepal": "AFC", "North Korea": "AFC",
    "Oman": "AFC", "Pakistan": "AFC", "Palestine": "AFC",
    "Philippines": "AFC", "Qatar": "AFC", "Saudi Arabia": "AFC",
    "Singapore": "AFC", "South Korea": "AFC", "Sri Lanka": "AFC",
    "Syria": "AFC", "Tajikistan": "AFC", "Thailand": "AFC",
    "Timor-Leste": "AFC", "Turkmenistan": "AFC", "United Arab Emirates": "AFC",
    "Uzbekistan": "AFC", "Vietnam": "AFC", "Yemen": "AFC",
    # ── OFC ─────────────────────────────────────────────────────────────────
    "American Samoa": "OFC", "Cook Islands": "OFC", "Fiji": "OFC",
    "New Caledonia": "OFC", "New Zealand": "OFC", "Papua New Guinea": "OFC",
    "Samoa": "OFC", "Solomon Islands": "OFC", "Tahiti": "OFC",
    "Tonga": "OFC", "Vanuatu": "OFC",
}

# WCQ weight by confederation: UEFA/CONMEBOL are strongly competitive
WCQ_WEIGHT_STRONG = 0.85   # UEFA, CONMEBOL
WCQ_WEIGHT_WEAK   = 0.60   # CAF, CONCACAF, AFC, OFC

# Competition weights — placeholder values; update after inspecting tournament counts below
COMPETITION_WEIGHTS = {
    # Tier 1 — World Cup finals + major continental championships
    "FIFA World Cup":        1.00,
    "UEFA Euro":             1.00,
    "Copa América":          1.00,
    "African Cup of Nations":1.00,
    "AFC Asian Cup":         1.00,
    "Gold Cup":              1.00,
    "Oceania Nations Cup":   1.00,
    "Confederations Cup":    1.00,
    # Tier 2 — WC qualification (blended; ideally split by confederation but
    # the source data has a single label — flagged as known limitation in PROGRESS.md D6)
    "FIFA World Cup qualification": 0.75,
    # Tier 2/3 — Continental qualification & Nations Leagues
    "UEFA Euro qualification":               0.65,
    "UEFA Nations League":                   0.65,
    "Copa América qualification":            0.65,
    "African Cup of Nations qualification":  0.55,
    "AFC Asian Cup qualification":           0.55,
    "CONCACAF Nations League":               0.55,
    "CONCACAF Nations League qualification": 0.45,
    "Gold Cup qualification":                0.45,
    "Oceania Nations Cup qualification":     0.45,
    # Tier 5 — Friendlies & invitational
    "Friendly":            0.20,
    "FIFA Series":         0.25,
    "CONCACAF Series":     0.25,
    "Kirin Cup":           0.20,
    "Kirin Challenge Cup": 0.20,
    "King's Cup":          0.20,
}
DEFAULT_WEIGHT = 0.35  # fallback for regional/minor tournaments (COSAFA, Island Games, etc.)


def load_results() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "intl_results.csv", parse_dates=["date"])

    # Filter to 2014 onward and drop missing scores
    df = df[df["date"].dt.year >= 2014].copy()
    df = df.dropna(subset=["home_score", "away_score"])

    # Normalise team names
    df["home_team"] = df["home_team"].replace(NAME_ALIASES)
    df["away_team"] = df["away_team"].replace(NAME_ALIASES)

    return df


def print_tournament_counts(df: pd.DataFrame) -> None:
    print("\n=== tournament value_counts ===")
    print(df["tournament"].value_counts().to_string())
    print("================================\n")


def apply_weights(df: pd.DataFrame) -> pd.DataFrame:
    # Time-decay: e^(-0.1 * age_in_years)
    age_days = (TODAY - df["date"].dt.date).apply(lambda d: d.days)
    df["age_years"] = age_days / 365.25
    df["time_decay"] = np.exp(-0.1 * df["age_years"])

    # Competition weight (base lookup — WCQ handled below)
    df["competition_weight"] = df["tournament"].map(COMPETITION_WEIGHTS).fillna(DEFAULT_WEIGHT)

    # Split FIFA World Cup qualification by confederation of the home team.
    # UEFA and CONMEBOL qualifiers are strongly competitive; all others less so.
    wcq_mask = df["tournament"] == "FIFA World Cup qualification"
    if wcq_mask.any():
        home_conf = df.loc[wcq_mask, "home_team"].map(CONFEDERATION)
        strong    = home_conf.isin(["UEFA", "CONMEBOL"])
        df.loc[wcq_mask & strong, "competition_weight"] = WCQ_WEIGHT_STRONG
        df.loc[wcq_mask & ~strong, "competition_weight"] = WCQ_WEIGHT_WEAK

    # Combined
    df["match_weight"] = df["competition_weight"] * df["time_decay"]

    return df


def prepare_data(verbose: bool = True) -> pd.DataFrame:
    df = load_results()

    if verbose:
        print_tournament_counts(df)
        print("Pausing — inspect the tournament labels above, then update COMPETITION_WEIGHTS.")
        input("Press Enter to continue...")

    df = apply_weights(df)

    keep_cols = [
        "date", "home_team", "away_team",
        "home_score", "away_score",
        "tournament", "neutral",
        "age_years", "time_decay", "competition_weight", "match_weight",
    ]
    return df[keep_cols].reset_index(drop=True)


if __name__ == "__main__":
    df = prepare_data(verbose=True)
    print(f"\nClean dataframe: {len(df):,} rows")
    print(df.dtypes)
    print(df.head())
