"""
Knockout Bracket page — draws the tournament tree from R32 through Final.
Reads finished/scheduled knockout matches from the DB.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QScrollArea
)
from PyQt6.QtCore import Qt
from database.database import get_matches_by_stage


STAGE_ORDER = [
    "Round of 32",
    "Round of 16",
    "Quarter Final",
    "Semi Final",
    "Final",
]


class MatchSlot(QFrame):
    """One match slot in the bracket."""
    def __init__(self, home: str, away: str,
                 home_score=None, away_score=None,
                 status="Scheduled"):
        super().__init__()
        self.setObjectName("card")
        self.setFixedWidth(200)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(4)

      
        winner = None
        if status == "Finished" and home_score is not None and away_score is not None:
            if home_score > away_score:
                winner = "home"
            elif away_score > home_score:
                winner = "away"

        def team_row(name: str, score, is_winner: bool):
            row = QHBoxLayout()
            row.setSpacing(6)
            name_lbl = QLabel(name or "TBD")
            if is_winner:
                name_lbl.setStyleSheet("font-size:12px; font-weight:700; color:#e6edf3;")
            else:
                name_lbl.setStyleSheet("font-size:12px; color:#8b949e;")
            name_lbl.setFixedWidth(120)
            name_lbl.setWordWrap(False)
            score_lbl = QLabel(str(score) if score is not None else "–")
            if is_winner:
                score_lbl.setStyleSheet("font-size:12px; font-weight:700; color:#3fb950;")
            else:
                score_lbl.setStyleSheet("font-size:12px; color:#8b949e;")
            score_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(name_lbl)
            row.addStretch()
            row.addWidget(score_lbl)
            return row

        lay.addLayout(team_row(home, home_score, winner == "home"))

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#30363d;")
        lay.addWidget(sep)

        lay.addLayout(team_row(away, away_score, winner == "away"))

       
        if status == "Live":
            badge = QLabel("🔴 LIVE")
            badge.setStyleSheet("font-size:9px; color:#da3633; font-weight:700;")
            lay.addWidget(badge)


class EmptySlot(QFrame):
    """TBD placeholder slot."""
    def __init__(self):
        super().__init__()
        self.setObjectName("card")
        self.setFixedWidth(200)
        self.setFixedHeight(72)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lbl = QLabel("TBD")
        lbl.setStyleSheet("color:#484f58; font-size:12px;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl)


class RoundColumn(QWidget):
    """One column of the bracket (one round)."""
    def __init__(self, stage_name: str, matches: list[dict]):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop)

        lbl = QLabel(stage_name)
        lbl.setObjectName("dateSeparator")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setFixedWidth(220)
        lay.addWidget(lbl)
        lay.addSpacing(8)

        if not matches:
            lay.addWidget(EmptySlot())
        else:
            for m in matches:
                slot = MatchSlot(
                    home=m.get("home_team_name", "TBD"),
                    away=m.get("away_team_name", "TBD"),
                    home_score=m.get("home_score"),
                    away_score=m.get("away_score"),
                    status=m.get("status", "Scheduled"),
                )
                lay.addWidget(slot)
                lay.addSpacing(6)

        lay.addStretch()


class BracketPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(16)

        title = QLabel("Knockout Bracket")
        title.setObjectName("sectionTitle")
        outer.addWidget(title)

        note = QLabel("Auto-populated from match results. Stages shown left to right from Round of 32 to Final.")
        note.setStyleSheet("color:#8b949e; font-size:11px;")
        outer.addWidget(note)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.inner = QWidget()
        self.inner_lay = QHBoxLayout(self.inner)
        self.inner_lay.setContentsMargins(0, 8, 0, 8)
        self.inner_lay.setSpacing(24)
        self.inner_lay.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        scroll.setWidget(self.inner)
        outer.addWidget(scroll, 1)

    def refresh(self):
        while self.inner_lay.count():
            item = self.inner_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for stage in STAGE_ORDER:
            matches = get_matches_by_stage(stage)
            col = RoundColumn(stage, matches)
            self.inner_lay.addWidget(col)
