def get_location_flag(birth_place: str | None) -> str:
    if not birth_place:
        return ""
    bp = birth_place.lower()

    # Match common regions/countries to ISO 3166-1 alpha-2 codes
    code = None
    if any(k in bp for k in ["wales", "cymru", "cardiff", "swansea", "newport", "welsh"]):
        return "🏴󠁧󠁢󠁷󠁬󠁳󠁿"  # Wales (Flag of Wales / Red Dragon)
    elif any(k in bp for k in ["scotland", "edinburgh", "glasgow", "aberdeen", "dundee", "scottish"]):
        return "🏴󠁧󠁢󠁳󠁣󠁴󠁿"  # Scotland (The Saltire)
    elif any(k in bp for k in ["northern ireland", "belfast", "derry", "ulster"]):
        return "🏴"  # Northern Ireland
    elif any(k in bp for k in
             ["england", "london", "yorkshire", "manchester", "birmingham", "liverpool", "lancashire", "cornwall",
              "devon", "essex", "kent", "surrey"]):
        return "🏴󠁧󠁢󠁥󠁮󠁧󠁿"  # England (St George's Cross)

    if any(k in bp for k in ["uk", "united kingdom", "britain", "great britain"]):
        return "🇬🇧"
    elif any(k in bp for k in ["usa", "united states", "america", "u.s."]):
        return "🇺🇸"
    elif "ireland" in bp:
        code = "IE"
    elif "canada" in bp:
        code = "CA"
    elif "australia" in bp:
        code = "AU"
    elif "france" in bp:
        code = "FR"
    elif "germany" in bp:
        code = "DE"
    elif "italy" in bp:
        code = "IT"
    elif "switzerland" in bp:
        code = "CH"
    elif "netherlands" in bp:
        code = "NL"
    elif "belgium" in bp:
        code = "BE"
    elif "native" in bp:
        return "🟡"

    if code:
        # Convert 2-letter ISO code to regional indicator symbol emoji
        return "".join(chr(127397 + ord(c)) for c in code.upper())
    return ""