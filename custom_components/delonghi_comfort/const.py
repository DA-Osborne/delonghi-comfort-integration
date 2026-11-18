# Constants for De'Longhi Comfort Integration
import base64

DOMAIN = "delonghi_comfort"

# API Constants from the original script
SDK_BUILD = 16650

API_KEY = "3_e5qn7USZK-QtsIso1wCelqUKAK_IVEsYshRIssQ-X-k55haiZXmKWDHDRul2e5Y2"
CLIENT_ID = "1S8q1WJEs-emOB43Z0-66WnL"
CLIENT_SECRET = "lmnceiD0B-4KPNN5ZS6WuWU70j9V5BCuSlz2OPsvHkyLryhMkJkPvKsivfTq3RfNYj8GpCELtOBvhaDIzKcBtg"
AUTHORIZATION_HEADER = (
    "Basic " + base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
)
APP_ID = "DeLonghiComfort2-mw-id"
APP_SECRET = "DeLonghiComfort2-Yg4miiqiNcf0Or-EhJwRh7ACfBY"

BROWSER_USER_AGENT = "Mozilla/5.0 (iPhone; CPU iPhone OS 13_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/79.0.3945.73 Mobile/15E148 Safari/604.1"
TOKEN_USER_AGENT = "DeLonghiComfort/3 CFNetwork/1568.300.101 Darwin/24.2.0"
API_USER_AGENT = "DeLonghiComfort/5.1.1 (iPhone; iOS 18.2; Scale/3.00)"

# Language mappings
LANGUAGES = {
    "en": "GB",
    "pt": "PT",
    "en-ca": "CA",
    "fr-ca": "CA",
    "es-mx": "MX",
    "es-co": "CO",
    "es-pe": "PE",
    "en-us": "US",
    "pt-br": "BR",
    "es-cl": "CL",
    "en-za": "ZA",
    "es": "ES",
    "fr": "FR",
    "lu": "LU",
    "nl": "NL",
    "my": "MY",
    "fr-be": "BE",
    "nl-inf": "BE",
    "de": "DE",
    "fr-ch": "CH",
    "de-inf": "CH",
    "it": "IT",
    "mt-mt": "MT",
    "en-mt": "MT",
    "hr": "HR",
    "sr": "RS",
    "sl": "SI",
    "br": "BG",
    "el": "GR",
    "ro": "RO",
    "tr": "TR",
    "cs": "CZ",
    "sk": "SK",
    "hu": "HU",
    "de-at": "AT",
    "uk": "UA",
    "sv": "SE",
    "fi": "FI",
    "no": "NO",
    "da": "DK",
    "pl": "PL",
    "et-ee": "EE",
    "lt-lt": "LT",
    "lv-lv": "LV",
    "en-ae": "AE",
    "ar-ae": "AE",
    "en-sg": "SG",
    "en-my": "MY",
    "en-au": "AU",
    "en-nz": "NZ",
    "ja": "JP",
    "ko": "KR",
    "en-kh": "KH",
    "en-hk": "HK",
    "en-bd": "BD",
    "en-th": "TH",
    "th": "TH",
    "es-ar": "AR",
    "ar-eg": "EG",
    "en-eg": "EG",
    "en-in": "IN",
    "en-ir": "IR",
    "fa": "IR",
    "en-il": "IL",
    "en-sa": "SA",
    "ar-sa": "SA",
    "en-ie": "IE",
    "en-id": "ID",
    "en-ph": "PH",
    "zh-tw": "TW",
    "en-om": "OM",
    "en-qa": "QA",
    "en-bh": "BH",
    "en-kw": "KW",
    "vi": "VN",
}

# Configuration keys
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_LANGUAGE = "language"
CONF_SCAN_INTERVAL = "scan_interval"

# Default values
DEFAULT_LANGUAGE = "en"

# Update intervals
SCAN_INTERVAL = 60  # seconds
MIN_SCAN_INTERVAL = 30
MAX_SCAN_INTERVAL = 300
