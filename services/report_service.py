"""
Report service — generates a PDF "End-of-Tournament" summary using ReportLab.

Generates to the user's home directory as:
  ~/WorldCup2026_Report.pdf

Returns the path on success, raises ReportError on failure.
"""

import os
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class ReportError(Exception):
    pass


def generate_report() -> str:
    """
    Build a PDF report and return its absolute path.
    Raises ReportError if generation fails.
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
            HRFlowable, KeepTogether
        )
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
    except ImportError:
        raise ReportError(
            "ReportLab is not installed.\n"
            "Run:  pip install reportlab"
        )

    from database.database import (
        get_watch_statistics, get_all_matches_with_teams,
        get_favorite_teams, get_last_sync
    )

  
    stats   = get_watch_statistics()
    matches = get_all_matches_with_teams()
    favs    = get_favorite_teams()
    last_sync = get_last_sync()

    total    = stats.get("total", 0) or 0
    watched  = stats.get("watched", 0) or 0
    missed   = stats.get("missed", 0) or 0
    planned  = stats.get("planned", 0) or 0
    favorite = stats.get("favorite", 0) or 0
    finished = stats.get("finished", 0) or 0
    watch_pct = int(watched / total * 100) if total else 0
    completion_pct = int(finished / total * 100) if total else 0

 
  
    from collections import Counter
    watched_stages = Counter(
        m.get("stage") for m in matches
        if m.get("user_watch_status") == "Watched"
    )
    fav_stage = watched_stages.most_common(1)[0][0] if watched_stages else "N/A"


    out_path = os.path.join(os.path.expanduser("~"), "WorldCup2026_Report.pdf")

 
    styles = getSampleStyleSheet()

   
    GREEN  = colors.HexColor("#2da44e")
    DARK   = colors.HexColor("#24292f")
    MID    = colors.HexColor("#57606a")
    LIGHT  = colors.HexColor("#f6f8fa")
    GOLD   = colors.HexColor("#bf8700")
    RED    = colors.HexColor("#cf222e")

    title_style = ParagraphStyle(
        "WCTitle",
        parent=styles["Title"],
        fontSize=26,
        textColor=DARK,
        spaceAfter=4,
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
    )
    sub_style = ParagraphStyle(
        "WCSub",
        parent=styles["Normal"],
        fontSize=11,
        textColor=MID,
        spaceAfter=2,
        alignment=TA_CENTER,
    )
    section_style = ParagraphStyle(
        "WCSection",
        parent=styles["Heading2"],
        fontSize=13,
        textColor=DARK,
        spaceBefore=18,
        spaceAfter=6,
        fontName="Helvetica-Bold",
        borderPad=0,
    )
    body_style = ParagraphStyle(
        "WCBody",
        parent=styles["Normal"],
        fontSize=10,
        textColor=DARK,
        leading=16,
    )
    small_style = ParagraphStyle(
        "WCSmall",
        parent=styles["Normal"],
        fontSize=8,
        textColor=MID,
        alignment=TA_CENTER,
    )

 
    story = []
    W, H = A4

 
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph("⚽  FIFA World Cup 2026", title_style))
    story.append(Paragraph("Personal Watch Report", sub_style))
    generated_at = datetime.now(timezone.utc).strftime("%B %d, %Y  %H:%M UTC")
    story.append(Paragraph(f"Generated: {generated_at}", small_style))
    story.append(Spacer(1, 0.3 * cm))
    story.append(HRFlowable(width="100%", thickness=1, color=GREEN))
    story.append(Spacer(1, 0.4 * cm))

   
    story.append(Paragraph("Tournament Overview", section_style))

    def pct_bar(value: int, maximum: int, color) -> Table:
        pct = value / maximum if maximum else 0
        bar_w = 10 * cm
        filled = bar_w * pct
        data = [["", ""]]
        t = Table(data, colWidths=[filled, bar_w - filled], rowHeights=[10])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), color),
            ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#d0d7de")),
            ("LINEABOVE",  (0, 0), (-1, 0), 0, colors.white),
        ]))
        return t

    summary_data = [
        ["Metric", "Value"],
        ["Total Matches",          str(total)],
        ["Matches Completed",      f"{finished}  ({completion_pct}%)"],
        ["Matches Watched",        f"{watched}"],
        ["Matches Missed",         f"{missed}"],
        ["Matches Planned",        f"{planned}"],
        ["Marked as Favourite",    f"{favorite}"],
        ["Watch Percentage",       f"{watch_pct}%"],
        ["Favourite Stage",        fav_stage],
        ["Favourite Teams",        ", ".join(t["name"] for t in favs) or "None set"],
    ]
    if last_sync:
        summary_data.append(
            ["Last Data Sync", last_sync["last_sync"][:16].replace("T", " ") + " UTC"]
        )

    tbl = Table(summary_data, colWidths=[7 * cm, 9.5 * cm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0),  DARK),
        ("TEXTCOLOR",    (0, 0), (-1, 0),  colors.white),
        ("FONTNAME",     (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, 0),  10),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [LIGHT, colors.white]),
        ("TEXTCOLOR",    (0, 1), (-1, -1), DARK),
        ("FONTSIZE",     (0, 1), (-1, -1), 9),
        ("FONTNAME",     (0, 1), (0, -1),  "Helvetica-Bold"),
        ("GRID",         (0, 0), (-1, -1), 0.5, colors.HexColor("#d0d7de")),
        ("TOPPADDING",   (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
        ("LEFTPADDING",  (0, 0), (-1, -1), 8),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 0.3 * cm))


    story.append(Paragraph("Progress Bars", section_style))
    for label, value, color in [
        ("Watched",  watched,  GREEN),
        ("Missed",   missed,   RED),
        ("Planned",  planned,  colors.HexColor("#0969da")),
    ]:
        row_data = [[f"{label}  ({value}/{total})", pct_bar(value, total, color)]]
        rt = Table(row_data, colWidths=[4.5 * cm, 10 * cm])
        rt.setStyle(TableStyle([
            ("VALIGN",  (0, 0), (-1, -1), "MIDDLE"),
            ("FONTSIZE",(0, 0), (0, 0),   9),
            ("TEXTCOLOR",(0,0), (0, 0),   DARK),
            ("FONTNAME",(0, 0), (0, 0),   "Helvetica-Bold"),
        ]))
        story.append(rt)
        story.append(Spacer(1, 0.15 * cm))

  
    watched_matches = [
        m for m in matches if m.get("user_watch_status") == "Watched"
    ]
    if watched_matches:
        story.append(Paragraph(f"Watched Matches  ({len(watched_matches)})", section_style))
        w_data = [["Date", "Home", "Score", "Away", "Stage"]]
        for m in watched_matches:
            hs = m.get("home_score")
            as_ = m.get("away_score")
            score = f"{hs} – {as_}" if hs is not None else "—"
            w_data.append([
                m.get("match_date", ""),
                m.get("home_team_name", "TBD"),
                score,
                m.get("away_team_name", "TBD"),
                m.get("stage", ""),
            ])
        wt = Table(w_data, colWidths=[2.3*cm, 4.5*cm, 2*cm, 4.5*cm, 3.2*cm])
        wt.setStyle(TableStyle([
            ("BACKGROUND",   (0, 0), (-1, 0),  DARK),
            ("TEXTCOLOR",    (0, 0), (-1, 0),  colors.white),
            ("FONTNAME",     (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("FONTSIZE",     (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),   [LIGHT, colors.white]),
            ("GRID",         (0, 0), (-1, -1), 0.5, colors.HexColor("#d0d7de")),
            ("TOPPADDING",   (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
            ("LEFTPADDING",  (0, 0), (-1, -1), 5),
            ("ALIGN",        (2, 0), (2, -1),  "CENTER"),
        ]))
        story.append(wt)

   
    story.append(Spacer(1, 0.6 * cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=MID))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(
        "Generated by FIFA World Cup 2026 Tracker  ·  Data from football-data.org",
        small_style
    ))

    
    try:
        doc = SimpleDocTemplate(
            out_path,
            pagesize=A4,
            leftMargin=2 * cm,
            rightMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
            title="FIFA World Cup 2026 — Personal Watch Report",
            author="WC 2026 Tracker",
        )
        doc.build(story)
    except Exception as exc:
        raise ReportError(f"PDF generation failed: {exc}") from exc

    logger.info("Report saved to %s", out_path)
    return out_path
