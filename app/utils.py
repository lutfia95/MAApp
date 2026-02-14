from __future__ import annotations

import datetime as dt
import re
from typing import Dict, Optional, Tuple

ANILIST_GQL = "https://graphql.anilist.co"

COUNTRY_MAP: Dict[str, Tuple[str, str]] = {
    "JPN": ("Japan", "Japanese"),
    "KOR": ("South Korea", "Korean"),
    "CHN": ("China", "Chinese"),
    "TWN": ("Taiwan", "Chinese"),
    "USA": ("United States", "English"),
    "CAN": ("Canada", "English"),
    "GBR": ("United Kingdom", "English"),
    "AUS": ("Australia", "English"),
    "FRA": ("France", "French"),
    "DEU": ("Germany", "German"),
    "ESP": ("Spain", "Spanish"),
    "ITA": ("Italy", "Italian"),
    "BRA": ("Brazil", "Portuguese"),
    "MEX": ("Mexico", "Spanish"),
    "RUS": ("Russia", "Russian"),
    "IND": ("India", "Hindi"),
    "PHL": ("Philippines", "Filipino"),
    "THA": ("Thailand", "Thai"),
    "VNM": ("Vietnam", "Vietnamese"),
}


def yyyymmdd_int(d: dt.date) -> int:
    return d.year * 10000 + d.month * 100 + d.day


def clean_text(s: Optional[str]) -> str:
    if not s:
        return ""
    s = s.replace("\r", "")
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"</p\s*>", "\n\n", s, flags=re.IGNORECASE)
    s = re.sub(r"<[^>]+>", "", s)
    s = (
        s.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#039;", "'")
    )
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    return s