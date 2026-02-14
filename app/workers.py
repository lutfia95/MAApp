from __future__ import annotations

import datetime as dt

from PySide6 import QtCore

from .anilist import AniListClient
from .utils import yyyymmdd_int


class FetchWorker(QtCore.QObject):
    finished = QtCore.Signal(list)  # List[MediaItem]
    error = QtCore.Signal(str)

    def __init__(self, date_from: dt.date, date_to: dt.date):
        super().__init__()
        self.date_from = date_from
        self.date_to = date_to
        self._abort = False

    @QtCore.Slot()
    def run(self):
        try:
            client = AniListClient(timeout=25)
            if self._abort:
                return
            anime = client.fetch_new("ANIME", self.date_from, self.date_to, per_page=40)
            if self._abort:
                return
            manga = client.fetch_new("MANGA", self.date_from, self.date_to, per_page=40)
            if self._abort:
                return

            items = anime + manga
            uniq = {}
            for it in items:
                uniq[(it.media_type, it.id)] = it
            items = list(uniq.values())

            items.sort(key=lambda x: (x.key_date, x.media_type, x.title.lower()), reverse=True)
            self.finished.emit(items)
        except Exception as e:
            self.error.emit(str(e))

    def abort(self):
        self._abort = True
