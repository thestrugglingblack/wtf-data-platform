from __future__ import annotations

"""
Normalize raw HostedSports API responses into clean tabular datasets.

Outputs:

    data/processed/
        teams.csv
        players.csv
        rosters.csv
        games.csv
        player_game_stats.csv
        player_season_stats.csv
        team_season_stats.csv
        standings.csv

Normalization reads valid JSON from data/raw and also uses successfully
repaired JSON from data/recovered. Raw *.invalid.txt responses remain
preserved and are never read directly by normalization.

For each logical source file, raw valid JSON takes precedence. A recovered
JSON file is used only when the corresponding valid raw JSON does not exist.
"""

import html
import json
import re
from pathlib import Path
from typing import Any, Iterator

import polars as pl

from config import PROCESSED_DATA_DIR, RAW_DATA_DIR


# Repaired responses mirror the raw directory structure under data/recovered.
RECOVERED_DATA_DIR = RAW_DATA_DIR.parent / "recovered"


# ============================================================
# Constants
# ============================================================

NULL_VALUES = {
    "",
    "-",
    "NULL",
    "null",
    "None",
    "Not Reported",
    "N/A",
    "NR",
}

PLAYER_ID_PATTERN = re.compile(r"^player\d+$", re.IGNORECASE)
GAME_ID_PATTERN = re.compile(r"^game\d+$", re.IGNORECASE)

KEY_ALIASES = {
    # Common spelling / naming inconsistencies
    "team_id": "team_id",
    "player_id": "player_id",
    "pct": "win_pct",
    "fiend_goals": "field_goals",
    "safties": "safeties",
    "saftey": "safety",
    "yars_per_catch": "yards_per_catch",
    "passes_deflected": "passes_deflected",
    "deflected_passes": "passes_deflected",
    "blocked_kicks": "blocked_kicks",

    # Special teams
    "number_ko_returns": "kickoff_returns",
    "ko_ret_yards": "kickoff_return_yards",
    "ko_ret_tds": "kickoff_return_tds",
    "ko_ret_long": "kickoff_return_long",
    "ko_ret_ave": "kickoff_return_average",

    "number_punt_returns": "punt_returns",
    "punt_ret_yards": "punt_return_yards",
    "punt_ret_tds": "punt_return_tds",
    "punt_ret_long": "punt_return_long",
    "punt_ret_ave": "punt_return_average",

    "number_punts": "punts",
    "punt_average": "punt_average",
    "punt_yards": "punt_yards",
    "punt_touchbacks": "punt_touchbacks",
    "punt_long": "punt_long",

    # Interceptions
    "ints": "interceptions",
    "int_yards": "interception_return_yards",
    "int_tds": "interception_return_tds",
    "int_yards_long": "interception_return_long",
    "int_return_yards": "interception_return_yards",
    "int_return_tds": "interception_return_tds",
    "int_return_long": "interception_return_long",

    # Fumbles
    "fumble_rec": "fumble_recoveries",
    "fumble_rec_yards": "fumble_recovery_yards",
    "fumble_rec_tds": "fumble_recovery_tds",
    "fumble_rec_yards_long": "fumble_recovery_long",
    "fumble_forced": "forced_fumbles",
    "fumbles_recovered": "fumble_recoveries",
    "fumbles_rec_return_yds": "fumble_recovery_yards",
    "fumbles_rec_ret_tds": "fumble_recovery_tds",
    "fumbles_rec_ret_long": "fumble_recovery_long",

    # Passing
    "pass_ints": "passing_interceptions",
    "passing_ints": "passing_interceptions",
    "pass_long": "passing_long",
    "pass_ave": "passing_average",

    # Scoring
    "pat_2": "two_point_conversions",
}

PLAYER_GAME_STRING_COLUMNS = {
    "league",
    "game_id",
    "date",
    "team_id",
    "team_name",
    "opponent_id",
    "opponent_name",
    "home_away",
    "player_id",
    "source_player_id",
    "player_name",
    "roster_number",
}

PLAYER_SEASON_STRING_COLUMNS = {
    "league",
    "player_id",
    "player_name",
    "team_city",
    "team_name",
    "team_id",
}


# ============================================================
# Generic Cleaning
# ============================================================

def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def clean_key(key: str) -> str:
    key = str(key).strip().lower()
    key = key.replace("-", "_")
    key = key.replace(" ", "_")
    key = re.sub(r"_+", "_", key)
    return key.strip("_")


def canonical_key(key: str) -> str:
    cleaned = clean_key(key)
    return KEY_ALIASES.get(cleaned, cleaned)


def clean_value(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, str):
        value = html.unescape(value.strip())
        if value in NULL_VALUES:
            return None

    return value


def clean_record(record: dict) -> dict:
    return {
        canonical_key(key): clean_value(value)
        for key, value in record.items()
    }


# ============================================================
# File Discovery
# ============================================================

def iter_league_seasons() -> Iterator[tuple[str, int, Path]]:
    """
    Yield every league/season found in either data/raw or data/recovered.

    The returned Path is the relative league/season path. Source-file helpers
    decide whether a particular file should come from raw or recovered data.
    """
    seasons: set[tuple[str, int]] = set()

    for root in (RAW_DATA_DIR, RECOVERED_DATA_DIR):
        if not root.exists():
            continue

        for league_dir in sorted(root.iterdir()):
            if not league_dir.is_dir():
                continue

            league = league_dir.name.strip().lower()

            for season_dir in sorted(league_dir.iterdir()):
                if not season_dir.is_dir():
                    continue

                try:
                    season = int(season_dir.name)
                except ValueError:
                    continue

                seasons.add((league, season))

    for league, season in sorted(seasons):
        yield league, season, Path(league) / str(season)


def source_file(relative_path: Path) -> Path | None:
    """
    Resolve one logical JSON source.

    Precedence:
        1. data/raw/<relative_path>
        2. data/recovered/<relative_path>

    This prevents a repaired response from duplicating or overriding a valid
    raw JSON response.
    """
    raw_path = RAW_DATA_DIR / relative_path

    if raw_path.exists():
        return raw_path

    recovered_path = RECOVERED_DATA_DIR / relative_path

    if recovered_path.exists():
        return recovered_path

    return None


def source_json_files(relative_dir: Path) -> list[Path]:
    """
    Return the union of *.json files from a logical directory.

    A valid raw JSON file wins when the same filename also exists in recovered.
    Recovered-only files are included.
    """
    selected: dict[str, Path] = {}

    recovered_dir = RECOVERED_DATA_DIR / relative_dir
    raw_dir = RAW_DATA_DIR / relative_dir

    if recovered_dir.exists():
        for path in sorted(recovered_dir.glob("*.json")):
            selected[path.name] = path

    if raw_dir.exists():
        for path in sorted(raw_dir.glob("*.json")):
            selected[path.name] = path

    return [
        selected[name]
        for name in sorted(selected)
    ]


def invalid_files(relative_season_dir: Path) -> list[Path]:
    season_dir = RAW_DATA_DIR / relative_season_dir

    if not season_dir.exists():
        return []

    return list(season_dir.rglob("*.invalid.txt"))


def is_recovered_file(path: Path) -> bool:
    try:
        path.relative_to(RECOVERED_DATA_DIR)
        return True
    except ValueError:
        return False


# ============================================================
# Generic Nested-JSON Helpers
# ============================================================

def find_first_list(data: Any, target_key: str) -> list:
    target_key = clean_key(target_key)

    if isinstance(data, dict):
        for key, value in data.items():
            if clean_key(key) == target_key and isinstance(value, list):
                return value

            found = find_first_list(value, target_key)
            if found:
                return found

    elif isinstance(data, list):
        for item in data:
            found = find_first_list(item, target_key)
            if found:
                return found

    return []


def dynamic_id(record: dict, pattern: re.Pattern) -> Any:
    for key, value in record.items():
        if pattern.fullmatch(str(key).strip()):
            return clean_value(value)
    return None


def find_dicts_with_keys(data: Any, required_keys: set[str]) -> list[dict]:
    results = []

    if isinstance(data, dict):
        cleaned_keys = {clean_key(key) for key in data}

        if required_keys.issubset(cleaned_keys):
            results.append(data)

        for value in data.values():
            results.extend(find_dicts_with_keys(value, required_keys))

    elif isinstance(data, list):
        for item in data:
            results.extend(find_dicts_with_keys(item, required_keys))

    return results


# ============================================================
# Type Helpers
# ============================================================

def cast_if_present(
    df: pl.DataFrame,
    columns: list[str],
    dtype: pl.DataType,
) -> pl.DataFrame:
    expressions = []

    for column in columns:
        if column in df.columns:
            expressions.append(
                pl.col(column).cast(dtype, strict=False)
            )

    if not expressions:
        return df

    return df.with_columns(expressions)


def cast_stat_columns(
    df: pl.DataFrame,
    string_columns: set[str],
) -> pl.DataFrame:
    expressions = []

    for column in df.columns:
        if column in string_columns:
            continue

        if column in {"season", "week"}:
            continue

        expressions.append(
            pl.col(column).cast(pl.Float64, strict=False)
        )

    if expressions:
        df = df.with_columns(expressions)

    return df


def normalize_game_date_column(
    df: pl.DataFrame,
) -> pl.DataFrame:
    """
    Normalize game dates to a Polars Date column.

    HostedSports may provide game dates in multiple forms, including:

        2023-05-01
        May 1
        Sep 7

    When the source date does not contain a year, the row's season is
    used as the year.

    Missing or unparseable dates become null because parsing is
    intentionally non-strict.
    """
    if "date" not in df.columns:
        return df

    date_string = (
        pl.col("date")
        .cast(pl.String)
        .str.strip_chars()
    )

    if "season" not in df.columns:
        return df.with_columns(
            date_string
            .str.to_date(
                "%Y-%m-%d",
                strict=False,
            )
            .alias("date")
        )

    season_date = pl.concat_str(
        [
            pl.col("season").cast(pl.String),
            pl.lit(" "),
            date_string,
        ]
    )

    return df.with_columns(
        pl.coalesce(
            [
                # ISO date:
                # 2023-05-01
                date_string.str.to_date(
                    "%Y-%m-%d",
                    strict=False,
                ),

                # Full month:
                # May 1
                season_date.str.to_date(
                    "%Y %B %d",
                    strict=False,
                ),

                # Abbreviated month:
                # Sep 7
                season_date.str.to_date(
                    "%Y %b %d",
                    strict=False,
                ),
            ]
        ).alias("date")
    )


# ============================================================
# Teams
# ============================================================

def normalize_team_hierarchy(league: str, record: dict) -> dict:
    conf = clean_value(record.get("conf"))
    div = clean_value(record.get("div"))
    region = clean_value(record.get("region"))

    tier = None
    conference = None
    division = None

    if league == "wnfc":
        division = div

    elif league == "wfa":
        conf_upper = str(conf).upper() if conf else ""
        div_upper = str(div).upper() if div else ""

        if conf_upper == "WFA PRO" or conf_upper.startswith("DIV "):
            tier = conf
            conference = div

        elif div_upper == "WFA PRO" or div_upper.startswith("DIV "):
            tier = div
            conference = conf

        else:
            conference = conf
            division = div

    else:
        conference = conf
        division = div

    return {
        "tier": tier,
        "conference": conference,
        "division": division,
        "region": region,
    }


def normalize_teams_file(
    path: Path,
    league: str,
    season: int,
) -> list[dict]:
    data = load_json(path)
    teams = find_first_list(data, "league_teams_list")
    records = []

    for team in teams:
        if not isinstance(team, dict):
            continue

        cleaned = clean_record(team)
        hierarchy = normalize_team_hierarchy(league, cleaned)

        team_number = cleaned.get("team#")
        if team_number is not None:
            team_number = str(team_number).strip()

        records.append(
            {
                "league": league,
                "season": season,
                "team_id": cleaned.get("id"),
                "team_number": team_number,
                "team_city": cleaned.get("city"),
                "team_name": cleaned.get("name"),
                **hierarchy,
            }
        )

    return records


def normalize_teams() -> pl.DataFrame:
    records = []

    for league, season, season_rel in iter_league_seasons():
        path = source_file(season_rel / "teams.json")

        if path is None:
            continue

        records.extend(
            normalize_teams_file(
                path,
                league,
                season,
            )
        )

    if not records:
        return pl.DataFrame()

    df = pl.DataFrame(
        records,
        infer_schema_length=None,
    )

    df = cast_if_present(
        df,
        ["season"],
        pl.Int64,
    )

    return df.unique(
        subset=[
            "league",
            "season",
            "team_id",
        ],
        keep="first",
        maintain_order=True,
    )


# ============================================================
# Rosters + Players
# ============================================================

def roster_team_record(data: Any) -> dict | None:
    candidates = find_dicts_with_keys(
        data,
        {
            "league",
            "season",
            "team",
            "players",
        },
    )

    if not candidates:
        return None

    return candidates[0]


def normalize_roster_file(
    path: Path,
    league: str,
    season: int,
) -> tuple[list[dict], list[dict]]:
    data = load_json(path)
    team_record = roster_team_record(data)

    if not team_record:
        return [], []

    cleaned_team = clean_record(team_record)

    team_id = path.stem
    team_name = clean_value(cleaned_team.get("team"))

    players = team_record.get("players", [])

    if not isinstance(players, list):
        return [], []

    roster_rows = []
    player_rows = []

    for player in players:
        if not isinstance(player, dict):
            continue

        player_id = dynamic_id(
            player,
            PLAYER_ID_PATTERN,
        )

        cleaned = clean_record(player)

        if not player_id:
            continue

        player_name = clean_value(
            cleaned.get("name")
        )

        roster_number = cleaned.get("number")
        if roster_number is not None:
            roster_number = str(roster_number).strip()

        weight = cleaned.get("weight")
        if weight is not None:
            weight = str(weight).strip()

        roster_rows.append(
            {
                "league": league,
                "season": season,
                "team_id": team_id,
                "team_name": team_name,
                "player_id": player_id,
                "roster_number": roster_number,
                "position": cleaned.get("pos"),
            }
        )

        player_rows.append(
            {
                "player_id": player_id,
                "player_name": player_name,
                "height": cleaned.get("height"),
                "weight": weight,
                "school": cleaned.get("school"),
                "hometown": cleaned.get("hometown"),
            }
        )

    return roster_rows, player_rows


def normalize_rosters_and_players(
) -> tuple[pl.DataFrame, pl.DataFrame]:
    roster_rows = []
    player_rows = []

    for league, season, season_rel in iter_league_seasons():
        for path in source_json_files(season_rel / "rosters"):
            rosters, players = normalize_roster_file(
                path,
                league,
                season,
            )

            roster_rows.extend(rosters)
            player_rows.extend(players)

    if roster_rows:
        rosters_df = pl.DataFrame(
            roster_rows,
            infer_schema_length=None,
        )

        rosters_df = cast_if_present(
            rosters_df,
            ["season"],
            pl.Int64,
        )

        rosters_df = rosters_df.unique(
            subset=[
                "league",
                "season",
                "team_id",
                "player_id",
            ],
            keep="first",
            maintain_order=True,
        )
    else:
        rosters_df = pl.DataFrame()

    if player_rows:
        players_df = pl.DataFrame(
            player_rows,
            infer_schema_length=None,
        )

        players_df = players_df.unique(
            subset=["player_id"],
            keep="first",
            maintain_order=True,
        )
    else:
        players_df = pl.DataFrame()

    return rosters_df, players_df


# ============================================================
# Games
# ============================================================

def normalize_schedule_file(
    path: Path,
    league: str,
    season: int,
) -> list[dict]:
    data = load_json(path)
    weeks = find_first_list(data, "schedule_games")
    records = []

    for week_record in weeks:
        if not isinstance(week_record, dict):
            continue

        cleaned_week = clean_record(week_record)

        if cleaned_week.get("week_number") is not None:
            season_type = "regular"
            week_number = cleaned_week.get("week_number")

        elif cleaned_week.get("psw") is not None:
            season_type = "postseason"
            week_number = cleaned_week.get("psw")

        else:
            season_type = None
            week_number = None

        games = week_record.get("games", [])

        if not isinstance(games, list):
            continue

        for game in games:
            if not isinstance(game, dict):
                continue

            game_id = dynamic_id(
                game,
                GAME_ID_PATTERN,
            )

            cleaned_game = clean_record(game)

            records.append(
                {
                    "league": league,
                    "season": season,
                    "game_id": game_id,
                    "season_type": season_type,
                    "week": week_number,
                    "date": cleaned_game.get("date"),
                    "visitor_team_name": cleaned_game.get("visitor"),
                    "visitor_score": cleaned_game.get("visitor_score"),
                    "home_team_name": cleaned_game.get("home"),
                    "home_score": cleaned_game.get("home_score"),
                }
            )

    return records


def normalize_games() -> pl.DataFrame:
    records = []

    for league, season, season_rel in iter_league_seasons():
        path = source_file(season_rel / "schedule.json")

        if path is None:
            continue

        records.extend(
            normalize_schedule_file(
                path,
                league,
                season,
            )
        )

    if not records:
        return pl.DataFrame()

    df = pl.DataFrame(
        records,
        infer_schema_length=None,
    )

    df = cast_if_present(
        df,
        [
            "season",
            "week",
            "visitor_score",
            "home_score",
        ],
        pl.Int64,
    )

    # Use the same canonical game-date normalization as
    # player_game_stats so both datasets expose date as pl.Date.
    df = normalize_game_date_column(
        df
    )

    return df.unique(
        subset=[
            "league",
            "season",
            "game_id",
        ],
        keep="first",
        maintain_order=True,
    )


# ============================================================
# Player Game Stats
# ============================================================

def get_game_data(data: Any) -> dict | None:
    game_data = find_first_list(
        data,
        "game_data",
    )

    if not game_data:
        return None

    if not isinstance(
        game_data[0],
        dict,
    ):
        return None

    return clean_record(
        game_data[0]
    )


def extract_side_players(
    data: Any,
    side_key: str,
) -> list[dict]:
    stats_key = (
        "home_stats"
        if side_key == "home"
        else "visitor_stats"
    )

    stats = find_first_list(
        data,
        stats_key,
    )

    player_records = []

    for item in stats:
        if not isinstance(item, dict):
            continue

        for key, value in item.items():
            if not re.fullmatch(
                r"player_number[_-]\d+",
                str(key),
                re.IGNORECASE,
            ):
                continue

            if not isinstance(value, list):
                continue

            for player in value:
                if isinstance(player, dict):
                    player_records.append(player)

    return player_records


def normalize_game_stats_file(
    path: Path,
    league: str,
    season: int,
) -> list[dict]:
    data = load_json(path)
    game_data = get_game_data(data)

    if not game_data:
        return []

    game_id = path.stem

    home_team_id = game_data.get("home_team_id")
    home_team_name = game_data.get("home_team")

    visitor_team_id = game_data.get("visitor_team_id")
    visitor_team_name = game_data.get("visitor_team")

    records = []

    sides = [
        (
            "home",
            home_team_id,
            home_team_name,
            visitor_team_id,
            visitor_team_name,
        ),
        (
            "visitor",
            visitor_team_id,
            visitor_team_name,
            home_team_id,
            home_team_name,
        ),
    ]

    for (
        side,
        team_id,
        team_name,
        opponent_id,
        opponent_name,
    ) in sides:

        players = extract_side_players(
            data,
            side,
        )

        for player in players:
            cleaned = clean_record(player)

            row = {
                "league": league,
                "season": season,
                "game_id": game_id,
                "week": game_data.get("week_number"),
                "date": game_data.get("date"),
                "team_id": team_id,
                "team_name": team_name,
                "opponent_id": opponent_id,
                "opponent_name": opponent_name,
                "home_away": side,
            }

            for key, value in cleaned.items():
                if key == "player_id":
                    # HostedSports game-stat Player_ID values are not
                    # the same identifier namespace as roster/player IDs.
                    # Preserve the source value separately and resolve the
                    # canonical player_id after all game rows are flattened.
                    row["source_player_id"] = value
                else:
                    row[key] = value

            records.append(row)

    return records


def propagate_player_ids_from_source_player_id(
    df: pl.DataFrame,
) -> pl.DataFrame:
    """
    Resolve still-unresolved player_game_stats rows using source_player_id.

    A canonical player_id is propagated only when:
    - player_id is currently null
    - source_player_id is present
    - within the same league + season, that source_player_id already appears
      on one or more resolved rows
    - those resolved rows map to exactly ONE distinct canonical player_id

    If a source_player_id maps to zero or multiple canonical player_ids,
    the row remains unresolved.

    This is deterministic identity propagation. It does not use fuzzy
    matching or player-name similarity.
    """
    required_columns = {
        "league",
        "season",
        "source_player_id",
        "player_id",
    }

    if df.is_empty():
        return df

    if not required_columns.issubset(set(df.columns)):
        return df

    resolved_lookup = (
        df
        .filter(
            pl.col("source_player_id").is_not_null()
            & pl.col("player_id").is_not_null()
        )
        .group_by(
            [
                "league",
                "season",
                "source_player_id",
            ]
        )
        .agg(
            [
                pl.col("player_id")
                .drop_nulls()
                .n_unique()
                .alias("_source_player_id_count"),

                pl.col("player_id")
                .drop_nulls()
                .first()
                .alias("_source_player_id_candidate"),
            ]
        )
        .filter(
            pl.col("_source_player_id_count") == 1
        )
        .select(
            [
                "league",
                "season",
                "source_player_id",
                "_source_player_id_candidate",
            ]
        )
    )

    if resolved_lookup.is_empty():
        return df

    return (
        df
        .join(
            resolved_lookup,
            on=[
                "league",
                "season",
                "source_player_id",
            ],
            how="left",
        )
        .with_columns(
            pl.when(
                pl.col("player_id").is_null()
                & pl.col("_source_player_id_candidate").is_not_null()
            )
            .then(
                pl.col("_source_player_id_candidate")
            )
            .otherwise(
                pl.col("player_id")
            )
            .alias("player_id")
        )
        .drop("_source_player_id_candidate")
    )


def add_player_ids_to_game_stats(
    df: pl.DataFrame,
    rosters: pl.DataFrame,
    players: pl.DataFrame,
) -> pl.DataFrame:
    """
    Resolve canonical player_id for game-stat rows.

    Resolution happens in two conservative passes.

    PASS 1
    ------
    HostedSports game-stat Player_ID values do not match the UUIDs used
    in roster/player responses. The raw game ID is therefore preserved as
    source_player_id, while canonical player_id is first resolved from:

        league + season + team_id + case-insensitive exact player_name

    The player-name comparison only:
        - casts to string
        - strips leading/trailing whitespace
        - lowercases the value

    It does NOT use fuzzy matching, punctuation removal, token matching,
    initials, nicknames, or edit distance.

    A canonical player_id is accepted only when the case-insensitive name
    key maps to exactly one distinct roster player_id for the same league,
    season, and team_id.

    PASS 2
    ------
    Rows that remain unresolved may inherit a canonical player_id through
    source_player_id, but only when the same:

        league + season + source_player_id

    already maps to exactly one distinct canonical player_id on other
    resolved game-stat rows.

    If either lookup is ambiguous, the row remains unresolved for
    audit/validation.
    """
    if df.is_empty():
        return df

    if rosters.is_empty() or players.is_empty():
        if "player_id" not in df.columns:
            df = df.with_columns(
                pl.lit(None, dtype=pl.String).alias("player_id")
            )

        return propagate_player_ids_from_source_player_id(df)

    lookup = (
        rosters
        .join(
            players.select(
                [
                    "player_id",
                    "player_name",
                ]
            ),
            on="player_id",
            how="left",
        )
        .with_columns(
            pl.col("player_name")
            .cast(pl.String)
            .str.strip_chars()
            .str.to_lowercase()
            .alias("_player_name_match_key")
        )
        .filter(
            pl.col("_player_name_match_key").is_not_null()
            & (pl.col("_player_name_match_key") != "")
        )
        .select(
            [
                "league",
                "season",
                "team_id",
                "_player_name_match_key",
                "player_id",
            ]
        )
        .group_by(
            [
                "league",
                "season",
                "team_id",
                "_player_name_match_key",
            ]
        )
        .agg(
            [
                pl.col("player_id")
                .n_unique()
                .alias("_id_count"),

                pl.col("player_id")
                .first()
                .alias("_canonical_player_id"),
            ]
        )
        .filter(
            pl.col("_id_count") == 1
        )
        .drop("_id_count")
    )

    working = df.with_columns(
        pl.col("player_name")
        .cast(pl.String)
        .str.strip_chars()
        .str.to_lowercase()
        .alias("_player_name_match_key")
    )

    enriched = working.join(
        lookup,
        on=[
            "league",
            "season",
            "team_id",
            "_player_name_match_key",
        ],
        how="left",
    )

    if "player_id" in enriched.columns:
        enriched = enriched.with_columns(
            pl.coalesce(
                [
                    pl.col("player_id"),
                    pl.col("_canonical_player_id"),
                ]
            ).alias("player_id")
        )
    else:
        enriched = enriched.rename(
            {
                "_canonical_player_id": "player_id"
            }
        )

    if "_canonical_player_id" in enriched.columns:
        enriched = enriched.drop(
            "_canonical_player_id"
        )

    enriched = enriched.drop(
        "_player_name_match_key"
    )

    return propagate_player_ids_from_source_player_id(
        enriched
    )


def normalize_player_game_stats(
    rosters: pl.DataFrame,
    players: pl.DataFrame,
) -> pl.DataFrame:
    records = []

    for league, season, season_rel in iter_league_seasons():
        for path in source_json_files(season_rel / "games"):
            records.extend(
                normalize_game_stats_file(
                    path,
                    league,
                    season,
                )
            )

    if not records:
        return pl.DataFrame()

    df = pl.DataFrame(
        records,
        infer_schema_length=None,
    )

    df = cast_if_present(
        df,
        [
            "season",
            "week",
        ],
        pl.Int64,
    )

    # Keep date protected as a string while all football statistic
    # columns are converted to numeric values.
    df = cast_stat_columns(
        df,
        PLAYER_GAME_STRING_COLUMNS,
    )

    # Convert the source game date into the same canonical Date type
    # used by the games dataset.
    df = normalize_game_date_column(
        df
    )

    # Remove only exact duplicate normalized rows. Rows that share a
    # logical player/game key but contain different statistics are kept
    # so validation can surface the source inconsistency.
    df = df.unique(
        keep="first",
        maintain_order=True,
    )

    # Convert the game endpoint's source-specific player identifier into
    # a canonical player foreign key while retaining source_player_id.
    df = add_player_ids_to_game_stats(
        df,
        rosters,
        players,
    )

    return df


# ============================================================
# Team Season Stats
# ============================================================

def normalize_team_stats_file(
    path: Path,
    league: str,
    season: int,
) -> list[dict]:
    data = load_json(path)
    records = []

    if not isinstance(data, dict):
        return records

    for value in data.values():
        if not isinstance(value, list):
            continue

        for record in value:
            if not isinstance(record, dict):
                continue

            cleaned = clean_record(record)

            if "team_name" not in cleaned:
                continue

            cleaned["league"] = league
            cleaned["season"] = season

            records.append(cleaned)

    return records


def add_team_ids_to_team_season_stats(
    df: pl.DataFrame,
    teams: pl.DataFrame,
) -> pl.DataFrame:
    """
    Add canonical team_id to team-season stats using exact league/season
    and city/name matching where possible.

    Unmatched rows remain in the output with null team_id so validation
    can identify source placeholders or naming mismatches.
    """
    if df.is_empty() or teams.is_empty():
        return df

    team_lookup = (
        teams
        .select(
            [
                "league",
                "season",
                "team_id",
                "team_city",
                "team_name",
            ]
        )
        .unique(
            subset=[
                "league",
                "season",
                "team_city",
                "team_name",
            ],
            keep="first",
        )
    )

    if "team_id" in df.columns:
        df = df.rename(
            {
                "team_id": "_source_team_id"
            }
        )

    joined = df.join(
        team_lookup.rename(
            {
                "team_id": "_matched_team_id"
            }
        ),
        on=[
            "league",
            "season",
            "team_city",
            "team_name",
        ],
        how="left",
    )

    if "_source_team_id" in joined.columns:
        joined = joined.with_columns(
            pl.coalesce(
                [
                    pl.col("_source_team_id"),
                    pl.col("_matched_team_id"),
                ]
            ).alias("team_id")
        ).drop(
            [
                "_source_team_id",
                "_matched_team_id",
            ]
        )
    else:
        joined = joined.rename(
            {
                "_matched_team_id": "team_id"
            }
        )

    return joined


def normalize_team_season_stats(
    teams: pl.DataFrame,
) -> pl.DataFrame:
    records = []

    for league, season, season_rel in iter_league_seasons():
        path = source_file(season_rel / "team_stats.json")

        if path is None:
            continue

        records.extend(
            normalize_team_stats_file(
                path,
                league,
                season,
            )
        )

    if not records:
        return pl.DataFrame()

    df = pl.DataFrame(
        records,
        infer_schema_length=None,
    )

    df = cast_if_present(
        df,
        ["season"],
        pl.Int64,
    )

    string_columns = {
        "league",
        "team_id",
        "team_city",
        "team_name",
        "team_logo",
        "team_number",
    }

    df = cast_stat_columns(
        df,
        string_columns,
    )

    df = add_team_ids_to_team_season_stats(
        df,
        teams,
    )

    return df


# ============================================================
# Player Season Stats
# ============================================================

def category_stat_records(data: Any) -> list[dict]:
    records = []

    if isinstance(data, dict):
        for value in data.values():
            records.extend(
                category_stat_records(value)
            )

    elif isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue

            cleaned = clean_record(item)

            if (
                "player_name" in cleaned
                and "team_name" in cleaned
            ):
                records.append(cleaned)

            else:
                records.extend(
                    category_stat_records(item)
                )

    return records


def normalize_player_stat_file(
    path: Path,
    league: str,
    season: int,
) -> list[dict]:
    data = load_json(path)
    records = category_stat_records(data)
    output = []

    for record in records:
        cleaned = clean_record(record)

        # Rank is category-specific and should not be merged across
        # passing/rushing/defense/etc.
        cleaned.pop(
            "rank",
            None,
        )

        cleaned["league"] = league
        cleaned["season"] = season

        output.append(cleaned)

    return output


def merge_player_season_records(
    records: list[dict],
) -> list[dict]:
    merged = {}

    for record in records:
        key = (
            record.get("league"),
            record.get("season"),
            record.get("team_city"),
            record.get("team_name"),
            record.get("player_name"),
        )

        if key not in merged:
            merged[key] = {
                "league": record.get("league"),
                "season": record.get("season"),
                "player_id": None,
                "team_id": None,
                "player_name": record.get("player_name"),
                "team_city": record.get("team_city"),
                "team_name": record.get("team_name"),
            }

        for field, value in record.items():
            if field in {
                "league",
                "season",
                "player_name",
                "team_city",
                "team_name",
            }:
                continue

            if value is not None:
                merged[key][field] = value

    return list(merged.values())


def build_team_alias_lookup(
    teams: pl.DataFrame,
) -> pl.DataFrame:
    """
    Build a lookup that can match league-level stat team labels to the
    canonical team table.

    HostedSports league stat files often separate the team into:
        team_city = "Washington"
        team_name = "Prodigy"

    while rosters use:
        team_name = "Washington Prodigy"

    This lookup bridges those two representations using the canonical
    teams table.
    """
    if teams.is_empty():
        return pl.DataFrame()

    return (
        teams
        .select(
            [
                "league",
                "season",
                "team_id",
                "team_city",
                "team_name",
            ]
        )
        .with_columns(
            [
                pl.col("team_city")
                .cast(pl.String)
                .str.strip_chars()
                .alias("_team_city_key"),

                pl.col("team_name")
                .cast(pl.String)
                .str.strip_chars()
                .alias("_team_name_key"),
            ]
        )
        .select(
            [
                "league",
                "season",
                "team_id",
                "_team_city_key",
                "_team_name_key",
            ]
        )
        .unique(
            subset=[
                "league",
                "season",
                "_team_city_key",
                "_team_name_key",
            ],
            keep="first",
        )
    )


def add_team_ids_to_player_season_stats(
    df: pl.DataFrame,
    teams: pl.DataFrame,
) -> pl.DataFrame:
    """
    Match league-level player season stats to canonical team_id using:
        league
        season
        team_city
        short team_name
    """
    if df.is_empty() or teams.is_empty():
        return df

    lookup = build_team_alias_lookup(
        teams
    )

    working = df.with_columns(
        [
            pl.col("team_city")
            .cast(pl.String)
            .str.strip_chars()
            .alias("_team_city_key"),

            pl.col("team_name")
            .cast(pl.String)
            .str.strip_chars()
            .alias("_team_name_key"),
        ]
    )

    joined = working.join(
        lookup.rename(
            {
                "team_id": "_matched_team_id"
            }
        ),
        on=[
            "league",
            "season",
            "_team_city_key",
            "_team_name_key",
        ],
        how="left",
    )

    joined = joined.with_columns(
        pl.coalesce(
            [
                pl.col("team_id"),
                pl.col("_matched_team_id"),
            ]
        ).alias("team_id")
    )

    return joined.drop(
        [
            "_team_city_key",
            "_team_name_key",
            "_matched_team_id",
        ]
    )


def add_player_ids_from_rosters(
    df: pl.DataFrame,
    rosters: pl.DataFrame,
    players: pl.DataFrame,
) -> pl.DataFrame:
    """
    Enrich player-season rows with canonical player_id through:

        league + season + team_id + case-insensitive exact player_name

    This handles source capitalization differences such as:

        REGINA ESCOTO -> Regina Escoto
        iemah Perry   -> Iemah Perry
        erin miller   -> Erin Miller

    while remaining intentionally stricter than fuzzy name matching.
    The match key only strips leading/trailing whitespace and lowercases
    the player name.

    A match is accepted only if that case-insensitive name key maps to
    exactly one distinct player_id on the roster for the same league,
    season, and team_id. Ambiguous duplicate names remain unresolved.
    """
    if (
        df.is_empty()
        or rosters.is_empty()
        or players.is_empty()
    ):
        return df

    unique_lookup = (
        rosters
        .join(
            players.select(
                [
                    "player_id",
                    "player_name",
                ]
            ),
            on="player_id",
            how="left",
        )
        .with_columns(
            pl.col("player_name")
            .cast(pl.String)
            .str.strip_chars()
            .str.to_lowercase()
            .alias("_player_name_match_key")
        )
        .filter(
            pl.col("_player_name_match_key").is_not_null()
            & (pl.col("_player_name_match_key") != "")
        )
        .select(
            [
                "league",
                "season",
                "team_id",
                "_player_name_match_key",
                "player_id",
            ]
        )
        .group_by(
            [
                "league",
                "season",
                "team_id",
                "_player_name_match_key",
            ]
        )
        .agg(
            [
                pl.col("player_id")
                .n_unique()
                .alias("_id_count"),

                pl.col("player_id")
                .first()
                .alias("_matched_player_id"),
            ]
        )
        .filter(
            pl.col("_id_count") == 1
        )
        .drop("_id_count")
    )

    working = df.with_columns(
        pl.col("player_name")
        .cast(pl.String)
        .str.strip_chars()
        .str.to_lowercase()
        .alias("_player_name_match_key")
    )

    enriched = working.join(
        unique_lookup,
        on=[
            "league",
            "season",
            "team_id",
            "_player_name_match_key",
        ],
        how="left",
    )

    enriched = enriched.with_columns(
        pl.coalesce(
            [
                pl.col("player_id"),
                pl.col("_matched_player_id"),
            ]
        ).alias("player_id")
    )

    return enriched.drop(
        [
            "_matched_player_id",
            "_player_name_match_key",
        ]
    )


def normalize_player_season_stats(
    teams: pl.DataFrame,
    rosters: pl.DataFrame,
    players: pl.DataFrame,
) -> pl.DataFrame:
    source_files = [
        "offensive_stats.json",
        "defensive_stats.json",
        "scoring_stats.json",
        "special_teams_stats.json",
    ]

    records = []

    for league, season, season_rel in iter_league_seasons():
        for filename in source_files:
            path = source_file(season_rel / filename)

            if path is None:
                continue

            records.extend(
                normalize_player_stat_file(
                    path,
                    league,
                    season,
                )
            )

    if not records:
        return pl.DataFrame()

    records = merge_player_season_records(
        records
    )

    df = pl.DataFrame(
        records,
        infer_schema_length=None,
    )

    df = cast_if_present(
        df,
        ["season"],
        pl.Int64,
    )

    df = cast_stat_columns(
        df,
        PLAYER_SEASON_STRING_COLUMNS,
    )

    # Step 1: league stats short team labels -> canonical team_id
    df = add_team_ids_to_player_season_stats(
        df,
        teams,
    )

    # Step 2: canonical team_id + player_name -> player_id
    df = add_player_ids_from_rosters(
        df,
        rosters,
        players,
    )

    return df


# ============================================================
# Standings
# ============================================================

def is_standing_record(record: dict) -> bool:
    cleaned = {
        clean_key(key)
        for key in record
    }

    return (
        "team_name" in cleaned
        and "w" in cleaned
        and "l" in cleaned
    )


def standing_hierarchy(
    league: str,
    context: list[str],
) -> dict:
    tier = None
    conference = None
    division = None
    region = None

    for label in context:
        cleaned_label = str(label).strip()
        upper = cleaned_label.upper()

        if not cleaned_label:
            continue

        if (
            upper == "DEFAULT REGION"
            or "LEAGUE STANDING" in upper
            or "LEAGUE RANKING" in upper
        ):
            continue

        if league == "wnfc":
            if upper.endswith("DIVISION"):
                division = cleaned_label

        elif league == "wfa":
            if (
                upper == "WFA PRO"
                or upper.startswith("DIV ")
            ):
                tier = cleaned_label

            elif upper.endswith("CONFERENCE"):
                conference = cleaned_label

            elif upper.endswith("REGION"):
                region = cleaned_label

    return {
        "tier": tier,
        "conference": conference,
        "division": division,
        "region": region,
    }


def walk_standings(
    data: Any,
    league: str,
    season: int,
    context: list[str] | None = None,
) -> list[dict]:
    if context is None:
        context = []

    records = []

    if isinstance(data, dict):
        if is_standing_record(data):
            cleaned = clean_record(data)

            hierarchy = standing_hierarchy(
                league,
                context,
            )

            records.append(
                {
                    "league": league,
                    "season": season,
                    **hierarchy,
                    "team_name": cleaned.get("team_name"),
                    "team_logo": cleaned.get("team_logo"),
                    "wins": cleaned.get("w"),
                    "losses": cleaned.get("l"),
                    "ties": cleaned.get("t"),
                    "win_pct": cleaned.get("win_pct"),
                    "points_for": cleaned.get("pf"),
                    "points_against": cleaned.get("pa"),
                    "home_record": cleaned.get("home"),
                    "away_record": cleaned.get("away"),
                    "conference_record": cleaned.get("conf"),
                    "division_record": cleaned.get("div"),
                    "nonconference_record": cleaned.get("non_conf"),
                    "nondivision_record": cleaned.get("non_div"),
                    "streak": cleaned.get("streak"),
                }
            )

            return records

        for key, value in data.items():
            records.extend(
                walk_standings(
                    value,
                    league,
                    season,
                    context + [str(key)],
                )
            )

    elif isinstance(data, list):
        for item in data:
            records.extend(
                walk_standings(
                    item,
                    league,
                    season,
                    context,
                )
            )

    return records


def normalize_standings() -> pl.DataFrame:
    records = []

    for league, season, season_rel in iter_league_seasons():
        path = source_file(season_rel / "standings.json")

        if path is None:
            continue

        data = load_json(path)

        records.extend(
            walk_standings(
                data,
                league,
                season,
            )
        )

    if not records:
        return pl.DataFrame()

    df = pl.DataFrame(
        records,
        infer_schema_length=None,
    )

    df = cast_if_present(
        df,
        [
            "season",
            "wins",
            "losses",
            "ties",
            "points_for",
            "points_against",
        ],
        pl.Int64,
    )

    df = cast_if_present(
        df,
        ["win_pct"],
        pl.Float64,
    )

    return df


# ============================================================
# Output
# ============================================================

def save_dataframe(
    df: pl.DataFrame,
    filename: str,
):
    if df.is_empty():
        print(
            f"Skipping {filename}: "
            f"no normalized records found."
        )
        return

    PROCESSED_DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path = (
        PROCESSED_DATA_DIR
        / filename
    )

    df.write_csv(
        output_path
    )

    print(
        f"✓ {filename}: "
        f"{df.height} rows"
    )


def report_invalid_files():
    invalid = []

    for league, season, season_rel in iter_league_seasons():
        for path in invalid_files(season_rel):
            invalid.append(
                (
                    league,
                    season,
                    path,
                )
            )

    if not invalid:
        return

    print(
        "\nInvalid/unavailable raw responses preserved:"
    )

    for league, season, path in invalid:
        print(
            f"  - {league.upper()} "
            f"{season}: "
            f"{path.relative_to(RAW_DATA_DIR)}"
        )


def report_recovered_files():
    """
    Report recovered JSON that is eligible for normalization.

    Files shadowed by a valid raw JSON response are not counted as used.
    """
    if not RECOVERED_DATA_DIR.exists():
        print("\nRecovered source files used: 0")
        return

    used = []

    for path in sorted(RECOVERED_DATA_DIR.rglob("*.json")):
        relative = path.relative_to(RECOVERED_DATA_DIR)

        if not (RAW_DATA_DIR / relative).exists():
            used.append(relative)

    print(
        "\nRecovered source files available to normalization: "
        f"{len(used)}"
    )

    by_endpoint: dict[str, int] = {}

    for relative in used:
        if len(relative.parts) >= 4:
            endpoint = relative.parts[-2]
        else:
            endpoint = relative.stem

        by_endpoint[endpoint] = by_endpoint.get(endpoint, 0) + 1

    for endpoint, count in sorted(by_endpoint.items()):
        print(
            f"  {endpoint}: {count}"
        )


def report_normalization_quality(
    player_game_stats: pl.DataFrame,
    player_season_stats: pl.DataFrame,
    team_season_stats: pl.DataFrame,
):
    """
    Small normalization-level report.

    This does not replace validate.py. It only surfaces normalization
    gaps that are useful while developing the pipeline.
    """
    print("\nNormalization quality summary:")

    if not player_game_stats.is_empty():
        duplicate_keys = (
            player_game_stats
            .group_by(
                [
                    "league",
                    "season",
                    "game_id",
                    "team_id",
                    "player_id",
                ]
            )
            .len()
            .filter(
                pl.col("len") > 1
            )
        )

        print(
            "  player_game_stats duplicate logical keys "
            f"(after exact-row dedupe): {duplicate_keys.height}"
        )

        missing_player_ids = (
            player_game_stats
            .filter(
                pl.col("player_id").is_null()
            )
            .height
        )

        print(
            "  player_game_stats missing canonical player_id: "
            f"{missing_player_ids}"
        )

    if not player_season_stats.is_empty():
        missing_player_ids = (
            player_season_stats
            .filter(
                pl.col("player_id").is_null()
            )
            .height
        )

        missing_team_ids = (
            player_season_stats
            .filter(
                pl.col("team_id").is_null()
            )
            .height
        )

        print(
            "  player_season_stats missing player_id: "
            f"{missing_player_ids}"
        )

        print(
            "  player_season_stats missing team_id: "
            f"{missing_team_ids}"
        )

    if not team_season_stats.is_empty():
        missing_team_ids = (
            team_season_stats
            .filter(
                pl.col("team_id").is_null()
            )
            .height
        )

        print(
            "  team_season_stats missing team_id: "
            f"{missing_team_ids}"
        )


def normalize_all():
    print("\n" + "=" * 60)
    print("NORMALIZING HOSTEDSPORTS DATA")
    print("=" * 60)

    # Teams first because they become the canonical bridge for
    # team IDs in downstream datasets.
    teams = normalize_teams()

    rosters, players = (
        normalize_rosters_and_players()
    )

    games = normalize_games()

    player_game_stats = (
        normalize_player_game_stats(
            rosters,
            players,
        )
    )

    player_season_stats = (
        normalize_player_season_stats(
            teams,
            rosters,
            players,
        )
    )

    team_season_stats = (
        normalize_team_season_stats(
            teams
        )
    )

    standings = normalize_standings()

    save_dataframe(
        teams,
        "teams.csv",
    )

    save_dataframe(
        players,
        "players.csv",
    )

    save_dataframe(
        rosters,
        "rosters.csv",
    )

    save_dataframe(
        games,
        "games.csv",
    )

    save_dataframe(
        player_game_stats,
        "player_game_stats.csv",
    )

    save_dataframe(
        player_season_stats,
        "player_season_stats.csv",
    )

    save_dataframe(
        team_season_stats,
        "team_season_stats.csv",
    )

    save_dataframe(
        standings,
        "standings.csv",
    )

    report_normalization_quality(
        player_game_stats,
        player_season_stats,
        team_season_stats,
    )

    report_recovered_files()

    report_invalid_files()

    print("\n" + "-" * 60)
    print("Normalization finished.")
    print("-" * 60)


if __name__ == "__main__":
    normalize_all()