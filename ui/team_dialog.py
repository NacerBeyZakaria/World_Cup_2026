"""
Team Details Dialog.

Opens when the user clicks a team name in the Groups page.
Shows: team profile, current group position, stats, full fixture list.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QScrollArea, QWidget
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from database.database import (
    get_team_by_id, get_matches_for_team, get_favorite_team_ids,
    add_favorite_team, remove_favorite_team, get_all_teams,
    get_all_matches_with_teams
)
from ui.tz_utils import format_kickoff


def _compute_team_standing(team_id: int) -> dict:
    """Compute W/D/L/GF/GA/Pts for a single team from finished group matches."""
    from database.database import get_all_matches_with_teams
    matches = get_all_matches_with_teams()
    s = dict(played=0, won=0, drawn=0, lost=0, gf=0, ga=0)
    for m in matches:
        if m.get("stage") != "Group Stage" or m.get("status") != "Finished":
            continue
        hs, as_ = m.get("home_score"), m.get("away_score")
        if hs is None or as_ is None:
            continue
        is_home = m.get("home_team_id") == team_id
        is_away = m.get("away_team_id") == team_id
        if not is_home and not is_away:
            continue
        s["played"] += 1
        if is_home:
            s["gf"] += hs; s["ga"] += as_
            if hs > as_: s["won"] += 1
            elif hs == as_: s["drawn"] += 1
            else: s["lost"] += 1
        else:
            s["gf"] += as_; s["ga"] += hs
            if as_ > hs: s["won"] += 1
            elif as_ == hs: s["drawn"] += 1
            else: s["lost"] += 1
    s["pts"] = s["won"] * 3 + s["drawn"]
    s["gd"]  = s["gf"] - s["ga"]
    return s


def _group_position(team_id: int, group: str) -> int:
    """Return 1-based group position (1 = top). 0 if unknown."""
    from ui.groups_page import compute_standings
    teams   = get_all_teams()
    matches = get_all_matches_with_teams()
    standings = compute_standings(teams, matches)
    grp_list = standings.get(group.upper(), [])
    for i, ts in enumerate(grp_list):
        if ts.team_id == team_id:
            return i + 1
    return 0


def _sep() -> QFrame:
    f = QFrame(); f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet("color:#21262d;"); return f


class TeamDialog(QDialog):
    favorite_changed = pyqtSignal()

    def __init__(self, team_id: int, parent=None):
        super().__init__(parent)
        self._team_id = team_id
        self.setWindowTitle("Team Details")
        self.setMinimumWidth(500)
        self.setMinimumHeight(540)
        self.setModal(True)
        self.setStyleSheet("QDialog{background:#0d1117;color:#e6edf3;} QLabel{color:#e6edf3;}")
        team = get_team_by_id(team_id)
        if team:
            self._build(team)
        else:
            QVBoxLayout(self).addWidget(QLabel("Team not found."))

    def _build(self, team: dict):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)

        # ── Header: name + favourite star ─────────────────────────────────
        hdr = QHBoxLayout()
        name_lbl = QLabel(team["name"])
        name_lbl.setStyleSheet("font-size:20px; font-weight:800;")
        hdr.addWidget(name_lbl, 1)

        self._fav_btn = QPushButton()
        self._fav_btn.setFixedSize(36, 36)
        self._fav_btn.setStyleSheet(
            "border:1px solid #30363d; border-radius:6px; background:#21262d;"
            "font-size:16px;"
        )
        self._fav_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._fav_btn.clicked.connect(self._toggle_favorite)
        hdr.addWidget(self._fav_btn)
        self._refresh_fav_btn()
        outer.addLayout(hdr)

        # ── Meta badges ────────────────────────────────────────────────────
        meta = QHBoxLayout()
        meta.setSpacing(8)
        group = team.get("group_name", "")
        if group:
            gb = QLabel(f"Group {group}")
            gb.setStyleSheet(
                "background:#1f2937; color:#58a6ff; padding:3px 10px;"
                "border-radius:4px; font-size:11px; font-weight:600;"
            )
            meta.addWidget(gb)

        code = team.get("fifa_code", "")
        if code:
            cb = QLabel(code)
            cb.setStyleSheet(
                "background:#21262d; color:#8b949e; padding:3px 10px;"
                "border-radius:4px; font-size:11px; font-weight:700;"
            )
            meta.addWidget(cb)
        meta.addStretch()
        outer.addLayout(meta)

        outer.addWidget(_sep())

        # ── Standing stats ─────────────────────────────────────────────────
        s = _compute_team_standing(self._team_id)
        pos = _group_position(self._team_id, group) if group else 0

        stats_frame = QFrame()
        stats_frame.setStyleSheet(
            "background:#161b22; border-radius:8px; border:1px solid #21262d;"
        )
        sf_lay = QHBoxLayout(stats_frame)
        sf_lay.setContentsMargins(16, 14, 16, 14)
        sf_lay.setSpacing(0)

        def stat_block(val, lbl, color="#e6edf3"):
            col = QVBoxLayout()
            col.setSpacing(2)
            v = QLabel(str(val))
            v.setAlignment(Qt.AlignmentFlag.AlignCenter)
            v.setStyleSheet(f"font-size:22px; font-weight:800; color:{color};")
            l = QLabel(lbl)
            l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            l.setStyleSheet("font-size:10px; color:#8b949e; letter-spacing:1px;")
            col.addWidget(v); col.addWidget(l)
            return col

        def vdiv():
            d = QFrame(); d.setFrameShape(QFrame.Shape.VLine)
            d.setStyleSheet("color:#21262d;"); d.setFixedWidth(1)
            return d

        pos_color = "#3fb950" if pos in (1, 2) else ("#d29922" if pos == 3 else "#e6edf3")
        for block, div in [
            (stat_block(f"#{pos}" if pos else "—", "POSITION", pos_color), True),
            (stat_block(s["played"], "PLAYED"), True),
            (stat_block(s["won"],    "WON",    "#3fb950"), True),
            (stat_block(s["drawn"],  "DRAWN",  "#d29922"), True),
            (stat_block(s["lost"],   "LOST",   "#f85149"), True),
            (stat_block(f"{s['gd']:+d}" if s["played"] else "—", "GD",
                        "#3fb950" if s["gd"] > 0 else ("#f85149" if s["gd"] < 0 else "#e6edf3")), True),
            (stat_block(s["pts"],    "PTS",    "#e6edf3"), False),
        ]:
            sf_lay.addLayout(block, 1)
            if div:
                sf_lay.addWidget(vdiv())

        outer.addWidget(stats_frame)
        outer.addWidget(_sep())

        # ── Fixtures list (scrollable) ─────────────────────────────────────
        fix_title = QLabel("Fixtures & Results")
        fix_title.setStyleSheet("font-size:13px; font-weight:700;")
        outer.addWidget(fix_title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setMaximumHeight(260)

        inner = QWidget()
        inner_lay = QVBoxLayout(inner)
        inner_lay.setContentsMargins(0, 0, 0, 0)
        inner_lay.setSpacing(4)

        matches = get_matches_for_team(self._team_id)
        if not matches:
            inner_lay.addWidget(QLabel("No fixtures found."))
        for m in matches:
            inner_lay.addWidget(self._fixture_row(m, self._team_id))
        inner_lay.addStretch()

        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

        # ── Close ──────────────────────────────────────────────────────────
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(
            "background:#21262d; color:#e6edf3; border:1px solid #30363d;"
            "border-radius:6px; padding:8px 24px; font-size:13px; font-weight:600;"
        )
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        outer.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignRight)

    def _fixture_row(self, m: dict, team_id: int) -> QFrame:
        row = QFrame()
        row.setStyleSheet(
            "background:#161b22; border-radius:6px; border:1px solid #21262d;"
        )
        lay = QHBoxLayout(row)
        lay.setContentsMargins(10, 7, 10, 7)
        lay.setSpacing(10)

        # Date + time
        kick = format_kickoff(m.get("match_date", ""), m.get("match_time", ""))
        date_lbl = QLabel(f"{m.get('match_date', '')}  {kick}")
        date_lbl.setStyleSheet("color:#8b949e; font-size:10px; min-width:100px;")
        lay.addWidget(date_lbl)

        # Teams + score
        hs, as_ = m.get("home_score"), m.get("away_score")
        is_home = m.get("home_team_id") == team_id
        opp = m.get("away_team_name" if is_home else "home_team_name", "TBD")
        home_str = m.get("home_team_name", "TBD")
        away_str = m.get("away_team_name", "TBD")
        match_str = f"{home_str}  vs  {away_str}"
        match_lbl = QLabel(match_str)
        match_lbl.setStyleSheet("font-size:11px; font-weight:600;")
        lay.addWidget(match_lbl, 1)

        # Score / result indicator
        if hs is not None and as_ is not None:
            sc_lbl = QLabel(f"{hs} – {as_}")
            # Determine W/D/L from this team's perspective
            team_score = hs if is_home else as_
            opp_score  = as_ if is_home else hs
            if team_score > opp_score:
                result_color = "#3fb950"
            elif team_score == opp_score:
                result_color = "#d29922"
            else:
                result_color = "#f85149"
            sc_lbl.setStyleSheet(f"font-size:12px; font-weight:700; color:{result_color};")
        else:
            sc_lbl = QLabel("–")
            sc_lbl.setStyleSheet("color:#484f58; font-size:12px;")
        lay.addWidget(sc_lbl)

        # Status badge
        status = m.get("status", "")
        if status == "Live":
            sb = QLabel("LIVE")
            sb.setStyleSheet(
                "background:#da3633; color:white; padding:1px 5px;"
                "border-radius:3px; font-size:9px; font-weight:700;"
            )
            lay.addWidget(sb)

        return row

    def _refresh_fav_btn(self):
        is_fav = self._team_id in get_favorite_team_ids()
        self._fav_btn.setText("⭐" if is_fav else "☆")
        self._fav_btn.setToolTip(
            "Remove from favourites" if is_fav else "Add to favourites"
        )

    def _toggle_favorite(self):
        if self._team_id in get_favorite_team_ids():
            remove_favorite_team(self._team_id)
        else:
            add_favorite_team(self._team_id)
        self._refresh_fav_btn()
        self.favorite_changed.emit()
