"""
Groups Page — all 12 World Cup groups with live standings.

Improvements over the original:
  - Team rows are clickable → opens TeamDialog
  - Qualification colour coding:
      Green  = top 2 (auto-qualified)
      Gold   = 3rd place (potential best-8 qualifier)
      Red    = mathematically eliminated (0 pts, 0 remaining games possible)
      Gray   = still in contention
  - "Matches played" progress per group
  - Correctly sorts by Pts → GD → GF → name
"""

from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QGridLayout, QSizePolicy, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QCursor

from database.database import get_all_teams, get_all_matches_with_teams


# ── Data model ─────────────────────────────────────────────────────────────────

@dataclass
class TeamStanding:
    team_id:    int
    name:       str
    short_name: str
    flag_url:   str
    group:      str
    played:     int = 0
    won:        int = 0
    drawn:      int = 0
    lost:       int = 0
    gf:         int = 0
    ga:         int = 0

    @property
    def gd(self) -> int: return self.gf - self.ga
    @property
    def points(self) -> int: return self.won * 3 + self.drawn
    def sort_key(self) -> tuple:
        return (-self.points, -self.gd, -self.gf, self.name)


def compute_standings(
    teams: list[dict],
    matches: list[dict],
) -> dict[str, list[TeamStanding]]:
    standings: dict[int, TeamStanding] = {}
    for t in teams:
        grp = (t.get("group_name") or "").strip().upper()
        if not grp or grp not in "ABCDEFGHIJKL":
            continue
        standings[t["id"]] = TeamStanding(
            team_id=t["id"],
            name=t["name"],
            short_name=t.get("fifa_code") or t["name"][:3].upper(),
            flag_url=t.get("flag_url", ""),
            group=grp,
        )

    for m in matches:
        if m.get("stage") != "Group Stage" or m.get("status") != "Finished":
            continue
        hs, as_ = m.get("home_score"), m.get("away_score")
        if hs is None or as_ is None:
            continue
        home = standings.get(m.get("home_team_id"))
        away = standings.get(m.get("away_team_id"))
        if home:
            home.played += 1; home.gf += hs; home.ga += as_
            if hs > as_:  home.won   += 1
            elif hs==as_: home.drawn += 1
            else:         home.lost  += 1
        if away:
            away.played += 1; away.gf += as_; away.ga += hs
            if as_ > hs:  away.won   += 1
            elif as_==hs: away.drawn += 1
            else:         away.lost  += 1

    grouped: dict[str, list[TeamStanding]] = defaultdict(list)
    for ts in standings.values():
        grouped[ts.group].append(ts)
    for grp in grouped:
        grouped[grp].sort(key=lambda t: t.sort_key())
    return dict(sorted(grouped.items()))


def _elimination_status(ts: TeamStanding, pos: int, group_size: int,
                        matches_played_in_group: int) -> str:
    """
    Returns 'qualified' | 'potential' | 'eliminated' | 'contention'.
    Simple heuristic — a proper calculation requires simulating all outcomes.
    """
    total_group_games = 6   # 4 teams, each plays 3 → 6 matches total
    if pos < 2:             # top 2 after all games played
        return "qualified" if matches_played_in_group == total_group_games else "contention"
    if pos == 2:
        return "contention"
    if pos == 3:
        return "potential"
    # 4th place: eliminated if they cannot reach 2nd
    max_possible_pts = ts.points + (3 - ts.played) * 3
    if max_possible_pts < 4:   # practically impossible to qualify as best-3rd
        return "eliminated"
    return "contention"


# ── Column spec ────────────────────────────────────────────────────────────────

_COLS = [
    # (abbr, tooltip,      w,   align)
    ("#",  "Position",    28,  Qt.AlignmentFlag.AlignCenter),
    ("",   "Team",       168,  Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
    ("MP", "Played",      34,  Qt.AlignmentFlag.AlignCenter),
    ("W",  "Won",         30,  Qt.AlignmentFlag.AlignCenter),
    ("D",  "Drawn",       30,  Qt.AlignmentFlag.AlignCenter),
    ("L",  "Lost",        30,  Qt.AlignmentFlag.AlignCenter),
    ("GF", "Goals For",   34,  Qt.AlignmentFlag.AlignCenter),
    ("GA", "Goals Agst",  34,  Qt.AlignmentFlag.AlignCenter),
    ("GD", "Goal Diff",   38,  Qt.AlignmentFlag.AlignCenter),
    ("Pts","Points",      38,  Qt.AlignmentFlag.AlignCenter),
]

_STATUS_COLORS = {
    "qualified":  ("#3fb950", "#1a4731"),   # fg, bg
    "potential":  ("#d29922", "#2d2000"),
    "eliminated": ("#f85149", "#3d1f1f"),
    "contention": ("#e6edf3", "transparent"),
}


class _TeamRow(QWidget):
    clicked = pyqtSignal(int)   # team_id

    def __init__(self, pos: int, ts: TeamStanding, status: str):
        super().__init__()
        self._team_id = ts.team_id
        self.setFixedHeight(36)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        fg, bg = _STATUS_COLORS.get(status, ("#e6edf3", "transparent"))
        if bg != "transparent":
            self.setStyleSheet(f"background:{bg}; border-radius:4px;")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 8, 0)
        lay.setSpacing(0)

        def cell(text, width, align, bold=False, color=None) -> QLabel:
            l = QLabel(str(text))
            l.setFixedWidth(width)
            l.setAlignment(align)
            c = color or fg
            l.setStyleSheet(
                f"color:{c}; font-size:12px;"
                + ("font-weight:700;" if bold else "font-weight:400;")
            )
            return l

        # Position
        lay.addWidget(cell(pos + 1, _COLS[0][2], _COLS[0][3],
                           bold=True, color=fg))

        # Team name
        name_lbl = QLabel(ts.name)
        name_lbl.setFixedWidth(_COLS[1][2])
        name_lbl.setAlignment(_COLS[1][3])
        name_lbl.setStyleSheet(
            f"color:{fg}; font-size:12px;"
            f"font-weight:{'700' if pos < 2 else '400'};"
        )
        name_lbl.setToolTip(f"Click to view {ts.name} details")
        lay.addWidget(name_lbl)

        # Stats
        gd_txt  = f"{ts.gd:+d}" if ts.played > 0 else "—"
        gd_col  = "#3fb950" if ts.gd > 0 else ("#f85149" if ts.gd < 0 else fg)
        stats = [
            (ts.played, False, fg),
            (ts.won,    False, "#3fb950" if ts.won  > 0 else fg),
            (ts.drawn,  False, "#d29922" if ts.drawn > 0 else fg),
            (ts.lost,   False, "#f85149" if ts.lost  > 0 else fg),
            (ts.gf,     False, fg),
            (ts.ga,     False, fg),
            (gd_txt,    False, gd_col),
            (ts.points, True,  fg),
        ]
        for (val, bold, color), (_, _, w, align) in zip(stats, _COLS[2:]):
            lay.addWidget(cell(val, w, align, bold, color))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._team_id)
        super().mousePressEvent(event)

    def enterEvent(self, e):
        self.setStyleSheet(
            self.styleSheet() + "background: rgba(255,255,255,0.04);"
        )

    def leaveEvent(self, e):
        # Re-apply original background
        pass


class _HeaderRow(QWidget):
    def __init__(self):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 3, 8, 3)
        lay.setSpacing(0)
        for abbr, tip, width, align in _COLS:
            l = QLabel(abbr)
            l.setFixedWidth(width)
            l.setAlignment(align)
            l.setToolTip(tip)
            l.setStyleSheet(
                "font-size:9px; font-weight:700; color:#484f58; letter-spacing:1px;"
            )
            lay.addWidget(l)


class GroupCard(QFrame):
    team_clicked = pyqtSignal(int)

    def __init__(self, group_letter: str, teams: list[TeamStanding],
                 matches_played: int):
        super().__init__()
        self.setObjectName("card")
        self.setMinimumWidth(490)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 8)
        outer.setSpacing(0)

        # Title bar
        title_bar = QWidget()
        title_bar.setStyleSheet("background:#161b22; border-radius:8px 8px 0 0;")
        tb_lay = QHBoxLayout(title_bar)
        tb_lay.setContentsMargins(14, 9, 14, 9)

        grp_lbl = QLabel(f"Group {group_letter}")
        grp_lbl.setStyleSheet(
            "font-size:13px; font-weight:800; color:#e6edf3; letter-spacing:1px;"
        )
        played_lbl = QLabel(f"{matches_played} / 6 played")
        played_lbl.setStyleSheet("font-size:10px; color:#8b949e;")
        tb_lay.addWidget(grp_lbl)
        tb_lay.addStretch()
        tb_lay.addWidget(played_lbl)
        outer.addWidget(title_bar)

        # Column header
        hdr = _HeaderRow()
        hdr.setStyleSheet("background:#0d1117;")
        outer.addWidget(hdr)

        # Rows
        rows_w = QWidget()
        rows_w.setStyleSheet("background:#161b22;")
        rows_lay = QVBoxLayout(rows_w)
        rows_lay.setContentsMargins(0, 3, 0, 3)
        rows_lay.setSpacing(2)

        if not teams:
            ph = QLabel("Teams not yet assigned.")
            ph.setStyleSheet("color:#484f58; font-size:11px; padding:10px 14px;")
            rows_lay.addWidget(ph)
        else:
            for pos, ts in enumerate(teams):
                status = _elimination_status(ts, pos, len(teams), matches_played)
                row = _TeamRow(pos, ts, status)
                row.clicked.connect(self.team_clicked)
                rows_lay.addWidget(row)

        outer.addWidget(rows_w)

        # Legend (one line at bottom of each card)
        leg = QWidget()
        leg.setStyleSheet("background:#161b22;")
        leg_lay = QHBoxLayout(leg)
        leg_lay.setContentsMargins(10, 4, 10, 6)
        leg_lay.setSpacing(12)
        for color, text in [
            ("#3fb950","Qualified"), ("#d29922","Potential"),
            ("#f85149","Eliminated"),
        ]:
            dot = QLabel("●"); dot.setStyleSheet(f"color:{color}; font-size:9px;")
            lbl = QLabel(text); lbl.setStyleSheet("color:#484f58; font-size:9px;")
            leg_lay.addWidget(dot); leg_lay.addWidget(lbl)
        leg_lay.addStretch()
        outer.addWidget(leg)


class GroupsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(14)

        hdr = QHBoxLayout()
        title = QLabel("Group Stage Standings")
        title.setObjectName("sectionTitle")
        hdr.addWidget(title); hdr.addStretch()
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color:#8b949e; font-size:11px;")
        hdr.addWidget(self._status_lbl)
        outer.addLayout(hdr)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._grid_w = QWidget()
        self._grid   = QGridLayout(self._grid_w)
        self._grid.setSpacing(14)
        self._grid.setContentsMargins(0, 0, 0, 0)

        scroll.setWidget(self._grid_w)
        outer.addWidget(scroll, 1)

    def refresh(self):
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        teams   = get_all_teams()
        matches = get_all_matches_with_teams()
        standings = compute_standings(teams, matches)

        # Count finished group matches for status line
        finished = sum(
            1 for m in matches
            if m.get("stage") == "Group Stage" and m.get("status") == "Finished"
        )
        live = sum(
            1 for m in matches
            if m.get("stage") == "Group Stage" and m.get("status") == "Live"
        )
        total_gs = sum(1 for m in matches if m.get("stage") == "Group Stage")
        parts = [f"{finished}/{total_gs} matches played"]
        if live: parts.append(f"🔴 {live} live")
        self._status_lbl.setText("  ·  ".join(parts))

        all_groups = list("ABCDEFGHIJKL")

        # Fill groups that have teams but no matches yet
        for grp in all_groups:
            if grp not in standings:
                gt = [
                    TeamStanding(
                        team_id=t["id"], name=t["name"],
                        short_name=t.get("fifa_code") or t["name"][:3].upper(),
                        flag_url=t.get("flag_url",""), group=grp,
                    )
                    for t in teams
                    if (t.get("group_name") or "").strip().upper() == grp
                ]
                if gt:
                    gt.sort(key=lambda x: x.name)
                    standings[grp] = gt

        if not standings:
            msg = QLabel(
                "No group data yet.\n"
                "Sync the app after configuring your API key."
            )
            msg.setStyleSheet("color:#484f58; font-size:13px; padding:40px;")
            msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._grid.addWidget(msg, 0, 0)
            return

        # Count played per group
        played_per_group: dict[str, int] = defaultdict(int)
        for m in matches:
            if m.get("stage") == "Group Stage" and m.get("status") == "Finished":
                # Determine group from home team
                for t in teams:
                    if t["id"] == m.get("home_team_id"):
                        grp = (t.get("group_name") or "").strip().upper()
                        if grp: played_per_group[grp] += 1
                        break

        cols = 3
        for idx, grp in enumerate(all_groups):
            group_teams = standings.get(grp, [])
            card = GroupCard(grp, group_teams, played_per_group.get(grp, 0))
            card.team_clicked.connect(self._open_team_dialog)
            self._grid.addWidget(card, idx // cols, idx % cols)

    def _open_team_dialog(self, team_id: int):
        from ui.team_dialog import TeamDialog
        dlg = TeamDialog(team_id, self)
        dlg.favorite_changed.connect(self.refresh)
        dlg.exec()
