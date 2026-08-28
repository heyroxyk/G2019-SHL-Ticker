"""Pull every player a member has ever iced into data.json and archive.json.

Two hosts. The portal knows who the member is and which players they own, and
carries the award and draft history. The index is the sim's output and supplies
the on-ice numbers.

Retired careers cannot change, so they are captured once into archive.json and
never fetched again. Only active players are re-fetched nightly. Awards are the
exception: they stay in the nightly file for everyone, because it is a single
call and a player who retires in the offseason can still be voted an award for
their last season.

Because a frozen player is never fetched again, the archive has to be
self-contained: it carries the club records its own players need. Leaving those
in the nightly file looked fine on the first run and then quietly dropped every
retired player's club colours on the second.

Neither file holds anything derived or formatted, and neither holds a
timestamp. That keeps them byte-stable between runs, so the workflow can skip
the commit when nothing moved and the log stays a dated record of progression.

Run with --recapture to re-fetch frozen players anyway, which is what to reach
for if the index ever corrects a historical season.
"""
import json
import pathlib
import sys
import urllib.error
import urllib.request

USER_ID = 5745  # portal uid; the forum username is G2019

PORTAL = "https://portal.simulationhockey.com/api/v1"
INDEX = "https://index.simulationhockey.com/api"

# The portal answers 403 to urllib's default "Python-urllib/3.x". Identify the
# job and where it comes from, so whoever runs the API can see who is calling.
USER_AGENT = "G2019-SHL-Ticker/1.0 (+https://github.com/heyroxyk/G2019-SHL-Ticker)"

# The index numbers its leagues in /api/v1/leagues, and the portal's own
# indexRecords use the same numbering, so one map serves both hosts.
LEAGUE_IDS = {"SHL": 0, "SMJHL": 1, "IIHF": 2, "WJC": 3}
LEAGUE_NAMES = {value: key for key, value in LEAGUE_IDS.items()}

# Only these two are clubs. IIHF and WJC are tournaments whose "teams" are
# nations that change most years, so a stint there means nothing; they are
# counted as selections instead.
CLUB_LEAGUES = ("SHL", "SMJHL")

# Positions the portal supplies. Anything else is a placeholder to be filled in
# from the index, which is the only source for a player who predates the portal.
PORTAL_POSITIONS = ("Goalie", "Center", "Left Wing", "Right Wing",
                    "Left Defense", "Right Defense")

# The index documents these as "rs", "ps" and "po". Those values are silently
# ignored and fall through to regular season, so passing them looks like it
# works while quietly returning the wrong phase. Only the full words select.
REGULAR = "regular"
PLAYOFFS = "playoffs"

# Summed across stints and checked against the career line the index reports
# independently. Anything not summable (gaa, savePct) is derived at build time
# from these, never stored.
SKATER_FIELDS = (
    "gamesPlayed", "goals", "assists", "points", "plusMinus", "pim", "hits",
    "shotsBlocked", "takeaways", "giveaways", "shotsOnGoal", "timeOnIce",
    "ppPoints", "shPoints",
)
GOALIE_FIELDS = (
    "gamesPlayed", "minutes", "wins", "losses", "ot", "shotsAgainst", "saves",
    "goalsAgainst", "shutouts",
)

HERE = pathlib.Path(__file__).parent
DATA_PATH = HERE / "data.json"
ARCHIVE_PATH = HERE / "archive.json"


class ShapeError(Exception):
    """The API answered, but not with what we need to build a valid ticker."""


def get_json(url):
    request = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": USER_AGENT}
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            if response.status != 200:
                raise ShapeError(f"{url} returned HTTP {response.status}")
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise ShapeError(f"{url} unreachable: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ShapeError(f"{url} returned malformed JSON: {exc}") from exc


def kind_for(is_goalie):
    return "goalies" if is_goalie else "players"


def fields_for(is_goalie):
    return GOALIE_FIELDS if is_goalie else SKATER_FIELDS


# --------------------------------------------------------------------------
# portal
# --------------------------------------------------------------------------

def fetch_portal_players():
    payload = get_json(f"{PORTAL}/player?uid={USER_ID}")
    if not isinstance(payload, list) or not payload:
        raise ShapeError(f"portal /player?uid={USER_ID} returned no players")
    for record in payload:
        missing = [f for f in ("pid", "name", "position", "status") if f not in record]
        if missing:
            raise ShapeError(f"portal player record is missing {', '.join(missing)}")
    return payload


def fetch_history(path):
    payload = get_json(f"{PORTAL}/{path}?uid={USER_ID}")
    if not isinstance(payload, list):
        raise ShapeError(f"portal /{path} did not return a list")
    return payload


# --------------------------------------------------------------------------
# index
# --------------------------------------------------------------------------

def season_log(is_goalie, index_id, league_id, phase):
    """Every season this player actually played, oldest first. Empty is legal."""
    url = (f"{INDEX}/v1/{kind_for(is_goalie)}/stats/{index_id}"
           f"?league={league_id}&type={phase}")
    rows = get_json(url)
    if not isinstance(rows, list):
        raise ShapeError(f"index {phase} log for {index_id} is not a list")
    played = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if not isinstance(row.get("gamesPlayed"), int) or row["gamesPlayed"] <= 0:
            continue
        if not isinstance(row.get("season"), int) or not isinstance(row.get("team"), str):
            raise ShapeError(f"index {phase} row for {index_id} has no usable season/team")
        played.append(row)
    return sorted(played, key=lambda row: row["season"])


def career_line(is_goalie, index_id, league_id, phase):
    """The index's own career aggregate, used to check our stint arithmetic."""
    url = (f"{INDEX}/v1/{kind_for(is_goalie)}/stats/allTime"
           f"?playerID={index_id}&league={league_id}&type={phase}&grouped=true")
    rows = get_json(url)
    if not isinstance(rows, list) or not rows:
        return None
    return rows[0]


def totals(rows, is_goalie):
    """Sum the fields we keep. Null in a historical row counts as zero."""
    return {
        field: sum(row.get(field) or 0 for row in rows)
        for field in fields_for(is_goalie)
    }


def check_against_career(summed, career, where, is_goalie):
    """Our stints must reproduce the aggregate the index reports on its own.

    This check is free and it is real evidence rather than a restatement: the
    two figures come from different endpoints, so agreement means the stint
    split actually reconstructs the career.
    """
    if career is None:
        return
    problems = []
    for field in fields_for(is_goalie):
        reported = career.get(field)
        if isinstance(reported, (int, float)) and summed[field] != reported:
            problems.append(f"{field} stints={summed[field]} index={reported}")
    if problems:
        raise ShapeError(f"{where}: stint totals disagree with the index career "
                         f"line: {'; '.join(problems)}")


def build_league(is_goalie, index_id, league_id, where):
    """Club stints for one league, merged by team.

    A player who returns to a former club is one stint with a gapped season
    range, not two. 225 of 3198 SHL careers have done this, so it is common
    enough that two separate entries would clutter the rotation.
    """
    regular = season_log(is_goalie, index_id, league_id, REGULAR)
    if not regular:
        return None
    playoffs = season_log(is_goalie, index_id, league_id, PLAYOFFS)

    by_team, playoff_by_team = {}, {}
    for row in regular:
        by_team.setdefault(row["team"], []).append(row)
    for row in playoffs:
        playoff_by_team.setdefault(row["team"], []).append(row)

    stints = []
    for team, rows in by_team.items():
        team_ids = sorted({r["teamID"] for r in rows if isinstance(r.get("teamID"), int)})
        stint = {
            "team": team,
            "teamID": team_ids[-1] if team_ids else None,
            "seasons": sorted(row["season"] for row in rows),
            "regular": totals(rows, is_goalie),
        }
        if team in playoff_by_team:
            stint["playoffs"] = totals(playoff_by_team[team], is_goalie)
        stints.append(stint)
    stints.sort(key=lambda stint: stint["seasons"][0])

    check_against_career(totals(regular, is_goalie),
                         career_line(is_goalie, index_id, league_id, REGULAR),
                         f"{where} regular season", is_goalie)
    if playoffs:
        check_against_career(totals(playoffs, is_goalie),
                             career_line(is_goalie, index_id, league_id, PLAYOFFS),
                             f"{where} playoffs", is_goalie)

    league = {
        "indexID": index_id,
        "stints": stints,
        "regular": totals(regular, is_goalie),
        # The newest season's position, because a career can change it and the
        # portal holds none at all for a player who predates it.
        "position": regular[-1].get("position") or "",
        "lastSeason": regular[-1]["season"],
    }
    if playoffs:
        league["playoffs"] = totals(playoffs, is_goalie)
    return league


def build_tournament(is_goalie, index_id, league_id):
    """Selections and the nations worn, which is all a tournament run means here."""
    rows = season_log(is_goalie, index_id, league_id, REGULAR)
    if not rows:
        return None
    return {
        "indexID": index_id,
        "selections": len(rows),
        "seasons": [row["season"] for row in rows],
        "nations": sorted({row["team"] for row in rows}),
    }


def fetch_team(team_id, league_id, season, cache):
    """Name and colours for one club. Cached: a career revisits the same clubs."""
    key = f"{league_id}:{team_id}"
    if key in cache:
        return
    team = get_json(f"{INDEX}/v1/teams/{team_id}?league={league_id}&season={season}")
    if not isinstance(team, dict) or "name" not in team:
        raise ShapeError(f"index /teams/{team_id}?league={league_id} returned no team")
    colors = team.get("colors") or {}
    cache[key] = {
        "name": team["name"],
        "abbreviation": team.get("abbreviation", ""),
        "primary": colors.get("primary", "#8a8a8a"),
        "secondary": colors.get("secondary", "#8a8a8a"),
    }


# --------------------------------------------------------------------------
# the player who predates the portal
# --------------------------------------------------------------------------

def index_names(league_id, cache):
    if league_id not in cache:
        rows = get_json(f"{INDEX}/v2/player/playerSearch?league={league_id}")
        if not isinstance(rows, list):
            raise ShapeError(f"index playerSearch for league {league_id} is not a list")
        cache[league_id] = rows
    return cache[league_id]


def corroborate(name, is_goalie, index_id, league_id, awards):
    """Does this index record actually belong to our member?

    Matching on name alone would happily attach a stranger's career to the
    signature, so every award the member holds for this player in this league
    has to line up with the index season log: same season, same team. A
    same-named stranger fails on the first one.

    Returns the pairs actually checked, so the run can report what the match
    was built on rather than just asserting that it passed.
    """
    pairs = sorted({
        (record["seasonID"], record["teamID"])
        for record in awards
        if record.get("playerName") == name
        and record.get("leagueID") == league_id
        and isinstance(record.get("seasonID"), int)
        and isinstance(record.get("teamID"), int)
    })
    if not pairs:
        return []

    log = {(row["season"], row.get("teamID")) for row in
           season_log(is_goalie, index_id, league_id, REGULAR)}
    unmatched = [pair for pair in pairs if pair not in log]
    if unmatched:
        listed = ", ".join(f"S{season} team {team}" for season, team in unmatched)
        raise ShapeError(
            f"refusing to claim index record {index_id} in "
            f"{LEAGUE_NAMES[league_id]} as {name!r}: the member holds awards for "
            f"{listed}, which that record's season log does not contain"
        )
    return pairs


def find_pre_portal(name, is_goalie, awards, name_cache):
    """Locate a player the portal has no record of, and prove the match.

    Players who retired before the portal existed survive only in the index and
    in the member's own award history. The index can be searched by name; the
    award history is what turns that guess into evidence.
    """
    found, evidence = {}, {}
    for league, league_id in LEAGUE_IDS.items():
        matches = [row for row in index_names(league_id, name_cache)
                   if row.get("Name") == name]
        if not matches:
            continue
        if len(matches) > 1:
            ids = ", ".join(str(row.get("PlayerID")) for row in matches)
            raise ShapeError(
                f"{name!r} matches {len(matches)} index records in {league} "
                f"({ids}); refusing to guess which one is the member's"
            )
        index_id = matches[0]["PlayerID"]
        evidence[league] = corroborate(name, is_goalie, index_id, league_id, awards)
        found[league] = index_id
    return found, evidence


# --------------------------------------------------------------------------
# assembling a career
# --------------------------------------------------------------------------

def career_block(name, position, status, pid, index_ids):
    """One player's whole record, plus the club records it depends on."""
    is_goalie = position == "Goalie"
    block = {
        "name": name,
        "pid": pid,
        "position": position,
        "isGoalie": is_goalie,
        "status": status,
        "leagues": {},
        "tournaments": {},
    }
    teams = {}
    newest = (-1, "")
    for league, index_id in sorted(index_ids.items(), key=lambda kv: LEAGUE_IDS[kv[0]]):
        league_id = LEAGUE_IDS[league]
        if league in CLUB_LEAGUES:
            built = build_league(is_goalie, index_id, league_id, f"{name} {league}")
            if not built:
                continue
            block["leagues"][league] = built
            if built["lastSeason"] > newest[0]:
                newest = (built["lastSeason"], built["position"])
            for stint in built["stints"]:
                if stint["teamID"] is not None:
                    fetch_team(stint["teamID"], league_id, stint["seasons"][-1], teams)
        else:
            built = build_tournament(is_goalie, index_id, league_id)
            if built:
                block["tournaments"][league] = built

    if position not in PORTAL_POSITIONS and newest[1]:
        block["position"] = newest[1]
    return block, teams


def index_ids_from_portal(player):
    """Which index records the portal says exist for this player.

    A player can sit on a roster with no index record in that league yet: a
    call-up joins a club before the sim has ever iced them. That league simply
    appears on its own once they play, so it is not an error.
    """
    found = {}
    for record in player.get("indexRecords") or []:
        if not isinstance(record, dict):
            continue
        league_id, index_id = record.get("leagueID"), record.get("indexID")
        if isinstance(league_id, int) and isinstance(index_id, int):
            if league_id in LEAGUE_NAMES:
                found[LEAGUE_NAMES[league_id]] = index_id
    return found


def load_archive(recapture):
    if recapture or not ARCHIVE_PATH.exists():
        return {}, {}
    stored = json.loads(ARCHIVE_PATH.read_text(encoding="utf-8"))
    return ({block["name"]: block for block in stored.get("players", [])},
            dict(stored.get("teams", {})))


def collect(recapture=False):
    portal_players = fetch_portal_players()
    awards = fetch_history("history/player")
    drafts = fetch_history("history/draft")

    archive, archive_teams = load_archive(recapture)
    active, active_teams, notes = [], {}, []
    name_cache = {}

    for player in portal_players:
        name, status = player["name"], player["status"]
        if status == "retired" and name in archive:
            notes.append(f"{name}: retired, already archived, not fetched")
            continue
        block, teams = career_block(name, player["position"], status, player["pid"],
                                    index_ids_from_portal(player))
        if status == "retired":
            archive[name] = block
            archive_teams.update(teams)
            notes.append(f"{name}: retired, captured and frozen")
        else:
            active.append(block)
            active_teams.update(teams)
            notes.append(f"{name}: active, refreshed")

    # Anyone the award or draft history names who the portal has never heard
    # of. They retired before the portal existed, so they are frozen on sight.
    known = {player["name"] for player in portal_players}
    historical = sorted({
        record["playerName"] for record in awards + drafts
        if isinstance(record.get("playerName"), str)
        and record["playerName"] not in known
    })
    for name in historical:
        if name in archive:
            notes.append(f"{name}: pre-portal, already archived, not fetched")
            continue
        # The portal holds no position for them, and an award name is not a
        # reliable tell, so try the skater endpoints first and fall back.
        for is_goalie in (False, True):
            index_ids, evidence = find_pre_portal(name, is_goalie, awards, name_cache)
            if index_ids:
                break
        if not index_ids:
            notes.append(f"{name}: pre-portal, no index record found, skipped")
            continue
        checked = sum(len(pairs) for pairs in evidence.values())
        where = ", ".join(f"{league} {len(pairs)}" for league, pairs in evidence.items())
        notes.append(f"{name}: pre-portal, matched by name and corroborated against "
                     f"{checked} award records ({where})")
        block, teams = career_block(name, "Goalie" if is_goalie else "Skater",
                                    "retired", None, index_ids)
        archive[name] = block
        archive_teams.update(teams)

    data = {
        "user": {"uid": USER_ID, "username": portal_players[0].get("username", "")},
        "players": sorted(active, key=lambda block: block["name"]),
        "awards": awards,
        "drafts": drafts,
        "teams": active_teams,
    }
    frozen = {
        "players": sorted(archive.values(), key=lambda block: block["name"]),
        # Carried here so a frozen player never depends on a fetch that will
        # not happen again.
        "teams": archive_teams,
    }
    return data, frozen, notes


def write_stable(path, payload):
    """sort_keys and a trailing newline keep the file byte-identical between
    runs, so an unchanged API produces an unchanged file and the workflow can
    tell the difference."""
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8", newline="\n")


def main(argv):
    recapture = "--recapture" in argv
    try:
        data, frozen, notes = collect(recapture)
    except ShapeError as exc:
        print(f"fetch failed: {exc}", file=sys.stderr)
        return 1

    write_stable(DATA_PATH, data)
    write_stable(ARCHIVE_PATH, frozen)

    for note in notes:
        print(f"  {note}")
    blocks = data["players"] + frozen["players"]
    stints = sum(len(league["stints"]) for block in blocks
                 for league in block["leagues"].values())
    print(f"{data['user']['username']}: {len(data['players'])} active, "
          f"{len(frozen['players'])} archived, {stints} club stints across "
          f"{len(data['teams']) + len(frozen['teams'])} clubs, "
          f"{len(data['awards'])} award records")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
