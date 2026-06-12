#!/usr/bin/env python3
"""
FIFA World Cup 2026 Tracker
Entry point — sets up logging, creates the QApplication, and launches the window.

Usage:
    pip install -r requirements.txt
    python main.py
"""

import sys
import os
import logging

# Ensure the package root is on the path when running directly
sys.path.insert(0, os.path.dirname(__file__))

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("worldcup")

# ── Qt bootstrap ──────────────────────────────────────────────────────────────
try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QFont
    from PyQt6.QtCore import Qt
except ImportError:
    print("PyQt6 is required.  Run:  pip install -r requirements.txt")
    sys.exit(1)

from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("FIFA World Cup 2026 Tracker")
    app.setOrganizationName("WorldCupTracker")

    # Use a clean system font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # High-DPI support
    try:
        app.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
    except Exception:
        pass

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
