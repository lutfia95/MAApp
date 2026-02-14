from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt

from .cache import ImageCache
from .models import MediaItem


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
