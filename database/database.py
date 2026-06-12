"""
SQLite database manager for FIFA World Cup 2026 Tracker.
Handles schema creation, migrations, and all CRUD operations.

Tables:
  teams            — 48 WC teams
  matches          — 104 fixtures with live scores + user watch status
  favorite_teams   — user's chosen favourite teams (multi-select)
  sync_log         — API sync history
  settings         — key/value app settings
"""

import sqlite3
import os
from contextlib import contextmanager
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "worldcup.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db_cursor():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize_db():
    """Create all tables if they don't exist (safe to call multiple times)."""
    with db_cursor() as cur:
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS teams (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                api_team_id INTEGER UNIQUE,
                fifa_code   TEXT,
                name        TEXT NOT NULL,
                group_name  TEXT,
                flag_url    TEXT
            );

            CREATE TABLE IF NOT EXISTS matches (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                api_match_id      INTEGER UNIQUE,
                match_date        TEXT NOT NULL,
                match_time        TEXT,
                home_team_id      INTEGER REFERENCES teams(id),
                away_team_id      INTEGER REFERENCES teams(id),
                stage             TEXT DEFAULT 'Group Stage',
                home_score        INTEGER,
                away_score        INTEGER,
                status            TEXT DEFAULT 'Scheduled',
                user_watch_status TEXT DEFAULT 'Not Set',
                winner_team_id    INTEGER REFERENCES teams(id),
                venue             TEXT,
                city              TEXT
            );

            CREATE TABLE IF NOT EXISTS favorite_teams (
                team_id INTEGER PRIMARY KEY REFERENCES teams(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS sync_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                last_sync  TEXT NOT NULL,
                source     TEXT,
                records    INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
        """)
    _seed_default_settings()


def _seed_default_settings():
    defaults = {
        "theme":        "dark",
        "api_key":      "",
        "api_provider": "football-data.org",
        "timezone":     "UTC",
        "notifications": "true",
    }
    with db_cursor() as cur:
        for k, v in defaults.items():
            cur.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v)
            )




def upsert_team(api_team_id, fifa_code, name, group_name, flag_url):
    with db_cursor() as cur:
        cur.execute("""
            INSERT INTO teams (api_team_id, fifa_code, name, group_name, flag_url)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(api_team_id) DO UPDATE SET
                fifa_code  = excluded.fifa_code,
                name       = excluded.name,
                group_name = excluded.group_name,
                flag_url   = excluded.flag_url
        """, (api_team_id, fifa_code, name, group_name, flag_url))


def get_all_teams():
    with db_cursor() as cur:
        cur.execute("SELECT * FROM teams ORDER BY group_name, name")
        return [dict(r) for r in cur.fetchall()]


def get_team_by_id(team_id):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM teams WHERE id = ?", (team_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def get_team_by_api_id(api_id):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM teams WHERE api_team_id = ?", (api_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def get_matches_for_team(team_id: int) -> list[dict]:
    """All matches (past + future) involving a specific team."""
    with db_cursor() as cur:
        cur.execute("""
            SELECT m.*,
                   ht.name AS home_team_name, ht.flag_url AS home_flag, ht.fifa_code AS home_code,
                   at.name AS away_team_name, at.flag_url AS away_flag, at.fifa_code AS away_code
            FROM matches m
            LEFT JOIN teams ht ON m.home_team_id = ht.id
            LEFT JOIN teams at ON m.away_team_id = at.id
            WHERE m.home_team_id = ? OR m.away_team_id = ?
            ORDER BY m.match_date, m.match_time
        """, (team_id, team_id))
        return [dict(r) for r in cur.fetchall()]




def get_favorite_team_ids() -> list[int]:
    with db_cursor() as cur:
        cur.execute("SELECT team_id FROM favorite_teams")
        return [r[0] for r in cur.fetchall()]


def get_favorite_teams() -> list[dict]:
    """Return full team rows for all favourited teams."""
    with db_cursor() as cur:
        cur.execute("""
            SELECT t.* FROM teams t
            INNER JOIN favorite_teams f ON t.id = f.team_id
            ORDER BY t.group_name, t.name
        """)
        return [dict(r) for r in cur.fetchall()]


def add_favorite_team(team_id: int):
    with db_cursor() as cur:
        cur.execute(
            "INSERT OR IGNORE INTO favorite_teams (team_id) VALUES (?)", (team_id,)
        )


def remove_favorite_team(team_id: int):
    with db_cursor() as cur:
        cur.execute("DELETE FROM favorite_teams WHERE team_id = ?", (team_id,))


def is_favorite_team(team_id: int) -> bool:
    with db_cursor() as cur:
        cur.execute("SELECT 1 FROM favorite_teams WHERE team_id = ?", (team_id,))
        return cur.fetchone() is not None




def upsert_match(api_match_id, match_date, match_time, home_team_id, away_team_id,
                 stage, home_score, away_score, status, winner_team_id=None,
                 venue=None, city=None):
    with db_cursor() as cur:
        cur.execute("""
            INSERT INTO matches
                (api_match_id, match_date, match_time, home_team_id, away_team_id,
                 stage, home_score, away_score, status, winner_team_id, venue, city)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(api_match_id) DO UPDATE SET
                match_date     = excluded.match_date,
                match_time     = excluded.match_time,
                home_team_id   = excluded.home_team_id,
                away_team_id   = excluded.away_team_id,
                stage          = excluded.stage,
                home_score     = excluded.home_score,
                away_score     = excluded.away_score,
                status         = excluded.status,
                winner_team_id = excluded.winner_team_id,
                venue          = COALESCE(NULLIF(excluded.venue, ''), matches.venue),
                city           = COALESCE(NULLIF(excluded.city,  ''), matches.city)
        """, (api_match_id, match_date, match_time, home_team_id, away_team_id,
              stage, home_score, away_score, status, winner_team_id, venue, city))


def upsert_tbd_match(api_match_id, match_date, match_time, home_team_id, away_team_id,
                     stage, home_score, away_score, status, winner_team_id=None,
                     venue=None, city=None):
    """Like upsert_match but COALESCE-protects team FKs for TBD knockout slots."""
    with db_cursor() as cur:
        cur.execute("""
            INSERT INTO matches
                (api_match_id, match_date, match_time, home_team_id, away_team_id,
                 stage, home_score, away_score, status, winner_team_id, venue, city)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(api_match_id) DO UPDATE SET
                match_date     = excluded.match_date,
                match_time     = excluded.match_time,
                home_team_id   = COALESCE(excluded.home_team_id, matches.home_team_id),
                away_team_id   = COALESCE(excluded.away_team_id, matches.away_team_id),
                stage          = excluded.stage,
                home_score     = excluded.home_score,
                away_score     = excluded.away_score,
                status         = excluded.status,
                winner_team_id = excluded.winner_team_id,
                venue          = COALESCE(NULLIF(excluded.venue, ''), matches.venue),
                city           = COALESCE(NULLIF(excluded.city,  ''), matches.city)
        """, (api_match_id, match_date, match_time, home_team_id, away_team_id,
              stage, home_score, away_score, status, winner_team_id, venue, city))


def get_all_matches_with_teams() -> list[dict]:
    with db_cursor() as cur:
        cur.execute("""
            SELECT m.*,
                   ht.name AS home_team_name, ht.flag_url AS home_flag,
                   ht.fifa_code AS home_code,
                   at.name AS away_team_name, at.flag_url AS away_flag,
                   at.fifa_code AS away_code
            FROM matches m
            LEFT JOIN teams ht ON m.home_team_id = ht.id
            LEFT JOIN teams at ON m.away_team_id = at.id
            ORDER BY m.match_date, m.match_time
        """)
        return [dict(r) for r in cur.fetchall()]


def get_match_by_id(match_id: int) -> Optional[dict]:
    with db_cursor() as cur:
        cur.execute("""
            SELECT m.*,
                   ht.name AS home_team_name, ht.flag_url AS home_flag, ht.fifa_code AS home_code,
                   at.name AS away_team_name, at.flag_url AS away_flag, at.fifa_code AS away_code
            FROM matches m
            LEFT JOIN teams ht ON m.home_team_id = ht.id
            LEFT JOIN teams at ON m.away_team_id = at.id
            WHERE m.id = ?
        """, (match_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def get_matches_by_date(date_str: str) -> list[dict]:
    with db_cursor() as cur:
        cur.execute("""
            SELECT m.*,
                   ht.name AS home_team_name, ht.flag_url AS home_flag, ht.fifa_code AS home_code,
                   at.name AS away_team_name, at.flag_url AS away_flag, at.fifa_code AS away_code
            FROM matches m
            LEFT JOIN teams ht ON m.home_team_id = ht.id
            LEFT JOIN teams at ON m.away_team_id = at.id
            WHERE m.match_date = ?
            ORDER BY m.match_time
        """, (date_str,))
        return [dict(r) for r in cur.fetchall()]


def get_matches_by_stage(stage: str) -> list[dict]:
    with db_cursor() as cur:
        cur.execute("""
            SELECT m.*,
                   ht.name AS home_team_name, ht.flag_url AS home_flag, ht.fifa_code AS home_code,
                   at.name AS away_team_name, at.flag_url AS away_flag, at.fifa_code AS away_code
            FROM matches m
            LEFT JOIN teams ht ON m.home_team_id = ht.id
            LEFT JOIN teams at ON m.away_team_id = at.id
            WHERE m.stage = ?
            ORDER BY m.match_date, m.match_time
        """, (stage,))
        return [dict(r) for r in cur.fetchall()]


def get_todays_matches() -> list[dict]:
    """Return all matches on today's UTC date, ordered by kickoff time."""
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return get_matches_by_date(today)


def get_next_match() -> Optional[dict]:
    """Return the next scheduled or live match (UTC)."""
    from datetime import datetime, timezone
    now_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    now_time = datetime.now(timezone.utc).strftime("%H:%M")
    with db_cursor() as cur:
        cur.execute("""
            SELECT m.*,
                   ht.name AS home_team_name, ht.flag_url AS home_flag, ht.fifa_code AS home_code,
                   at.name AS away_team_name, at.flag_url AS away_flag, at.fifa_code AS away_code
            FROM matches m
            LEFT JOIN teams ht ON m.home_team_id = ht.id
            LEFT JOIN teams at ON m.away_team_id = at.id
            WHERE m.status IN ('Scheduled','Live')
              AND (m.match_date > ? OR (m.match_date = ? AND m.match_time >= ?))
            ORDER BY m.match_date, m.match_time
            LIMIT 1
        """, (now_date, now_date, now_time))
        row = cur.fetchone()
        return dict(row) if row else None


def get_next_favorite_match() -> Optional[dict]:
    """Return the next upcoming match for any favourited team."""
    from datetime import datetime, timezone
    now_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    now_time = datetime.now(timezone.utc).strftime("%H:%M")
    with db_cursor() as cur:
        cur.execute("""
            SELECT m.*,
                   ht.name AS home_team_name, ht.flag_url AS home_flag, ht.fifa_code AS home_code,
                   at.name AS away_team_name, at.flag_url AS away_flag, at.fifa_code AS away_code
            FROM matches m
            LEFT JOIN teams ht ON m.home_team_id = ht.id
            LEFT JOIN teams at ON m.away_team_id = at.id
            WHERE m.status IN ('Scheduled','Live')
              AND (m.match_date > ? OR (m.match_date = ? AND m.match_time >= ?))
              AND (m.home_team_id IN (SELECT team_id FROM favorite_teams)
                   OR m.away_team_id IN (SELECT team_id FROM favorite_teams))
            ORDER BY m.match_date, m.match_time
            LIMIT 1
        """, (now_date, now_date, now_time))
        row = cur.fetchone()
        return dict(row) if row else None


def get_last_favorite_result() -> Optional[dict]:
    """Return the most recently finished match involving a favourite team."""
    with db_cursor() as cur:
        cur.execute("""
            SELECT m.*,
                   ht.name AS home_team_name, ht.flag_url AS home_flag, ht.fifa_code AS home_code,
                   at.name AS away_team_name, at.flag_url AS away_flag, at.fifa_code AS away_code
            FROM matches m
            LEFT JOIN teams ht ON m.home_team_id = ht.id
            LEFT JOIN teams at ON m.away_team_id = at.id
            WHERE m.status = 'Finished'
              AND (m.home_team_id IN (SELECT team_id FROM favorite_teams)
                   OR m.away_team_id IN (SELECT team_id FROM favorite_teams))
            ORDER BY m.match_date DESC, m.match_time DESC
            LIMIT 1
        """)
        row = cur.fetchone()
        return dict(row) if row else None


def get_upcoming_notification_matches() -> list[dict]:
    """
    Return matches starting in 25-35 minutes (UTC) that are Planned, Favorite,
    or involve a favourite team. Used by the notification service.
    """
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    lo  = (now + timedelta(minutes=25)).strftime("%H:%M")
    hi  = (now + timedelta(minutes=35)).strftime("%H:%M")
    today = now.strftime("%Y-%m-%d")
    with db_cursor() as cur:
        cur.execute("""
            SELECT m.*,
                   ht.name AS home_team_name, at.name AS away_team_name
            FROM matches m
            LEFT JOIN teams ht ON m.home_team_id = ht.id
            LEFT JOIN teams at ON m.away_team_id = at.id
            WHERE m.match_date = ?
              AND m.match_time BETWEEN ? AND ?
              AND m.status = 'Scheduled'
              AND (
                  m.user_watch_status IN ('Planned','Favorite')
                  OR m.home_team_id IN (SELECT team_id FROM favorite_teams)
                  OR m.away_team_id IN (SELECT team_id FROM favorite_teams)
                  OR m.stage NOT LIKE 'Group%'
              )
        """, (today, lo, hi))
        return [dict(r) for r in cur.fetchall()]


def set_watch_status(match_id: int, status: str):
    with db_cursor() as cur:
        cur.execute(
            "UPDATE matches SET user_watch_status = ? WHERE id = ?",
            (status, match_id)
        )


def get_watch_statistics() -> dict:
    with db_cursor() as cur:
        cur.execute("""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN user_watch_status = 'Watched'  THEN 1 ELSE 0 END) AS watched,
                SUM(CASE WHEN user_watch_status = 'Missed'   THEN 1 ELSE 0 END) AS missed,
                SUM(CASE WHEN user_watch_status = 'Planned'  THEN 1 ELSE 0 END) AS planned,
                SUM(CASE WHEN user_watch_status = 'Favorite' THEN 1 ELSE 0 END) AS favorite,
                SUM(CASE WHEN user_watch_status = 'Not Set'  THEN 1 ELSE 0 END) AS not_set,
                SUM(CASE WHEN status = 'Finished'            THEN 1 ELSE 0 END) AS finished,
                SUM(CASE WHEN status = 'Live'                THEN 1 ELSE 0 END) AS live
            FROM matches
        """)
        row = cur.fetchone()
        return dict(row) if row else {}


def search_matches(query: str) -> list[dict]:
    q = f"%{query}%"
    with db_cursor() as cur:
        cur.execute("""
            SELECT m.*,
                   ht.name AS home_team_name, ht.flag_url AS home_flag, ht.fifa_code AS home_code,
                   at.name AS away_team_name, at.flag_url AS away_flag, at.fifa_code AS away_code
            FROM matches m
            LEFT JOIN teams ht ON m.home_team_id = ht.id
            LEFT JOIN teams at ON m.away_team_id = at.id
            WHERE ht.name LIKE ? OR at.name LIKE ?
            ORDER BY m.match_date, m.match_time
        """, (q, q))
        return [dict(r) for r in cur.fetchall()]


def get_distinct_match_dates() -> list[str]:
    with db_cursor() as cur:
        cur.execute("SELECT DISTINCT match_date FROM matches ORDER BY match_date")
        return [r[0] for r in cur.fetchall()]




def log_sync(source: str, records: int):
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).isoformat()
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO sync_log (last_sync, source, records) VALUES (?, ?, ?)",
            (ts, source, records)
        )


def get_last_sync() -> Optional[dict]:
    with db_cursor() as cur:
        cur.execute("SELECT * FROM sync_log ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        return dict(row) if row else None




def get_setting(key: str, default=None):
    with db_cursor() as cur:
        cur.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cur.fetchone()
        return row[0] if row else default


def set_setting(key: str, value: str):
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value)
        )
