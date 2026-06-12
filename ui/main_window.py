"""
Main window — sidebar navigation + stacked pages.
Wires: sync timer (30 min), live score timer (60 s),
       countdown tick (60 s), notification check (60 s),
       timezone_changed → refresh all pages,
       theme_changed → apply stylesheet.
"""

import sys
import logging
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QLabel, QStackedWidget,
    QStatusBar, QApplication, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QObject
from database.database import initialize_db, get_setting
from ui.theme import DARK_THEME, LIGHT_THEME

logger = logging.getLogger(__name__)


class SyncWorker(QObject):
    finished = pyqtSignal(dict)
    error    = pyqtSignal(str)

    def run(self):
        try:
            from services.sync_service import run_sync
            result = run_sync()
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


class NavButton(QPushButton):
    def __init__(self, icon: str, label: str):
        super().__init__(f"  {icon}  {label}")
        self.setObjectName("navBtn")
        self.setFixedHeight(44)

    def set_active(self, active: bool):
        self.setProperty("active", "true" if active else "false")
        self.style().unpolish(self); self.style().polish(self)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FIFA World Cup 2026 Tracker")
        self.setMinimumSize(1100, 720)
        self.resize(1300, 820)

        initialize_db()
        self._apply_theme(get_setting("theme", "dark"))
        self._user_initiated_sync = False
        self._build_ui()
        self._setup_timers()
        self._run_initial_sync()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        
        sidebar = QWidget(); sidebar.setObjectName("sidebar")
        sb = QVBoxLayout(sidebar)
        sb.setContentsMargins(8, 0, 8, 16)
        sb.setSpacing(2)

        logo = QLabel("⚽ WC 2026"); logo.setObjectName("sidebarTitle")
        sb.addWidget(logo)
        sb.addSpacing(8)

        self._nav_buttons: list[NavButton] = []
        nav_items = [
            ("🏠", "Dashboard"),
            ("📋", "Matches"),
            ("📅", "Calendar"),
            ("🗂️", "Groups"),
            ("🏆", "Bracket"),
            ("📊", "Statistics"),
            ("⚙️", "Settings"),
        ]
        for icon, label in nav_items:
            btn = NavButton(icon, label)
            btn.clicked.connect(lambda _, l=label: self._navigate(l))
            sb.addWidget(btn)
            self._nav_buttons.append(btn)

        sb.addStretch()

        self.sync_btn = QPushButton("🔄  Sync Now")
        self.sync_btn.setObjectName("syncBtn")
        self.sync_btn.setFixedHeight(36)
        self.sync_btn.clicked.connect(self._manual_sync)
        sb.addWidget(self.sync_btn)
        root.addWidget(sidebar)

        
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        from ui.dashboard       import DashboardPage
        from ui.matches_page    import MatchesPage
        from ui.calendar_page   import CalendarPage
        from ui.groups_page     import GroupsPage
        from ui.bracket_page    import BracketPage
        from ui.statistics_page import StatisticsPage
        from ui.settings_page   import SettingsPage

        self.pages: dict[str, QWidget] = {}
        for name, cls in [
            ("Dashboard",  DashboardPage),
            ("Matches",    MatchesPage),
            ("Calendar",   CalendarPage),
            ("Groups",     GroupsPage),
            ("Bracket",    BracketPage),
            ("Statistics", StatisticsPage),
            ("Settings",   SettingsPage),
        ]:
            page = cls()
            self.stack.addWidget(page)
            self.pages[name] = page

        self.pages["Settings"].theme_changed.connect(self._apply_theme)
        self.pages["Settings"].timezone_changed.connect(self._refresh_all_pages)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

        self._navigate("Dashboard")

    def _navigate(self, page_name: str):
        for btn in self._nav_buttons:
            label = btn.text().strip().split("  ")[-1]
            btn.set_active(label == page_name)
        page = self.pages.get(page_name)
        if page:
            self.stack.setCurrentWidget(page)
            if hasattr(page, "refresh"):
                page.refresh()

    def _setup_timers(self):
      
        self.sync_timer = QTimer(self)
        self.sync_timer.setInterval(30 * 60 * 1000)
        self.sync_timer.timeout.connect(self._background_sync)
        self.sync_timer.start()

        
        self.live_timer = QTimer(self)
        self.live_timer.setInterval(60_000)
        self.live_timer.timeout.connect(self._live_tick)
        self.live_timer.start()

    def _live_tick(self):
        
        from services.sync_service import sync_live_scores
        try:
            updated = sync_live_scores()
            if updated > 0:
                current = self.stack.currentWidget()
                if current and hasattr(current, "refresh"):
                    current.refresh()
        except Exception as exc:
            logger.warning("Live tick error: %s", exc)

      
        try:
            from services.notification_service import check_and_notify
            check_and_notify()
        except Exception as exc:
            logger.debug("Notification check error: %s", exc)

        
        dash = self.pages.get("Dashboard")
        if dash and hasattr(dash, "_countdown"):
            dash._countdown._tick()

    def _run_initial_sync(self):
        self.status_bar.showMessage("Syncing data…")
        self.sync_btn.setEnabled(False)
        self._start_sync()

    def _manual_sync(self):
        self.sync_btn.setEnabled(False)
        self.status_bar.showMessage("Syncing…")
        self._user_initiated_sync = True
        self._start_sync()

    def _background_sync(self):
        self._start_sync()

    def _start_sync(self):
        self._thread = QThread()
        self._worker = SyncWorker()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_sync_done)
        self._worker.error.connect(self._on_sync_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.start()

    def _on_sync_done(self, result: dict):
        self.sync_btn.setEnabled(True)
        error = result.get("error")
        if error:
            self.status_bar.showMessage("Sync failed — check Settings → API Key")
            if self._user_initiated_sync:
                QMessageBox.critical(
                    self, "Sync Failed",
                    "Could not fetch World Cup data:\n\n" + str(error) +
                    "\n\nGo to Settings to configure your free API key."
                )
            self._user_initiated_sync = False
            return

        source  = result.get("source", "?")
        matches = result.get("matches", 0)
        teams   = result.get("teams", 0)
        self.status_bar.showMessage(
            f"✅  Synced {matches} matches, {teams} teams from {source}  •  Just now"
        )
        self._user_initiated_sync = False
        
        settings = self.pages.get("Settings")
        if settings and hasattr(settings, "_populate_fav_grid"):
            settings._populate_fav_grid()
        current = self.stack.currentWidget()
        if current and hasattr(current, "refresh"):
            current.refresh()

    def _on_sync_error(self, msg: str):
        self.status_bar.showMessage(f"Sync error: {msg}")
        self.sync_btn.setEnabled(True)
        logger.error("Sync error: %s", msg)

    def _refresh_all_pages(self):
        for page in self.pages.values():
            if hasattr(page, "refresh"):
                page.refresh()

    def _apply_theme(self, theme: str):
        app = QApplication.instance()
        app.setStyleSheet(LIGHT_THEME if theme == "light" else DARK_THEME)
