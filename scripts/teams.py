"""teams.py: the 32 NHL teams. NHL abbreviation -> names the odds feed uses and the Daily Faceoff page slug."""

TEAMS = {
    "ANA": (["Anaheim Ducks"], "anaheim-ducks"),
    "BOS": (["Boston Bruins"], "boston-bruins"),
    "BUF": (["Buffalo Sabres"], "buffalo-sabres"),
    "CGY": (["Calgary Flames"], "calgary-flames"),
    "CAR": (["Carolina Hurricanes"], "carolina-hurricanes"),
    "CHI": (["Chicago Blackhawks"], "chicago-blackhawks"),
    "COL": (["Colorado Avalanche"], "colorado-avalanche"),
    "CBJ": (["Columbus Blue Jackets"], "columbus-blue-jackets"),
    "DAL": (["Dallas Stars"], "dallas-stars"),
    "DET": (["Detroit Red Wings"], "detroit-red-wings"),
    "EDM": (["Edmonton Oilers"], "edmonton-oilers"),
    "FLA": (["Florida Panthers"], "florida-panthers"),
    "LAK": (["Los Angeles Kings"], "los-angeles-kings"),
    "MIN": (["Minnesota Wild"], "minnesota-wild"),
    "MTL": (["Montreal Canadiens", "Montréal Canadiens"], "montreal-canadiens"),
    "NSH": (["Nashville Predators"], "nashville-predators"),
    "NJD": (["New Jersey Devils"], "new-jersey-devils"),
    "NYI": (["New York Islanders"], "new-york-islanders"),
    "NYR": (["New York Rangers"], "new-york-rangers"),
    "OTT": (["Ottawa Senators"], "ottawa-senators"),
    "PHI": (["Philadelphia Flyers"], "philadelphia-flyers"),
    "PIT": (["Pittsburgh Penguins"], "pittsburgh-penguins"),
    "SJS": (["San Jose Sharks"], "san-jose-sharks"),
    "SEA": (["Seattle Kraken"], "seattle-kraken"),
    "STL": (["St Louis Blues", "St. Louis Blues"], "st-louis-blues"),
    "TBL": (["Tampa Bay Lightning"], "tampa-bay-lightning"),
    "TOR": (["Toronto Maple Leafs"], "toronto-maple-leafs"),
    "UTA": (["Utah Mammoth", "Utah Hockey Club"], "utah-mammoth"),
    "VAN": (["Vancouver Canucks"], "vancouver-canucks"),
    "VGK": (["Vegas Golden Knights"], "vegas-golden-knights"),
    "WSH": (["Washington Capitals"], "washington-capitals"),
    "WPG": (["Winnipeg Jets"], "winnipeg-jets"),
}


def _key(name):
    import re
    import unicodedata
    n = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]", "", n)


NAME_TO_ABBREV = {_key(n): ab for ab, (names, _) in TEAMS.items() for n in names}


def abbrev_for(feed_name):
    """'Montreal Canadiens' -> 'MTL'. None when the name is not known (never guessed)."""
    return NAME_TO_ABBREV.get(_key(feed_name))


def df_slug(abbrev):
    t = TEAMS.get(abbrev)
    return t[1] if t else None
