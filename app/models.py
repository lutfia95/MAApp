from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class MediaItem:
    id: int
    media_type: str
    title: str
    title_native: str
    image_url: str
    country_code: str
    country: str
    language: str
    start_date: Optional[dt.date]
    format: str
    status: str
    description: str
    site_url: str

    @property
    def publication_day(self) -> str:
        return self.start_date.isoformat() if self.start_date else "Unknown"

    @property
    def key_date(self) -> dt.date:
        return self.start_date if self.start_date else dt.date(1900, 1, 1)
