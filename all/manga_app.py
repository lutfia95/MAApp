

from __future__ import annotations

import re
import sys
import json
import datetime as dt
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple

import requests
from PySide6 import QtCore, QtGui, QtWidgets, QtNetwork
from PySide6.QtCore import Qt, QUrl


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


class ImageCache(QtCore.QObject):
    image_ready = QtCore.Signal(str)

    def __init__(self):
        super().__init__()
        self._manager = QtNetwork.QNetworkAccessManager(self)
        self._cache: Dict[str, QtGui.QPixmap] = {}
        self._pending: Dict[str, QtNetwork.QNetworkReply] = {}

    def get(self, url: str) -> Optional[QtGui.QPixmap]:
        if not url:
            return None
        return self._cache.get(url)

    def request(self, url: str):
        if not url or url in self._cache or url in self._pending:
            return
        req = QtNetwork.QNetworkRequest(QUrl(url))
        req.setAttribute(
            QtNetwork.QNetworkRequest.RedirectPolicyAttribute,
            QtNetwork.QNetworkRequest.NoLessSafeRedirectPolicy,
        )
        reply = self._manager.get(req)
        self._pending[url] = reply
        reply.finished.connect(lambda u=url: self._on_finished(u))

    def _on_finished(self, url: str):
        reply = self._pending.pop(url, None)
        if not reply:
            return
        if reply.error() == QtNetwork.QNetworkReply.NetworkError.NoError:
            data = reply.readAll()
            pix = QtGui.QPixmap()
            if pix.loadFromData(bytes(data)):
                self._cache[url] = pix
                self.image_ready.emit(url)
        reply.deleteLater()


class Pill(QtWidgets.QLabel):
    def __init__(self, text: str, kind: str = "neutral"):
        super().__init__(text)
        self.setObjectName(f"pill_{kind}")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(22)
        self.setContentsMargins(10, 2, 10, 2)


class MediaCard(QtWidgets.QFrame):
    def __init__(self, item: MediaItem, img_cache: ImageCache):
        super().__init__()
        self.item = item
        self.img_cache = img_cache

        self.setObjectName("MediaCard")
        self.setFrameShape(QtWidgets.QFrame.NoFrame)

        root = QtWidgets.QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        self.thumb = QtWidgets.QLabel()
        self.thumb.setObjectName("Thumb")
        self.thumb.setFixedSize(60, 84)
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setScaledContents(True)

        self._set_placeholder()

        mid = QtWidgets.QVBoxLayout()
        mid.setContentsMargins(0, 0, 0, 0)
        mid.setSpacing(4)

        title_row = QtWidgets.QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)

        self.title = QtWidgets.QLabel(item.title)
        self.title.setObjectName("CardTitle")
        self.title.setWordWrap(False)
        self.title.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)

        kind = "anime" if item.media_type == "ANIME" else "manga"
        self.badge = Pill(item.media_type, kind)

        title_row.addWidget(self.title, 1)
        title_row.addWidget(self.badge, 0)

        meta = QtWidgets.QLabel(
            f"{item.publication_day} • {item.country} • {item.language} • {item.format} • {item.status}"
        )
        meta.setObjectName("CardMeta")
        meta.setWordWrap(False)
        meta.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)

        self.subtitle = QtWidgets.QLabel(item.title_native or "")
        self.subtitle.setObjectName("CardSub")
        self.subtitle.setWordWrap(False)
        self.subtitle.setVisible(bool(item.title_native))

        mid.addLayout(title_row)
        if item.title_native:
            mid.addWidget(self.subtitle)
        mid.addWidget(meta)

        root.addWidget(self.thumb, 0)
        root.addLayout(mid, 1)

        if item.image_url:
            self.img_cache.request(item.image_url)

    def _set_placeholder(self):
        pm = QtGui.QPixmap(self.thumb.size())
        pm.fill(Qt.transparent)
        p = QtGui.QPainter(pm)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = pm.rect().adjusted(1, 1, -1, -1)
        grad = QtGui.QLinearGradient(rect.topLeft(), rect.bottomRight())
        grad.setColorAt(0.0, QtGui.QColor(45, 52, 64))
        grad.setColorAt(1.0, QtGui.QColor(22, 26, 33))
        p.setBrush(QtGui.QBrush(grad))
        p.setPen(QtGui.QPen(QtGui.QColor(70, 80, 96), 1))
        p.drawRoundedRect(rect, 10, 10)
        p.setPen(QtGui.QColor(150, 160, 180))
        p.setFont(QtGui.QFont("Inter", 9))
        p.drawText(rect, Qt.AlignCenter, "No\nImage")
        p.end()
        self.thumb.setPixmap(pm)

    def update_image_if_ready(self):
        url = self.item.image_url
        if not url:
            return
        pix = self.img_cache.get(url)
        if not pix:
            return
        scaled = pix.scaled(self.thumb.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        self.thumb.setPixmap(scaled)


class Window(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Anime & Manga")
        self.setMinimumSize(980, 600)

        self.img_cache = ImageCache()
        self.img_cache.image_ready.connect(self._on_image_ready)

        self._items: List[MediaItem] = []
        self._worker_thread: Optional[QtCore.QThread] = None
        self._worker: Optional[FetchWorker] = None

        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        outer = QtWidgets.QWidget()
        self.setCentralWidget(outer)

        root = QtWidgets.QVBoxLayout(outer)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        header = QtWidgets.QFrame()
        header.setObjectName("Header")
        h = QtWidgets.QHBoxLayout(header)
        h.setContentsMargins(14, 14, 14, 14)
        h.setSpacing(12)

        title_col = QtWidgets.QVBoxLayout()
        title_col.setSpacing(2)

        self.h_title = QtWidgets.QLabel("New releases")
        self.h_title.setObjectName("HeaderTitle")

        self.h_sub = QtWidgets.QLabel("")
        self.h_sub.setObjectName("HeaderSub")

        title_col.addWidget(self.h_title)
        title_col.addWidget(self.h_sub)

        h.addLayout(title_col, 1)
        date_bar = QtWidgets.QFrame()
        date_bar.setObjectName("DateBar")
        db = QtWidgets.QHBoxLayout(date_bar)
        db.setContentsMargins(8, 6, 8, 6)
        db.setSpacing(8)

        self.from_date = QtWidgets.QDateEdit()
        self.to_date = QtWidgets.QDateEdit()
        for d in (self.from_date, self.to_date):
            d.setCalendarPopup(True)
            d.setDisplayFormat("yyyy-MM-dd")
            d.setObjectName("DateEdit")
            d.setCursor(Qt.PointingHandCursor)

        today_q = QtCore.QDate.currentDate()
        self.to_date.setDate(today_q)
        self.from_date.setDate(today_q.addDays(-7))

        db.addWidget(QtWidgets.QLabel("From:"))
        db.addWidget(self.from_date)
        db.addSpacing(6)
        db.addWidget(QtWidgets.QLabel("To:"))
        db.addWidget(self.to_date)

        h.addWidget(date_bar, 0)

        self.from_date.dateChanged.connect(lambda _=None: self._update_date_subtitle())
        self.to_date.dateChanged.connect(lambda _=None: self._update_date_subtitle())


        self.filter_all = QtWidgets.QPushButton("All")
        self.filter_anime = QtWidgets.QPushButton("Anime")
        self.filter_manga = QtWidgets.QPushButton("Manga")
        for b in (self.filter_all, self.filter_anime, self.filter_manga):
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setObjectName("SegButton")

        self.filter_all.setChecked(True)
        self.filter_all.clicked.connect(lambda: self._apply_filter("ALL"))
        self.filter_anime.clicked.connect(lambda: self._apply_filter("ANIME"))
        self.filter_manga.clicked.connect(lambda: self._apply_filter("MANGA"))

        seg = QtWidgets.QFrame()
        seg.setObjectName("SegWrap")
        seg_l = QtWidgets.QHBoxLayout(seg)
        seg_l.setContentsMargins(4, 4, 4, 4)
        seg_l.setSpacing(6)
        seg_l.addWidget(self.filter_all)
        seg_l.addWidget(self.filter_anime)
        seg_l.addWidget(self.filter_manga)

        h.addWidget(seg, 0)

        self.btn_download = QtWidgets.QPushButton("Download")
        self.btn_download.setCursor(Qt.PointingHandCursor)
        self.btn_download.setObjectName("PrimaryButton")
        self.btn_download.clicked.connect(self._download)

        h.addWidget(self.btn_download, 0)

        root.addWidget(header)

        split = QtWidgets.QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)
        split.setHandleWidth(10)
        split.setObjectName("MainSplit")

        left = QtWidgets.QFrame()
        left.setObjectName("Pane")
        ll = QtWidgets.QVBoxLayout(left)
        ll.setContentsMargins(12, 12, 12, 12)
        ll.setSpacing(10)

        top_row = QtWidgets.QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(10)

        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Search title…")
        self.search.setObjectName("SearchBox")
        self.search.textChanged.connect(self._rebuild_list)

        self.count = QtWidgets.QLabel("0 items")
        self.count.setObjectName("CountLabel")
        self.count.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        top_row.addWidget(self.search, 1)
        top_row.addWidget(self.count, 0)

        ll.addLayout(top_row)

        self.listw = QtWidgets.QListWidget()
        self.listw.setObjectName("MediaList")
        self.listw.setSpacing(10)
        self.listw.setUniformItemSizes(False)
        self.listw.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.listw.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.listw.currentRowChanged.connect(self._on_selected_row)

        ll.addWidget(self.listw, 1)

        self.progress = QtWidgets.QProgressBar()
        self.progress.setObjectName("Progress")
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        ll.addWidget(self.progress, 0)

        split.addWidget(left)

        right = QtWidgets.QFrame()
        right.setObjectName("Pane")
        rl = QtWidgets.QVBoxLayout(right)
        rl.setContentsMargins(14, 14, 14, 14)
        rl.setSpacing(10)

        hero = QtWidgets.QFrame()
        hero.setObjectName("DetailHero")
        hl = QtWidgets.QHBoxLayout(hero)
        hl.setContentsMargins(12, 12, 12, 12)
        hl.setSpacing(12)

        self.detail_img = QtWidgets.QLabel()
        self.detail_img.setObjectName("DetailImg")
        self.detail_img.setFixedSize(140, 196)
        self.detail_img.setAlignment(Qt.AlignCenter)
        self.detail_img.setScaledContents(True)
        self._set_detail_placeholder()

        info_col = QtWidgets.QVBoxLayout()
        info_col.setSpacing(6)

        self.detail_title = QtWidgets.QLabel("Select an item")
        self.detail_title.setObjectName("DetailTitle")
        self.detail_title.setWordWrap(True)

        self.detail_native = QtWidgets.QLabel("")
        self.detail_native.setObjectName("DetailNative")
        self.detail_native.setWordWrap(True)
        self.detail_native.setVisible(False)

        self.detail_meta = QtWidgets.QLabel("")
        self.detail_meta.setObjectName("DetailMeta")
        self.detail_meta.setWordWrap(True)

        pill_row = QtWidgets.QHBoxLayout()
        pill_row.setSpacing(6)
        pill_row.setContentsMargins(0, 0, 0, 0)

        self.p_type = Pill("—", "neutral")
        self.p_country = Pill("—", "neutral")
        self.p_lang = Pill("—", "neutral")

        pill_row.addWidget(self.p_type)
        pill_row.addWidget(self.p_country)
        pill_row.addWidget(self.p_lang)
        pill_row.addStretch(1)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.setContentsMargins(0, 0, 0, 0)

        self.btn_open = QtWidgets.QPushButton("Open page")
        self.btn_open.setCursor(Qt.PointingHandCursor)
        self.btn_open.setObjectName("GhostButton")
        self.btn_open.clicked.connect(self._open_current)

        self.btn_copy = QtWidgets.QPushButton("Copy link")
        self.btn_copy.setCursor(Qt.PointingHandCursor)
        self.btn_copy.setObjectName("GhostButton")
        self.btn_copy.clicked.connect(self._copy_current)

        btn_row.addWidget(self.btn_open)
        btn_row.addWidget(self.btn_copy)
        btn_row.addStretch(1)

        info_col.addWidget(self.detail_title)
        info_col.addWidget(self.detail_native)
        info_col.addLayout(pill_row)
        info_col.addWidget(self.detail_meta)
        info_col.addLayout(btn_row)
        info_col.addStretch(1)

        hl.addWidget(self.detail_img, 0)
        hl.addLayout(info_col, 1)

        rl.addWidget(hero, 0)

        self.detail_desc = QtWidgets.QTextBrowser()
        self.detail_desc.setObjectName("DetailDesc")
        self.detail_desc.setOpenExternalLinks(False)
        self.detail_desc.setReadOnly(True)
        self.detail_desc.setText(
            "Click Download to fetch the last 7 days of new anime/manga start dates.\n\n"
            "Note: This is based on AniList startDate; it is not a store/volume release tracker."
        )
        rl.addWidget(self.detail_desc, 1)

        split.addWidget(right)
        split.setSizes([520, 440])

        root.addWidget(split, 1)

        self.status = QtWidgets.QLabel("Ready.")
        self.status.setObjectName("StatusLabel")
        self.statusBar().addWidget(self.status, 1)

        self._filter_mode = "ALL"
        self._current_item: Optional[MediaItem] = None

        self._update_date_subtitle()
        
    def _get_range_dates(self) -> tuple[dt.date, dt.date]:
        f = self.from_date.date()
        t = self.to_date.date()
        date_from = dt.date(f.year(), f.month(), f.day())
        date_to = dt.date(t.year(), t.month(), t.day())
        return date_from, date_to

    def _apply_style(self):
        self.setStyleSheet(
            """
            QWidget { font-family: Inter, Segoe UI, Arial; font-size: 12.5px; color: #EAF0FF; }
            QMainWindow { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #0B0F1A, stop:0.5 #0A1221, stop:1 #070A12); }

            #Header { border-radius: 18px; background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 rgba(40, 60, 120, 0.35), stop:0.6 rgba(25, 30, 55, 0.55), stop:1 rgba(15, 18, 30, 0.65));
                border: 1px solid rgba(120, 150, 255, 0.15);
            }
            #HeaderTitle { font-size: 18px; font-weight: 700; letter-spacing: 0.2px; }
            #HeaderSub { color: rgba(234, 240, 255, 0.72); }

            #SegWrap { border-radius: 14px; background: rgba(0,0,0,0.18); border: 1px solid rgba(255,255,255,0.08); }
            #SegButton { padding: 8px 12px; border-radius: 10px; background: transparent; border: 1px solid transparent; color: rgba(234, 240, 255, 0.85); }
            #SegButton:hover { background: rgba(255,255,255,0.06); border-color: rgba(255,255,255,0.08); }
            #SegButton:checked { background: rgba(110,145,255,0.22); border-color: rgba(110,145,255,0.35); }

            #PrimaryButton { padding: 10px 16px; border-radius: 14px; background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #6E91FF, stop:1 #8C5BFF);
                border: 1px solid rgba(255,255,255,0.10); font-weight: 700;
            }
            #PrimaryButton:pressed { background: rgba(110,145,255,0.75); }

            #GhostButton { padding: 8px 12px; border-radius: 12px; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.09); }
            #GhostButton:disabled { color: rgba(234,240,255,0.35); }

            #Pane { border-radius: 18px; background: rgba(10, 12, 20, 0.55); border: 1px solid rgba(255,255,255,0.08); }

            #SearchBox { padding: 10px 12px; border-radius: 14px; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.09); selection-background-color: rgba(110,145,255,0.5); }
            #SearchBox:focus { border-color: rgba(110,145,255,0.45); }
            #CountLabel { color: rgba(234,240,255,0.68); }

            #MediaList { border: none; background: transparent; outline: none; }
            #MediaList::item { border: none; padding: 0px; margin: 0px; }
            #MediaList::item:selected { background: transparent; }

            #MediaCard { border-radius: 18px; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.08); }
            #MediaCard:hover { background: rgba(255,255,255,0.08); border-color: rgba(110,145,255,0.22); }
            #Thumb { border-radius: 12px; background: rgba(0,0,0,0.25); border: 1px solid rgba(255,255,255,0.07); }
            #CardTitle { font-size: 13.5px; font-weight: 700; }
            #CardSub { color: rgba(234,240,255,0.72); }
            #CardMeta { color: rgba(234,240,255,0.62); }

            QLabel#pill_neutral { border-radius: 11px; background: rgba(255,255,255,0.07); border: 1px solid rgba(255,255,255,0.10); font-weight: 600; }
            QLabel#pill_anime { border-radius: 11px; background: rgba(110,145,255,0.18); border: 1px solid rgba(110,145,255,0.30); font-weight: 700; }
            QLabel#pill_manga { border-radius: 11px; background: rgba(140,91,255,0.18); border: 1px solid rgba(140,91,255,0.30); font-weight: 700; }

            #DetailHero { border-radius: 18px; background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 rgba(255,255,255,0.06), stop:1 rgba(255,255,255,0.03));
                border: 1px solid rgba(255,255,255,0.08);
            }
            #DetailImg { border-radius: 16px; background: rgba(0,0,0,0.25); border: 1px solid rgba(255,255,255,0.08); }
            #DetailTitle { font-size: 16px; font-weight: 800; }
            #DetailNative { color: rgba(234,240,255,0.70); }
            #DetailMeta { color: rgba(234,240,255,0.65); }

            #DetailDesc { border-radius: 18px; background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); padding: 10px; }

            #Progress { border-radius: 10px; background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.08); height: 10px; }
            #Progress::chunk { background: rgba(110,145,255,0.55); border-radius: 10px; }

            QStatusBar { background: transparent; color: rgba(234,240,255,0.60); }
            #StatusLabel { color: rgba(234,240,255,0.65); }
            #DateBar {
                border-radius: 14px;
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.08);
            }
            #DateEdit {
                padding: 8px 10px;
                border-radius: 12px;
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.09);
            }
            #DateEdit:focus {
                border-color: rgba(110,145,255,0.45);
            }
            """
        )

        for w in [self.findChild(QtWidgets.QFrame, "Header")]:
            if w:
                eff = QtWidgets.QGraphicsDropShadowEffect(self)
                eff.setBlurRadius(26)
                eff.setOffset(0, 10)
                eff.setColor(QtGui.QColor(0, 0, 0, 130))
                w.setGraphicsEffect(eff)

    def _update_date_subtitle(self):
        date_from, date_to = self._get_range_dates()
        if date_from > date_to:
            self.from_date.blockSignals(True)
            self.to_date.blockSignals(True)
            self.from_date.setDate(QtCore.QDate(date_to.year, date_to.month, date_to.day))
            self.to_date.setDate(QtCore.QDate(date_from.year, date_from.month, date_from.day))
            self.from_date.blockSignals(False)
            self.to_date.blockSignals(False)
            date_from, date_to = self._get_range_dates()

        self.h_sub.setText(f"{date_from.isoformat()} → {date_to.isoformat()} (based on AniList startDate)")


    def _download(self):
        self._stop_worker_if_any()

        date_from, date_to = self._get_range_dates()
        if date_from > date_to:
            date_from, date_to = date_to, date_from

        self.status.setText("Fetching from AniList…")
        self.btn_download.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)

        self._worker_thread = QtCore.QThread(self)
        self._worker = FetchWorker(date_from=date_from, date_to=date_to)
        self._worker.moveToThread(self._worker_thread)

        self._worker_thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_fetched)
        self._worker.error.connect(self._on_fetch_error)

        self._worker.finished.connect(self._worker_thread.quit)
        self._worker.error.connect(self._worker_thread.quit)
        self._worker_thread.finished.connect(self._cleanup_worker)

        self._worker_thread.start()

    def _stop_worker_if_any(self):
        if self._worker:
            self._worker.abort()
        if self._worker_thread and self._worker_thread.isRunning():
            self._worker_thread.quit()
            self._worker_thread.wait(500)

    def _cleanup_worker(self):
        if self._worker:
            self._worker.deleteLater()
        if self._worker_thread:
            self._worker_thread.deleteLater()
        self._worker = None
        self._worker_thread = None

    def _on_fetched(self, items: list):
        self._items = list(items)
        self._rebuild_list()
        self.btn_download.setEnabled(True)
        self.progress.setVisible(False)
        self.progress.setRange(0, 1)
        self.status.setText(f"Loaded {len(self._items)} items.")
        if self.listw.count() > 0:
            self.listw.setCurrentRow(0)

    def _on_fetch_error(self, msg: str):
        self.btn_download.setEnabled(True)
        self.progress.setVisible(False)
        self.progress.setRange(0, 1)
        self.status.setText("Fetch failed.")
        QtWidgets.QMessageBox.critical(self, "Fetch failed", msg)

    def _apply_filter(self, mode: str):
        self._filter_mode = mode
        self.filter_all.setChecked(mode == "ALL")
        self.filter_anime.setChecked(mode == "ANIME")
        self.filter_manga.setChecked(mode == "MANGA")
        self._rebuild_list()

    def _passes_filter(self, it: MediaItem) -> bool:
        return True if self._filter_mode == "ALL" else it.media_type == self._filter_mode

    def _passes_search(self, it: MediaItem) -> bool:
        q = self.search.text().strip().lower()
        if not q:
            return True
        return q in it.title.lower() or (it.title_native and q in it.title_native.lower())

    def _rebuild_list(self):
        self.listw.blockSignals(True)
        self.listw.clear()

        filtered = [it for it in self._items if self._passes_filter(it) and self._passes_search(it)]
        self.count.setText(f"{len(filtered)} items")

        for it in filtered:
            lw_item = QtWidgets.QListWidgetItem()
            lw_item.setData(Qt.UserRole, it)

            card = MediaCard(it, self.img_cache)
            self._add_card_shadow(card)

            lw_item.setSizeHint(QtCore.QSize(10, 106))
            self.listw.addItem(lw_item)
            self.listw.setItemWidget(lw_item, card)

        self.listw.blockSignals(False)

        if self.listw.count() == 0:
            self._show_detail(None)
        else:
            self.listw.setCurrentRow(0)

    def _add_card_shadow(self, card: QtWidgets.QWidget):
        eff = QtWidgets.QGraphicsDropShadowEffect(self)
        eff.setBlurRadius(18)
        eff.setOffset(0, 8)
        eff.setColor(QtGui.QColor(0, 0, 0, 120))
        card.setGraphicsEffect(eff)

    def _on_selected_row(self, row: int):
        if row < 0:
            self._show_detail(None)
            return
        lw_item = self.listw.item(row)
        if not lw_item:
            self._show_detail(None)
            return
        it = lw_item.data(Qt.UserRole)
        self._show_detail(it if isinstance(it, MediaItem) else None)

    def _set_detail_placeholder(self):
        pm = QtGui.QPixmap(self.detail_img.size())
        pm.fill(Qt.transparent)
        p = QtGui.QPainter(pm)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = pm.rect().adjusted(1, 1, -1, -1)
        grad = QtGui.QLinearGradient(rect.topLeft(), rect.bottomRight())
        grad.setColorAt(0.0, QtGui.QColor(60, 74, 95))
        grad.setColorAt(1.0, QtGui.QColor(20, 24, 35))
        p.setBrush(QtGui.QBrush(grad))
        p.setPen(QtGui.QPen(QtGui.QColor(90, 105, 130), 1))
        p.drawRoundedRect(rect, 16, 16)
        p.setPen(QtGui.QColor(170, 185, 210))
        p.setFont(QtGui.QFont("Inter", 10, 700))
        p.drawText(rect, Qt.AlignCenter, "Cover")
        p.end()
        self.detail_img.setPixmap(pm)

    def _show_detail(self, it: Optional[MediaItem]):
        self._current_item = it
        if not it:
            self.detail_title.setText("Select an item")
            self.detail_native.setVisible(False)
            self.detail_meta.setText("")
            self.detail_desc.setText(
                "Click Download to fetch the last 7 days of new anime/manga start dates.\n\n"
                "Note: This is based on AniList startDate; it is not a store/volume release tracker."
            )
            self.p_type.setText("—")
            self.p_country.setText("—")
            self.p_lang.setText("—")
            self.btn_open.setEnabled(False)
            self.btn_copy.setEnabled(False)
            self._set_detail_placeholder()
            return

        self.detail_title.setText(it.title)
        self.detail_native.setText(it.title_native)
        self.detail_native.setVisible(bool(it.title_native))

        self.p_type.setText(it.media_type)
        self.p_country.setText(it.country)
        self.p_lang.setText(it.language)

        meta = (
            f"Publication day: {it.publication_day}\n"
            f"Country of release: {it.country} ({it.country_code or 'Unknown'})\n"
            f"Main language: {it.language}\n"
            f"Format: {it.format}\n"
            f"Status: {it.status}"
        )
        self.detail_meta.setText(meta)
        self.detail_desc.setText(it.description or "No description provided.")

        self.btn_open.setEnabled(bool(it.site_url))
        self.btn_copy.setEnabled(bool(it.site_url))

        if it.image_url:
            self.img_cache.request(it.image_url)
            self._update_detail_image_if_ready()

    def _update_detail_image_if_ready(self):
        it = self._current_item
        if not it or not it.image_url:
            return
        pix = self.img_cache.get(it.image_url)
        if not pix:
            return
        scaled = pix.scaled(self.detail_img.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        self.detail_img.setPixmap(scaled)

    def _on_image_ready(self, url: str):
        for i in range(self.listw.count()):
            lw_item = self.listw.item(i)
            w = self.listw.itemWidget(lw_item)
            if isinstance(w, MediaCard) and w.item.image_url == url:
                w.update_image_if_ready()

        it = self._current_item
        if it and it.image_url == url:
            self._update_detail_image_if_ready()

    def _open_current(self):
        it = self._current_item
        if it and it.site_url:
            QtGui.QDesktopServices.openUrl(QUrl(it.site_url))

    def _copy_current(self):
        it = self._current_item
        if not it or not it.site_url:
            return
        QtWidgets.QApplication.clipboard().setText(it.site_url)
        self.status.setText("Link copied to clipboard.")

    def closeEvent(self, e: QtGui.QCloseEvent):
        self._stop_worker_if_any()
        super().closeEvent(e)


def main():
    app = QtWidgets.QApplication(sys.argv)
    w = Window()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

