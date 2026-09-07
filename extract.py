"""
Extract HostedSports API responses and save them in their raw format.
"""

import re
from pathlib import Path
from typing import Any, Callable, Optional

from client import Client, InvalidJSONResponseError
from config import RAW_DATA_DIR
from utils import find_game_ids, find_values_by_key, save_json


PLAYER_ID_KEY_PATTERN = re.compile(r"^player\d+$", re.IGNORECASE)


def extract_and_save(
    fetch_func: Callable[[], Any],
    output_path: Path,
    description: str,
):
    """
    Fetch data from an API endpoint and save it as raw JSON.

    If invalid JSON is returned, save the raw response to an
    .invalid.txt file.

    If any other request error occurs, log it and continue.

    Returns:
        API response if successful, otherwise None.
    """
    try:
        data = fetch_func()

        save_json(
            data,
            output_path,
        )

        print(f"✓ {description}")

        return data

    except InvalidJSONResponseError as error:
        invalid_path = output_path.with_suffix(
            ".invalid.txt"
        )

        invalid_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        invalid_path.write_text(
            error.raw_text,
            encoding="utf-8",
        )

        print(
            f"✗ {description}: invalid JSON "
            f"(raw response saved to {invalid_path})"
        )

        return None

    except Exception as error:
        print(
            f"✗ {description}: {error}"
        )

        return None


def find_player_ids(data: Any) -> list[str]:
    """
    Find player IDs inside HostedSports roster responses.

    HostedSports roster files use dynamic keys such as:

        player1
        player2
        player3

    Example:

        {
            "player1": "uuid-here",
            "Number": "0",
            "Name": "Player Name"
        }

    Returns:
        Deduplicated player IDs in source order.
    """
    player_ids = []

    if isinstance(data, dict):
        for key, value in data.items():
            if (
                PLAYER_ID_KEY_PATTERN.fullmatch(str(key))
                and isinstance(value, str)
                and value.strip()
            ):
                player_ids.append(
                    value.strip()
                )

            player_ids.extend(
                find_player_ids(value)
            )

    elif isinstance(data, list):
        for item in data:
            player_ids.extend(
                find_player_ids(item)
            )

    return list(
        dict.fromkeys(player_ids)
    )


def extract_rosters(
    client: Client,
    league: str,
    season: int,
    team_ids: list[str],
) -> dict[str, Any]:
    """
    Extract rosters for every team in a league/season.

    Returns:
        Dictionary keyed by team ID containing only successfully
        extracted roster responses.

    Teams with unpublished or invalid rosters are omitted.
    """
    root = (
        RAW_DATA_DIR
        / league
        / str(season)
        / "rosters"
    )

    root.mkdir(
        parents=True,
        exist_ok=True,
    )

    rosters = {}

    for team_id in team_ids:
        roster = extract_and_save(
            lambda team_id=team_id: client.get_team_roster(
                team_id,
                league,
                season,
            ),
            root / f"{team_id}.json",
            f"Roster {team_id}",
        )

        if roster is not None:
            rosters[team_id] = roster

    return rosters


def extract_games(
    client: Client,
    league: str,
    season: int,
    schedule: Any,
) -> int:
    """
    Extract game-level statistics for all games in the schedule.

    Game IDs are discovered from dynamic keys such as:

        game1
        game2
        game3
    """
    root = (
        RAW_DATA_DIR
        / league
        / str(season)
        / "games"
    )

    root.mkdir(
        parents=True,
        exist_ok=True,
    )

    game_ids = find_game_ids(
        schedule
    )

    game_ids = list(
        dict.fromkeys(game_ids)
    )

    print(
        f"Found {len(game_ids)} games."
    )

    successful = 0

    for game_id in game_ids:
        stats = extract_and_save(
            lambda game_id=game_id: client.get_game_stats(
                game_id,
                season,
            ),
            root / f"{game_id}.json",
            f"Game {game_id}",
        )

        if stats is not None:
            successful += 1

    return successful


def extract_players(
    client: Client,
    league: str,
    season: int,
    rosters: dict[str, Any],
):
    """
    Extract player profile and season-stat data for rostered players.

    Uses the roster responses already downloaded by extract_rosters()
    instead of requesting every roster a second time.
    """
    root = (
        RAW_DATA_DIR
        / league
        / str(season)
        / "players"
    )

    root.mkdir(
        parents=True,
        exist_ok=True,
    )

    all_player_ids = []

    for team_id, roster in rosters.items():
        player_ids = find_player_ids(
            roster
        )

        print(
            f"Found {len(player_ids)} players "
            f"on team {team_id}."
        )

        all_player_ids.extend(
            player_ids
        )

    # A player should only need one player-info/stat request
    # per league and season even if somehow present in multiple
    # roster responses.
    all_player_ids = list(
        dict.fromkeys(all_player_ids)
    )

    print(
        f"Extracting data for "
        f"{len(all_player_ids)} unique players..."
    )

    for player_id in all_player_ids:
        player_root = (
            root
            / str(player_id)
        )

        player_root.mkdir(
            parents=True,
            exist_ok=True,
        )

        extract_and_save(
            lambda player_id=player_id: client.get_player_info(
                player_id,
                league,
                season,
            ),
            player_root / "info.json",
            f"Player info {player_id}",
        )

        extract_and_save(
            lambda player_id=player_id: client.get_player_stats(
                player_id,
                league,
                season,
            ),
            player_root / "stats.json",
            f"Player stats {player_id}",
        )


def extract_league_season(
    client: Client,
    league: str,
    season: int,
    tier: Optional[str] = None,
):
    """
    Extract all available data for one league and season.

    Extraction order:

        teams
          ↓
        team IDs
          ↓
        rosters
          ↓
        player IDs
          ↓
        player information
        player season statistics

        schedule
          ↓
        game IDs
          ↓
        game statistics

        standings
        team statistics
        offensive statistics
        defensive statistics
        special teams statistics
        scoring statistics
    """
    root = (
        RAW_DATA_DIR
        / league
        / str(season)
    )

    root.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("\n" + "=" * 60)
    print(
        f"Extracting {league.upper()} season {season}"
    )
    print("=" * 60)

    # --------------------------------------------------
    # Teams
    # --------------------------------------------------

    teams = extract_and_save(
        lambda: client.get_league_teams(
            league,
            season,
            tier=tier,
        ),
        root / "teams.json",
        f"{league} {season} teams",
    )

    team_ids = []
    rosters = {}

    if teams is not None:
        team_ids = find_values_by_key(
            teams,
            "id",
        )

        team_ids = [
            str(team_id)
            for team_id in team_ids
            if team_id
        ]

        team_ids = list(
            dict.fromkeys(team_ids)
        )

        print(
            f"Found {len(team_ids)} teams."
        )

        # ----------------------------------------------
        # Rosters
        # ----------------------------------------------

        rosters = extract_rosters(
            client=client,
            league=league,
            season=season,
            team_ids=team_ids,
        )

        print(
            f"Successfully extracted "
            f"{len(rosters)} of "
            f"{len(team_ids)} rosters."
        )

        # ----------------------------------------------
        # Players
        # ----------------------------------------------

        if rosters:
            extract_players(
                client=client,
                league=league,
                season=season,
                rosters=rosters,
            )

        else:
            print(
                f"Skipping players for "
                f"{league} {season}: "
                f"no usable roster data."
            )

    else:
        print(
            f"Skipping rosters and players for "
            f"{league} {season}: "
            f"team data unavailable."
        )

    # --------------------------------------------------
    # Schedule
    # --------------------------------------------------

    schedule = extract_and_save(
        lambda: client.get_league_current_season_schedule(
            league,
            season,
        ),
        root / "schedule.json",
        f"{league} {season} schedule",
    )

    if schedule is not None:
        extract_games(
            client=client,
            league=league,
            season=season,
            schedule=schedule,
        )

    else:
        print(
            f"Skipping game extraction for "
            f"{league} {season}: "
            f"schedule unavailable."
        )

    # --------------------------------------------------
    # Standings
    # --------------------------------------------------

    extract_and_save(
        lambda: client.get_league_standings(
            league,
            season,
        ),
        root / "standings.json",
        f"{league} {season} standings",
    )

    # --------------------------------------------------
    # Team Stats
    # --------------------------------------------------

    extract_and_save(
        lambda: client.get_team_stats(
            league,
            season,
            tier=tier,
        ),
        root / "team_stats.json",
        f"{league} {season} team stats",
    )

    # --------------------------------------------------
    # Offensive Stats
    # --------------------------------------------------

    extract_and_save(
        lambda: client.get_offensive_stats(
            league,
            season,
            tier=tier,
        ),
        root / "offensive_stats.json",
        f"{league} {season} offensive stats",
    )

    # --------------------------------------------------
    # Defensive Stats
    # --------------------------------------------------

    extract_and_save(
        lambda: client.get_defensive_stats(
            league,
            season,
            tier=tier,
        ),
        root / "defensive_stats.json",
        f"{league} {season} defensive stats",
    )

    # --------------------------------------------------
    # Special Teams Stats
    # --------------------------------------------------

    extract_and_save(
        lambda: client.get_special_teams_stats(
            league,
            season,
            tier=tier,
        ),
        root / "special_teams_stats.json",
        f"{league} {season} special teams stats",
    )

    # --------------------------------------------------
    # Scoring Stats
    # --------------------------------------------------

    extract_and_save(
        lambda: client.get_scoring_stats(
            league,
            season,
            tier=tier,
        ),
        root / "scoring_stats.json",
        f"{league} {season} scoring stats",
    )

    print("\n" + "-" * 60)
    print(
        f"Finished {league.upper()} season {season}"
    )
    print("-" * 60)