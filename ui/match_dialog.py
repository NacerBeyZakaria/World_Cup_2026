"""
Match Details Dialog.

Fixes in this version:
  1. VENUE   — read from DB (already stored during sync). Additionally, a
               lightweight _VenueWorker fetches GET /v4/matches/{id} (free tier)
               or GET /v3/fixtures?id={id} to get the venue even when events are
               not available (football-data.org free tier includes venue on the
               single-match endpoint even though it omits it from bulk fixtures).

  2. FLAGS   — FlagWidget downloads the crest/logo URL stored in home_flag /
               away_flag.  For football-data.org the URLs are SVGs behind
               X-Auth-Token; the widget adds that header automatically.
               For API-Football the URLs are public PNGs — fetched without auth.
               Fallback: a styled badge showing the FIFA 3-letter code.

  3. EVENTS  — football-data.org free tier: clear informational message
               (not an error) explaining the tier limitation.
               API-Football free tier: full event rendering via background worker.
"""

from __future__ import annotations
import logging

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QComboBox, QWidget, QScrollArea, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QObject, QUrl, QTimer
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PyQt6.QtSvgWidgets import QSvgWidget
from PyQt6.QtGui import QPixmap

from database.database import get_match_by_id, set_watch_status, get_setting
from ui.tz_utils import format_kickoff, convert_match_time

logger = logging.getLogger(__name__)

WATCH_OPTIONS = ["Not Set", "Watched", "Missed", "Planned", "Favorite"]

# One shared NAM per process — safe because we never use it across threads
_NAM: QNetworkAccessManager | None = None

def _get_nam() -> QNetworkAccessManager:
    global _NAM
    if _NAM is None:
        _NAM = QNetworkAccessManager()
    return _NAM


# ── Flag widget ────────────────────────────────────────────────────────────────

class FlagWidget(QWidget):
    """
    Renders a team crest/logo from a URL.

    football-data.org: SVG behind X-Auth-Token header
    API-Football:      PNG, publicly accessible CDN
    Fallback:          styled label showing the 3-letter FIFA code
    """
    SIZE = 48

    def __init__(self, url: str, code: str, provider: str = "", api_key: str = "",
                 parent=None):
        super().__init__(parent)
        self.setFixedSize(self.SIZE + 4, self.SIZE + 4)
        self._url      = (url or "").strip()
        self._code     = (code or "?").strip()
        self._provider = provider
        self._api_key  = api_key

        # SVG container (shown when SVG data loads)
        self._svg = QSvgWidget(self)
        self._svg.setFixedSize(self.SIZE, self.SIZE)
        self._svg.move(2, 2)
        self._svg.hide()

        # PNG pixmap label (shown when PNG data loads)
        self._img = QLabel(self)
        self._img.setFixedSize(self.SIZE, self.SIZE)
        self._img.move(2, 2)
        self._img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img.hide()

        # Fallback badge (shown until a real image loads, or on failure)
        self._fallback = QLabel(self._code, self)
        self._fallback.setFixedSize(self.SIZE, self.SIZE)
        self._fallback.move(2, 2)
        self._fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._fallback.setStyleSheet(
            "background:#1c2128; color:#8b949e; font-size:10px; font-weight:700;"
            "border-radius:5px; border:1px solid #30363d;"
        )
        self._fallback.show()

        if self._url:
            QTimer.singleShot(0, self._fetch)   # defer until event loop running

    def _fetch(self):
        req = QNetworkRequest(QUrl(self._url))
        req.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy
        )
        # football-data.org crests require the API token as auth header
        if self._provider == "football-data.org" and self._api_key:
            req.setRawHeader(b"X-Auth-Token", self._api_key.encode())
        req.setRawHeader(b"User-Agent", b"WC2026Tracker/1.0")
        reply = _get_nam().get(req)
        reply.finished.connect(lambda: self._on_reply(reply))

    def _on_reply(self, reply: QNetworkReply):
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                return  # keep fallback
            data = bytes(reply.readAll())
            if not data:
                return

            url_lower = self._url.lower()
            if ".svg" in url_lower or b"<svg" in data[:200]:
                self._svg.load(data if isinstance(data, bytes) else data.encode())
                self._svg.show()
                self._fallback.hide()
                self._img.hide()
            else:
                px = QPixmap()
                px.loadFromData(data)
                if not px.isNull():
                    self._img.setPixmap(
                        px.scaled(self.SIZE, self.SIZE,
                                  Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation)
                    )
                    self._img.show()
                    self._fallback.hide()
                    self._svg.hide()
        except Exception as exc:
            logger.debug("FlagWidget load error: %s", exc)
        finally:
            reply.deleteLater()


# ── Venue worker (lightweight — free tier safe) ────────────────────────────────

class _VenueWorker(QObject):
    """
    Fetches only the venue string from the single-match endpoint.
    football-data.org free tier includes venue on GET /v4/matches/{id}.
    Runs on a QThread; emits venue string (may be empty).
    """
    finished = pyqtSignal(str)

    def __init__(self, api_match_id: int, provider: str, api_key: str):
        super().__init__()
        self._id       = api_match_id
        self._provider = provider
        self._key      = api_key

    def run(self):
        venue = ""
        try:
            from services.api_service import get_service, APIError
            svc  = get_service(self._provider, self._key)
            data = svc._get(
                f"/matches/{self._id}"
                if self._provider == "football-data.org"
                else "fixtures",
                {} if self._provider == "football-data.org"
                else {"id": self._id}
            )
            if self._provider == "football-data.org":
                venue = (data.get("venue") or "").strip()
            else:
                resp = data.get("response") or []
                if resp:
                    venue = (
                        (resp[0].get("fixture") or {})
                        .get("venue", {})
                        .get("name", "")
                        or ""
                    ).strip()
        except Exception as exc:
            logger.debug("VenueWorker error: %s", exc)
        self.finished.emit(venue)


# ── Events worker ──────────────────────────────────────────────────────────────

class _EventsWorker(QObject):
    """
    Fetches full match events (goals, cards, subs, possession).
    Only used for API-Football — football-data.org free tier doesn't expose events.
    """
    finished = pyqtSignal(dict)

    def __init__(self, api_match_id: int, provider: str, api_key: str):
        super().__init__()
        self._id       = api_match_id
        self._provider = provider
        self._key      = api_key

    def run(self):
        empty = dict(goals=[], yellow_cards=[], red_cards=[],
                     substitutions=[], possession=None,
                     venue="", error=None)
        try:
            from services.api_service import get_service, APIError
            svc    = get_service(self._provider, self._key)
            events = svc.fetch_match_events(self._id)
            self.finished.emit(events)
        except Exception as exc:
            empty["error"] = str(exc)
            self.finished.emit(empty)


# ── Small UI helpers ───────────────────────────────────────────────────────────

def _hline() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet("color:#21262d; margin:2px 0;")
    return f


def _badge(text: str, fg: str, bg: str) -> QLabel:
    l = QLabel(text)
    l.setStyleSheet(
        f"color:{fg}; background:{bg}; padding:2px 8px;"
        "border-radius:4px; font-size:10px; font-weight:700;"
    )
    return l


def _info_row(icon: str, label: str, value: str) -> tuple:
    row = QHBoxLayout()
    l   = QLabel(f"{icon}  {label}")
    l.setStyleSheet("color:#8b949e; font-size:11px; min-width:75px;")
    v   = QLabel(value or "—")
    v.setStyleSheet("font-size:12px; font-weight:600;")
    v.setWordWrap(True)
    row.addWidget(l); row.addWidget(v, 1)
    return row, v


def _section_header(title: str) -> QLabel:
    l = QLabel(title)
    l.setStyleSheet(
        "font-size:11px; font-weight:700; color:#8b949e;"
        "letter-spacing:1px; padding-top:8px; padding-bottom:2px;"
    )
    return l


def _event_row(icon: str, minute, description: str, team: str = "") -> QWidget:
    w   = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 1, 0, 1)
    lay.setSpacing(8)

    il = QLabel(icon)
    il.setFixedWidth(24)
    il.setAlignment(Qt.AlignmentFlag.AlignCenter)
    il.setStyleSheet("font-size:14px;")
    lay.addWidget(il)

    if minute is not None:
        ml = QLabel(f"{minute}'")
        ml.setFixedWidth(34)
        ml.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        ml.setStyleSheet("font-size:11px; font-weight:700; color:#8b949e;")
        lay.addWidget(ml)

    dl = QLabel(description)
    dl.setStyleSheet("font-size:12px; color:#e6edf3;")
    dl.setWordWrap(True)
    lay.addWidget(dl, 1)

    if team:
        tl = QLabel(team)
        tl.setStyleSheet("font-size:10px; color:#484f58;")
        lay.addWidget(tl)

    return w


def _placeholder(text: str, is_info: bool = False) -> QLabel:
    """
    is_info=True  → neutral blue-ish tone (not an error, just informational)
    is_info=False → subtle gray (nothing to show)
    """
    l = QLabel(text)
    if is_info:
        l.setStyleSheet(
            "color:#58a6ff; background:#1c2f4a; border-radius:6px;"
            "font-size:11px; padding:10px 12px; border:1px solid #1f3a5f;"
        )
    else:
        l.setStyleSheet("color:#484f58; font-size:11px; padding:8px 0;")
    l.setWordWrap(True)
    return l


def _possession_bar(home_name: str, home_pct: int,
                    away_name: str, away_pct: int) -> QWidget:
    w   = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 4, 0, 4)
    lay.setSpacing(4)

    row = QHBoxLayout()
    hl  = QLabel(f"{home_name}  {home_pct}%")
    hl.setStyleSheet("font-size:11px; font-weight:600; color:#58a6ff;")
    al  = QLabel(f"{away_pct}%  {away_name}")
    al.setStyleSheet("font-size:11px; font-weight:600; color:#d29922;")
    al.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    row.addWidget(hl); row.addWidget(al)
    lay.addLayout(row)

    track = QFrame(); track.setFixedHeight(10)
    track.setStyleSheet("background:#21262d; border-radius:5px;")
    lay.addWidget(track)

    fill = QFrame(track); fill.setFixedHeight(10)
    fill.setStyleSheet("background:#58a6ff; border-radius:5px;")
    QTimer.singleShot(80, lambda: fill.setFixedWidth(
        max(8, int(track.width() * home_pct / 100))
    ))
    return w


# ── Main dialog ────────────────────────────────────────────────────────────────

class MatchDialog(QDialog):
    watch_status_changed = pyqtSignal(int, str)

    def __init__(self, match_id: int, parent=None):
        super().__init__(parent)
        self._match_id = match_id
        self.setWindowTitle("Match Details")
        self.setMinimumWidth(520)
        self.setMaximumWidth(600)
        self.setMinimumHeight(440)
        self.setModal(True)
        self.setStyleSheet(
            "QDialog{background:#0d1117; color:#e6edf3;}"
            "QLabel{color:#e6edf3;}"
            "QScrollBar:vertical{width:5px; background:#0d1117;}"
            "QScrollBar::handle:vertical{background:#30363d; border-radius:2px;}"
        )
        self._provider = get_setting("api_provider", "football-data.org")
        self._api_key  = get_setting("api_key", "")
        self._match    = get_match_by_id(match_id)

        if self._match:
            self._build()
        else:
            lbl = QLabel("Match not found.")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            QVBoxLayout(self).addWidget(lbl)

    # ── Build ──────────────────────────────────────────────────────────────

    def _build(self):
        m      = self._match
        status = m.get("status", "Scheduled")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 18, 22, 18)
        outer.setSpacing(10)
        self._outer = outer

        # ① Stage + status badges ─────────────────────────────────────────
        top = QHBoxLayout()
        top.addWidget(_badge(m.get("stage", ""), "#8b949e", "#21262d"))
        top.addStretch()
        if status == "Live":
            top.addWidget(_badge("🔴  LIVE",  "#ffffff", "#da3633"))
        elif status == "Finished":
            top.addWidget(_badge("Full Time", "#8b949e", "#21262d"))
        else:
            top.addWidget(_badge("Scheduled", "#58a6ff", "#1c2f4a"))
        outer.addLayout(top)

        # ② Score block with flags ────────────────────────────────────────
        score_frame = QFrame()
        score_frame.setStyleSheet(
            "background:#161b22; border-radius:10px; border:1px solid #21262d;"
        )
        sf = QHBoxLayout(score_frame)
        sf.setContentsMargins(16, 16, 16, 16)
        sf.setSpacing(10)

        AL = Qt.AlignmentFlag.AlignLeft  | Qt.AlignmentFlag.AlignVCenter
        AR = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        AC = Qt.AlignmentFlag.AlignCenter

        def team_col(name: str, code: str, flag_url: str,
                     name_align, flag_align) -> QVBoxLayout:
            col = QVBoxLayout()
            col.setSpacing(6)
            col.setAlignment(Qt.AlignmentFlag.AlignVCenter)

            # Flag row
            fl = QHBoxLayout()
            fl.setContentsMargins(0, 0, 0, 0)
            fw = FlagWidget(
                flag_url, code,
                provider=self._provider,
                api_key=self._api_key,
            )
            fl.addWidget(fw, 0, flag_align)
            col.addLayout(fl)

            # Name
            nl = QLabel(name or "TBD")
            nl.setAlignment(name_align)
            nl.setWordWrap(True)
            nl.setStyleSheet("font-size:14px; font-weight:700;")
            col.addWidget(nl)

            return col

        sf.addLayout(
            team_col(
                m.get("home_team_name", "TBD"),
                m.get("home_code", ""),
                m.get("home_flag", ""),
                AL, Qt.AlignmentFlag.AlignLeft,
            ), 2
        )

        # Score / vs
        hs, as_ = m.get("home_score"), m.get("away_score")
        sc_col  = QVBoxLayout()
        sc_col.setAlignment(AC)
        if hs is not None and as_ is not None:
            sc = QLabel(f"{hs}  –  {as_}")
            sc.setStyleSheet("font-size:30px; font-weight:800; color:#e6edf3;")
        else:
            sc = QLabel("vs")
            sc.setStyleSheet("font-size:20px; color:#484f58; font-weight:600;")
        sc.setAlignment(AC)
        sc_col.addWidget(sc)
        sf.addLayout(sc_col, 1)

        sf.addLayout(
            team_col(
                m.get("away_team_name", "TBD"),
                m.get("away_code", ""),
                m.get("away_flag", ""),
                AR, Qt.AlignmentFlag.AlignRight,
            ), 2
        )
        outer.addWidget(score_frame)

        # ③ Info rows ─────────────────────────────────────────────────────
        outer.addWidget(_hline())

        tz_str = (get_setting("timezone", "UTC") or "UTC").split(" ")[0]
        local_date, local_time = convert_match_time(
            m.get("match_date", ""), m.get("match_time", "")
        )
        try:
            from datetime import date as _d
            date_fmt = _d.fromisoformat(local_date).strftime("%A, %B %d, %Y")
        except Exception:
            date_fmt = local_date

        time_display = local_time + (f"  ({tz_str})" if tz_str != "UTC" else "")

        for row, _ in [
            _info_row("📅", "Date",    date_fmt),
            _info_row("🕐", "Kickoff", time_display),
        ]:
            outer.addLayout(row)

        # Venue — show DB value immediately; worker may enrich it
        venue_val  = (m.get("venue") or "").strip()
        city_val   = (m.get("city")  or "").strip()
        if venue_val and city_val:
            venue_text = f"{venue_val}  ·  {city_val}"
        elif venue_val:
            venue_text = venue_val
        elif city_val:
            venue_text = city_val
        else:
            venue_text = ""   # worker will try to fill this

        venue_row, self._venue_lbl = _info_row("🏟️", "Venue", venue_text or "—")
        outer.addLayout(venue_row)

        outer.addWidget(_hline())

        # ④ Events area ───────────────────────────────────────────────────
        self._events_scroll = QScrollArea()
        self._events_scroll.setWidgetResizable(True)
        self._events_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._events_scroll.setMaximumHeight(220)

        self._ev_container = QWidget()
        self._ev_lay = QVBoxLayout(self._ev_container)
        self._ev_lay.setContentsMargins(0, 0, 0, 0)
        self._ev_lay.setSpacing(2)
        self._events_scroll.setWidget(self._ev_container)
        outer.addWidget(self._events_scroll, 1)

        # ⑤ Watch status ──────────────────────────────────────────────────
        outer.addWidget(_hline())
        ws_row = QHBoxLayout()
        wl = QLabel("Watch Status")
        wl.setStyleSheet("color:#8b949e; font-size:11px; min-width:90px;")
        ws_row.addWidget(wl)

        self._ws_combo = QComboBox()
        self._ws_combo.addItems(WATCH_OPTIONS)
        cur_ws = m.get("user_watch_status", "Not Set")
        self._ws_combo.setCurrentIndex(
            WATCH_OPTIONS.index(cur_ws) if cur_ws in WATCH_OPTIONS else 0
        )
        self._ws_combo.setStyleSheet(
            "background:#21262d; border:1px solid #30363d; border-radius:5px;"
            "padding:4px 8px; color:#e6edf3; font-size:12px; min-width:130px;"
        )
        self._ws_combo.currentTextChanged.connect(self._on_ws_changed)
        ws_row.addWidget(self._ws_combo)
        ws_row.addStretch()
        outer.addLayout(ws_row)

        # Close
        outer.addSpacing(2)
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(
            "background:#21262d; color:#e6edf3; border:1px solid #30363d;"
            "border-radius:6px; padding:7px 22px; font-size:12px; font-weight:600;"
        )
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        outer.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignRight)

        # Kick off background work
        self._start_background_work(status, venue_text)

    # ── Background work orchestration ──────────────────────────────────────

    def _start_background_work(self, status: str, existing_venue: str):
        """
        Always fetch venue via lightweight worker (free tier safe).
        Fetch events only for API-Football on a Finished/Live match.
        Show correct messages for all other states.
        """
        api_match_id = self._match.get("api_match_id")

        # ── Venue worker ───────────────────────────────────────────────────
        # Run even if we already have a venue — the single-match endpoint may
        # return a richer or more accurate value than the bulk fixtures list.
        if self._api_key and api_match_id:
            self._v_thread = QThread()
            self._v_worker = _VenueWorker(api_match_id, self._provider, self._api_key)
            self._v_worker.moveToThread(self._v_thread)
            self._v_thread.started.connect(self._v_worker.run)
            self._v_worker.finished.connect(self._on_venue_ready)
            self._v_worker.finished.connect(self._v_thread.quit)
            self._v_thread.start()

        # ── Events area ────────────────────────────────────────────────────
        if not self._api_key:
            self._set_ev_placeholder(
                "ℹ️  Add an API key in Settings to see match events.",
                is_info=True,
            )
            return

        if status == "Scheduled":
            self._set_ev_placeholder(
                "🕐  Match has not started yet.\n"
                "Events will appear here once the match kicks off.",
                is_info=True,
            )
            return

        if self._provider == "football-data.org":
            # Tier limitation — informational, not an error
            self._set_ev_placeholder(
                "ℹ️  Detailed match events (goals, cards, substitutions)\n"
                "require a Tier 2 or higher plan on football-data.org.\n\n"
                "To see full events for free, switch to API-Football\n"
                "in Settings → API Configuration.",
                is_info=True,
            )
            return

        # API-Football with Finished/Live match — fetch full events
        if not api_match_id:
            self._set_ev_placeholder("No API match ID stored for this fixture.")
            return

        self._set_ev_placeholder("⏳  Loading match events…")
        self._e_thread = QThread()
        self._e_worker = _EventsWorker(api_match_id, self._provider, self._api_key)
        self._e_worker.moveToThread(self._e_thread)
        self._e_thread.started.connect(self._e_worker.run)
        self._e_worker.finished.connect(self._on_events_ready)
        self._e_worker.finished.connect(self._e_thread.quit)
        self._e_thread.start()

    # ── Slot: venue ────────────────────────────────────────────────────────

    def _on_venue_ready(self, venue: str):
        if not venue:
            return
        city = (self._match.get("city") or "").strip()
        if city and city not in venue:
            self._venue_lbl.setText(f"{venue}  ·  {city}")
        else:
            self._venue_lbl.setText(venue)

    # ── Slot: events ───────────────────────────────────────────────────────

    def _on_events_ready(self, events: dict):
        self._clear_ev()

        if events.get("error"):
            self._ev_lay.addWidget(
                _placeholder(f"Could not load events:\n{events['error']}")
            )
            return

        # Update venue if API returned a richer value
        api_venue = (events.get("venue") or "").strip()
        if api_venue:
            city = (self._match.get("city") or "").strip()
            self._venue_lbl.setText(
                f"{api_venue}  ·  {city}" if city and city not in api_venue
                else api_venue
            )

        home = self._match.get("home_team_name", "Home")
        away = self._match.get("away_team_name", "Away")
        has  = False

        # Goals
        goals = events.get("goals", [])
        if goals:
            has = True
            self._ev_lay.addWidget(_section_header("⚽  GOALS"))
            for g in sorted(goals, key=lambda x: x.get("minute") or 0):
                t     = g.get("type", "REGULAR")
                icon  = "⚽🅿" if t == "PENALTY" else ("⚽ OG" if t == "OWN" else "⚽")
                side  = home if g.get("team") == "home" else away
                self._ev_lay.addWidget(
                    _event_row(icon, g.get("minute"), g.get("scorer", ""), side)
                )

        # Yellow cards
        yellows = events.get("yellow_cards", [])
        if yellows:
            has = True
            self._ev_lay.addWidget(_section_header("🟨  YELLOW CARDS"))
            for c in sorted(yellows, key=lambda x: x.get("minute") or 0):
                self._ev_lay.addWidget(
                    _event_row("🟨", c.get("minute"), c.get("player", ""), c.get("team", ""))
                )

        # Red cards
        reds = events.get("red_cards", [])
        if reds:
            has = True
            self._ev_lay.addWidget(_section_header("🟥  RED CARDS"))
            for c in sorted(reds, key=lambda x: x.get("minute") or 0):
                self._ev_lay.addWidget(
                    _event_row("🟥", c.get("minute"), c.get("player", ""), c.get("team", ""))
                )

        # Possession
        poss = events.get("possession")
        if poss:
            has = True
            self._ev_lay.addWidget(_section_header("📊  POSSESSION"))
            self._ev_lay.addWidget(
                _possession_bar(home, poss.get("home", 50),
                                away, poss.get("away", 50))
            )

        # Substitutions
        subs = events.get("substitutions", [])
        if subs:
            has = True
            self._ev_lay.addWidget(_section_header("🔄  SUBSTITUTIONS"))
            for s in sorted(subs, key=lambda x: x.get("minute") or 0):
                desc = f"{s.get('player_out', '')}  →  {s.get('player_in', '')}"
                self._ev_lay.addWidget(
                    _event_row("🔄", s.get("minute"), desc, s.get("team", ""))
                )

        if not has:
            self._ev_lay.addWidget(
                _placeholder("No events recorded for this match yet.")
            )
        self._ev_lay.addStretch()

    # ── Helpers ────────────────────────────────────────────────────────────

    def _clear_ev(self):
        while self._ev_lay.count():
            item = self._ev_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _set_ev_placeholder(self, text: str, is_info: bool = False):
        self._clear_ev()
        self._ev_lay.addWidget(_placeholder(text, is_info=is_info))

    def _on_ws_changed(self, new_status: str):
        set_watch_status(self._match_id, new_status)
        self.watch_status_changed.emit(self._match_id, new_status)