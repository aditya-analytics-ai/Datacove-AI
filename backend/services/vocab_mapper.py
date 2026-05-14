"""
vocab_mapper.py - Standardised vocabulary dictionaries and mapping engine.

Built-in vocabularies:
  - country_name   : free-text → ISO 3166-1 alpha-2 (e.g. "United States" → "US")
  - country_code   : ISO alpha-2 → ISO alpha-3
  - currency       : free-text / 3-letter → ISO 4217 code (e.g. "dollar" → "USD")
  - us_state       : abbreviation / name → full name (e.g. "CA" → "California")
  - gender         : free-text → normalised canonical (e.g. "M", "male" → "Male")
  - boolean        : free-text → True/False string ("yes"→"True", "0"→"False")

Usage (called from cleaning_engine via action "map_to_standard"):
  params = {
      "column": "country",
      "vocab":  "country_name",   # one of the keys above
      "unmapped": "keep"          # "keep" | "blank" | "error"
  }
"""
from __future__ import annotations
from typing import Any, Dict, Optional
import pandas as pd

# ── Vocabulary dictionaries ────────────────────────────────────────────────────

_COUNTRY_NAME_TO_ALPHA2: Dict[str, str] = {
    # Full names
    "afghanistan": "AF", "albania": "AL", "algeria": "DZ", "andorra": "AD",
    "angola": "AO", "argentina": "AR", "armenia": "AM", "australia": "AU",
    "austria": "AT", "azerbaijan": "AZ", "bahrain": "BH", "bangladesh": "BD",
    "belarus": "BY", "belgium": "BE", "belize": "BZ", "benin": "BJ",
    "bolivia": "BO", "bosnia": "BA", "botswana": "BW", "brazil": "BR",
    "brunei": "BN", "bulgaria": "BG", "burkina faso": "BF", "burundi": "BI",
    "cambodia": "KH", "cameroon": "CM", "canada": "CA", "chad": "TD",
    "chile": "CL", "china": "CN", "colombia": "CO", "congo": "CG",
    "costa rica": "CR", "croatia": "HR", "cuba": "CU", "cyprus": "CY",
    "czech republic": "CZ", "czechia": "CZ", "denmark": "DK",
    "dominican republic": "DO", "ecuador": "EC", "egypt": "EG",
    "el salvador": "SV", "ethiopia": "ET", "finland": "FI", "france": "FR",
    "georgia": "GE", "germany": "DE", "ghana": "GH", "greece": "GR",
    "guatemala": "GT", "haiti": "HT", "honduras": "HN", "hong kong": "HK",
    "hungary": "HU", "iceland": "IS", "india": "IN", "indonesia": "ID",
    "iran": "IR", "iraq": "IQ", "ireland": "IE", "israel": "IL",
    "italy": "IT", "jamaica": "JM", "japan": "JP", "jordan": "JO",
    "kazakhstan": "KZ", "kenya": "KE", "kuwait": "KW", "kyrgyzstan": "KG",
    "laos": "LA", "latvia": "LV", "lebanon": "LB", "libya": "LY",
    "liechtenstein": "LI", "lithuania": "LT", "luxembourg": "LU",
    "madagascar": "MG", "malaysia": "MY", "mali": "ML", "malta": "MT",
    "mauritius": "MU", "mexico": "MX", "moldova": "MD", "monaco": "MC",
    "mongolia": "MN", "montenegro": "ME", "morocco": "MA", "mozambique": "MZ",
    "myanmar": "MM", "namibia": "NA", "nepal": "NP", "netherlands": "NL",
    "new zealand": "NZ", "nicaragua": "NI", "nigeria": "NG",
    "north korea": "KP", "north macedonia": "MK", "norway": "NO", "oman": "OM",
    "pakistan": "PK", "panama": "PA", "paraguay": "PY", "peru": "PE",
    "philippines": "PH", "poland": "PL", "portugal": "PT", "qatar": "QA",
    "romania": "RO", "russia": "RU", "russian federation": "RU",
    "rwanda": "RW", "saudi arabia": "SA", "senegal": "SN", "serbia": "RS",
    "singapore": "SG", "slovakia": "SK", "slovenia": "SI",
    "south africa": "ZA", "south korea": "KR", "spain": "ES",
    "sri lanka": "LK", "sudan": "SD", "sweden": "SE", "switzerland": "CH",
    "syria": "SY", "taiwan": "TW", "tajikistan": "TJ", "tanzania": "TZ",
    "thailand": "TH", "togo": "TG", "trinidad and tobago": "TT",
    "tunisia": "TN", "turkey": "TR", "türkiye": "TR", "turkmenistan": "TM",
    "uganda": "UG", "ukraine": "UA", "united arab emirates": "AE", "uae": "AE",
    "united kingdom": "GB", "uk": "GB", "great britain": "GB",
    "united states": "US", "united states of america": "US", "usa": "US",
    "us": "US", "u.s.": "US", "u.s.a.": "US", "uruguay": "UY",
    "uzbekistan": "UZ", "venezuela": "VE", "vietnam": "VN", "yemen": "YE",
    "zambia": "ZM", "zimbabwe": "ZW",
}

# ISO alpha-2 → alpha-3
_ALPHA2_TO_ALPHA3: Dict[str, str] = {
    "AF":"AFG","AL":"ALB","DZ":"DZA","AD":"AND","AO":"AGO","AR":"ARG",
    "AM":"ARM","AU":"AUS","AT":"AUT","AZ":"AZE","BH":"BHR","BD":"BGD",
    "BY":"BLR","BE":"BEL","BZ":"BLZ","BJ":"BEN","BO":"BOL","BA":"BIH",
    "BW":"BWA","BR":"BRA","BN":"BRN","BG":"BGR","BF":"BFA","BI":"BDI",
    "KH":"KHM","CM":"CMR","CA":"CAN","TD":"TCD","CL":"CHL","CN":"CHN",
    "CO":"COL","CG":"COG","CR":"CRI","HR":"HRV","CU":"CUB","CY":"CYP",
    "CZ":"CZE","DK":"DNK","DO":"DOM","EC":"ECU","EG":"EGY","SV":"SLV",
    "ET":"ETH","FI":"FIN","FR":"FRA","GE":"GEO","DE":"DEU","GH":"GHA",
    "GR":"GRC","GT":"GTM","HT":"HTI","HN":"HND","HK":"HKG","HU":"HUN",
    "IS":"ISL","IN":"IND","ID":"IDN","IR":"IRN","IQ":"IRQ","IE":"IRL",
    "IL":"ISR","IT":"ITA","JM":"JAM","JP":"JPN","JO":"JOR","KZ":"KAZ",
    "KE":"KEN","KW":"KWT","KG":"KGZ","LA":"LAO","LV":"LVA","LB":"LBN",
    "LY":"LBY","LI":"LIE","LT":"LTU","LU":"LUX","MG":"MDG","MY":"MYS",
    "ML":"MLI","MT":"MLT","MU":"MUS","MX":"MEX","MD":"MDA","MC":"MCO",
    "MN":"MNG","ME":"MNE","MA":"MAR","MZ":"MOZ","MM":"MMR","NA":"NAM",
    "NP":"NPL","NL":"NLD","NZ":"NZL","NI":"NIC","NG":"NGA","KP":"PRK",
    "MK":"MKD","NO":"NOR","OM":"OMN","PK":"PAK","PA":"PAN","PY":"PRY",
    "PE":"PER","PH":"PHL","PL":"POL","PT":"PRT","QA":"QAT","RO":"ROU",
    "RU":"RUS","RW":"RWA","SA":"SAU","SN":"SEN","RS":"SRB","SG":"SGP",
    "SK":"SVK","SI":"SVN","ZA":"ZAF","KR":"KOR","ES":"ESP","LK":"LKA",
    "SD":"SDN","SE":"SWE","CH":"CHE","SY":"SYR","TW":"TWN","TJ":"TJK",
    "TZ":"TZA","TH":"THA","TG":"TGO","TT":"TTO","TN":"TUN","TR":"TUR",
    "TM":"TKM","UG":"UGA","UA":"UKR","AE":"ARE","GB":"GBR","US":"USA",
    "UY":"URY","UZ":"UZB","VE":"VEN","VN":"VNM","YE":"YEM","ZM":"ZMB",
    "ZW":"ZWE",
}

_CURRENCY_TO_ISO4217: Dict[str, str] = {
    # ISO codes (pass-through)
    "usd": "USD", "eur": "EUR", "gbp": "GBP", "jpy": "JPY", "cny": "CNY",
    "cad": "CAD", "aud": "AUD", "chf": "CHF", "inr": "INR", "mxn": "MXN",
    "brl": "BRL", "krw": "KRW", "sgd": "SGD", "hkd": "HKD", "nok": "NOK",
    "sek": "SEK", "dkk": "DKK", "nzd": "NZD", "zar": "ZAR", "rub": "RUB",
    "try": "TRY", "aed": "AED", "sar": "SAR", "qar": "QAR", "kwd": "KWD",
    "egp": "EGP", "pln": "PLN", "czk": "CZK", "huf": "HUF", "ron": "RON",
    "ils": "ILS", "pkr": "PKR", "php": "PHP", "idr": "IDR", "myr": "MYR",
    "thb": "THB", "vnd": "VND", "ngn": "NGN", "kes": "KES", "ghc": "GHS",
    "clp": "CLP", "cop": "COP", "ars": "ARS", "pen": "PEN",
    # Common names / symbols
    "dollar": "USD", "dollars": "USD", "us dollar": "USD", "usd $": "USD",
    "euro": "EUR", "euros": "EUR", "€": "EUR",
    "pound": "GBP", "pounds": "GBP", "pound sterling": "GBP", "£": "GBP",
    "yen": "JPY", "¥": "JPY",
    "yuan": "CNY", "renminbi": "CNY", "rmb": "CNY",
    "rupee": "INR", "rupees": "INR", "₹": "INR",
    "franc": "CHF", "francs": "CHF", "swiss franc": "CHF",
    "krona": "SEK", "krone": "NOK",
    "won": "KRW", "₩": "KRW",
    "real": "BRL", "reais": "BRL",
    "peso": "MXN",  # default; ambiguous
    "rand": "ZAR",
    "dirham": "AED",
    "riyal": "SAR",
    "lira": "TRY",
    "ruble": "RUB", "rouble": "RUB",
    "ringgit": "MYR",
    "baht": "THB",
    "dong": "VND",
    "rupiah": "IDR",
    "shekel": "ILS", "new shekel": "ILS",
    "zloty": "PLN",
    "forint": "HUF",
    "koruna": "CZK",
    "leu": "RON",
}

_US_STATE_TO_FULL: Dict[str, str] = {
    "al": "Alabama", "ak": "Alaska", "az": "Arizona", "ar": "Arkansas",
    "ca": "California", "co": "Colorado", "ct": "Connecticut",
    "de": "Delaware", "fl": "Florida", "ga": "Georgia", "hi": "Hawaii",
    "id": "Idaho", "il": "Illinois", "in": "Indiana", "ia": "Iowa",
    "ks": "Kansas", "ky": "Kentucky", "la": "Louisiana", "me": "Maine",
    "md": "Maryland", "ma": "Massachusetts", "mi": "Michigan",
    "mn": "Minnesota", "ms": "Mississippi", "mo": "Missouri",
    "mt": "Montana", "ne": "Nebraska", "nv": "Nevada",
    "nh": "New Hampshire", "nj": "New Jersey", "nm": "New Mexico",
    "ny": "New York", "nc": "North Carolina", "nd": "North Dakota",
    "oh": "Ohio", "ok": "Oklahoma", "or": "Oregon", "pa": "Pennsylvania",
    "ri": "Rhode Island", "sc": "South Carolina", "sd": "South Dakota",
    "tn": "Tennessee", "tx": "Texas", "ut": "Utah", "vt": "Vermont",
    "va": "Virginia", "wa": "Washington", "wv": "West Virginia",
    "wi": "Wisconsin", "wy": "Wyoming", "dc": "District of Columbia",
}
# also accept full names (pass-through normalised)
_US_STATE_TO_FULL.update({v.lower(): v for v in _US_STATE_TO_FULL.values()})

_GENDER_NORM: Dict[str, str] = {
    "m": "Male", "male": "Male", "man": "Male", "men": "Male",
    "boy": "Male", "mr": "Male", "gents": "Male", "masculine": "Male",
    "1": "Male",
    "f": "Female", "female": "Female", "woman": "Female", "women": "Female",
    "girl": "Female", "ms": "Female", "mrs": "Female", "feminine": "Female",
    "0": "Female",
    "nb": "Non-binary", "non-binary": "Non-binary", "nonbinary": "Non-binary",
    "non binary": "Non-binary", "enby": "Non-binary", "x": "Non-binary",
    "other": "Other", "prefer not to say": "Prefer not to say",
    "unknown": "Unknown", "n/a": "Unknown", "na": "Unknown", "": "Unknown",
    "unspecified": "Unknown",
}

_BOOLEAN_NORM: Dict[str, str] = {
    "true": "True", "yes": "True", "y": "True", "1": "True",
    "on": "True", "enabled": "True", "active": "True", "✓": "True",
    "false": "False", "no": "False", "n": "False", "0": "False",
    "off": "False", "disabled": "False", "inactive": "False", "✗": "False",
}

# Registry exposed to the outside world
VOCABS: Dict[str, Dict[str, str]] = {
    "country_name":  _COUNTRY_NAME_TO_ALPHA2,
    "country_code":  _ALPHA2_TO_ALPHA3,
    "currency":      _CURRENCY_TO_ISO4217,
    "us_state":      _US_STATE_TO_FULL,
    "gender":        _GENDER_NORM,
    "boolean":       _BOOLEAN_NORM,
}

VOCAB_META: Dict[str, Dict[str, Any]] = {
    "country_name": {
        "label": "Country Name → ISO Alpha-2",
        "description": 'Normalises free-text country names to ISO 3166-1 alpha-2 codes. E.g. "United States" → "US".',
        "example_in": "United States",
        "example_out": "US",
        "size": len(_COUNTRY_NAME_TO_ALPHA2),
    },
    "country_code": {
        "label": "Country Code: Alpha-2 → Alpha-3",
        "description": 'Converts ISO 3166-1 alpha-2 codes to alpha-3. E.g. "US" → "USA".',
        "example_in": "US",
        "example_out": "USA",
        "size": len(_ALPHA2_TO_ALPHA3),
    },
    "currency": {
        "label": "Currency → ISO 4217",
        "description": 'Normalises currency names and symbols to ISO 4217 codes. E.g. "dollar" → "USD", "€" → "EUR".',
        "example_in": "euro",
        "example_out": "EUR",
        "size": len(_CURRENCY_TO_ISO4217),
    },
    "us_state": {
        "label": "US State → Full Name",
        "description": 'Expands US state abbreviations to full names. E.g. "CA" → "California".',
        "example_in": "CA",
        "example_out": "California",
        "size": len({k for k in _US_STATE_TO_FULL if len(k) <= 2}),
    },
    "gender": {
        "label": "Gender → Canonical",
        "description": 'Normalises gender free-text to a consistent canonical form. E.g. "M", "male", "1" → "Male".',
        "example_in": "m",
        "example_out": "Male",
        "size": len(_GENDER_NORM),
    },
    "boolean": {
        "label": "Boolean → True/False",
        "description": 'Normalises boolean-like strings to "True" or "False". E.g. "yes", "1", "on" → "True".',
        "example_in": "yes",
        "example_out": "True",
        "size": len(_BOOLEAN_NORM),
    },
}


# ── Mapping engine ─────────────────────────────────────────────────────────────

def map_column_to_standard(
    df: pd.DataFrame,
    column: str,
    vocab: str,
    unmapped: str = "keep",   # "keep" | "blank" | "error"
) -> pd.DataFrame:
    """
    Map values in *column* through the named *vocab* dictionary.

    Returns a new DataFrame with the column values replaced.
    Adds a '__vocab_unmapped_<col>' flag column listing original
    values that had no mapping (when unmapped == "keep").
    """
    if column not in df.columns:
        raise ValueError(f"Column '{column}' not found in dataset.")
    if vocab not in VOCABS:
        raise ValueError(
            f"Unknown vocab '{vocab}'. Valid options: {sorted(VOCABS.keys())}"
        )

    lookup = VOCABS[vocab]
    df = df.copy()
    series = df[column].astype(str)

    def _map(val: str) -> Optional[str]:
        return lookup.get(val.strip().lower())

    mapped   = series.map(_map)
    unmapped_mask = mapped.isna()
    unmapped_vals = series[unmapped_mask].unique().tolist()

    if unmapped == "error" and unmapped_mask.any():
        raise ValueError(
            f"{int(unmapped_mask.sum())} values could not be mapped: "
            f"{unmapped_vals[:10]}"
        )
    elif unmapped == "blank":
        df[column] = mapped  # NaN for unmapped
    else:  # "keep"
        df[column] = mapped.where(~unmapped_mask, series)

    return df, {
        "vocab": vocab,
        "mapped": int((~unmapped_mask).sum()),
        "unmapped": int(unmapped_mask.sum()),
        "unmapped_sample": unmapped_vals[:20],
    }


def preview_mapping(
    values: list[str],
    vocab: str,
) -> list[dict]:
    """
    Return a preview list of {original, mapped, status} for a sample of values.
    Used by the API preview endpoint before committing.
    """
    if vocab not in VOCABS:
        raise ValueError(f"Unknown vocab '{vocab}'.")
    lookup = VOCABS[vocab]
    results = []
    for v in values:
        key = str(v).strip().lower()
        mapped = lookup.get(key)
        results.append({
            "original": v,
            "mapped": mapped,
            "status": "mapped" if mapped is not None else "unmapped",
        })
    return results
