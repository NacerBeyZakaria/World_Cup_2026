"""
Dashboard — the central overview page.

Sections:
  1. Stat cards row  (total, watched, missed, planned, favourite, completion%)
  2. Tournament progress bar  (matches completed / 104)
  3. Favourite teams panel  (next match, last result, group position)
  4. Next match countdown  (auto-ticks every minute)
  5. Today's matches  (scrollable, sorted by kickoff)
  6. Watch progress bars  (watched / missed / planned relative to total)
"""

from datetime import datetime, timezone, timedelta

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QPushButton, QGridLayout, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont

from database.database import (
    get_watch_statistics, get_all_matches_with_teams, get_last_sync,
    get_favorite_teams, get_next_favorite_match, get_last_favorite_result,
    get_next_match, get_todays_matches, get_all_teams,
    get_watch_statistics,
)
from ui.tz_utils import format_kickoff, convert_match_time


# ── Reusable helpers ───────────────────────────────────────────────────────────

def _section(title: str) -> QLabel:
    lbl = QLabel(title)
    lbl.setStyleSheet(
        "font-size:13px; font-weight:700; color:#e6edf3; margin-top:4px;"
    )
    return lbl


def _sep() -> QFrame:
    f = QFrame(); f.setFixedHeight(1)
    f.setStyleSheet("background:#21262d;")
    return f


class _ProgressBar(QWidget):
    def __init__(self, label: str, value: int, maximum: int, color: str):
        super().__init__()
        self._value = value
        self._max   = maximum

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        row = QHBoxLayout()
        l = QLabel(label); l.setStyleSheet("font-size:11px; color:#8b949e; font-weight:600;")
        p = QLabel(f"{value}  ({int(value/maximum*100) if maximum else 0}%)")
        p.setStyleSheet("font-size:11px; color:#8b949e;")
        row.addWidget(l); row.addStretch(); row.addWidget(p)
        lay.addLayout(row)

        track = QFrame(); track.setFixedHeight(7)
        track.setStyleSheet("background:#21262d; border-radius:3px;")
        lay.addWidget(track)

        self._fill = QFrame(track); self._fill.setFixedHeight(7)
        self._fill.setStyleSheet(f"background:{color}; border-radius:3px;")
        self._color = color; self._track = track
        self._pct = (value / maximum) if maximum else 0

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fill.setFixedWidth(max(7, int(self._track.width() * self._pct)))


# ── Stat card ──────────────────────────────────────────────────────────────────

class StatCard(QFrame):
    def __init__(self, number: str, label: str, color: str = "#e6edf3",
                 icon: str = ""):
        super().__init__()
        self.setObjectName("card")
        self.setMinimumHeight(100)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(4)

        if icon:
            icon_lbl = QLabel(icon)
            icon_lbl.setStyleSheet("font-size:18px;")
            lay.addWidget(icon_lbl)

        self._num = QLabel(number)
        self._num.setStyleSheet(
            f"font-size:30px; font-weight:800; color:{color};"
        )
        lay.addWidget(self._num)

        lbl = QLabel(label)
        lbl.setStyleSheet("font-size:10px; color:#8b949e; letter-spacing:1px;")
        lay.addWidget(lbl)
        lay.addStretch()

    def set_value(self, v: str): self._num.setText(v)


# ── Countdown widget ───────────────────────────────────────────────────────────

class CountdownWidget(QFrame):
    """Shows 'Next match in Xh Ym' and ticks every minute."""

    def __init__(self):
        super().__init__()
        self.setObjectName("card")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(6)

        header = QHBoxLayout()
        h = QLabel("⏱  Next Match")
        h.setStyleSheet("font-size:11px; font-weight:700; color:#8b949e; letter-spacing:1px;")
        header.addWidget(h)
        header.addStretch()
        lay.addLayout(header)

        self._teams_lbl = QLabel("—")
        self._teams_lbl.setStyleSheet("font-size:14px; font-weight:700; color:#e6edf3;")
        lay.addWidget(self._teams_lbl)

        self._time_lbl = QLabel("")
        self._time_lbl.setStyleSheet("font-size:11px; color:#8b949e;")
        lay.addWidget(self._time_lbl)

        self._countdown_lbl = QLabel("")
        self._countdown_lbl.setStyleSheet(
            "font-size:20px; font-weight:800; color:#3fb950;"
        )
        lay.addWidget(self._countdown_lbl)

        self._match = None

        # Tick every 60 s
        self._timer = QTimer(self)
        self._timer.setInterval(60_000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def load(self, match: dict | None):
        self._match = match
        self._tick()

    def _tick(self):
        if not self._match:
            self._teams_lbl.setText("No upcoming matches")
            self._time_lbl.setText("")
            self._countdown_lbl.setText("")
            return

        home = self._match.get("home_team_name", "TBD")
        away = self._match.get("away_team_name", "TBD")
        self._teams_lbl.setText(f"{home}  vs  {away}")

        kick = format_kickoff(
            self._match.get("match_date", ""),
            self._match.get("match_time", "")
        )
        stage = self._match.get("stage", "")
        self._time_lbl.setText(f"{kick}  ·  {stage}")

        # Countdown
        try:
            dt_str = (
                f"{self._match['match_date']} {self._match['match_time']}"
            )
            match_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M").replace(
                tzinfo=timezone.utc
            )
            now = datetime.now(timezone.utc)
            diff = match_dt - now
            if diff.total_seconds() < 0:
                self._countdown_lbl.setText("In progress" if self._match.get("status") == "Live" else "Started")
                return
            total_min = int(diff.total_seconds() // 60)
            h, m = divmod(total_min, 60)
            if h > 0:
                self._countdown_lbl.setText(f"Starts in  {h}h {m}m")
            else:
                self._countdown_lbl.setText(f"Starts in  {m}m")
        except Exception:
            self._countdown_lbl.setText("")


# ── Favourite team panel ───────────────────────────────────────────────────────

class FavouritePanel(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("card")
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(18, 14, 18, 14)
        self._lay.setSpacing(8)

    def load(self, favs: list[dict], next_match, last_result):
        while self._lay.count():
            item = self._lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        h = QLabel("⭐  Favourite Teams")
        h.setStyleSheet(
            "font-size:11px; font-weight:700; color:#8b949e; letter-spacing:1px;"
        )
        self._lay.addWidget(h)

        if not favs:
            lbl = QLabel("No favourite teams selected.\nGo to Settings to add favourites.")
            lbl.setStyleSheet("color:#484f58; font-size:12px;")
            lbl.setWordWrap(True)
            self._lay.addWidget(lbl)
            return

        # Team names row
        names = QLabel("  ·  ".join(t["name"] for t in favs))
        names.setStyleSheet("font-size:13px; font-weight:700; color:#e6edf3;")
        names.setWordWrap(True)
        self._lay.addWidget(names)

        self._lay.addWidget(_sep())

        # Next match
        nm_hdr = QLabel("NEXT MATCH")
        nm_hdr.setStyleSheet("font-size:10px; color:#8b949e; letter-spacing:1px;")
        self._lay.addWidget(nm_hdr)

        if next_match:
            kick = format_kickoff(
                next_match.get("match_date", ""),
                next_match.get("match_time", "")
            )
            nm_lbl = QLabel(
                f"{next_match.get('home_team_name','?')}  vs  "
                f"{next_match.get('away_team_name','?')}"
                f"  ·  {kick}  ·  {next_match.get('stage','')}"
            )
            nm_lbl.setStyleSheet("font-size:12px; font-weight:600; color:#58a6ff;")
            nm_lbl.setWordWrap(True)
        else:
            nm_lbl = QLabel("No upcoming matches")
            nm_lbl.setStyleSheet("font-size:12px; color:#484f58;")
        self._lay.addWidget(nm_lbl)

        # Last result
        lr_hdr = QLabel("LAST RESULT")
        lr_hdr.setStyleSheet(
            "font-size:10px; color:#8b949e; letter-spacing:1px; margin-top:4px;"
        )
        self._lay.addWidget(lr_hdr)

        if last_result:
            hs  = last_result.get("home_score")
            as_ = last_result.get("away_score")
            sc  = f"{hs} – {as_}" if hs is not None else "—"
            lr_lbl = QLabel(
                f"{last_result.get('home_team_name','?')}  {sc}  "
                f"{last_result.get('away_team_name','?')}"
            )
            lr_lbl.setStyleSheet("font-size:12px; font-weight:600; color:#d29922;")
        else:
            lr_lbl = QLabel("No results yet")
            lr_lbl.setStyleSheet("font-size:12px; color:#484f58;")
        self._lay.addWidget(lr_lbl)
        self._lay.addStretch()


# ── Today's match mini-card ────────────────────────────────────────────────────

class TodayMatchCard(QFrame):
    def __init__(self, match: dict):
        super().__init__()
        self.setObjectName("matchCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._match_id = match["id"]

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(10)

        # Time
        kick = format_kickoff(match.get("match_date",""), match.get("match_time",""))
        tl = QLabel(kick)
        tl.setStyleSheet("color:#8b949e; font-size:11px; min-width:70px;")
        lay.addWidget(tl)

        # Teams
        tms = QLabel(
            f"{match.get('home_team_name','?')}  vs  {match.get('away_team_name','?')}"
        )
        tms.setStyleSheet("font-weight:600; font-size:12px;")
        lay.addWidget(tms, 1)

        # Score / vs
        hs, as_ = match.get("home_score"), match.get("away_score")
        if hs is not None and as_ is not None:
            sc = QLabel(f"{hs}  –  {as_}")
            sc.setStyleSheet("font-weight:700; color:#d29922; font-size:12px;")
        else:
            sc = QLabel("—")
            sc.setStyleSheet("color:#484f58; font-size:12px;")
        lay.addWidget(sc)

        # Status badge
        status = match.get("status", "Scheduled")
        if status == "Live":
            sb = QLabel("🔴 LIVE")
            sb.setStyleSheet(
                "background:#da3633; color:white; padding:2px 6px;"
                "border-radius:3px; font-size:9px; font-weight:700;"
            )
        elif status == "Finished":
            sb = QLabel("FT")
            sb.setStyleSheet(
                "background:#21262d; color:#8b949e; padding:2px 6px;"
                "border-radius:3px; font-size:9px;"
            )
        else:
            sb = QLabel("Soon")
            sb.setStyleSheet(
                "background:#1c2f4a; color:#58a6ff; padding:2px 6px;"
                "border-radius:3px; font-size:9px;"
            )
        lay.addWidget(sb)

        stage_lbl = QLabel(match.get("stage",""))
        stage_lbl.setObjectName("stageBadge")
        lay.addWidget(stage_lbl)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            from ui.match_dialog import MatchDialog
            dlg = MatchDialog(self._match_id, self)
            dlg.exec()
        super().mousePressEvent(event)


# ── Main dashboard ─────────────────────────────────────────────────────────────

class DashboardPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        # Outer scroll so it works at any height
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(20)

        # ── Header ─────────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        title = QLabel("Dashboard")
        title.setObjectName("sectionTitle")
        self._sync_lbl = QLabel("Never synced")
        self._sync_lbl.setStyleSheet("color:#8b949e; font-size:11px;")
        hdr.addWidget(title); hdr.addStretch(); hdr.addWidget(self._sync_lbl)
        lay.addLayout(hdr)

        # ── Stat cards (2 rows × 3) ────────────────────────────────────────
        grid = QGridLayout(); grid.setSpacing(12)
        self._c_total   = StatCard("—", "TOTAL MATCHES",    "#e6edf3", "🏆")
        self._c_watched = StatCard("—", "WATCHED",          "#3fb950", "✅")
        self._c_missed  = StatCard("—", "MISSED",           "#f85149", "❌")
        self._c_planned = StatCard("—", "PLANNED",          "#58a6ff", "📌")
        self._c_fav     = StatCard("—", "FAVOURITED",       "#d29922", "⭐")
        self._c_pct     = StatCard("—%","WATCH COMPLETION", "#d29922", "📊")

        for col, card in enumerate([
            self._c_total, self._c_watched, self._c_missed
        ]):
            grid.addWidget(card, 0, col)
        for col, card in enumerate([
            self._c_planned, self._c_fav, self._c_pct
        ]):
            grid.addWidget(card, 1, col)
        lay.addLayout(grid)

        # ── Tournament progress ────────────────────────────────────────────
        lay.addWidget(_section("Tournament Progress"))
        prog_card = QFrame(); prog_card.setObjectName("card")
        pc_lay = QVBoxLayout(prog_card); pc_lay.setContentsMargins(18,14,18,14)
        pc_lay.setSpacing(8)

        self._prog_label = QLabel("0 / 104 matches completed  ·  0%")
        self._prog_label.setStyleSheet("font-size:13px; font-weight:600;")
        pc_lay.addWidget(self._prog_label)

        prog_track = QFrame(); prog_track.setFixedHeight(10)
        prog_track.setStyleSheet("background:#21262d; border-radius:5px;")
        pc_lay.addWidget(prog_track)

        self._prog_fill = QFrame(prog_track); self._prog_fill.setFixedHeight(10)
        self._prog_fill.setStyleSheet("background:#3fb950; border-radius:5px;")
        self._prog_track = prog_track
        lay.addWidget(prog_card)

        # ── Middle row: Countdown + Favourites ────────────────────────────
        mid = QHBoxLayout(); mid.setSpacing(12)
        self._countdown = CountdownWidget()
        self._countdown.setMinimumHeight(120)
        mid.addWidget(self._countdown, 1)

        self._fav_panel = FavouritePanel()
        self._fav_panel.setMinimumHeight(120)
        mid.addWidget(self._fav_panel, 2)
        lay.addLayout(mid)

        # ── Today's matches ────────────────────────────────────────────────
        today_hdr = QHBoxLayout()
        today_hdr.addWidget(_section("Today's Matches"))
        self._today_count = QLabel("")
        self._today_count.setStyleSheet("color:#8b949e; font-size:11px;")
        today_hdr.addStretch(); today_hdr.addWidget(self._today_count)
        lay.addLayout(today_hdr)

        self._today_container = QWidget()
        self._today_lay = QVBoxLayout(self._today_container)
        self._today_lay.setContentsMargins(0,0,0,0)
        self._today_lay.setSpacing(6)
        lay.addWidget(self._today_container)

        # ── Watch progress bars ────────────────────────────────────────────
        lay.addWidget(_section("Watch Progress"))
        self._wprog_frame = QFrame(); self._wprog_frame.setObjectName("card")
        self._wprog_lay = QVBoxLayout(self._wprog_frame)
        self._wprog_lay.setContentsMargins(18,14,18,14)
        self._wprog_lay.setSpacing(10)
        lay.addWidget(self._wprog_frame)

        lay.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll)

    # ── Refresh ────────────────────────────────────────────────────────────

    def refresh(self):
        stats   = get_watch_statistics()
        total   = stats.get("total",    0) or 0
        watched = stats.get("watched",  0) or 0
        missed  = stats.get("missed",   0) or 0
        planned = stats.get("planned",  0) or 0
        fav_cnt = stats.get("favorite", 0) or 0
        finished= stats.get("finished", 0) or 0
        pct     = int(watched / total * 100) if total else 0

        self._c_total.set_value(str(total))
        self._c_watched.set_value(str(watched))
        self._c_missed.set_value(str(missed))
        self._c_planned.set_value(str(planned))
        self._c_fav.set_value(str(fav_cnt))
        self._c_pct.set_value(f"{pct}%")

        # Tournament progress bar
        comp_pct = int(finished / total * 100) if total else 0
        self._prog_label.setText(
            f"{finished} / {total} matches completed  ·  {comp_pct}%"
        )
        # Resize fill after layout settles
        QTimer.singleShot(
            50, lambda: self._prog_fill.setFixedWidth(
                max(0, int(self._prog_track.width() * comp_pct / 100))
            )
        )

        # Countdown
        next_m = get_next_match()
        self._countdown.load(next_m)

        # Favourite panel
        favs       = get_favorite_teams()
        next_fav   = get_next_favorite_match()
        last_result= get_last_favorite_result()
        self._fav_panel.load(favs, next_fav, last_result)

        # Today's matches
        while self._today_lay.count():
            item = self._today_lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        today = get_todays_matches()
        if not today:
            no_lbl = QLabel("No matches scheduled today.")
            no_lbl.setStyleSheet("color:#484f58; font-size:12px; padding:8px 0;")
            self._today_lay.addWidget(no_lbl)
        else:
            for m in today:
                self._today_lay.addWidget(TodayMatchCard(m))
        self._today_count.setText(
            f"{len(today)} match{'es' if len(today) != 1 else ''}"
        )

        # Watch progress bars
        while self._wprog_lay.count():
            item = self._wprog_lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        for label, value, color in [
            ("Watched",  watched, "#3fb950"),
            ("Missed",   missed,  "#f85149"),
            ("Planned",  planned, "#58a6ff"),
        ]:
            self._wprog_lay.addWidget(
                _ProgressBar(label, value, total or 1, color)
            )

        # Sync label
        last = get_last_sync()
        if last:
            self._sync_lbl.setText(
                f"Last sync: {last['last_sync'][:16].replace('T',' ')} UTC"
                f"  ({last['source']})"
            )
