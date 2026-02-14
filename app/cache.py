from __future__ import annotations

from typing import Dict, Optional

from PySide6 import QtCore, QtGui, QtNetwork
from PySide6.QtCore import QUrl


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
