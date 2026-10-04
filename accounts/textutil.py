import unicodedata

def clean_text(value):
    if not isinstance(value, str):
        return None
    value = unicodedata.normalize("NFC", value)
    if any(unicodedata.category(ch).startswith("C") for ch in value):
        return None
    return " ".join(value.split())
