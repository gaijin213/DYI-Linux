"""Pick lists for the questions people cannot answer from memory: time zones, locales, keyboard layouts.

Everything here is data for the TUI pickers (value + human readable label). The lists come from the live
system where possible (tzdata, /usr/share/i18n/SUPPORTED) and fall back to built-in tables so the dry run
on any OS shows the same screens.
"""
from __future__ import annotations

import os
import zoneinfo

# ------------------------------------------------------------------ time zones
_TZ_SKIP = ("Etc/", "SystemV/", "US/", "posix/", "right/", "Canada/", "Mexico/", "Brazil/", "Chile/")


def timezones() -> list[tuple[str, str]]:
    """[(value, label)] e.g. ("Europe/Berlin", "Europe/Berlin"). Region/City names only, plus UTC."""
    try:
        names = zoneinfo.available_timezones()
    except Exception:  # noqa: BLE001
        names = set()
    if not names and os.path.isdir("/usr/share/zoneinfo"):
        for root, _, files in os.walk("/usr/share/zoneinfo"):
            for f in files:
                names.add(os.path.relpath(os.path.join(root, f), "/usr/share/zoneinfo"))
    tz = sorted(n for n in names if "/" in n and not n.startswith(_TZ_SKIP) and n[0].isupper())
    return [("UTC", "UTC  (no local time, good for servers)")] + [(n, n.replace("_", " ")) for n in tz]


# ------------------------------------------------------------------ locales
LANGUAGES = {
    "aa": "Afar", "af": "Afrikaans", "am": "Amharic", "ar": "Arabic", "as": "Assamese", "ast": "Asturian", "az": "Azerbaijani",
    "be": "Belarusian", "bg": "Bulgarian", "bn": "Bangla", "bo": "Tibetan", "br": "Breton", "bs": "Bosnian", "ca": "Catalan",
    "cs": "Czech", "cy": "Welsh", "da": "Danish", "de": "German", "dz": "Dzongkha", "el": "Greek", "en": "English",
    "eo": "Esperanto", "es": "Spanish", "et": "Estonian", "eu": "Basque", "fa": "Persian", "fi": "Finnish", "fil": "Filipino",
    "fo": "Faroese", "fr": "French", "fy": "Western Frisian", "ga": "Irish", "gd": "Scottish Gaelic", "gl": "Galician",
    "gu": "Gujarati", "he": "Hebrew", "hi": "Hindi", "hr": "Croatian", "hu": "Hungarian", "hy": "Armenian", "id": "Indonesian",
    "is": "Icelandic", "it": "Italian", "ja": "Japanese", "ka": "Georgian", "kk": "Kazakh", "km": "Khmer", "kn": "Kannada",
    "ko": "Korean", "ku": "Kurdish", "ky": "Kyrgyz", "lb": "Luxembourgish", "lo": "Lao", "lt": "Lithuanian", "lv": "Latvian",
    "mg": "Malagasy", "mi": "Maori", "mk": "Macedonian", "ml": "Malayalam", "mn": "Mongolian", "mr": "Marathi", "ms": "Malay",
    "mt": "Maltese", "my": "Burmese", "nb": "Norwegian Bokmal", "ne": "Nepali", "nl": "Dutch", "nn": "Norwegian Nynorsk",
    "oc": "Occitan", "or": "Odia", "pa": "Punjabi", "pl": "Polish", "ps": "Pashto", "pt": "Portuguese", "ro": "Romanian",
    "ru": "Russian", "rw": "Kinyarwanda", "sa": "Sanskrit", "sd": "Sindhi", "si": "Sinhala", "sk": "Slovak", "sl": "Slovenian",
    "so": "Somali", "sq": "Albanian", "sr": "Serbian", "sv": "Swedish", "sw": "Swahili", "ta": "Tamil", "te": "Telugu",
    "tg": "Tajik", "th": "Thai", "ti": "Tigrinya", "tk": "Turkmen", "tl": "Tagalog", "tr": "Turkish", "tt": "Tatar",
    "ug": "Uyghur", "uk": "Ukrainian", "ur": "Urdu", "uz": "Uzbek", "vi": "Vietnamese", "wa": "Walloon", "xh": "Xhosa",
    "yi": "Yiddish", "yo": "Yoruba", "zh": "Chinese", "zu": "Zulu",
}
COUNTRIES = {
    "AE": "United Arab Emirates", "AR": "Argentina", "AT": "Austria", "AU": "Australia", "BA": "Bosnia and Herzegovina",
    "BD": "Bangladesh", "BE": "Belgium", "BG": "Bulgaria", "BO": "Bolivia", "BR": "Brazil", "BY": "Belarus", "CA": "Canada",
    "CH": "Switzerland", "CL": "Chile", "CN": "China", "CO": "Colombia", "CR": "Costa Rica", "CU": "Cuba", "CY": "Cyprus",
    "CZ": "Czechia", "DE": "Germany", "DK": "Denmark", "DO": "Dominican Republic", "DZ": "Algeria", "EC": "Ecuador",
    "EE": "Estonia", "EG": "Egypt", "ES": "Spain", "ET": "Ethiopia", "FI": "Finland", "FO": "Faroe Islands", "FR": "France",
    "GB": "United Kingdom", "GE": "Georgia", "GR": "Greece", "GT": "Guatemala", "HK": "Hong Kong", "HN": "Honduras",
    "HR": "Croatia", "HU": "Hungary", "ID": "Indonesia", "IE": "Ireland", "IL": "Israel", "IN": "India", "IQ": "Iraq",
    "IR": "Iran", "IS": "Iceland", "IT": "Italy", "JO": "Jordan", "JP": "Japan", "KE": "Kenya", "KH": "Cambodia",
    "KR": "South Korea", "KW": "Kuwait", "KZ": "Kazakhstan", "LA": "Laos", "LB": "Lebanon", "LK": "Sri Lanka",
    "LT": "Lithuania", "LU": "Luxembourg", "LV": "Latvia", "LY": "Libya", "MA": "Morocco", "MD": "Moldova", "ME": "Montenegro",
    "MK": "North Macedonia", "MM": "Myanmar", "MN": "Mongolia", "MT": "Malta", "MX": "Mexico", "MY": "Malaysia", "NG": "Nigeria",
    "NI": "Nicaragua", "NL": "Netherlands", "NO": "Norway", "NP": "Nepal", "NZ": "New Zealand", "OM": "Oman", "PA": "Panama",
    "PE": "Peru", "PH": "Philippines", "PK": "Pakistan", "PL": "Poland", "PR": "Puerto Rico", "PT": "Portugal", "PY": "Paraguay",
    "QA": "Qatar", "RO": "Romania", "RS": "Serbia", "RU": "Russia", "SA": "Saudi Arabia", "SE": "Sweden", "SG": "Singapore",
    "SI": "Slovenia", "SK": "Slovakia", "SV": "El Salvador", "SY": "Syria", "TH": "Thailand", "TN": "Tunisia", "TR": "Turkey",
    "TW": "Taiwan", "UA": "Ukraine", "US": "United States", "UY": "Uruguay", "UZ": "Uzbekistan", "VE": "Venezuela",
    "VN": "Vietnam", "YE": "Yemen", "ZA": "South Africa", "ZW": "Zimbabwe",
}
# shown when /usr/share/i18n/SUPPORTED is not available (dry run on a non-glibc host)
FALLBACK_LOCALES = [
    "en_US", "en_GB", "en_AU", "en_CA", "en_IE", "en_IN", "en_NZ", "en_ZA", "de_DE", "de_AT", "de_CH", "fr_FR", "fr_BE", "fr_CA",
    "fr_CH", "es_ES", "es_MX", "es_AR", "es_CL", "es_CO", "it_IT", "pt_PT", "pt_BR", "nl_NL", "nl_BE", "sv_SE", "nb_NO",
    "da_DK", "fi_FI", "pl_PL", "cs_CZ", "sk_SK", "hu_HU", "ro_RO", "bg_BG", "el_GR", "tr_TR", "ru_RU", "uk_UA", "he_IL",
    "ar_EG", "ar_SA", "fa_IR", "hi_IN", "bn_BD", "ta_IN", "th_TH", "vi_VN", "id_ID", "ms_MY", "zh_CN", "zh_TW", "ja_JP",
    "ko_KR", "et_EE", "lv_LV", "lt_LT", "sl_SI", "hr_HR", "sr_RS", "is_IS", "ga_IE", "ca_ES", "eu_ES", "gl_ES",
]


def describe_locale(code: str) -> str:
    """'de_CH.UTF-8' -> 'German (Switzerland)'."""
    base = code.split(".")[0].split("@")[0]
    lang, _, country = base.partition("_")
    name = LANGUAGES.get(lang, lang)
    if country:
        name += f" ({COUNTRIES.get(country, country)})"
    mod = code.split("@")[1] if "@" in code else ""
    if mod:
        name += f" [{mod}]"
    return name


def locales() -> list[tuple[str, str]]:
    """[(value, label)] of UTF-8 locales, e.g. ("de_DE.UTF-8", "de_DE.UTF-8  German (Germany)")."""
    codes: list[str] = []
    try:
        with open("/usr/share/i18n/SUPPORTED") as f:
            for line in f:
                code, _, charset = line.strip().partition(" ")
                if charset == "UTF-8" and code.endswith(".UTF-8"):
                    codes.append(code)
    except OSError:
        codes = [c + ".UTF-8" for c in FALLBACK_LOCALES]
    if "en_US.UTF-8" not in codes:
        codes.insert(0, "en_US.UTF-8")
    codes = sorted(set(codes), key=lambda c: (c.split("_")[0] != "en", describe_locale(c)))
    return [(c, f"{c:<22} {describe_locale(c)}") for c in codes]


# ------------------------------------------------------------------ keyboard layouts
# (xkb layout, console keymap for /etc/vconsole.conf, label). The console name is what Arch, Fedora and
# openSUSE need for the text console; Debian/Ubuntu derive the console map from the XKB layout themselves.
KEYMAPS = [
    ("us", "us", "English (US)"), ("us-intl", "us-acentos", "English (US, international with dead keys)"),
    ("gb", "uk", "English (UK)"), ("au", "us", "English (Australia)"), ("ca", "cf", "French (Canada)"),
    ("de", "de-latin1", "German"), ("de-nodeadkeys", "de-latin1-nodeadkeys", "German (no dead keys)"),
    ("at", "de-latin1", "German (Austria)"), ("ch", "sg-latin1", "German (Switzerland)"), ("ch-fr", "fr_CH-latin1", "French (Switzerland)"),
    ("fr", "fr-latin1", "French"), ("fr-azerty", "fr-latin1", "French (AZERTY)"), ("be", "be-latin1", "Belgian"),
    ("es", "es", "Spanish"), ("latam", "la-latin1", "Spanish (Latin America)"), ("pt", "pt-latin1", "Portuguese"),
    ("br", "br-abnt2", "Portuguese (Brazil)"), ("it", "it", "Italian"), ("nl", "us", "Dutch (US layout is standard in NL)"),
    ("dk", "dk-latin1", "Danish"), ("se", "sv-latin1", "Swedish"), ("no", "no-latin1", "Norwegian"), ("fi", "fi", "Finnish"),
    ("is", "is-latin1", "Icelandic"), ("ie", "ie", "Irish"), ("pl", "pl2", "Polish"), ("cz", "cz-lat2", "Czech"),
    ("sk", "sk-qwertz", "Slovak"), ("hu", "hu", "Hungarian"), ("ro", "ro", "Romanian"), ("bg", "bg_bds-utf8", "Bulgarian"),
    ("hr", "croat", "Croatian"), ("si", "slovene", "Slovenian"), ("rs", "sr-cy", "Serbian (Cyrillic)"), ("gr", "gr", "Greek"),
    ("tr", "trq", "Turkish (Q)"), ("ru", "ru", "Russian"), ("ua", "ua-utf", "Ukrainian"), ("by", "by", "Belarusian"),
    ("ee", "et", "Estonian"), ("lv", "lv", "Latvian"), ("lt", "lt", "Lithuanian"), ("il", "il", "Hebrew"), ("ara", "us", "Arabic"),
    ("ir", "ir", "Persian"), ("in", "us", "Indian"), ("jp", "jp106", "Japanese"), ("kr", "kr", "Korean"), ("cn", "us", "Chinese"),
    ("th", "th", "Thai"), ("vn", "us", "Vietnamese"), ("za", "us", "English (South Africa)"), ("mt", "mt", "Maltese"),
    ("epo", "us", "Esperanto"), ("dvorak", "dvorak", "English (Dvorak)"), ("colemak", "us", "English (Colemak)"),
]


def keymaps() -> list[tuple[str, str]]:
    """[(xkb layout, label)]; the console map is looked up with console_keymap()."""
    return [(x, f"{label}  ({x})") for x, _, label in KEYMAPS]


def console_keymap(xkb: str) -> str:
    for x, console, _ in KEYMAPS:
        if x == xkb:
            return console
    return xkb or "us"


def xkb_for_console(console: str) -> str:
    """Reverse lookup for profiles that only carry an old-style console keymap."""
    for x, c, _ in KEYMAPS:
        if c == console:
            return x
    return console or "us"


def xkb_parts(xkb: str) -> tuple[str, str]:
    """'de-nodeadkeys' -> ('de', 'nodeadkeys'); 'us' -> ('us', '')."""
    layout, _, variant = xkb.partition("-")
    if xkb == "us-intl":
        return "us", "intl"
    if xkb == "fr-azerty":
        return "fr", "azerty"
    if xkb == "ch-fr":
        return "ch", "fr"
    if xkb in ("dvorak", "colemak"):
        return "us", xkb
    return layout, variant
