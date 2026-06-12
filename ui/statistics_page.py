"""Statistics page — watch habits visualised with a custom pie chart."""

import math
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, QRectF, QRect
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QBrush
from database.database import get_watch_statistics, get_all_matches_with_teams


class PieChart(QWidget):
    def __init__(self, data: list[tuple[str, int, str]], parent=None):
        """data = [(label, value, hex_color), ...]"""
        super().__init__(parent)
        self.data = data
        self.setMinimumSize(260, 260)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        total = sum(v for _, v, _ in self.data)
        if total == 0:
            painter.setPen(QColor("#484f58"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No data")
            return

        w, h   = self.width(), self.height()
        size   = min(w, h) - 40
        x_off  = (w - size) // 2
        y_off  = (h - size) // 2
        rect   = QRectF(x_off, y_off, size, size)

        start_angle = 90 * 16   # 12 o'clock, in 1/16th degree units
        for label, value, color in self.data:
            span = int(value / total * 360 * 16)
            if span == 0:
                continue
            painter.setBrush(QBrush(QColor(color)))
            painter.setPen(QPen(QColor("#0d1117"), 2))
            painter.drawPie(rect, start_angle, -span)
            start_angle -= span

        # Inner white circle (donut hole)
        hole = size * 0.55
        hx   = x_off + (size - hole) / 2
        hy   = y_off + (size - hole) / 2
        painter.setBrush(QBrush(QColor("#0d1117")))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(hx, hy, hole, hole))

        # Center text
        painter.setPen(QColor("#e6edf3"))
        font = QFont()
        font.setPointSize(20)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRectF(hx, hy, hole, hole - 10),
                         Qt.AlignmentFlag.AlignCenter, str(total))
        font2 = QFont()
        font2.setPointSize(9)
        painter.setFont(font2)
        painter.setPen(QColor("#8b949e"))
        painter.drawText(QRectF(hx, hy + hole * 0.5, hole, hole * 0.3),
                         Qt.AlignmentFlag.AlignCenter, "matches")

    def update_data(self, data):
        self.data = data
        self.update()


class LegendItem(QWidget):
    def __init__(self, color: str, label: str, value: int, total: int):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(10)

        dot = QLabel("●")
        dot.setStyleSheet(f"color:{color}; font-size:14px;")
        dot.setFixedWidth(18)
        lay.addWidget(dot)

        name_lbl = QLabel(label)
        name_lbl.setStyleSheet("font-size:13px; font-weight:600;")
        lay.addWidget(name_lbl, 1)

        val_lbl = QLabel(str(value))
        val_lbl.setStyleSheet("font-size:13px; color:#e6edf3;")
        lay.addWidget(val_lbl)

        pct = int(value / total * 100) if total else 0
        pct_lbl = QLabel(f"{pct}%")
        pct_lbl.setStyleSheet("font-size:11px; color:#8b949e; min-width:38px;")
        pct_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(pct_lbl)


class ProgressBar(QWidget):
    def __init__(self, label: str, value: int, max_val: int, color: str):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        row = QHBoxLayout()
        lbl  = QLabel(label)
        lbl.setStyleSheet("font-size:12px; color:#8b949e; font-weight:600;")
        pct  = QLabel(f"{int(value/max_val*100) if max_val else 0}%  ({value})")
        pct.setStyleSheet("font-size:11px; color:#8b949e;")
        row.addWidget(lbl)
        row.addStretch()
        row.addWidget(pct)
        lay.addLayout(row)

        track = QFrame()
        track.setFixedHeight(8)
        track.setStyleSheet("background:#21262d; border-radius:4px;")
        lay.addWidget(track)

        self.track = track
        self.fill  = QFrame(track)
        self.fill.setFixedHeight(8)
        self.fill.setStyleSheet(f"background:{color}; border-radius:4px;")
        self._pct = (value / max_val) if max_val else 0
        self.show()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.fill.setFixedWidth(max(8, int(self.track.width() * self._pct)))


class StatisticsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(24)

        title = QLabel("Statistics")
        title.setObjectName("sectionTitle")
        outer.addWidget(title)

        # Main content row
        content = QHBoxLayout()
        content.setSpacing(24)

        # Left: pie chart
        left = QFrame()
        left.setObjectName("card")
        left.setFixedWidth(320)
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(20, 20, 20, 20)
        left_lay.setSpacing(16)

        chart_title = QLabel("Watch Status Breakdown")
        chart_title.setStyleSheet("font-size:13px; font-weight:600;")
        left_lay.addWidget(chart_title)

        self.pie = PieChart([("Loading", 1, "#484f58")])
        left_lay.addWidget(self.pie, 0, Qt.AlignmentFlag.AlignCenter)

        self.legend_lay = QVBoxLayout()
        left_lay.addLayout(self.legend_lay)
        left_lay.addStretch()
        content.addWidget(left)

        # Right: detailed stats
        right = QVBoxLayout()
        right.setSpacing(16)

        # Stage breakdown card
        self.stage_card = QFrame()
        self.stage_card.setObjectName("card")
        stage_lay = QVBoxLayout(self.stage_card)
        stage_lay.setContentsMargins(20, 20, 20, 20)
        stage_lay.setSpacing(12)

        st = QLabel("Progress by Stage")
        st.setStyleSheet("font-size:13px; font-weight:600;")
        stage_lay.addWidget(st)

        self.stage_progress_lay = QVBoxLayout()
        self.stage_progress_lay.setSpacing(8)
        stage_lay.addLayout(self.stage_progress_lay)
        right.addWidget(self.stage_card)

        # Numbers card
        self.numbers_card = QFrame()
        self.numbers_card.setObjectName("card")
        num_lay = QVBoxLayout(self.numbers_card)
        num_lay.setContentsMargins(20, 20, 20, 20)
        num_lay.setSpacing(8)

        nt = QLabel("Quick Stats")
        nt.setStyleSheet("font-size:13px; font-weight:600;")
        num_lay.addWidget(nt)

        self.quick_stats_lay = QVBoxLayout()
        self.quick_stats_lay.setSpacing(6)
        num_lay.addLayout(self.quick_stats_lay)
        right.addWidget(self.numbers_card)
        right.addStretch()

        content.addLayout(right, 1)
        outer.addLayout(content, 1)

    def refresh(self):
        stats   = get_watch_statistics()
        total   = stats.get("total", 0) or 0
        watched = stats.get("watched", 0) or 0
        missed  = stats.get("missed", 0) or 0
        planned = stats.get("planned", 0) or 0
        fav     = stats.get("favorite", 0) or 0
        not_set = stats.get("not_set", 0) or 0

        pie_data = [
            ("Watched",  watched, "#3fb950"),
            ("Missed",   missed,  "#f85149"),
            ("Planned",  planned, "#58a6ff"),
            ("Favorite", fav,     "#d29922"),
            ("Not Set",  not_set, "#30363d"),
        ]
        pie_data = [(l, v, c) for l, v, c in pie_data if v > 0]
        if not pie_data:
            pie_data = [("No Data", 1, "#30363d")]
        self.pie.update_data(pie_data)

        # Legend
        while self.legend_lay.count():
            item = self.legend_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for label, value, color in [
            ("Watched",  watched, "#3fb950"),
            ("Missed",   missed,  "#f85149"),
            ("Planned",  planned, "#58a6ff"),
            ("Favorite", fav,     "#d29922"),
            ("Not Set",  not_set, "#484f58"),
        ]:
            self.legend_lay.addWidget(LegendItem(color, label, value, total))

        # Stage progress
        while self.stage_progress_lay.count():
            item = self.stage_progress_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        matches = get_all_matches_with_teams()
        from collections import Counter
        stage_totals   = Counter(m.get("stage") for m in matches)
        stage_watched  = Counter(
            m.get("stage") for m in matches if m.get("user_watch_status") == "Watched"
        )

        stage_order = ["Group Stage", "Round of 32", "Round of 16",
                       "Quarter Final", "Semi Final", "Third Place Match", "Final"]
        colors = ["#3fb950", "#58a6ff", "#d29922", "#f0883e", "#bc8cff", "#ff7b72", "#e3b341"]
        for stage, color in zip(stage_order, colors):
            tot = stage_totals.get(stage, 0)
            wat = stage_watched.get(stage, 0)
            if tot > 0:
                self.stage_progress_lay.addWidget(
                    ProgressBar(stage, wat, tot, color)
                )

        # Quick stats
        while self.quick_stats_lay.count():
            item = self.quick_stats_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        finished = stats.get("finished", 0) or 0
        live_now = stats.get("live", 0) or 0
        pct      = int(watched / total * 100) if total else 0

        quick = [
            ("Total Matches", total,    "#e6edf3"),
            ("Matches Played", finished, "#8b949e"),
            ("Live Right Now", live_now, "#da3633"),
            ("Watch Rate", f"{pct}%",   "#3fb950"),
        ]
        for label, value, color in quick:
            row = QHBoxLayout()
            lbl  = QLabel(label)
            lbl.setStyleSheet("color:#8b949e; font-size:12px;")
            val  = QLabel(str(value))
            val.setStyleSheet(f"color:{color}; font-size:13px; font-weight:700;")
            row.addWidget(lbl)
            row.addStretch()
            row.addWidget(val)
            w = QWidget()
            w.setLayout(row)
            self.quick_stats_lay.addWidget(w)
