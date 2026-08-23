"""
Saves the API response in its raw format.
"""

from pathlib import Path
from typing import Optional, Callable, Any

from client import Client
from utils import find_values_by_key, save_json, find_game_ids
from config import RAW_DATA_DIR


def extract_and_save(
    fetch_func: Callable[[], Any],
    output_path: Path,
    description: str
):
    """
    Fetch data from an API endpoint and save it as raw JSON.

    If the request fails, log the error and allow the rest of the
    extraction pipeline to continue.

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
        try:
            roster = client.get_team_roster(
                team_id,
                league,
                season
            )

            save_json(
                roster,
                root / f"{team_id}.json"
            )

            print(f"✓ Roster: {team_id}")

        except Exception as e:
            print(
                f"✗ Roster unavailable for team "
                f"{team_id}: {e}"
            )


def extract_games(
        client: Client,
        league: str,
        season: int,
        schedule
):
    root = RAW_DATA_DIR / league / str(season) / "games"
    root.mkdir(parents=True, exist_ok=True)

    game_ids = find_game_ids(schedule)

    # Deduplicate just in case
    game_ids = list(dict.fromkeys(game_ids))

    print(f"Found {len(game_ids)} games.")

    successful = 0

    for game_id in game_ids:
        try:
            stats = client.get_game_stats(
                game_id,
                season
            )

            save_json(
                stats,
                root / f"{game_id}.json"
            )

            successful += 1
            print(f"✓ Game: {game_id}")

        except Exception as e:
            print(
                f"✗ Game unavailable {game_id}: {e}"
            )

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
        try:
            roster = client.get_team_roster(
                team_id,
                league,
                season
            )

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
                try:
                    player_info = client.get_player_info(
                        player_id,
                        league,
                        season
                    )

                    save_json(
                        player_info,
                        root / f"{player_id}.json"
                    )

                    player_stats = client.get_player_stats(
                        player_id,
                        league,
                        season
                    )

                    save_json(
                        player_stats,
                        root / f"{player_id}_stats.json"
                    )

                    print(f"✓ Player: {player_id}")

                except Exception as e:
                    print(
                        f"✗ Error fetching player "
                        f"{player_id}: {e}"
                    )

        except Exception as e:
            print(
                f"✗ Error fetching roster for "
                f"team {team_id}: {e}"
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

    # Rosters depend on team data
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

    # Game stats depend on the schedule
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