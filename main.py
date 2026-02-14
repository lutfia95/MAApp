from __future__ import annotations

import sys
from PySide6 import QtWidgets

from app.window import Window


def main():
    app = QtWidgets.QApplication(sys.argv)
    w = Window()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()