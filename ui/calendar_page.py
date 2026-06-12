"""Calendar page — click a day to see its matches."""

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame,
    QScrollArea, QCalendarWidget, QSizePolicy
)
from PyQt6.QtCore import Qt, QDate
from database.database import get_matches_by_date, get_distinct_match_dates, set_watch_status, get_all_matches_with_teams
from ui.matches_page import MatchCard
from ui.tz_utils import convert_match_time, get_user_offset_minutes


class CalendarPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._match_dates = set()
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(20)

        # Left: calendar
        left = QVBoxLayout()
        title = QLabel("Calendar")
        title.setObjectName("sectionTitle")
        left.addWidget(title)
        left.addSpacing(12)

        self.cal = QCalendarWidget()
        self.cal.setGridVisible(False)
        self.cal.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self.cal.setMinimumDate(QDate(2026, 6, 1))
        self.cal.setMaximumDate(QDate(2026, 7, 31))
        self.cal.setSelectedDate(QDate(2026, 6, 11))
        self.cal.setStyleSheet("""
            QCalendarWidget QWidget { background: #161b22; }
            QCalendarWidget QAbstractItemView { font-size: 13px; }
            QCalendarWidget QToolButton { color: #e6edf3; font-size: 13px; }
        """)
        self.cal.selectionChanged.connect(self._on_date_selected)
        self.cal.setFixedWidth(340)
        left.addWidget(self.cal)
        left.addStretch()
        outer.addLayout(left)

        # Right: matches for selected day
        right = QVBoxLayout()
        self.day_title = QLabel("Select a day")
        self.day_title.setObjectName("sectionTitle")
        right.addWidget(self.day_title)
        right.addSpacing(12)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.matches_container = QWidget()
        self.matches_layout    = QVBoxLayout(self.matches_container)
        self.matches_layout.setContentsMargins(0, 0, 0, 0)
        self.matches_layout.setSpacing(8)
        scroll.setWidget(self.matches_container)
        right.addWidget(scroll, 1)
        outer.addLayout(right, 1)

    def refresh(self):
        # Build a mapping of local date → list of matches (respects user timezone)
        # A match stored as UTC 2026-06-11 23:00 appears on 2026-06-12 for UTC+1 users.
        all_matches = get_all_matches_with_teams()
        self._local_date_matches: dict[str, list] = {}
        for m in all_matches:
            local_date, _ = convert_match_time(
                m.get("match_date", ""), m.get("match_time", "")
            )
            key = local_date or m.get("match_date", "")
            self._local_date_matches.setdefault(key, []).append(m)

        self._match_dates = set(self._local_date_matches.keys())

        # Jump to first match day
        if self._match_dates:
            first = min(self._match_dates)
            try:
                from datetime import date
                d = date.fromisoformat(first)
                self.cal.setSelectedDate(QDate(d.year, d.month, d.day))
            except Exception:
                pass
        self._on_date_selected()

    def _on_date_selected(self):
        selected = self.cal.selectedDate()
        date_str = selected.toString("yyyy-MM-dd")

        try:
            from datetime import date as _date
            dt = _date.fromisoformat(date_str)
            label = dt.strftime("%A, %B %d, %Y")
        except Exception:
            label = date_str

        # Append timezone label when not UTC
        from database.database import get_setting
        tz = (get_setting("timezone", "UTC") or "UTC").split(" ")[0]
        if tz != "UTC":
            label += f"  ({tz})"
        self.day_title.setText(label)

        # Clear
        while self.matches_layout.count():
            item = self.matches_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Use local-date mapping built in refresh()
        matches = getattr(self, "_local_date_matches", {}).get(date_str, [])
        if not matches:
            no_match = QLabel("No matches on this day.")
            no_match.setStyleSheet("color:#484f58; font-size:13px; padding:20px 0;")
            self.matches_layout.addWidget(no_match)
        else:
            for m in matches:
                card = MatchCard(m)
                self.matches_layout.addWidget(card)

        self.matches_layout.addStretch()
