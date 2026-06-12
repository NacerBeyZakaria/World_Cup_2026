"""
Sync service: pulls real data from the configured API provider and writes it to SQLite.

Key behaviours:
  - No demo/fake data. If no API key is configured, raises MissingAPIKeyError immediately.
  - user_watch_status is NEVER overwritten — the upsert_match SQL excludes it from the
    ON CONFLICT UPDATE clause, so a user's Watched/Missed/Planned/Favorite marks survive
    every sync.
  - Groups are extracted from fixtures (match.group_name) and written back to teams so
    the DB always reflects the official draw.
  - TBD knockout slots (home_api_id or away_api_id is None) are stored with NULL team
    FKs so they appear in the bracket as "TBD" and are filled in as teams qualify.
  - run_sync()       — full refresh (teams + all fixtures). Called at startup and every 30 min.
  - sync_live_scores() — lightweight poll of live-only matches. Called every 60 s.
"""

import logging
from database.database import (
    upsert_team, upsert_match, upsert_tbd_match,
    get_team_by_api_id, get_all_teams, log_sync, get_setting
)
from services.api_service import get_service, APIError, MissingAPIKeyError

logger = logging.getLogger(__name__)


# ── Internal helpers ───────────────────────────────────────────────────────────

def _build_id_map() -> dict[int, int]:
    """Return {api_team_id: local_db_id} for all teams already in the DB."""
    teams = get_all_teams()
    return {t["api_team_id"]: t["id"] for t in teams if t.get("api_team_id")}


def _save_teams(teams: list[dict]) -> dict[int, int]:
    """
    Upsert all teams into the DB.
    Returns the {api_team_id → local db id} mapping.
    """
    id_map: dict[int, int] = {}
    for t in teams:
        api_id = t.get("api_team_id")
        if not api_id:
            continue
        upsert_team(
            api_team_id=api_id,
            fifa_code=t.get("fifa_code", ""),
            name=t["name"],
            group_name=t.get("group_name"),   # may still be None here; filled below
            flag_url=t.get("flag_url", ""),
        )
        row = get_team_by_api_id(api_id)
        if row:
            id_map[api_id] = row["id"]
    logger.info("Saved %d teams to DB", len(id_map))
    return id_map


def _apply_group_names_from_fixtures(fixtures: list[dict], id_map: dict[int, int]):
    """
    football-data.org returns group letters on each fixture, not on the teams endpoint.
    Walk the group-stage fixtures and patch each team's group_name in the DB.
    """
    from database.database import db_cursor
    group_updates: dict[int, str] = {}  # local_team_id → group letter

    for f in fixtures:
        grp = f.get("group_name", "")
        if not grp:
            continue
        for api_id in (f.get("home_api_id"), f.get("away_api_id")):
            local_id = id_map.get(api_id)
            if local_id and grp:
                group_updates[local_id] = grp

    if group_updates:
        with db_cursor() as cur:
            cur.executemany(
                "UPDATE teams SET group_name = ? WHERE id = ? AND (group_name IS NULL OR group_name = '')",
                [(g, tid) for tid, g in group_updates.items()],
            )
        logger.info("Updated group_name for %d teams", len(group_updates))


def _save_fixtures(fixtures: list[dict], id_map: dict[int, int]) -> int:
    """
    Upsert every fixture into the DB.

    Knockout matches where a team has not yet been determined arrive with
    home_api_id / away_api_id = None. We store these with NULL FKs using
    upsert_tbd_match so the bracket can show "TBD" slots until teams qualify.

    Returns the number of rows written.
    """
    count = 0
    for f in fixtures:
        h_api = f.get("home_api_id")
        a_api = f.get("away_api_id")
        h_id  = id_map.get(h_api) if h_api else None
        a_id  = id_map.get(a_api) if a_api else None
        w_id  = id_map.get(f["winner_api_id"]) if f.get("winner_api_id") else None

        if h_id is None or a_id is None:
            # TBD knockout slot — persist it so the bracket stage appears
            upsert_tbd_match(
                api_match_id=f["api_match_id"],
                match_date=f["match_date"],
                match_time=f["match_time"],
                home_team_id=h_id,
                away_team_id=a_id,
                stage=f.get("stage", "Group Stage"),
                home_score=f.get("home_score"),
                away_score=f.get("away_score"),
                status=f.get("status", "Scheduled"),
                winner_team_id=w_id,
                venue=f.get("venue"),
                city=f.get("city"),
            )
        else:
            upsert_match(
                api_match_id=f["api_match_id"],
                match_date=f["match_date"],
                match_time=f["match_time"],
                home_team_id=h_id,
                away_team_id=a_id,
                stage=f.get("stage", "Group Stage"),
                home_score=f.get("home_score"),
                away_score=f.get("away_score"),
                status=f.get("status", "Scheduled"),
                winner_team_id=w_id,
                venue=f.get("venue"),
                city=f.get("city"),
            )
        count += 1
    logger.info("Saved %d fixtures to DB", count)
    return count


# ── Public API ─────────────────────────────────────────────────────────────────

def run_sync() -> dict:
    """
    Full synchronisation: fetch teams + all fixtures, write to SQLite.

    Returns a result dict:
      {
        "success":  bool,
        "source":   "football-data.org" | "api-football",
        "teams":    int,
        "matches":  int,
        "error":    str | None,
      }

    Raises nothing — all errors are caught and returned in result["error"]
    so the UI thread can show a user-friendly message.
    """
    api_key  = get_setting("api_key", "")
    provider = get_setting("api_provider", "football-data.org")
    result   = {
        "success": False,
        "source":  provider,
        "teams":   0,
        "matches": 0,
        "error":   None,
    }

    try:
        svc      = get_service(provider, api_key)
        teams    = svc.fetch_teams()
        fixtures = svc.fetch_fixtures()
    except APIError as exc:
        result["error"] = str(exc)
        logger.error("Sync failed: %s", exc)
        return result
    except Exception as exc:
        result["error"] = f"Unexpected error: {exc}"
        logger.exception("Unexpected sync error")
        return result

    try:
        id_map  = _save_teams(teams)
        _apply_group_names_from_fixtures(fixtures, id_map)
        count   = _save_fixtures(fixtures, id_map)
        log_sync(provider, count)
        result.update(success=True, teams=len(id_map), matches=count)
    except Exception as exc:
        result["error"] = f"DB write error: {exc}"
        logger.exception("DB write failed during sync")

    return result


def sync_live_scores() -> int:
    """
    Lightweight poll: fetch live matches AND any matches that finished recently.

    Strategy:
      1. Fetch currently IN_PLAY / PAUSED matches — updates live scores.
      2. Check the DB for any matches still marked "Live" that are no longer
         in the live feed — they have just finished. Fetch them individually
         to get the final score and FINISHED status.
      3. This closes the gap between the live feed dropping a match and the
         next 30-minute full sync picking up the result.

    Returns total number of DB rows updated.
    """
    api_key  = get_setting("api_key", "")
    provider = get_setting("api_provider", "football-data.org")

    if not api_key:
        return 0

    try:
        svc    = get_service(provider, api_key)
        id_map = _build_id_map()
        total  = 0

        # Step 1: currently live matches
        live_fixtures = svc.fetch_live_fixtures()
        if live_fixtures:
            total += _save_fixtures(live_fixtures, id_map)
            logger.debug("Live poll: updated %d in-play fixtures", len(live_fixtures))

        # Step 2: matches still "Live" in DB but absent from live feed
        # → they just finished; fetch each one for the final score
        live_api_ids = {f["api_match_id"] for f in live_fixtures}
        stale = _get_stale_live_matches(live_api_ids)
        for match in stale:
            api_id = match.get("api_match_id")
            if not api_id:
                continue
            try:
                finished = svc.fetch_fixture_by_id(api_id)
                if finished:
                    total += _save_fixtures([finished], id_map)
                    logger.info("Closed result for match %s: %s-%s",
                                api_id,
                                finished.get("home_score"),
                                finished.get("away_score"))
            except APIError as exc:
                logger.warning("Could not fetch result for match %s: %s", api_id, exc)

        return total

    except APIError as exc:
        logger.warning("Live score sync skipped: %s", exc)
        return 0
    except Exception as exc:
        logger.error("Live score sync error: %s", exc)
        return 0


def _get_stale_live_matches(live_api_ids: set) -> list[dict]:
    """
    Return matches currently marked Live in the DB whose api_match_id is NOT
    in the live feed anymore — they have finished since the last poll.
    """
    from database.database import db_cursor
    with db_cursor() as cur:
        cur.execute(
            "SELECT api_match_id FROM matches WHERE status = 'Live'"
        )
        rows = cur.fetchall()
    stale = [{"api_match_id": r[0]} for r in rows if r[0] not in live_api_ids]
    if stale:
        logger.info("Found %d stale-live matches to resolve", len(stale))
    return stale
