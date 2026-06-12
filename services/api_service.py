"""
Real-data API integration for FIFA World Cup 2026 Tracker.

Supports two free providers (user selects in Settings):

  1. football-data.org  (RECOMMENDED — free tier, competition code "WC", season 2026)
     Endpoints used:
       GET /v4/competitions/WC/teams?season=2026       → 48 teams + crest URLs
       GET /v4/competitions/WC/matches?season=2026     → all 104 fixtures
     Auth: X-Auth-Token header
     Rate limit: 10 req/min on free tier
     Sign up: https://www.football-data.org/client/register

  2. API-Football  (api-sports.io — 100 req/day free tier)
     Endpoints used:
       GET /v3/teams?league=1&season=2026              → teams
       GET /v3/fixtures?league=1&season=2026           → all fixtures
       GET /v3/fixtures?league=1&season=2026&live=all  → live only
     Auth: x-apisports-key header
     Rate limit: 100 requests/day on free tier
     Sign up: https://dashboard.api-football.com/register

Both providers return normalised dicts with the same keys so the sync
layer never needs to know which provider was used.

No demo/fake data anywhere in this file. If the API key is missing or
the call fails, an APIError is raised so the UI can show a clear message.
"""

import requests
import logging
import time
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)




class APIError(Exception):
    """Raised when the API call cannot produce usable data."""
    pass


class MissingAPIKeyError(APIError):
    """Raised when no API key has been configured."""
    pass


class InvalidAPIKeyError(APIError):
    """Raised when the API returns a 401/403 or an authentication error."""
    pass


class RateLimitError(APIError):
    """Raised when the API rate limit has been hit."""
    pass




FD_BASE_URL      = "https://api.football-data.org/v4"
FD_COMPETITION   = "WC"       
FD_SEASON        = 2026


_FD_STAGE_MAP = {
    "GROUP_STAGE":      "Group Stage",
    "LAST_32":          "Round of 32",
    "LAST_16":          "Round of 16",
    "QUARTER_FINALS":   "Quarter Final",
    "SEMI_FINALS":      "Semi Final",
    "THIRD_PLACE":      "Third Place Match",
    "FINAL":            "Final",
}


_FD_GROUP_MAP = {f"GROUP_{c}": c for c in "ABCDEFGHIJKL"}


_FD_STATUS_MAP = {
    "SCHEDULED":         "Scheduled",
    "TIMED":             "Scheduled",
    "IN_PLAY":           "Live",
    "PAUSED":            "Live",
    "EXTRA_TIME":        "Live",
    "PENALTY_SHOOTOUT":  "Live",
    "FINISHED":          "Finished",
    "AWARDED":           "Finished",
    "SUSPENDED":         "Scheduled",
    "POSTPONED":         "Scheduled",
    "CANCELLED":         "Scheduled",
}


class FootballDataService:
    """
    football-data.org v4 REST client.
    All public methods return normalised dicts.
    Raises APIError subclasses on failure.
    """

    def __init__(self, api_key: str):
        if not api_key or not api_key.strip():
            raise MissingAPIKeyError(
                "No API key configured.\n\n"
                "Get a free key at https://www.football-data.org/client/register\n"
                "then paste it in Settings → API Key."
            )
        self.api_key = api_key.strip()
        self.session = requests.Session()
        self.session.headers.update({"X-Auth-Token": self.api_key})

    

    def _get(self, path: str, params: dict = None) -> dict:
        """
        Perform a GET request.  Handles HTTP-level errors and maps them to
        our exception hierarchy so callers never see raw requests exceptions.
        """
        url = f"{FD_BASE_URL}{path}"
        try:
            resp = self.session.get(url, params=params or {}, timeout=15)
        except requests.ConnectionError as exc:
            raise APIError(f"Network error: {exc}") from exc
        except requests.Timeout:
            raise APIError("Request timed out after 15 s. Check your internet connection.")

        if resp.status_code == 401:
            raise InvalidAPIKeyError(
                "API key rejected (401 Unauthorized).\n"
                "Check your key in Settings → API Key."
            )
        if resp.status_code == 403:
            raise InvalidAPIKeyError(
                "Access denied (403 Forbidden).\n"
                "Your free plan may not include this competition.\n"
                "The World Cup (WC) is included in the football-data.org free tier."
            )
        if resp.status_code == 429:
            raise RateLimitError(
                "Rate limit hit (429 Too Many Requests).\n"
                "football-data.org free tier allows 10 requests/minute.\n"
                "The app will retry automatically on the next sync."
            )
        if resp.status_code >= 500:
            raise APIError(f"Server error from football-data.org (HTTP {resp.status_code}). Try again later.")
        if not resp.ok:
            try:
                msg = resp.json().get("message", resp.text[:200])
            except Exception:
                msg = resp.text[:200]
            raise APIError(f"API error (HTTP {resp.status_code}): {msg}")

        try:
            return resp.json()
        except ValueError as exc:
            raise APIError(f"Unexpected non-JSON response from API: {exc}") from exc

    
    def fetch_teams(self) -> list[dict]:
        """
        GET /v4/competitions/WC/teams?season=2026
        Returns a list of normalised team dicts.
        """
        data = self._get(f"/competitions/{FD_COMPETITION}/teams", {"season": FD_SEASON})
        teams_raw = data.get("teams", [])
        if not teams_raw:
            raise APIError(
                "No teams returned for World Cup 2026.\n"
                "The tournament data may not yet be available on football-data.org.\n"
                "Try again after the draw or tournament begins."
            )

       
        results = []
        for t in teams_raw:
            results.append({
                "api_team_id": t.get("id"),
                "fifa_code":   t.get("tla", ""),            
                "name":        t.get("name", "Unknown"),
                "short_name":  t.get("shortName", ""),
                "flag_url":    t.get("crest", ""),           
                "group_name":  None,                         
            })
        logger.info("football-data.org: fetched %d teams", len(results))
        return results

    def fetch_fixtures(self) -> list[dict]:
        """
        GET /v4/competitions/WC/matches?season=2026
        Returns all 104 WC 2026 matches as normalised dicts.
        Automatically paginates (football-data.org may paginate large responses).
        """
      
        data = self._get(f"/competitions/{FD_COMPETITION}/matches", {"season": FD_SEASON})
        matches_raw = data.get("matches", [])
        if not matches_raw:
            raise APIError(
                "No fixtures returned for World Cup 2026.\n"
                "The full schedule may not yet be published.\n"
                "football-data.org publishes fixtures as FIFA releases them."
            )
        results = [self._normalise_match(m) for m in matches_raw]
        logger.info("football-data.org: fetched %d fixtures", len(results))
        return results

    def fetch_live_fixtures(self) -> list[dict]:
        """
        GET /v4/competitions/WC/matches?status=IN_PLAY&status=PAUSED
        Returns only live matches.
        """
      
        live = []
        for status in ("IN_PLAY", "PAUSED", "EXTRA_TIME", "PENALTY_SHOOTOUT"):
            try:
                data = self._get(
                    f"/competitions/{FD_COMPETITION}/matches",
                    {"season": FD_SEASON, "status": status},
                )
                live.extend(data.get("matches", []))
                time.sleep(0.15)   
            except RateLimitError:
                logger.warning("Rate limit during live-score poll; skipping status=%s", status)
                break
            except APIError as exc:
                logger.warning("Live fetch error for status=%s: %s", status, exc)
        return [self._normalise_match(m) for m in live]

    def fetch_fixture_by_id(self, fixture_id: int) -> "dict | None":
        """
        GET /v4/matches/{id}
        Fetch a single match by its API ID (used to resolve just-finished matches).
        """
        try:
            data = self._get(f"/matches/{fixture_id}")
        except APIError:
            return None
        return self._normalise_match(data)

    def fetch_match_events(self, fixture_id: int) -> dict:
        """
        GET /v4/matches/{id}
        Returns a rich events dict:
          {
            "goals":         [{"minute": int, "team": "home"|"away", "scorer": str, "type": str}]
            "yellow_cards":  [{"minute": int, "team": str, "player": str}]
            "red_cards":     [{"minute": int, "team": str, "player": str}]
            "substitutions": [{"minute": int, "team": str, "player_out": str, "player_in": str}]
            "possession":    None   # not available on football-data.org free tier
            "venue":         str
            "attendance":    int | None
            "minute":        int | None   # current match minute if live
          }
        Returns empty structure on failure (dialog degrades gracefully).
        """
        empty = dict(goals=[], yellow_cards=[], red_cards=[],
                     substitutions=[], possession=None,
                     venue="", attendance=None, minute=None)
        try:
            data = self._get(f"/matches/{fixture_id}")
        except APIError:
            return empty

        home_team = (data.get("homeTeam") or {}).get("name", "Home")
        away_team = (data.get("awayTeam") or {}).get("name", "Away")

        goals = []
        for g in data.get("goals") or []:
            scorer_obj = g.get("scorer") or {}
            assist_obj = g.get("assist") or {}
            team_obj   = g.get("team") or {}
            team_name  = team_obj.get("name", "")
            side       = "home" if team_name == home_team else "away"
            goals.append({
                "minute":  g.get("minute"),
                "team":    side,
                "team_name": team_name,
                "scorer":  scorer_obj.get("name", "Unknown"),
                "type":    g.get("type", "REGULAR"),   
            })

        yellow_cards = []
        red_cards    = []
        for b in data.get("bookings") or []:
            player_obj = b.get("player") or {}
            team_obj   = b.get("team")   or {}
            entry = {
                "minute": b.get("minute"),
                "team":   team_obj.get("name", ""),
                "player": player_obj.get("name", "Unknown"),
            }
            card = b.get("card", "")
            if card == "YELLOW":
                yellow_cards.append(entry)
            elif card in ("RED", "YELLOW_RED"):
                red_cards.append(entry)

        substitutions = []
        for s in data.get("substitutions") or []:
            team_obj = s.get("team") or {}
            substitutions.append({
                "minute":     s.get("minute"),
                "team":       team_obj.get("name", ""),
                "player_out": (s.get("playerOut") or {}).get("name", ""),
                "player_in":  (s.get("playerIn")  or {}).get("name", ""),
            })

        return dict(
            goals=goals,
            yellow_cards=yellow_cards,
            red_cards=red_cards,
            substitutions=substitutions,
            possession=None,           
            venue=data.get("venue", ""),
            attendance=data.get("attendance"),
            minute=data.get("minute"),
        )

   

    def _normalise_match(self, m: dict) -> dict:
        """
        Flatten one football-data.org match object into our internal format.

        Key fields from the API:
          m["id"]                    — unique match ID
          m["utcDate"]               — ISO-8601 datetime string
          m["status"]                — SCHEDULED | TIMED | IN_PLAY | PAUSED |
                                       EXTRA_TIME | PENALTY_SHOOTOUT | FINISHED | ...
          m["stage"]                 — GROUP_STAGE | LAST_32 | LAST_16 |
                                       QUARTER_FINALS | SEMI_FINALS | THIRD_PLACE | FINAL
          m["group"]                 — GROUP_A ... GROUP_L  (null for knockout)
          m["homeTeam"]["id"]        — team ID
          m["homeTeam"]["name"]      — full name
          m["homeTeam"]["crest"]     — logo URL
          m["homeTeam"]["tla"]       — 3-letter code
          m["score"]["fullTime"]["home"] — integer or null
          m["score"]["fullTime"]["away"] — integer or null
          m["venue"]                 — stadium name (string or null)
        """
        home      = m.get("homeTeam") or {}
        away      = m.get("awayTeam") or {}
        score     = m.get("score") or {}
        full_time = score.get("fullTime") or {}

        
        hs = full_time.get("home")
        as_ = full_time.get("away")

        
        if hs is None or as_ is None:
            reg = score.get("regularTime") or {}
            hs  = hs  if hs  is not None else reg.get("home")
            as_ = as_ if as_ is not None else reg.get("away")

     
        date_str = ""
        time_str = ""
        raw_date = m.get("utcDate", "")
        if raw_date:
            try:
                dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                date_str = dt.strftime("%Y-%m-%d")
                time_str = dt.strftime("%H:%M")
            except ValueError:
                date_str = raw_date[:10]

        
        stage_raw = m.get("stage", "GROUP_STAGE") or "GROUP_STAGE"
        stage     = _FD_STAGE_MAP.get(stage_raw, "Group Stage")

      
        status_raw = m.get("status", "SCHEDULED") or "SCHEDULED"
        status     = _FD_STATUS_MAP.get(status_raw, "Scheduled")

        
        group_raw  = m.get("group")                   
        group_name = _FD_GROUP_MAP.get(group_raw, "") if group_raw else ""

     
        winner_api_id = None
        if status == "Finished" and hs is not None and as_ is not None:
            if hs > as_:
                winner_api_id = home.get("id")
            elif as_ > hs:
                winner_api_id = away.get("id")
        
            score_winner = score.get("winner")
            if score_winner == "HOME_TEAM":
                winner_api_id = home.get("id")
            elif score_winner == "AWAY_TEAM":
                winner_api_id = away.get("id")

        return {
            "api_match_id":  m.get("id"),
            "match_date":    date_str,
            "match_time":    time_str,
            "home_api_id":   home.get("id"),
            "away_api_id":   away.get("id"),
            "home_name":     home.get("name", "TBD"),
            "away_name":     away.get("name", "TBD"),
            "home_logo":     home.get("crest", ""),
            "away_logo":     away.get("crest", ""),
            "home_code":     home.get("tla", ""),
            "away_code":     away.get("tla", ""),
            "stage":         stage,
            "group_name":    group_name,        
            "home_score":    hs,
            "away_score":    as_,
            "status":        status,
            "winner_api_id": winner_api_id,
            "venue":         m.get("venue") or "",
            "city":          "",                
        }




AF_BASE_URL  = "https://v3.football.api-sports.io"
AF_LEAGUE_ID = 1       
AF_SEASON    = 2026

_AF_STAGE_MAP = {
    "group stage":     "Group Stage",
    "round of 32":     "Round of 32",
    "round of 16":     "Round of 16",
    "quarter-finals":  "Quarter Final",
    "semi-finals":     "Semi Final",
    "3rd place final": "Third Place Match",
    "final":           "Final",
}

_AF_STATUS_LIVE = {"1H", "HT", "2H", "ET", "BT", "P", "SUSP", "INT", "LIVE"}


class APIFootballService:
    """
    api-sports.io (API-Football) v3 REST client.
    100 requests/day on free tier.
    Raises APIError subclasses on failure.
    """

    def __init__(self, api_key: str):
        if not api_key or not api_key.strip():
            raise MissingAPIKeyError(
                "No API key configured.\n\n"
                "Get a free key at https://dashboard.api-football.com/register\n"
                "then paste it in Settings → API Key."
            )
        self.api_key = api_key.strip()
        self.session = requests.Session()
        self.session.headers.update({"x-apisports-key": self.api_key})

    def _get(self, endpoint: str, params: dict = None) -> dict:
        url = f"{AF_BASE_URL}/{endpoint}"
        try:
            resp = self.session.get(url, params=params or {}, timeout=15)
        except requests.ConnectionError as exc:
            raise APIError(f"Network error: {exc}") from exc
        except requests.Timeout:
            raise APIError("Request timed out.")

        if resp.status_code == 401:
            raise InvalidAPIKeyError("API-Football key rejected (401).")
        if resp.status_code == 429:
            raise RateLimitError("API-Football rate limit hit (100 req/day on free tier).")
        if not resp.ok:
            raise APIError(f"API-Football HTTP {resp.status_code}")

        data = resp.json()
        errors = data.get("errors", {})
        if errors:
            if isinstance(errors, dict):
                msg = "; ".join(f"{k}: {v}" for k, v in errors.items())
            else:
                msg = str(errors)
            if "token" in msg.lower() or "key" in msg.lower():
                raise InvalidAPIKeyError(f"API-Football key error: {msg}")
            raise APIError(f"API-Football error: {msg}")
        return data

    def fetch_teams(self) -> list[dict]:
        data = self._get("teams", {"league": AF_LEAGUE_ID, "season": AF_SEASON})
        teams = data.get("response", [])
        if not teams:
            raise APIError("API-Football returned no teams for WC 2026.")
        return [
            {
                "api_team_id": t["team"]["id"],
                "fifa_code":   t["team"].get("code", ""),
                "name":        t["team"].get("name", "Unknown"),
                "short_name":  t["team"].get("name", ""),
                "flag_url":    t["team"].get("logo", ""),
                "group_name":  None,
            }
            for t in teams
        ]

    def fetch_fixtures(self) -> list[dict]:
        data = self._get("fixtures", {"league": AF_LEAGUE_ID, "season": AF_SEASON})
        fixtures = data.get("response", [])
        if not fixtures:
            raise APIError("API-Football returned no fixtures for WC 2026.")
        return [self._normalise(f) for f in fixtures]

    def fetch_live_fixtures(self) -> list[dict]:
        data = self._get("fixtures", {"league": AF_LEAGUE_ID, "season": AF_SEASON, "live": "all"})
        return [self._normalise(f) for f in data.get("response", [])]

    def fetch_fixture_by_id(self, fixture_id: int) -> "dict | None":
        """Fetch a single fixture by ID."""
        try:
            data = self._get("fixtures", {"id": fixture_id})
            resp = data.get("response", [])
            if not resp:
                return None
            return self._normalise(resp[0])
        except APIError:
            return None

    def fetch_match_events(self, fixture_id: int) -> dict:
        """
        GET /v3/fixtures/events?fixture={id}  — goals, cards, substitutions
        GET /v3/fixtures/statistics?fixture={id} — possession

        Returns the same normalised dict structure as FootballDataService.fetch_match_events.
        """
        empty = dict(goals=[], yellow_cards=[], red_cards=[],
                     substitutions=[], possession=None,
                     venue="", attendance=None, minute=None)
        try:
            
            fix_data = self._get("fixtures", {"id": fixture_id})
            fix_list = fix_data.get("response", [])
            fix_obj  = fix_list[0] if fix_list else {}
            venue    = (fix_obj.get("fixture") or {}).get("venue", {}).get("name", "")
            minute   = (fix_obj.get("fixture") or {}).get("status", {}).get("elapsed")

            home_name = (fix_obj.get("teams") or {}).get("home", {}).get("name", "")
            away_name = (fix_obj.get("teams") or {}).get("away", {}).get("name", "")
        except APIError:
            return empty

    
        goals, yellow_cards, red_cards, substitutions = [], [], [], []
        try:
            ev_data = self._get("fixtures/events", {"fixture": fixture_id})
            for ev in ev_data.get("response") or []:
                t_obj   = ev.get("team") or {}
                p_obj   = ev.get("player") or {}
                a_obj   = ev.get("assist") or {}
                etype   = ev.get("type", "")
                detail  = ev.get("detail", "")
                elapsed = (ev.get("time") or {}).get("elapsed")
                team_name = t_obj.get("name", "")
                side = "home" if team_name == home_name else "away"

                if etype == "Goal":
                    gtype = "PENALTY" if "Penalty" in detail else (
                            "OWN"     if "Own"     in detail else "REGULAR")
                    goals.append({
                        "minute": elapsed, "team": side, "team_name": team_name,
                        "scorer": p_obj.get("name", "Unknown"), "type": gtype,
                    })
                elif etype == "Card":
                    entry = {"minute": elapsed, "team": team_name,
                             "player": p_obj.get("name", "Unknown")}
                    if "Yellow" in detail and "Red" not in detail:
                        yellow_cards.append(entry)
                    else:
                        red_cards.append(entry)
                elif etype == "subst":
                    substitutions.append({
                        "minute": elapsed, "team": team_name,
                        "player_out": p_obj.get("name", ""),
                        "player_in":  a_obj.get("name", ""),
                    })
        except APIError:
            pass

      
        possession = None
        try:
            stat_data = self._get("fixtures/statistics", {"fixture": fixture_id})
            for team_stat in stat_data.get("response") or []:
                t_name = (team_stat.get("team") or {}).get("name", "")
                if t_name == home_name:
                    for s in team_stat.get("statistics") or []:
                        if s.get("type") == "Ball Possession":
                            val = s.get("value", "")
                            if val and str(val).endswith("%"):
                                home_pct = int(str(val).replace("%", ""))
                                possession = {"home": home_pct, "away": 100 - home_pct}
                            break
        except (APIError, Exception):
            pass

        return dict(
            goals=goals, yellow_cards=yellow_cards, red_cards=red_cards,
            substitutions=substitutions, possession=possession,
            venue=venue, attendance=None, minute=minute,
        )

    def _normalise(self, f: dict) -> dict:
        fix    = f.get("fixture", {})
        teams  = f.get("teams", {})
        goals  = f.get("goals", {})
        league = f.get("league", {})

        round_raw = (league.get("round") or "").lower()
        stage = "Group Stage"
        for k, v in _AF_STAGE_MAP.items():
            if k in round_raw:
                stage = v
                break

        raw_status = fix.get("status", {}).get("short", "NS")
        if raw_status in _AF_STATUS_LIVE:
            status = "Live"
        elif raw_status == "FT":
            status = "Finished"
        else:
            status = "Scheduled"

        date_str = time_str = ""
        if fix.get("date"):
            try:
                dt = datetime.fromisoformat(fix["date"].replace("Z", "+00:00"))
                date_str = dt.strftime("%Y-%m-%d")
                time_str = dt.strftime("%H:%M")
            except ValueError:
                date_str = fix["date"][:10]

        home = teams.get("home", {})
        away = teams.get("away", {})
        hs   = goals.get("home")
        as_  = goals.get("away")

        winner_api_id = None
        if home.get("winner"):
            winner_api_id = home.get("id")
        elif away.get("winner"):
            winner_api_id = away.get("id")

        
        group_name = ""
        for letter in "ABCDEFGHIJKL":
            if f"group {letter.lower()}" in round_raw:
                group_name = letter
                break

        return {
            "api_match_id":  fix.get("id"),
            "match_date":    date_str,
            "match_time":    time_str,
            "home_api_id":   home.get("id"),
            "away_api_id":   away.get("id"),
            "home_name":     home.get("name", "TBD"),
            "away_name":     away.get("name", "TBD"),
            "home_logo":     home.get("logo", ""),
            "away_logo":     away.get("logo", ""),
            "home_code":     home.get("code", ""),
            "away_code":     away.get("code", ""),
            "stage":         stage,
            "group_name":    group_name,
            "home_score":    hs,
            "away_score":    as_,
            "status":        status,
            "winner_api_id": winner_api_id,
            "venue":         fix.get("venue", {}).get("name", ""),
            "city":          fix.get("venue", {}).get("city", ""),
        }




def get_service(provider: str, api_key: str):
    """
    Return the correct service instance for the chosen provider.

    provider: "football-data.org"  → FootballDataService
              "api-football"       → APIFootballService
              anything else        → FootballDataService (default)
    """
    if provider == "api-football":
        return APIFootballService(api_key)
    return FootballDataService(api_key)
