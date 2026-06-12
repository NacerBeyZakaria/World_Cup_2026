"""
Notification service.

Checks every minute for matches starting in ~30 minutes and fires
a desktop notification if the match is:
  - marked Planned or Favorite by the user
  - involving a favourite team
  - a knockout-stage match

Uses plyer for cross-platform desktop notifications (Linux/Windows/macOS).
Falls back to a no-op if plyer is unavailable.

Notification deduplication: keeps a set of already-notified match IDs
(reset on app restart — perfectly fine since the timer only fires once
per session window anyway).
"""

import logging
from database.database import get_upcoming_notification_matches, get_setting

logger = logging.getLogger(__name__)

# Match IDs we've already notified about this session
_notified: set[int] = set()


def check_and_notify() -> int:
    """
    Called every 60 s by the main-window live timer.
    Returns number of notifications sent.
    """
    if get_setting("notifications", "true") != "true":
        return 0

    matches = get_upcoming_notification_matches()
    sent = 0
    for m in matches:
        mid = m.get("id") or m.get("api_match_id")
        if mid in _notified:
            continue
        _notified.add(mid)
        home = m.get("home_team_name", "?")
        away = m.get("away_team_name", "?")
        kick = m.get("match_time", "")
        stage = m.get("stage", "")
        _fire(
            title="⚽ Match in 30 minutes",
            message=f"{home}  vs  {away}\n{kick} UTC  ·  {stage}",
        )
        sent += 1
        logger.info("Notification sent: %s vs %s", home, away)
    return sent


def _fire(title: str, message: str):
    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message,
            app_name="WC 2026 Tracker",
            timeout=10,
        )
    except Exception as exc:
        # Plyer can fail on headless systems or when the notification daemon
        # is unavailable — we log and move on silently.
        logger.debug("Desktop notification failed: %s", exc)
