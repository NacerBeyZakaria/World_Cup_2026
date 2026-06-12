"""
Settings page.

Sections:
  1. API Configuration  (provider, key, test, signup links)
  2. Favourite Teams    (multi-select checkboxes from all 48 teams)
  3. Appearance         (dark / light theme)
  4. Time & Region      (UTC offset)
  5. Notifications      (toggle + export report button)
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QLineEdit, QPushButton, QComboBox, QCheckBox, QMessageBox,
    QScrollArea, QGridLayout
)
from PyQt6.QtCore import Qt, pyqtSignal
from database.database import (
    get_setting, set_setting, get_all_teams,
    get_favorite_team_ids, add_favorite_team, remove_favorite_team
)

TIMEZONES = [
    "UTC", "UTC-12", "UTC-11", "UTC-10", "UTC-9", "UTC-8 (PST)",
    "UTC-7 (MST)", "UTC-6 (CST)", "UTC-5 (EST)", "UTC-4 (AST)",
    "UTC-3", "UTC-2", "UTC-1",
    "UTC+1 (CET)", "UTC+2 (EET)", "UTC+3 (MSK)",
    "UTC+4", "UTC+5", "UTC+5:30 (IST)", "UTC+6", "UTC+7",
    "UTC+8 (CST)", "UTC+9 (JST)", "UTC+10 (AEST)", "UTC+11", "UTC+12",
]

PROVIDERS = ["football-data.org", "api-football"]

PROVIDER_INFO = {
    "football-data.org": {
        "label":  "football-data.org  (Recommended — free tier)",
        "signup": "https://www.football-data.org/client/register",
        "limits": "Free: 10 req/min · WC included · No credit card",
        "header": "X-Auth-Token",
        "note": (
            "1. Visit football-data.org/client/register — free account.\n"
            "2. Your token is emailed immediately.\n"
            "3. Paste it below and click Save Settings.\n\n"
            "Competition: WC  ·  Season: 2026  ·  All 104 matches included."
        ),
    },
    "api-football": {
        "label":  "API-Football  (api-sports.io — 100 req/day free)",
        "signup": "https://dashboard.api-football.com/register",
        "limits": "Free: 100 req/day · league=1 season=2026",
        "header": "x-apisports-key",
        "note": (
            "1. Visit dashboard.api-football.com/register.\n"
            "2. Copy the API key from your dashboard.\n"
            "3. Paste it below and click Save Settings."
        ),
    },
}


def _card(title: str) -> tuple[QFrame, QVBoxLayout]:
    f = QFrame(); f.setObjectName("card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(20, 18, 20, 18)
    lay.setSpacing(12)
    t = QLabel(title)
    t.setStyleSheet("font-size:14px; font-weight:700;")
    lay.addWidget(t)
    return f, lay


class SettingsPage(QWidget):
    theme_changed    = pyqtSignal(str)
    timezone_changed = pyqtSignal()
    sync_requested   = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fav_checkboxes: dict[int, QCheckBox] = {}
        self._build_ui()
        self._load()

    # ── Build ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0,0,0,0)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(18)

        title = QLabel("Settings"); title.setObjectName("sectionTitle")
        lay.addWidget(title)

        # ── 1. API ─────────────────────────────────────────────────────────
        api_card, api_lay = _card("API Configuration")

        sub = QLabel(
            "Choose a free football data provider and enter your API key. "
            "No key = no data."
        )
        sub.setWordWrap(True); sub.setStyleSheet("font-size:11px; color:#8b949e;")
        api_lay.addWidget(sub)

        # Provider
        p_row = QHBoxLayout()
        p_lbl = QLabel("Provider")
        p_lbl.setStyleSheet("font-size:12px; font-weight:600; min-width:90px;")
        self.prov_combo = QComboBox()
        for p in PROVIDERS:
            self.prov_combo.addItem(PROVIDER_INFO[p]["label"], userData=p)
        self.prov_combo.setFixedHeight(36)
        self.prov_combo.currentIndexChanged.connect(self._update_info_card)
        p_row.addWidget(p_lbl); p_row.addWidget(self.prov_combo, 1)
        api_lay.addLayout(p_row)

        # Info card
        self._info_lbl = QLabel()
        self._info_lbl.setWordWrap(True)
        self._info_lbl.setStyleSheet(
            "font-size:11px; color:#8b949e; background:#161b22;"
            "border-radius:6px; padding:10px; border:1px solid #21262d;"
        )
        api_lay.addWidget(self._info_lbl)

        self._limits_lbl = QLabel()
        self._limits_lbl.setStyleSheet(
            "font-size:11px; color:#3fb950; background:#1a4731;"
            "border-radius:4px; padding:4px 8px;"
        )
        api_lay.addWidget(self._limits_lbl)

        # Signup link
        self._signup_btn = QPushButton()
        self._signup_btn.setStyleSheet(
            "text-align:left; color:#58a6ff; background:transparent; border:none;"
            "font-size:11px; padding:0;"
        )
        self._signup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._signup_btn.clicked.connect(self._open_signup)
        api_lay.addWidget(self._signup_btn)

        # API Key
        k_row = QHBoxLayout()
        k_lbl = QLabel("API Key")
        k_lbl.setStyleSheet("font-size:12px; font-weight:600; min-width:90px;")
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setFixedHeight(36)
        self.show_key_btn = QPushButton("Show")
        self.show_key_btn.setObjectName("watchBtn")
        self.show_key_btn.setFixedSize(60, 36)
        self.show_key_btn.setCheckable(True)
        self.show_key_btn.clicked.connect(self._toggle_key)
        k_row.addWidget(k_lbl)
        k_row.addWidget(self.api_key_input, 1)
        k_row.addWidget(self.show_key_btn)
        api_lay.addLayout(k_row)

        btn_row = QHBoxLayout()
        self.test_btn = QPushButton("🔌  Test Connection")
        self.test_btn.setObjectName("watchBtn")
        self.test_btn.setFixedHeight(36)
        self.test_btn.clicked.connect(self._test_connection)
        self.save_btn = QPushButton("💾  Save Settings")
        self.save_btn.setObjectName("syncBtn")
        self.save_btn.setFixedHeight(36)
        self.save_btn.clicked.connect(self._save)
        btn_row.addWidget(self.test_btn); btn_row.addStretch()
        btn_row.addWidget(self.save_btn)
        api_lay.addLayout(btn_row)
        lay.addWidget(api_card)

        # ── 2. Favourite Teams ─────────────────────────────────────────────
        fav_card, fav_lay = _card("⭐  Favourite Teams")
        fav_sub = QLabel(
            "Select your favourite teams. They appear on the Dashboard with "
            "next match, last result, and receive notifications."
        )
        fav_sub.setWordWrap(True)
        fav_sub.setStyleSheet("font-size:11px; color:#8b949e;")
        fav_lay.addWidget(fav_sub)

        # Grid of checkboxes, grouped by group
        self._fav_grid = QGridLayout()
        self._fav_grid.setSpacing(6)
        fav_lay.addLayout(self._fav_grid)

        fav_btns = QHBoxLayout()
        clear_btn = QPushButton("Clear all")
        clear_btn.setObjectName("watchBtn")
        clear_btn.setFixedHeight(30)
        clear_btn.clicked.connect(self._clear_all_favs)
        fav_btns.addStretch(); fav_btns.addWidget(clear_btn)
        fav_lay.addLayout(fav_btns)
        lay.addWidget(fav_card)

        # ── 3. Appearance ──────────────────────────────────────────────────
        app_card, app_lay = _card("Appearance")
        t_row = QHBoxLayout()
        t_lbl = QLabel("Theme")
        t_lbl.setStyleSheet("font-size:12px; font-weight:600; min-width:90px;")
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["dark", "light"])
        self.theme_combo.setFixedHeight(36)
        t_row.addWidget(t_lbl); t_row.addWidget(self.theme_combo, 1)
        app_lay.addLayout(t_row)
        lay.addWidget(app_card)

        # ── 4. Time & Region ───────────────────────────────────────────────
        tz_card, tz_lay = _card("Time & Region")
        tz_row = QHBoxLayout()
        tz_lbl = QLabel("Timezone")
        tz_lbl.setStyleSheet("font-size:12px; font-weight:600; min-width:90px;")
        self.tz_combo = QComboBox()
        self.tz_combo.addItems(TIMEZONES)
        self.tz_combo.setFixedHeight(36)
        tz_row.addWidget(tz_lbl); tz_row.addWidget(self.tz_combo, 1)
        tz_lay.addLayout(tz_row)
        hint = QLabel("All match times are stored in UTC and converted to this offset for display.")
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size:11px; color:#8b949e;")
        tz_lay.addWidget(hint)
        lay.addWidget(tz_card)

        # ── 5. Notifications & Export ──────────────────────────────────────
        notif_card, notif_lay = _card("Notifications & Export")
        self.notif_check = QCheckBox(
            "Notify 30 min before Planned / Favourite / knockout matches"
        )
        self.notif_check.setStyleSheet("color:#e6edf3; font-size:12px;")
        notif_lay.addWidget(self.notif_check)

        export_row = QHBoxLayout()
        export_lbl = QLabel("Generate a PDF report of your watching activity.")
        export_lbl.setStyleSheet("font-size:11px; color:#8b949e;")
        export_lbl.setWordWrap(True)
        self.export_btn = QPushButton("📄  Export PDF Report")
        self.export_btn.setObjectName("primaryBtn")
        self.export_btn.setFixedHeight(36)
        self.export_btn.clicked.connect(self._export_report)
        export_row.addWidget(export_lbl, 1)
        export_row.addWidget(self.export_btn)
        notif_lay.addLayout(export_row)
        lay.addWidget(notif_card)

        lay.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll)

    # ── Load ───────────────────────────────────────────────────────────────

    def _load(self):
        self.api_key_input.setText(get_setting("api_key", ""))

        provider = get_setting("api_provider", "football-data.org")
        for i in range(self.prov_combo.count()):
            if self.prov_combo.itemData(i) == provider:
                self.prov_combo.setCurrentIndex(i); break

        theme = get_setting("theme", "dark")
        idx = self.theme_combo.findText(theme)
        if idx >= 0: self.theme_combo.setCurrentIndex(idx)

        tz = get_setting("timezone", "UTC")
        for i in range(self.tz_combo.count()):
            if self.tz_combo.itemText(i).startswith(tz.split(" ")[0]):
                self.tz_combo.setCurrentIndex(i); break

        self.notif_check.setChecked(
            get_setting("notifications", "true") == "true"
        )
        self._update_info_card()
        self._populate_fav_grid()

    def _populate_fav_grid(self):
        # Clear existing checkboxes
        while self._fav_grid.count():
            item = self._fav_grid.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self._fav_checkboxes.clear()

        teams = get_all_teams()
        fav_ids = set(get_favorite_team_ids())

        # Group by group_name
        from collections import defaultdict
        by_group: dict[str, list] = defaultdict(list)
        ungrouped = []
        for t in teams:
            grp = (t.get("group_name") or "").strip().upper()
            if grp and grp in "ABCDEFGHIJKL":
                by_group[grp].append(t)
            else:
                ungrouped.append(t)

        col = 0; row = 0
        for grp in sorted(by_group.keys()):
            grp_lbl = QLabel(f"Group {grp}")
            grp_lbl.setStyleSheet(
                "font-size:10px; font-weight:700; color:#3fb950;"
                "letter-spacing:1px;"
            )
            self._fav_grid.addWidget(grp_lbl, row, col)
            row += 1
            for t in sorted(by_group[grp], key=lambda x: x["name"]):
                cb = QCheckBox(t["name"])
                cb.setChecked(t["id"] in fav_ids)
                cb.setStyleSheet("color:#e6edf3; font-size:12px;")
                cb.stateChanged.connect(
                    lambda state, tid=t["id"]: self._on_fav_changed(tid, state)
                )
                self._fav_checkboxes[t["id"]] = cb
                self._fav_grid.addWidget(cb, row, col)
                row += 1

            # Move to next column after 6 rows
            if row > 14:
                row = 0; col += 1

        if ungrouped:
            for t in ungrouped:
                cb = QCheckBox(t["name"])
                cb.setChecked(t["id"] in fav_ids)
                cb.setStyleSheet("color:#e6edf3; font-size:12px;")
                cb.stateChanged.connect(
                    lambda state, tid=t["id"]: self._on_fav_changed(tid, state)
                )
                self._fav_checkboxes[t["id"]] = cb
                self._fav_grid.addWidget(cb, row, col)
                row += 1

    def _on_fav_changed(self, team_id: int, state: int):
        if state == Qt.CheckState.Checked.value:
            add_favorite_team(team_id)
        else:
            remove_favorite_team(team_id)

    def _clear_all_favs(self):
        for tid, cb in self._fav_checkboxes.items():
            cb.setChecked(False)
            remove_favorite_team(tid)

    # ── Save ───────────────────────────────────────────────────────────────

    def _save(self):
        set_setting("api_key",       self.api_key_input.text().strip())
        set_setting("api_provider",  self.prov_combo.currentData())
        set_setting("theme",         self.theme_combo.currentText())
        set_setting("timezone",      self.tz_combo.currentText().split(" ")[0])
        set_setting("notifications", "true" if self.notif_check.isChecked() else "false")

        self.theme_changed.emit(self.theme_combo.currentText())
        self.timezone_changed.emit()
        QMessageBox.information(
            self, "Settings Saved",
            "Settings saved.\nClick 'Sync Now' in the sidebar to fetch live data."
        )

    # ── Helpers ────────────────────────────────────────────────────────────

    def _update_info_card(self):
        provider = self.prov_combo.currentData() or "football-data.org"
        info = PROVIDER_INFO.get(provider, PROVIDER_INFO["football-data.org"])
        self._info_lbl.setText(info["note"])
        self._limits_lbl.setText(f"ℹ  {info['limits']}")
        self._signup_btn.setText(f"🔗  Signup: {info['signup']}")
        self._signup_btn.setProperty("_url", info["signup"])
        self.api_key_input.setPlaceholderText(f"{info['header']} — paste here…")

    def _toggle_key(self, checked: bool):
        self.api_key_input.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        )
        self.show_key_btn.setText("Hide" if checked else "Show")

    def _open_signup(self):
        url = self._signup_btn.property("_url") or "https://www.football-data.org/client/register"
        import webbrowser; webbrowser.open(url)

    def _test_connection(self):
        from services.api_service import get_service, APIError
        provider = self.prov_combo.currentData()
        key = self.api_key_input.text().strip()
        self.test_btn.setEnabled(False); self.test_btn.setText("Testing…")
        try:
            svc   = get_service(provider, key)
            teams = svc.fetch_teams()
            QMessageBox.information(
                self, "Connection Successful ✅",
                f"API key valid.\nProvider: {provider}\nTeams: {len(teams)}\n\n"
                "Click Save Settings, then Sync Now."
            )
        except APIError as exc:
            QMessageBox.critical(self, "Connection Failed ❌", str(exc))
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Unexpected: {exc}")
        finally:
            self.test_btn.setEnabled(True)
            self.test_btn.setText("🔌  Test Connection")

    def _export_report(self):
        self.export_btn.setEnabled(False)
        self.export_btn.setText("Generating…")
        try:
            from services.report_service import generate_report, ReportError
            path = generate_report()
            QMessageBox.information(
                self, "Report Exported ✅",
                f"PDF saved to:\n{path}"
            )
        except Exception as exc:
            QMessageBox.critical(self, "Export Failed", str(exc))
        finally:
            self.export_btn.setEnabled(True)
            self.export_btn.setText("📄  Export PDF Report")
