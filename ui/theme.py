"""
Global dark-theme stylesheet for the World Cup 2026 Tracker.
Colour palette:
  - Background dark  : #0d1117
  - Card background  : #161b22
  - Border           : #30363d
  - Accent green     : #3fb950  (FIFA grass green)
  - Accent gold      : #d29922
  - Text primary     : #e6edf3
  - Text secondary   : #8b949e
"""

DARK_THEME = """
/* ─── Base ─────────────────────────────────────────────── */
QMainWindow, QDialog, QWidget {
    background-color: #0d1117;
    color: #e6edf3;
    font-family: "Segoe UI", "Inter", "SF Pro Display", sans-serif;
    font-size: 13px;
}

QScrollArea {
    border: none;
    background: transparent;
}

QScrollBar:vertical {
    width: 6px;
    background: #0d1117;
}
QScrollBar::handle:vertical {
    background: #30363d;
    border-radius: 3px;
    min-height: 20px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

/* ─── Sidebar ───────────────────────────────────────────── */
#sidebar {
    background-color: #0d1117;
    border-right: 1px solid #21262d;
    min-width: 200px;
    max-width: 200px;
}

#sidebarTitle {
    font-size: 11px;
    font-weight: 700;
    color: #3fb950;
    letter-spacing: 2px;
    padding: 20px 16px 8px;
}

QPushButton#navBtn {
    text-align: left;
    padding: 10px 16px;
    border: none;
    border-radius: 6px;
    background: transparent;
    color: #8b949e;
    font-size: 13px;
    font-weight: 500;
}
QPushButton#navBtn:hover {
    background: #161b22;
    color: #e6edf3;
}
QPushButton#navBtn[active="true"] {
    background: #1f2937;
    color: #3fb950;
    border-left: 3px solid #3fb950;
}

/* ─── Cards ─────────────────────────────────────────────── */
QFrame#card {
    background-color: #161b22;
    border: 1px solid #21262d;
    border-radius: 10px;
}

QFrame#matchCard {
    background-color: #161b22;
    border: 1px solid #21262d;
    border-radius: 8px;
}
QFrame#matchCard:hover {
    border-color: #30363d;
    background-color: #1c2128;
}

/* ─── Labels ────────────────────────────────────────────── */
QLabel#sectionTitle {
    font-size: 18px;
    font-weight: 700;
    color: #e6edf3;
}
QLabel#dateSeparator {
    font-size: 12px;
    font-weight: 600;
    color: #3fb950;
    letter-spacing: 1px;
    padding: 12px 0 4px;
}
QLabel#statNumber {
    font-size: 36px;
    font-weight: 800;
    color: #e6edf3;
}
QLabel#statLabel {
    font-size: 11px;
    color: #8b949e;
    text-transform: uppercase;
    letter-spacing: 1px;
}
QLabel#teamName {
    font-size: 14px;
    font-weight: 600;
    color: #e6edf3;
}
QLabel#score {
    font-size: 20px;
    font-weight: 800;
    color: #e6edf3;
    min-width: 60px;
}
QLabel#stageBadge {
    font-size: 10px;
    font-weight: 600;
    color: #8b949e;
    background: #21262d;
    border-radius: 4px;
    padding: 2px 6px;
}
QLabel#liveBadge {
    font-size: 10px;
    font-weight: 700;
    color: #ffffff;
    background: #da3633;
    border-radius: 4px;
    padding: 2px 6px;
}

/* ─── Buttons ───────────────────────────────────────────── */
QPushButton#watchBtn {
    border-radius: 5px;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 600;
    border: 1px solid #30363d;
    background: #21262d;
    color: #8b949e;
}
QPushButton#watchBtn:hover { background: #2d333b; color: #e6edf3; }
QPushButton#watchBtn[status="Watched"]  { background: #1a4731; color: #3fb950; border-color: #3fb950; }
QPushButton#watchBtn[status="Missed"]   { background: #3d1f1f; color: #f85149; border-color: #f85149; }
QPushButton#watchBtn[status="Planned"]  { background: #1c2f4a; color: #58a6ff; border-color: #58a6ff; }
QPushButton#watchBtn[status="Favorite"] { background: #3d2f00; color: #d29922; border-color: #d29922; }

QPushButton#syncBtn {
    background: #238636;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 600;
}
QPushButton#syncBtn:hover { background: #2ea043; }
QPushButton#syncBtn:disabled { background: #21262d; color: #484f58; }

QPushButton#primaryBtn {
    background: #1f6feb;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 8px 18px;
    font-weight: 600;
}
QPushButton#primaryBtn:hover { background: #388bfd; }

/* ─── ComboBox ──────────────────────────────────────────── */
QComboBox {
    background: #21262d;
    border: 1px solid #30363d;
    border-radius: 5px;
    padding: 4px 8px;
    color: #e6edf3;
    font-size: 12px;
}
QComboBox QAbstractItemView {
    background: #161b22;
    border: 1px solid #30363d;
    selection-background-color: #1f6feb;
    color: #e6edf3;
}
QComboBox::drop-down { border: none; width: 20px; }

/* ─── LineEdit / Search ──────────────────────────────────── */
QLineEdit {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 8px 12px;
    color: #e6edf3;
    font-size: 13px;
}
QLineEdit:focus { border-color: #1f6feb; }

/* ─── Tab Widget ─────────────────────────────────────────── */
QTabWidget::pane  { border: none; }
QTabBar::tab {
    background: transparent;
    color: #8b949e;
    padding: 8px 16px;
    border-bottom: 2px solid transparent;
    font-size: 13px;
}
QTabBar::tab:selected { color: #e6edf3; border-bottom: 2px solid #3fb950; }
QTabBar::tab:hover    { color: #e6edf3; }

/* ─── Calendar ───────────────────────────────────────────── */
QCalendarWidget QToolButton {
    background: transparent;
    color: #e6edf3;
    border: none;
    font-size: 13px;
}
QCalendarWidget QMenu {
    background: #161b22;
    color: #e6edf3;
}
QCalendarWidget QAbstractItemView:enabled {
    background-color: #161b22;
    color: #e6edf3;
    selection-background-color: #1f6feb;
    selection-color: white;
}
QCalendarWidget QAbstractItemView:disabled { color: #484f58; }

/* ─── Tooltip ────────────────────────────────────────────── */
QToolTip {
    background: #161b22;
    color: #e6edf3;
    border: 1px solid #30363d;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 12px;
}

/* ─── Status bar ─────────────────────────────────────────── */
QStatusBar {
    background: #010409;
    color: #484f58;
    font-size: 11px;
    border-top: 1px solid #21262d;
}
"""

LIGHT_THEME = """
QMainWindow, QDialog, QWidget {
    background-color: #ffffff;
    color: #1f2328;
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
}
#sidebar {
    background-color: #f6f8fa;
    border-right: 1px solid #d0d7de;
    min-width: 200px;
    max-width: 200px;
}
QPushButton#navBtn {
    text-align: left;
    padding: 10px 16px;
    border: none;
    border-radius: 6px;
    background: transparent;
    color: #57606a;
    font-size: 13px;
}
QPushButton#navBtn:hover    { background: #eaeef2; color: #1f2328; }
QPushButton#navBtn[active="true"] { background: #dafbe1; color: #116329; border-left: 3px solid #2da44e; }
QFrame#card {
    background-color: #f6f8fa;
    border: 1px solid #d0d7de;
    border-radius: 10px;
}
QFrame#matchCard {
    background-color: #f6f8fa;
    border: 1px solid #d0d7de;
    border-radius: 8px;
}
QLineEdit {
    background: #f6f8fa;
    border: 1px solid #d0d7de;
    border-radius: 6px;
    padding: 8px 12px;
    color: #1f2328;
}
"""
