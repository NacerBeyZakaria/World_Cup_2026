"""
Matches page — all 104 matches grouped by date.
Match cards are clickable → opens MatchDialog.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QPushButton, QLineEdit, QComboBox, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal
from database.database import (
    get_all_matches_with_teams, get_matches_by_stage, set_watch_status
)
from ui.tz_utils import format_kickoff, convert_match_time

STAGES = ["All Stages", "Group Stage", "Round of 32", "Round of 16",
          "Quarter Final", "Semi Final", "Third Place Match", "Final"]
WATCH_OPTIONS  = ["Not Set", "Watched", "Missed", "Planned", "Favorite"]
STATUS_FILTER  = ["All", "Watched", "Missed", "Planned", "Not Set"]


class MatchCard(QFrame):
    status_changed = pyqtSignal(int, str)

    def __init__(self, match: dict):
        super().__init__()
        self.match_id = match["id"]
        self._ws      = match.get("user_watch_status", "Not Set")
        self.setObjectName("matchCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._build(match)

    def _build(self, m: dict):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 11, 16, 11)
        lay.setSpacing(12)

       
        info = QVBoxLayout(); info.setSpacing(2)
        info.setAlignment(Qt.AlignmentFlag.AlignTop)
        kick = format_kickoff(m.get("match_date",""), m.get("match_time",""))
        tl = QLabel(kick)
        tl.setStyleSheet("font-size:12px; color:#8b949e; min-width:70px;")
        info.addWidget(tl)
        venue = m.get("city") or m.get("venue") or ""
        if venue:
            vl = QLabel(venue)
            vl.setStyleSheet("font-size:10px; color:#484f58;")
            info.addWidget(vl)
        lay.addLayout(info)

      
        center = QHBoxLayout(); center.setSpacing(8)
        center.setAlignment(Qt.AlignmentFlag.AlignCenter)

        home_lbl = QLabel(m.get("home_team_name","TBD"))
        home_lbl.setObjectName("teamName")
        home_lbl.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)

        hs, as_ = m.get("home_score"), m.get("away_score")
        if hs is not None and as_ is not None:
            sc = QLabel(f"{hs}  –  {as_}")
            sc.setObjectName("score")
        else:
            sc = QLabel("vs")
            sc.setStyleSheet("font-size:14px; font-weight:600; color:#484f58; min-width:50px;")
        sc.setAlignment(Qt.AlignmentFlag.AlignCenter)

        away_lbl = QLabel(m.get("away_team_name","TBD"))
        away_lbl.setObjectName("teamName")
        away_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter)

        center.addWidget(home_lbl); center.addWidget(sc); center.addWidget(away_lbl)
        lay.addLayout(center, 1)

       
        right = QVBoxLayout(); right.setSpacing(5)
        right.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)

        badges = QHBoxLayout(); badges.setSpacing(5)
        status = m.get("status","Scheduled")
        if status == "Live":
            sb = QLabel("🔴 LIVE"); sb.setObjectName("liveBadge")
        elif status == "Finished":
            sb = QLabel("FT")
            sb.setStyleSheet("background:#21262d; color:#8b949e; padding:2px 6px; border-radius:4px; font-size:10px; font-weight:600;")
        else:
            sb = QLabel("Soon")
            sb.setStyleSheet("background:#1c2f4a; color:#58a6ff; padding:2px 6px; border-radius:4px; font-size:10px;")

        stage_b = QLabel(m.get("stage",""))
        stage_b.setObjectName("stageBadge")
        badges.addWidget(sb); badges.addWidget(stage_b)
        right.addLayout(badges)

        self.watch_btn = QPushButton(self._ws)
        self.watch_btn.setObjectName("watchBtn")
        self.watch_btn.setProperty("status", self._ws)
        self.watch_btn.setFixedWidth(90)
        self.watch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.watch_btn.clicked.connect(self._cycle_status)
        right.addWidget(self.watch_btn, 0, Qt.AlignmentFlag.AlignRight)
        lay.addLayout(right)

    def _cycle_status(self):
        idx = WATCH_OPTIONS.index(self._ws) if self._ws in WATCH_OPTIONS else 0
        self._ws = WATCH_OPTIONS[(idx + 1) % len(WATCH_OPTIONS)]
        self.watch_btn.setText(self._ws)
        self.watch_btn.setProperty("status", self._ws)
        self.watch_btn.style().unpolish(self.watch_btn)
        self.watch_btn.style().polish(self.watch_btn)
        set_watch_status(self.match_id, self._ws)
        self.status_changed.emit(self.match_id, self._ws)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            from ui.match_dialog import MatchDialog
            dlg = MatchDialog(self.match_id, self)
            dlg.watch_status_changed.connect(self._on_dialog_status)
            dlg.exec()
        super().mousePressEvent(event)

    def _on_dialog_status(self, mid: int, new_ws: str):
        self._ws = new_ws
        self.watch_btn.setText(new_ws)
        self.watch_btn.setProperty("status", new_ws)
        self.watch_btn.style().unpolish(self.watch_btn)
        self.watch_btn.style().polish(self.watch_btn)
        self.status_changed.emit(mid, new_ws)


class MatchesPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_matches  = []
        self._stage_filter = "All Stages"
        self._ws_filter    = "All"
        self._query        = ""
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(14)

        
        hdr = QHBoxLayout()
        title = QLabel("Matches"); title.setObjectName("sectionTitle")
        hdr.addWidget(title); hdr.addStretch()
        outer.addLayout(hdr)

        
        fil = QHBoxLayout(); fil.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍  Search by team name…")
        self.search.setFixedHeight(36)
        self.search.textChanged.connect(self._on_search)
        fil.addWidget(self.search, 1)

        self.stage_combo = QComboBox()
        self.stage_combo.addItems(STAGES)
        self.stage_combo.setFixedHeight(36)
        self.stage_combo.currentTextChanged.connect(self._on_stage_filter)
        fil.addWidget(self.stage_combo)

        self.ws_combo = QComboBox()
        self.ws_combo.addItems(STATUS_FILTER)
        self.ws_combo.setFixedHeight(36)
        self.ws_combo.currentTextChanged.connect(self._on_ws_filter)
        fil.addWidget(self.ws_combo)
        outer.addLayout(fil)

        self.count_lbl = QLabel()
        self.count_lbl.setStyleSheet("color:#8b949e; font-size:11px;")
        outer.addWidget(self.count_lbl)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.container     = QWidget()
        self.matches_layout = QVBoxLayout(self.container)
        self.matches_layout.setContentsMargins(0,0,0,0)
        self.matches_layout.setSpacing(4)
        scroll.setWidget(self.container)
        outer.addWidget(scroll, 1)

    def refresh(self):
        self._all_matches = get_all_matches_with_teams()
        self._render()

    def _on_search(self, text): self._query = text.strip(); self._render()
    def _on_stage_filter(self, s): self._stage_filter = s; self._render()
    def _on_ws_filter(self, s): self._ws_filter = s; self._render()

    def _filtered(self) -> list[dict]:
        ms = self._all_matches
        if self._query:
            q = self._query.lower()
            ms = [m for m in ms if
                  q in (m.get("home_team_name") or "").lower() or
                  q in (m.get("away_team_name") or "").lower()]
        if self._stage_filter != "All Stages":
            ms = [m for m in ms if m.get("stage") == self._stage_filter]
        if self._ws_filter != "All":
            ms = [m for m in ms if m.get("user_watch_status") == self._ws_filter]
        return ms

    def _render(self):
        while self.matches_layout.count():
            item = self.matches_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        matches = self._filtered()
        self.count_lbl.setText(f"{len(matches)} match{'es' if len(matches)!=1 else ''}")

        from collections import OrderedDict
        grouped: OrderedDict[str, list] = OrderedDict()
        for m in matches:
            local_date, _ = convert_match_time(
                m.get("match_date",""), m.get("match_time","")
            )
            grouped.setdefault(local_date or m.get("match_date","Unknown"), []).append(m)

        for date, day_matches in grouped.items():
            try:
                from datetime import datetime as _dt
                dt = _dt.strptime(date, "%Y-%m-%d")
                date_str = dt.strftime("%A, %B %d").replace(" 0"," ")
            except ValueError:
                date_str = date
            lbl = QLabel(date_str.upper()); lbl.setObjectName("dateSeparator")
            self.matches_layout.addWidget(lbl)
            for m in day_matches:
                card = MatchCard(m)
                card.status_changed.connect(self._on_card_status)
                self.matches_layout.addWidget(card)
            self.matches_layout.addSpacing(6)

        self.matches_layout.addStretch()

    def _on_card_status(self, match_id: int, new_status: str):
        for m in self._all_matches:
            if m["id"] == match_id:
                m["user_watch_status"] = new_status; break
