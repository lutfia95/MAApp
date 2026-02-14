from __future__ import annotations

import datetime as dt
import json
from typing import List

import requests

from .models import MediaItem
from .utils import ANILIST_GQL, COUNTRY_MAP, clean_text


class AniListClient:
    QUERY = """
    query ($type: MediaType, $startGreater: FuzzyDateInt, $startLesser: FuzzyDateInt, $perPage: Int) {
      Page(page: 1, perPage: $perPage) {
        media(type: $type, startDate_greater: $startGreater, startDate_lesser: $startLesser, sort: START_DATE_DESC) {
          id
          type
          format
          status
          title { romaji english native }
          startDate { year month day }
          countryOfOrigin
          description(asHtml: false)
          siteUrl
          coverImage { large medium color }
        }
      }
    }
    """

    def __init__(self, timeout: int = 25):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "MiniAniManga/1.0 (PySide6; personal use)",
        })

    def fetch_new(self, media_type: str, date_from: dt.date, date_to: dt.date, per_page: int = 35) -> List["MediaItem"]:
        start_greater = date_from.year * 10000 + date_from.month * 100 + date_from.day
        start_lesser  = date_to.year * 10000 + date_to.month * 100 + date_to.day

        payload = {
            "query": self.QUERY,
            "variables": {
                "type": media_type,
                "startGreater": start_greater,
                "startLesser": start_lesser,
                "perPage": per_page,
            },
        }

        r = self.session.post(ANILIST_GQL, json=payload, timeout=self.timeout)
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}\n\n{r.text[:2000]}")
        data = r.json()
        if data.get("errors"):
            raise RuntimeError("AniList GraphQL error:\n" + json.dumps(data["errors"], indent=2)[:2000])

        media_list = (data.get("data") or {}).get("Page", {}).get("media", []) or []

        out: List[MediaItem] = []
        for m in media_list:
            title_block = m.get("title") or {}
            title = title_block.get("english") or title_block.get("romaji") or "Untitled"
            title_native = title_block.get("native") or ""

            cover = m.get("coverImage") or {}
            image_url = cover.get("large") or cover.get("medium") or ""

            cc = m.get("countryOfOrigin") or ""
            country, language = COUNTRY_MAP.get(cc, (cc or "Unknown", "Unknown"))

            sd = m.get("startDate") or {}
            try:
                if sd.get("year") and sd.get("month") and sd.get("day"):
                    start_date = dt.date(int(sd["year"]), int(sd["month"]), int(sd["day"]))
                else:
                    start_date = None
            except Exception:
                start_date = None

            out.append(
                MediaItem(
                    id=int(m.get("id") or 0),
                    media_type=str(m.get("type") or media_type),
                    title=str(title),
                    title_native=str(title_native),
                    image_url=str(image_url),
                    country_code=str(cc),
                    country=str(country),
                    language=str(language),
                    start_date=start_date,
                    format=str(m.get("format") or "Unknown"),
                    status=str(m.get("status") or "Unknown"),
                    description=clean_text(m.get("description")),
                    site_url=str(m.get("siteUrl") or ""),
                )
            )

        return out
