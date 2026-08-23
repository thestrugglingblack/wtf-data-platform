"""
Saves the API response in its raw format.
"""

from pathlib import Path
from typing import Optional, Callable, Any

from client import Client, InvalidJSONResponseError
from utils import find_values_by_key, save_json, find_game_ids
from config import RAW_DATA_DIR


def extract_and_save(
    fetch_func: Callable[[], Any],
    output_path: Path,
    description: str
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
            output_path
        )

        print(f"✓ {description}")

        return data

    except InvalidJSONResponseError as e:
        invalid_path = output_path.with_suffix(
            ".invalid.txt"
        )

        invalid_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        invalid_path.write_text(
            e.raw_text,
            encoding="utf-8"
        )

        print(
            f"✗ {description}: invalid JSON "
            f"(raw response saved to {invalid_path})"
        )

        return None

    except Exception as e:
        print(f"✗ {description}: {e}")
        return None


def extract_rosters(
    client: Client,
    league: str,
    season: int,
    team_ids: list[str]
):
    """
    Extract rosters for every team in a league/season.
    """
    root = RAW_DATA_DIR / league / str(season) / "rosters"
    root.mkdir(parents=True, exist_ok=True)

    for team_id in team_ids:
        extract_and_save(
            lambda team_id=team_id: client.get_team_roster(
                team_id,
                league,
                season
            ),
            root / f"{team_id}.json",
            f"Roster {team_id}"
        )


def extract_games(
    client: Client,
    league: str,
    season: int,
    schedule
):
    """
    Extract game-level statistics for all games in the schedule.
    """
    root = RAW_DATA_DIR / league / str(season) / "games"
    root.mkdir(parents=True, exist_ok=True)

    game_ids = find_game_ids(schedule)

    # Deduplicate just in case
    game_ids = list(dict.fromkeys(game_ids))

    print(f"Found {len(game_ids)} games.")

    successful = 0

    for game_id in game_ids:
        stats = extract_and_save(
            lambda game_id=game_id: client.get_game_stats(
                game_id,
                season
            ),
            root / f"{game_id}.json",
            f"Game {game_id}"
        )

        if stats is not None:
            successful += 1

    return successful


def extract_players(
    client: Client,
    league: str,
    season: int,
    team_ids: list[str]
):
    """
    Extract player profile and season-stat data for each rostered player.
    """
    root = RAW_DATA_DIR / league / str(season) / "players"
    root.mkdir(parents=True, exist_ok=True)

    for team_id in team_ids:
        roster_path = (
            RAW_DATA_DIR
            / league
            / str(season)
            / "rosters"
            / f"{team_id}.json"
        )

        roster = extract_and_save(
            lambda team_id=team_id: client.get_team_roster(
                team_id,
                league,
                season
            ),
            roster_path,
            f"Roster {team_id}"
        )

        if roster is None:
            print(
                f"Skipping players for team {team_id}: "
                f"roster unavailable."
            )
            continue

        player_ids = find_values_by_key(
            roster,
            "UID"
        )

        player_ids = list(dict.fromkeys(player_ids))

        print(
            f"Extracting data for "
            f"{len(player_ids)} players "
            f"on team {team_id}..."
        )

        for player_id in player_ids:
            player_root = root / str(player_id)
            player_root.mkdir(
                parents=True,
                exist_ok=True
            )

            extract_and_save(
                lambda player_id=player_id: client.get_player_info(
                    player_id,
                    league,
                    season
                ),
                player_root / "info.json",
                f"Player info {player_id}"
            )

            extract_and_save(
                lambda player_id=player_id: client.get_player_stats(
                    player_id,
                    league,
                    season
                ),
                player_root / "stats.json",
                f"Player stats {player_id}"
            )


def extract_league_season(
    client: Client,
    league: str,
    season: int,
    tier: Optional[str] = None
):
    """
    Extract all available data for one league and season.

    Extraction order:

        teams
          ↓
        team IDs
          ↓
        rosters

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

    root = RAW_DATA_DIR / league / str(season)
    root.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 60)
    print(f"Extracting {league.upper()} season {season}")
    print("=" * 60)

    # --------------------------------------------------
    # Teams
    # --------------------------------------------------

    teams = extract_and_save(
        lambda: client.get_league_teams(
            league,
            season,
            tier=tier
        ),
        root / "teams.json",
        f"{league} {season} teams"
    )

    team_ids = []

    if teams is not None:
        team_ids = find_values_by_key(
            teams,
            "id"
        )

        team_ids = list(dict.fromkeys(team_ids))

        print(f"Found {len(team_ids)} teams.")

        extract_rosters(
            client=client,
            league=league,
            season=season,
            team_ids=team_ids
        )

    else:
        print(
            f"Skipping rosters for {league} {season}: "
            f"team data unavailable."
        )

    # --------------------------------------------------
    # Schedule
    # --------------------------------------------------

    schedule = extract_and_save(
        lambda: client.get_league_current_season_schedule(
            league,
            season
        ),
        root / "schedule.json",
        f"{league} {season} schedule"
    )

    if schedule is not None:
        extract_games(
            client=client,
            league=league,
            season=season,
            schedule=schedule
        )

    else:
        print(
            f"Skipping game extraction for "
            f"{league} {season}: schedule unavailable."
        )

    # --------------------------------------------------
    # Standings
    # --------------------------------------------------

    extract_and_save(
        lambda: client.get_league_standings(
            league,
            season
        ),
        root / "standings.json",
        f"{league} {season} standings"
    )

    # --------------------------------------------------
    # Team Stats
    # --------------------------------------------------

    extract_and_save(
        lambda: client.get_team_stats(
            league,
            season,
            tier=tier
        ),
        root / "team_stats.json",
        f"{league} {season} team stats"
    )

    # --------------------------------------------------
    # Offensive Stats
    # --------------------------------------------------

    extract_and_save(
        lambda: client.get_offensive_stats(
            league,
            season,
            tier=tier
        ),
        root / "offensive_stats.json",
        f"{league} {season} offensive stats"
    )

    # --------------------------------------------------
    # Defensive Stats
    # --------------------------------------------------

    extract_and_save(
        lambda: client.get_defensive_stats(
            league,
            season,
            tier=tier
        ),
        root / "defensive_stats.json",
        f"{league} {season} defensive stats"
    )

    # --------------------------------------------------
    # Special Teams Stats
    # --------------------------------------------------

    extract_and_save(
        lambda: client.get_special_teams_stats(
            league,
            season,
            tier=tier
        ),
        root / "special_teams_stats.json",
        f"{league} {season} special teams stats"
    )

    # --------------------------------------------------
    # Scoring Stats
    # --------------------------------------------------

    extract_and_save(
        lambda: client.get_scoring_stats(
            league,
            season,
            tier=tier
        ),
        root / "scoring_stats.json",
        f"{league} {season} scoring stats"
    )

    print("\n" + "-" * 60)
    print(f"Finished {league.upper()} season {season}")
    print("-" * 60)