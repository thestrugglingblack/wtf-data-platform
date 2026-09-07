from __future__ import annotations

"""
Audit unresolved identity and data-quality issues in normalized HostedSports data.

This script is intentionally diagnostic.

It DOES NOT:
- modify raw data
- modify recovered data
- modify processed CSVs
- perform fuzzy matching automatically
- assign canonical IDs automatically
- repair source payloads

It DOES:
- load normalized processed datasets
- investigate unresolved player_season_stats.player_id rows
- investigate unresolved player_game_stats.player_id rows
- investigate unresolved team_season_stats.team_id rows
- classify likely causes of unresolved identity problems
- surface exact-name and normalized-name candidate matches
- inspect whether unresolved players exist on another team in the same season
- inspect whether unresolved players exist in another season
- inspect surname and first-initial evidence
- inspect whether unresolved source_player_id values map consistently elsewhere
- write detailed CSV audit outputs under data/validation/

Primary outputs:

    data/validation/
        unresolved_player_season_audit.csv
        unresolved_player_game_audit.csv
        unresolved_team_season_audit.csv
        unresolved_summary.csv
        unresolved_player_season_by_period.csv
        unresolved_player_candidate_evidence.csv
        unresolved_source_player_id_evidence.csv
        unresolved_final_disposition.csv
        unresolved_final_disposition_summary.csv

The goal is to answer:

    Why did normalization fail to resolve this row?

without introducing unsafe automatic identity assumptions.
"""

from dataclasses import dataclass
from pathlib import Path
import re
import unicodedata

import polars as pl

from config import PROCESSED_DATA_DIR


# ============================================================
# Paths
# ============================================================

VALIDATION_DATA_DIR = PROCESSED_DATA_DIR.parent / "validation"


# ============================================================
# Input files
# ============================================================

FILES = {
    "teams": PROCESSED_DATA_DIR / "teams.csv",
    "players": PROCESSED_DATA_DIR / "players.csv",
    "rosters": PROCESSED_DATA_DIR / "rosters.csv",
    "games": PROCESSED_DATA_DIR / "games.csv",
    "player_game_stats": PROCESSED_DATA_DIR / "player_game_stats.csv",
    "player_season_stats": PROCESSED_DATA_DIR / "player_season_stats.csv",
    "team_season_stats": PROCESSED_DATA_DIR / "team_season_stats.csv",
}


# ============================================================
# Models
# ============================================================

@dataclass
class AuditCounts:
    total_rows: int = 0
    unresolved_rows: int = 0
    exact_name_candidates: int = 0
    normalized_name_candidates: int = 0
    no_roster_for_team_season: int = 0
    no_candidate: int = 0
    ambiguous_candidate: int = 0


# ============================================================
# Helpers
# ============================================================

def load_csv(path: Path) -> pl.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"Required processed file not found: {path}"
        )

    return pl.read_csv(
        path,
        infer_schema_length=None,
        null_values=["", "NULL", "null", "None"],
        try_parse_dates=True,
    )


def normalize_name(value: str | None) -> str | None:
    """
    Conservative normalized-name representation for diagnosis only.

    This DOES NOT assign IDs.

    Rules:
    - lowercase
    - unicode normalization
    - replace punctuation with spaces
    - collapse repeated whitespace
    - strip leading/trailing whitespace
    """
    if value is None:
        return None

    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(
        ch for ch in text
        if not unicodedata.combining(ch)
    )
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text or None


def casefold_exact_name(value: str | None) -> str | None:
    """
    Exact comparison key used by normalization-style diagnostics.

    Only:
    - strips leading/trailing whitespace
    - lowercases

    This is intentionally less aggressive than normalize_name().
    """
    if value is None:
        return None

    text = str(value).strip().lower()

    return text or None


def clean_string(value) -> str | None:
    if value is None:
        return None

    text = str(value).strip()

    if text == "":
        return None

    return text


def safe_unique(values: list[str | None]) -> list[str]:
    return sorted(
        {
            value
            for value in values
            if value is not None
        }
    )


def join_pipe(values: list[str | None]) -> str | None:
    cleaned = safe_unique(values)

    if not cleaned:
        return None

    return " | ".join(cleaned)


def ensure_validation_dir():
    VALIDATION_DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


def first_initial(value: str | None) -> str | None:
    normalized = normalize_name(value)

    if not normalized:
        return None

    first_token = normalized.split()[0]

    if not first_token:
        return None

    return first_token[0]


def surname(value: str | None) -> str | None:
    normalized = normalize_name(value)

    if not normalized:
        return None

    tokens = normalized.split()

    if not tokens:
        return None

    return tokens[-1]


def first_name(value: str | None) -> str | None:
    normalized = normalize_name(value)

    if not normalized:
        return None

    tokens = normalized.split()

    if not tokens:
        return None

    return tokens[0]


# ============================================================
# Lookup builders
# ============================================================

def build_player_lookup(
    players: pl.DataFrame,
) -> dict[str, str | None]:
    """
    player_id -> player_name
    """
    lookup = {}

    for row in players.select(
        [
            "player_id",
            "player_name",
        ]
    ).iter_rows(named=True):
        player_id = clean_string(
            row.get("player_id")
        )

        if player_id is None:
            continue

        lookup[player_id] = clean_string(
            row.get("player_name")
        )

    return lookup


def build_roster_indexes(
    rosters: pl.DataFrame,
    players: pl.DataFrame,
):
    """
    Build diagnostic roster indexes.

    exact_index:
        (league, season, team_id, lowercase exact player_name)
            -> list[player_id]

    normalized_index:
        (league, season, team_id, normalized player_name)
            -> list[player_id]

    same_season_exact_index:
        (league, season, lowercase exact player_name)
            -> list[(team_id, player_id)]

    same_season_normalized_index:
        (league, season, normalized player_name)
            -> list[(team_id, player_id)]

    all_seasons_exact_index:
        (league, lowercase exact player_name)
            -> list[(season, team_id, player_id)]

    all_seasons_normalized_index:
        (league, normalized player_name)
            -> list[(season, team_id, player_id)]

    surname_initial_index:
        (league, season, surname, first_initial)
            -> list[(team_id, player_id)]

    team_season_roster_count:
        (league, season, team_id)
            -> count of roster rows
    """
    player_id_to_name = build_player_lookup(
        players
    )

    exact_index = {}
    normalized_index = {}
    same_season_exact_index = {}
    same_season_normalized_index = {}
    all_seasons_exact_index = {}
    all_seasons_normalized_index = {}
    surname_initial_index = {}
    team_season_roster_count = {}

    for row in rosters.iter_rows(
        named=True
    ):
        league = clean_string(
            row.get("league")
        )
        season = clean_string(
            row.get("season")
        )
        team_id = clean_string(
            row.get("team_id")
        )
        player_id = clean_string(
            row.get("player_id")
        )

        if (
            league is None
            or season is None
            or team_id is None
            or player_id is None
        ):
            continue

        player_name = player_id_to_name.get(
            player_id
        )

        if player_name is None:
            player_name = clean_string(
                row.get("player_name")
            )

        league_key = league.lower()

        team_key = (
            league_key,
            season,
            team_id,
        )

        team_season_roster_count[
            team_key
        ] = (
            team_season_roster_count.get(
                team_key,
                0,
            )
            + 1
        )

        if player_name is None:
            continue

        exact_name = casefold_exact_name(
            player_name
        )
        normalized = normalize_name(
            player_name
        )
        player_surname = surname(
            player_name
        )
        player_initial = first_initial(
            player_name
        )

        if exact_name:
            exact_key = (
                league_key,
                season,
                team_id,
                exact_name,
            )

            exact_index.setdefault(
                exact_key,
                [],
            ).append(
                player_id
            )

            same_season_exact_index.setdefault(
                (
                    league_key,
                    season,
                    exact_name,
                ),
                [],
            ).append(
                (
                    team_id,
                    player_id,
                )
            )

            all_seasons_exact_index.setdefault(
                (
                    league_key,
                    exact_name,
                ),
                [],
            ).append(
                (
                    season,
                    team_id,
                    player_id,
                )
            )

        if normalized:
            normalized_key = (
                league_key,
                season,
                team_id,
                normalized,
            )

            normalized_index.setdefault(
                normalized_key,
                [],
            ).append(
                player_id
            )

            same_season_normalized_index.setdefault(
                (
                    league_key,
                    season,
                    normalized,
                ),
                [],
            ).append(
                (
                    team_id,
                    player_id,
                )
            )

            all_seasons_normalized_index.setdefault(
                (
                    league_key,
                    normalized,
                ),
                [],
            ).append(
                (
                    season,
                    team_id,
                    player_id,
                )
            )

        if (
            player_surname
            and player_initial
        ):
            surname_initial_index.setdefault(
                (
                    league_key,
                    season,
                    player_surname,
                    player_initial,
                ),
                [],
            ).append(
                (
                    team_id,
                    player_id,
                )
            )

    return {
        "exact_index": exact_index,
        "normalized_index": normalized_index,
        "same_season_exact_index": same_season_exact_index,
        "same_season_normalized_index": same_season_normalized_index,
        "all_seasons_exact_index": all_seasons_exact_index,
        "all_seasons_normalized_index": all_seasons_normalized_index,
        "surname_initial_index": surname_initial_index,
        "team_season_roster_count": team_season_roster_count,
        "player_id_to_name": player_id_to_name,
    }


def build_source_player_id_index(
    player_game_stats: pl.DataFrame,
):
    """
    Build evidence from already-resolved game rows.

    Key:
        (league, season, source_player_id)

    Value:
        set of canonical player_id values observed on rows that already
        resolved successfully.

    This lets audit.py answer:

        Has this source_player_id already mapped consistently elsewhere?

    without changing any data.
    """
    source_index = {}

    required = {
        "league",
        "season",
        "source_player_id",
        "player_id",
    }

    if not required.issubset(
        set(player_game_stats.columns)
    ):
        return source_index

    resolved = player_game_stats.filter(
        pl.col("source_player_id").is_not_null()
        & pl.col("player_id").is_not_null()
    )

    for row in resolved.select(
        [
            "league",
            "season",
            "source_player_id",
            "player_id",
        ]
    ).iter_rows(named=True):
        league = clean_string(
            row.get("league")
        )
        season = clean_string(
            row.get("season")
        )
        source_player_id = clean_string(
            row.get("source_player_id")
        )
        player_id = clean_string(
            row.get("player_id")
        )

        if (
            league is None
            or season is None
            or source_player_id is None
            or player_id is None
        ):
            continue

        key = (
            league.lower(),
            season,
            source_player_id,
        )

        source_index.setdefault(
            key,
            set(),
        ).add(
            player_id
        )

    return source_index


def build_team_indexes(
    teams: pl.DataFrame,
):
    by_id = {}
    exact_name = {}
    normalized_name = {}

    for row in teams.iter_rows(
        named=True
    ):
        league = clean_string(
            row.get("league")
        )
        season = clean_string(
            row.get("season")
        )
        team_id = clean_string(
            row.get("team_id")
        )
        team_name = clean_string(
            row.get("team_name")
        )

        if (
            league is None
            or season is None
        ):
            continue

        league_key = league.lower()

        if team_id is not None:
            by_id[
                (
                    league_key,
                    season,
                    team_id,
                )
            ] = row

        if team_name is not None:
            exact_key = (
                league_key,
                season,
                team_name.lower(),
            )

            exact_name.setdefault(
                exact_key,
                [],
            ).append(
                team_id
            )

            normalized = normalize_name(
                team_name
            )

            if normalized:
                normalized_key = (
                    league_key,
                    season,
                    normalized,
                )

                normalized_name.setdefault(
                    normalized_key,
                    [],
                ).append(
                    team_id
                )

    return (
        by_id,
        exact_name,
        normalized_name,
    )


# ============================================================
# Candidate formatting
# ============================================================

def format_team_player_candidates(
    candidates: list[tuple[str, str]],
    player_id_to_name: dict[str, str | None],
) -> dict:
    unique_pairs = sorted(
        set(
            (
                team_id,
                player_id,
            )
            for team_id, player_id in candidates
            if team_id and player_id
        )
    )

    team_ids = [
        team_id
        for team_id, _ in unique_pairs
    ]

    player_ids = [
        player_id
        for _, player_id in unique_pairs
    ]

    player_names = [
        player_id_to_name.get(
            player_id
        )
        for _, player_id in unique_pairs
    ]

    return {
        "count": len(unique_pairs),
        "team_ids": join_pipe(team_ids),
        "player_ids": join_pipe(player_ids),
        "player_names": join_pipe(player_names),
    }


def format_season_team_player_candidates(
    candidates: list[tuple[str, str, str]],
    player_id_to_name: dict[str, str | None],
) -> dict:
    unique_rows = sorted(
        set(
            (
                season,
                team_id,
                player_id,
            )
            for season, team_id, player_id in candidates
            if season and team_id and player_id
        )
    )

    seasons = [
        season
        for season, _, _ in unique_rows
    ]

    team_ids = [
        team_id
        for _, team_id, _ in unique_rows
    ]

    player_ids = [
        player_id
        for _, _, player_id in unique_rows
    ]

    player_names = [
        player_id_to_name.get(
            player_id
        )
        for _, _, player_id in unique_rows
    ]

    return {
        "count": len(unique_rows),
        "seasons": join_pipe(seasons),
        "team_ids": join_pipe(team_ids),
        "player_ids": join_pipe(player_ids),
        "player_names": join_pipe(player_names),
    }


# ============================================================
# Base player-resolution classification
# ============================================================

def classify_player_resolution(
    *,
    league: str | None,
    season: str | None,
    team_id: str | None,
    player_name: str | None,
    roster_indexes: dict,
) -> dict:
    """
    Diagnose why a player row failed canonical resolution.

    This returns candidates only.
    It does not assign a canonical player_id.
    """
    exact_index = roster_indexes[
        "exact_index"
    ]
    normalized_index = roster_indexes[
        "normalized_index"
    ]
    team_season_roster_count = roster_indexes[
        "team_season_roster_count"
    ]
    player_id_to_name = roster_indexes[
        "player_id_to_name"
    ]

    league_key = (
        league.lower()
        if league
        else None
    )

    normalized = normalize_name(
        player_name
    )

    result = {
        "normalized_player_name": normalized,
        "roster_rows_for_team_season": 0,
        "exact_candidate_count": 0,
        "exact_candidate_player_ids": None,
        "exact_candidate_player_names": None,
        "normalized_candidate_count": 0,
        "normalized_candidate_player_ids": None,
        "normalized_candidate_player_names": None,
        "diagnosis": None,
    }

    if (
        league_key is None
        or season is None
        or team_id is None
    ):
        result[
            "diagnosis"
        ] = "MISSING_IDENTITY_CONTEXT"

        return result

    team_key = (
        league_key,
        season,
        team_id,
    )

    roster_count = (
        team_season_roster_count.get(
            team_key,
            0,
        )
    )

    result[
        "roster_rows_for_team_season"
    ] = roster_count

    if roster_count == 0:
        result[
            "diagnosis"
        ] = "NO_ROSTER_FOR_TEAM_SEASON"

        return result

    if player_name is None:
        result[
            "diagnosis"
        ] = "MISSING_PLAYER_NAME"

        return result

    exact_name = casefold_exact_name(
        player_name
    )

    exact_key = (
        league_key,
        season,
        team_id,
        exact_name,
    )

    exact_ids = safe_unique(
        exact_index.get(
            exact_key,
            [],
        )
    )

    exact_names = [
        player_id_to_name.get(
            player_id
        )
        for player_id in exact_ids
    ]

    result[
        "exact_candidate_count"
    ] = len(
        exact_ids
    )

    result[
        "exact_candidate_player_ids"
    ] = join_pipe(
        exact_ids
    )

    result[
        "exact_candidate_player_names"
    ] = join_pipe(
        exact_names
    )

    if len(exact_ids) == 1:
        result[
            "diagnosis"
        ] = "EXACT_NAME_UNIQUE_CANDIDATE"

        return result

    if len(exact_ids) > 1:
        result[
            "diagnosis"
        ] = "EXACT_NAME_AMBIGUOUS"

        return result

    if normalized is None:
        result[
            "diagnosis"
        ] = "MISSING_NORMALIZED_NAME"

        return result

    normalized_key = (
        league_key,
        season,
        team_id,
        normalized,
    )

    normalized_ids = safe_unique(
        normalized_index.get(
            normalized_key,
            [],
        )
    )

    normalized_names = [
        player_id_to_name.get(
            player_id
        )
        for player_id in normalized_ids
    ]

    result[
        "normalized_candidate_count"
    ] = len(
        normalized_ids
    )

    result[
        "normalized_candidate_player_ids"
    ] = join_pipe(
        normalized_ids
    )

    result[
        "normalized_candidate_player_names"
    ] = join_pipe(
        normalized_names
    )

    if len(normalized_ids) == 1:
        result[
            "diagnosis"
        ] = "NORMALIZED_NAME_UNIQUE_CANDIDATE"

        return result

    if len(normalized_ids) > 1:
        result[
            "diagnosis"
        ] = "NORMALIZED_NAME_AMBIGUOUS"

        return result

    result[
        "diagnosis"
    ] = "NO_PLAYER_CANDIDATE_ON_ROSTER"

    return result


# ============================================================
# Extended evidence classification
# ============================================================

def investigate_unresolved_player(
    *,
    league: str | None,
    season: str | None,
    team_id: str | None,
    player_name: str | None,
    source_player_id: str | None,
    roster_indexes: dict,
    source_player_id_index: dict,
) -> dict:
    """
    Gather secondary evidence for unresolved players.

    No evidence here is used to assign a player_id.

    Evidence considered:
    1. exact same name on another team in same season
    2. normalized same name on another team in same season
    3. exact same name in another season
    4. normalized same name in another season
    5. same surname + first initial in same season
    6. source_player_id already resolved elsewhere in same league/season
    """
    league_key = (
        league.lower()
        if league
        else None
    )

    exact_name = casefold_exact_name(
        player_name
    )
    normalized = normalize_name(
        player_name
    )
    player_surname = surname(
        player_name
    )
    player_initial = first_initial(
        player_name
    )

    player_id_to_name = roster_indexes[
        "player_id_to_name"
    ]

    same_season_exact = []
    same_season_normalized = []
    other_season_exact = []
    other_season_normalized = []
    surname_initial_matches = []

    if (
        league_key
        and season
        and exact_name
    ):
        same_season_exact = (
            roster_indexes[
                "same_season_exact_index"
            ].get(
                (
                    league_key,
                    season,
                    exact_name,
                ),
                [],
            )
        )

    if (
        league_key
        and season
        and normalized
    ):
        same_season_normalized = (
            roster_indexes[
                "same_season_normalized_index"
            ].get(
                (
                    league_key,
                    season,
                    normalized,
                ),
                [],
            )
        )

    if (
        league_key
        and exact_name
    ):
        all_exact = (
            roster_indexes[
                "all_seasons_exact_index"
            ].get(
                (
                    league_key,
                    exact_name,
                ),
                [],
            )
        )

        other_season_exact = [
            candidate
            for candidate in all_exact
            if candidate[0] != season
        ]

    if (
        league_key
        and normalized
    ):
        all_normalized = (
            roster_indexes[
                "all_seasons_normalized_index"
            ].get(
                (
                    league_key,
                    normalized,
                ),
                [],
            )
        )

        other_season_normalized = [
            candidate
            for candidate in all_normalized
            if candidate[0] != season
        ]

    if (
        league_key
        and season
        and player_surname
        and player_initial
    ):
        surname_initial_matches = (
            roster_indexes[
                "surname_initial_index"
            ].get(
                (
                    league_key,
                    season,
                    player_surname,
                    player_initial,
                ),
                [],
            )
        )

    # Exclude the current team from "other team" evidence.
    same_season_exact_other_team = [
        candidate
        for candidate in same_season_exact
        if candidate[0] != team_id
    ]

    same_season_normalized_other_team = [
        candidate
        for candidate in same_season_normalized
        if candidate[0] != team_id
    ]

    surname_initial_other_team = [
        candidate
        for candidate in surname_initial_matches
        if candidate[0] != team_id
    ]

    same_season_exact_fmt = (
        format_team_player_candidates(
            same_season_exact_other_team,
            player_id_to_name,
        )
    )

    same_season_normalized_fmt = (
        format_team_player_candidates(
            same_season_normalized_other_team,
            player_id_to_name,
        )
    )

    other_season_exact_fmt = (
        format_season_team_player_candidates(
            other_season_exact,
            player_id_to_name,
        )
    )

    other_season_normalized_fmt = (
        format_season_team_player_candidates(
            other_season_normalized,
            player_id_to_name,
        )
    )

    surname_initial_fmt = (
        format_team_player_candidates(
            surname_initial_other_team,
            player_id_to_name,
        )
    )

    source_ids = []

    if (
        league_key
        and season
        and source_player_id
    ):
        source_ids = sorted(
            source_player_id_index.get(
                (
                    league_key,
                    season,
                    source_player_id,
                ),
                set(),
            )
        )

    source_names = [
        player_id_to_name.get(
            player_id
        )
        for player_id in source_ids
    ]

    source_candidate_count = len(
        source_ids
    )

    if source_candidate_count == 1:
        evidence_class = (
            "SOURCE_PLAYER_ID_UNIQUE_LINK"
        )
    elif source_candidate_count > 1:
        evidence_class = (
            "SOURCE_PLAYER_ID_AMBIGUOUS_LINK"
        )
    elif same_season_exact_fmt["count"] == 1:
        evidence_class = (
            "POSSIBLE_TEAM_TRANSFER_EXACT_NAME"
        )
    elif same_season_exact_fmt["count"] > 1:
        evidence_class = (
            "SAME_SEASON_EXACT_NAME_MULTIPLE_TEAMS"
        )
    elif (
        same_season_normalized_fmt["count"]
        == 1
    ):
        evidence_class = (
            "POSSIBLE_TEAM_TRANSFER_NORMALIZED_NAME"
        )
    elif (
        same_season_normalized_fmt["count"]
        > 1
    ):
        evidence_class = (
            "SAME_SEASON_NORMALIZED_NAME_MULTIPLE_TEAMS"
        )
    elif other_season_exact_fmt["count"] == 1:
        evidence_class = (
            "PLAYER_EXISTS_OTHER_SEASON_EXACT_NAME"
        )
    elif other_season_exact_fmt["count"] > 1:
        evidence_class = (
            "PLAYER_EXISTS_MULTIPLE_OTHER_SEASONS_EXACT_NAME"
        )
    elif (
        other_season_normalized_fmt["count"]
        == 1
    ):
        evidence_class = (
            "PLAYER_EXISTS_OTHER_SEASON_NORMALIZED_NAME"
        )
    elif (
        other_season_normalized_fmt["count"]
        > 1
    ):
        evidence_class = (
            "PLAYER_EXISTS_MULTIPLE_OTHER_SEASONS_NORMALIZED_NAME"
        )
    elif surname_initial_fmt["count"] == 1:
        evidence_class = (
            "POSSIBLE_NAME_VARIANT_SURNAME_INITIAL"
        )
    elif surname_initial_fmt["count"] > 1:
        evidence_class = (
            "AMBIGUOUS_SURNAME_INITIAL"
        )
    else:
        evidence_class = (
            "NO_CROSS_ROSTER_EVIDENCE"
        )

    return {
        "evidence_class": evidence_class,

        "same_season_exact_other_team_count":
            same_season_exact_fmt["count"],
        "same_season_exact_other_team_ids":
            same_season_exact_fmt["team_ids"],
        "same_season_exact_other_team_player_ids":
            same_season_exact_fmt["player_ids"],
        "same_season_exact_other_team_player_names":
            same_season_exact_fmt["player_names"],

        "same_season_normalized_other_team_count":
            same_season_normalized_fmt["count"],
        "same_season_normalized_other_team_ids":
            same_season_normalized_fmt["team_ids"],
        "same_season_normalized_other_team_player_ids":
            same_season_normalized_fmt["player_ids"],
        "same_season_normalized_other_team_player_names":
            same_season_normalized_fmt["player_names"],

        "other_season_exact_count":
            other_season_exact_fmt["count"],
        "other_season_exact_seasons":
            other_season_exact_fmt["seasons"],
        "other_season_exact_team_ids":
            other_season_exact_fmt["team_ids"],
        "other_season_exact_player_ids":
            other_season_exact_fmt["player_ids"],
        "other_season_exact_player_names":
            other_season_exact_fmt["player_names"],

        "other_season_normalized_count":
            other_season_normalized_fmt["count"],
        "other_season_normalized_seasons":
            other_season_normalized_fmt["seasons"],
        "other_season_normalized_team_ids":
            other_season_normalized_fmt["team_ids"],
        "other_season_normalized_player_ids":
            other_season_normalized_fmt["player_ids"],
        "other_season_normalized_player_names":
            other_season_normalized_fmt["player_names"],

        "surname_initial_other_team_count":
            surname_initial_fmt["count"],
        "surname_initial_other_team_ids":
            surname_initial_fmt["team_ids"],
        "surname_initial_other_team_player_ids":
            surname_initial_fmt["player_ids"],
        "surname_initial_other_team_player_names":
            surname_initial_fmt["player_names"],

        "source_player_id_candidate_count":
            source_candidate_count,
        "source_player_id_candidate_player_ids":
            join_pipe(source_ids),
        "source_player_id_candidate_player_names":
            join_pipe(source_names),
    }



# ============================================================
# Final disposition classification
# ============================================================

def classify_final_disposition(
    diagnosis: str | None,
    evidence_class: str | None,
) -> str:
    """
    Convert detailed diagnosis/evidence into a stable final disposition.

    These dispositions are intentionally conservative and describe WHY
    the row remains unresolved. They do not assign canonical IDs.

    SOURCE_ROSTER_MISSING
        No roster exists for the league + season + team_id context.

    SOURCE_PLAYER_NOT_ON_ROSTER
        The roster exists, but there is no usable player candidate and no
        supporting cross-roster evidence.

    SOURCE_PLAYER_IDENTITY_AMBIGUOUS
        Multiple exact/normalized candidates exist and normalization cannot
        determine which canonical player is correct.

    CROSS_SEASON_IDENTITY_ONLY
        The player name exists in one or more other seasons, but cross-season
        UUID reuse is not considered safe.

    NAME_VARIANT_REVIEW
        Only weaker name-variant evidence exists, such as surname + initial
        or normalized-name evidence that is not strong enough for automatic
        resolution.

    SOURCE_IDENTITY_CONTEXT_MISSING
        Required identity context is missing from the source row.

    NO_IDENTITY_EVIDENCE
        No stronger classification applies.
    """
    diagnosis = diagnosis or ""
    evidence_class = evidence_class or ""

    if diagnosis == "NO_ROSTER_FOR_TEAM_SEASON":
        return "SOURCE_ROSTER_MISSING"

    if diagnosis in {
        "EXACT_NAME_AMBIGUOUS",
        "NORMALIZED_NAME_AMBIGUOUS",
    }:
        return "SOURCE_PLAYER_IDENTITY_AMBIGUOUS"

    if diagnosis in {
        "MISSING_IDENTITY_CONTEXT",
        "MISSING_PLAYER_NAME",
        "MISSING_NORMALIZED_NAME",
    }:
        return "SOURCE_IDENTITY_CONTEXT_MISSING"

    if evidence_class in {
        "PLAYER_EXISTS_OTHER_SEASON_EXACT_NAME",
        "PLAYER_EXISTS_MULTIPLE_OTHER_SEASONS_EXACT_NAME",
    }:
        return "CROSS_SEASON_IDENTITY_ONLY"

    if evidence_class in {
        "PLAYER_EXISTS_OTHER_SEASON_NORMALIZED_NAME",
        "PLAYER_EXISTS_MULTIPLE_OTHER_SEASONS_NORMALIZED_NAME",
        "POSSIBLE_NAME_VARIANT_SURNAME_INITIAL",
        "AMBIGUOUS_SURNAME_INITIAL",
        "POSSIBLE_TEAM_TRANSFER_NORMALIZED_NAME",
        "SAME_SEASON_NORMALIZED_NAME_MULTIPLE_TEAMS",
    }:
        return "NAME_VARIANT_REVIEW"

    if evidence_class in {
        "POSSIBLE_TEAM_TRANSFER_EXACT_NAME",
        "SAME_SEASON_EXACT_NAME_MULTIPLE_TEAMS",
    }:
        return "SOURCE_PLAYER_IDENTITY_AMBIGUOUS"

    if diagnosis == "NO_PLAYER_CANDIDATE_ON_ROSTER":
        if evidence_class == "NO_CROSS_ROSTER_EVIDENCE":
            return "SOURCE_PLAYER_NOT_ON_ROSTER"

        return "NO_IDENTITY_EVIDENCE"

    return "NO_IDENTITY_EVIDENCE"


def add_final_disposition(
    df: pl.DataFrame,
) -> pl.DataFrame:
    """
    Add final_disposition to an audit DataFrame without modifying any
    canonical IDs or source data.
    """
    if df.is_empty():
        if "final_disposition" not in df.columns:
            return df.with_columns(
                pl.lit(None, dtype=pl.String).alias("final_disposition")
            )
        return df

    if "diagnosis" not in df.columns:
        return df

    evidence_expr = (
        pl.col("evidence_class")
        if "evidence_class" in df.columns
        else pl.lit(None, dtype=pl.String)
    )

    return df.with_columns(
        pl.struct(
            [
                pl.col("diagnosis"),
                evidence_expr.alias("evidence_class"),
            ]
        )
        .map_elements(
            lambda x: classify_final_disposition(
                x.get("diagnosis"),
                x.get("evidence_class"),
            ),
            return_dtype=pl.String,
        )
        .alias("final_disposition")
    )


def build_final_disposition_output(
    player_season_audit: pl.DataFrame,
    player_game_audit: pl.DataFrame,
    team_season_audit: pl.DataFrame,
) -> pl.DataFrame:
    """
    Produce one compact queue of every unresolved row with its final
    disposition.

    Team-season unresolved rows receive TEAM_SOURCE_UNRESOLVED because
    their diagnostics are team-level rather than player-level.
    """
    frames = []

    if not player_season_audit.is_empty():
        frames.append(
            player_season_audit.with_columns(
                pl.lit("player_season_stats").alias("source_table")
            )
        )

    if not player_game_audit.is_empty():
        frames.append(
            player_game_audit.with_columns(
                pl.lit("player_game_stats").alias("source_table")
            )
        )

    if not team_season_audit.is_empty():
        team_frame = (
            team_season_audit
            .with_columns(
                [
                    pl.lit("team_season_stats").alias("source_table"),
                    pl.lit("TEAM_SOURCE_UNRESOLVED").alias("final_disposition"),
                ]
            )
        )
        frames.append(team_frame)

    if not frames:
        return pl.DataFrame(
            {
                "source_table": [],
                "league": [],
                "season": [],
                "final_disposition": [],
            }
        )

    return (
        pl.concat(
            frames,
            how="diagonal_relaxed",
        )
        .sort(
            [
                "final_disposition",
                "source_table",
                "league",
                "season",
            ]
        )
    )


def summarize_final_dispositions(
    df: pl.DataFrame,
) -> pl.DataFrame:
    if df.is_empty():
        return pl.DataFrame(
            {
                "source_table": [],
                "final_disposition": [],
                "count": [],
            }
        )

    return (
        df
        .group_by(
            [
                "source_table",
                "final_disposition",
            ]
        )
        .len()
        .rename({"len": "count"})
        .sort(
            [
                "source_table",
                "count",
            ],
            descending=[
                False,
                True,
            ],
        )
    )


# ============================================================
# Player-season audit
# ============================================================

def audit_player_season_stats(
    player_season_stats: pl.DataFrame,
    rosters: pl.DataFrame,
    players: pl.DataFrame,
    player_game_stats: pl.DataFrame,
) -> pl.DataFrame:
    roster_indexes = build_roster_indexes(
        rosters,
        players,
    )

    source_player_id_index = (
        build_source_player_id_index(
            player_game_stats
        )
    )

    unresolved = player_season_stats.filter(
        pl.col("player_id").is_null()
    )

    records = []

    for row_number, row in enumerate(
        unresolved.iter_rows(
            named=True
        ),
        start=1,
    ):
        league = clean_string(
            row.get("league")
        )
        season = clean_string(
            row.get("season")
        )
        team_id = clean_string(
            row.get("team_id")
        )
        player_name = clean_string(
            row.get("player_name")
        )
        team_name = clean_string(
            row.get("team_name")
        )

        diagnosis = (
            classify_player_resolution(
                league=league,
                season=season,
                team_id=team_id,
                player_name=player_name,
                roster_indexes=roster_indexes,
            )
        )

        evidence = (
            investigate_unresolved_player(
                league=league,
                season=season,
                team_id=team_id,
                player_name=player_name,
                source_player_id=None,
                roster_indexes=roster_indexes,
                source_player_id_index=source_player_id_index,
            )
        )

        record = {
            "audit_row": row_number,
            "league": league,
            "season": season,
            "team_id": team_id,
            "team_name": team_name,
            "player_name": player_name,
            **diagnosis,
            **evidence,
        }

        for column in [
            "rank",
            "position",
            "stat_type",
            "source",
            "source_file",
        ]:
            if column in row:
                record[
                    column
                ] = row.get(
                    column
                )

        records.append(
            record
        )

    return pl.DataFrame(
        records,
        infer_schema_length=None,
    ) if records else pl.DataFrame(
        {
            "audit_row": [],
            "league": [],
            "season": [],
            "team_id": [],
            "team_name": [],
            "player_name": [],
            "diagnosis": [],
            "evidence_class": [],
        }
    )


# ============================================================
# Player-game audit
# ============================================================

def audit_player_game_stats(
    player_game_stats: pl.DataFrame,
    rosters: pl.DataFrame,
    players: pl.DataFrame,
) -> pl.DataFrame:
    roster_indexes = build_roster_indexes(
        rosters,
        players,
    )

    source_player_id_index = (
        build_source_player_id_index(
            player_game_stats
        )
    )

    unresolved = player_game_stats.filter(
        pl.col("player_id").is_null()
    )

    source_id_frequency = {}

    if "source_player_id" in unresolved.columns:
        for row in (
            unresolved
            .filter(
                pl.col(
                    "source_player_id"
                ).is_not_null()
            )
            .group_by(
                [
                    "league",
                    "season",
                    "source_player_id",
                ]
            )
            .len()
            .iter_rows(
                named=True
            )
        ):
            key = (
                clean_string(
                    row.get("league")
                ),
                clean_string(
                    row.get("season")
                ),
                clean_string(
                    row.get(
                        "source_player_id"
                    )
                ),
            )

            source_id_frequency[
                key
            ] = row["len"]

    records = []

    for row_number, row in enumerate(
        unresolved.iter_rows(
            named=True
        ),
        start=1,
    ):
        league = clean_string(
            row.get("league")
        )
        season = clean_string(
            row.get("season")
        )
        team_id = clean_string(
            row.get("team_id")
        )
        team_name = clean_string(
            row.get("team_name")
        )
        player_name = clean_string(
            row.get("player_name")
        )
        source_player_id = clean_string(
            row.get("source_player_id")
        )
        game_id = clean_string(
            row.get("game_id")
        )

        diagnosis = (
            classify_player_resolution(
                league=league,
                season=season,
                team_id=team_id,
                player_name=player_name,
                roster_indexes=roster_indexes,
            )
        )

        evidence = (
            investigate_unresolved_player(
                league=league,
                season=season,
                team_id=team_id,
                player_name=player_name,
                source_player_id=source_player_id,
                roster_indexes=roster_indexes,
                source_player_id_index=source_player_id_index,
            )
        )

        source_key = (
            league,
            season,
            source_player_id,
        )

        source_occurrences = (
            source_id_frequency.get(
                source_key,
                0,
            )
            if source_player_id
            else 0
        )

        record = {
            "audit_row": row_number,
            "league": league,
            "season": season,
            "game_id": game_id,
            "team_id": team_id,
            "team_name": team_name,
            "source_player_id": source_player_id,
            "source_player_id_unresolved_occurrences":
                source_occurrences,
            "player_name": player_name,
            **diagnosis,
            **evidence,
        }

        for column in [
            "week",
            "game_date",
            "season_type",
        ]:
            if column in row:
                record[
                    column
                ] = row.get(
                    column
                )

        records.append(
            record
        )

    return pl.DataFrame(
        records,
        infer_schema_length=None,
    ) if records else pl.DataFrame(
        {
            "audit_row": [],
            "league": [],
            "season": [],
            "game_id": [],
            "team_id": [],
            "team_name": [],
            "source_player_id": [],
            "player_name": [],
            "diagnosis": [],
            "evidence_class": [],
        }
    )


# ============================================================
# Team-season audit
# ============================================================

def audit_team_season_stats(
    team_season_stats: pl.DataFrame,
    teams: pl.DataFrame,
) -> pl.DataFrame:
    (
        _,
        exact_name_index,
        normalized_name_index,
    ) = build_team_indexes(
        teams
    )

    unresolved = team_season_stats.filter(
        pl.col("team_id").is_null()
    )

    records = []

    for row_number, row in enumerate(
        unresolved.iter_rows(
            named=True
        ),
        start=1,
    ):
        league = clean_string(
            row.get("league")
        )
        season = clean_string(
            row.get("season")
        )
        team_name = clean_string(
            row.get("team_name")
        )
        team_city = clean_string(
            row.get("team_city")
        )

        league_key = (
            league.lower()
            if league
            else None
        )

        exact_ids = []
        normalized_ids = []

        if (
            league_key
            and season
            and team_name
        ):
            exact_ids = safe_unique(
                exact_name_index.get(
                    (
                        league_key,
                        season,
                        team_name.lower(),
                    ),
                    [],
                )
            )

            normalized = normalize_name(
                team_name
            )

            if normalized:
                normalized_ids = safe_unique(
                    normalized_name_index.get(
                        (
                            league_key,
                            season,
                            normalized,
                        ),
                        [],
                    )
                )
        else:
            normalized = normalize_name(
                team_name
            )

        if len(exact_ids) == 1:
            diagnosis = (
                "EXACT_TEAM_NAME_UNIQUE_CANDIDATE"
            )
        elif len(exact_ids) > 1:
            diagnosis = (
                "EXACT_TEAM_NAME_AMBIGUOUS"
            )
        elif len(normalized_ids) == 1:
            diagnosis = (
                "NORMALIZED_TEAM_NAME_UNIQUE_CANDIDATE"
            )
        elif len(normalized_ids) > 1:
            diagnosis = (
                "NORMALIZED_TEAM_NAME_AMBIGUOUS"
            )
        else:
            diagnosis = (
                "NO_TEAM_CANDIDATE"
            )

        records.append(
            {
                "audit_row": row_number,
                "league": league,
                "season": season,
                "team_city": team_city,
                "team_name": team_name,
                "normalized_team_name": normalized,
                "exact_candidate_count": len(
                    exact_ids
                ),
                "exact_candidate_team_ids": join_pipe(
                    exact_ids
                ),
                "normalized_candidate_count": len(
                    normalized_ids
                ),
                "normalized_candidate_team_ids": join_pipe(
                    normalized_ids
                ),
                "diagnosis": diagnosis,
            }
        )

    return pl.DataFrame(
        records,
        infer_schema_length=None,
    ) if records else pl.DataFrame(
        {
            "audit_row": [],
            "league": [],
            "season": [],
            "team_city": [],
            "team_name": [],
            "normalized_team_name": [],
            "exact_candidate_count": [],
            "exact_candidate_team_ids": [],
            "normalized_candidate_count": [],
            "normalized_candidate_team_ids": [],
            "diagnosis": [],
        }
    )


# ============================================================
# Cross-audit evidence outputs
# ============================================================

def build_candidate_evidence_output(
    player_season_audit: pl.DataFrame,
    player_game_audit: pl.DataFrame,
) -> pl.DataFrame:
    """
    Combine only rows where the roster exists but the player could not be
    resolved.

    This is the most useful queue for investigating:
    - team transfers
    - name variants
    - cross-season identity evidence
    - true roster omissions
    """
    frames = []

    if not player_season_audit.is_empty():
        season_candidates = (
            player_season_audit
            .filter(
                pl.col("diagnosis")
                == "NO_PLAYER_CANDIDATE_ON_ROSTER"
            )
            .with_columns(
                pl.lit(
                    "player_season_stats"
                ).alias(
                    "source_table"
                )
            )
        )

        frames.append(
            season_candidates
        )

    if not player_game_audit.is_empty():
        game_candidates = (
            player_game_audit
            .filter(
                pl.col("diagnosis")
                == "NO_PLAYER_CANDIDATE_ON_ROSTER"
            )
            .with_columns(
                pl.lit(
                    "player_game_stats"
                ).alias(
                    "source_table"
                )
            )
        )

        frames.append(
            game_candidates
        )

    if not frames:
        return pl.DataFrame(
            {
                "source_table": [],
                "league": [],
                "season": [],
                "team_id": [],
                "team_name": [],
                "player_name": [],
                "evidence_class": [],
            }
        )

    return (
        pl.concat(
            frames,
            how="diagonal_relaxed",
        )
        .sort(
            [
                "evidence_class",
                "league",
                "season",
                "team_name",
                "player_name",
            ]
        )
    )


def build_source_player_id_evidence_output(
    player_game_audit: pl.DataFrame,
) -> pl.DataFrame:
    """
    Return unresolved game rows whose source_player_id has already mapped
    to one or more canonical player IDs elsewhere.
    """
    if player_game_audit.is_empty():
        return pl.DataFrame(
            {
                "league": [],
                "season": [],
                "game_id": [],
                "team_id": [],
                "team_name": [],
                "player_name": [],
                "source_player_id": [],
                "source_player_id_candidate_count": [],
                "source_player_id_candidate_player_ids": [],
                "source_player_id_candidate_player_names": [],
                "evidence_class": [],
            }
        )

    return (
        player_game_audit
        .filter(
            pl.col(
                "source_player_id_candidate_count"
            )
            > 0
        )
        .select(
            [
                "league",
                "season",
                "game_id",
                "team_id",
                "team_name",
                "player_name",
                "source_player_id",
                "source_player_id_unresolved_occurrences",
                "source_player_id_candidate_count",
                "source_player_id_candidate_player_ids",
                "source_player_id_candidate_player_names",
                "diagnosis",
                "evidence_class",
            ]
        )
        .sort(
            [
                "league",
                "season",
                "source_player_id",
                "game_id",
            ]
        )
    )


# ============================================================
# Summary builders
# ============================================================

def summarize_audit(
    table_name: str,
    df: pl.DataFrame,
) -> pl.DataFrame:
    if df.is_empty():
        return pl.DataFrame(
            {
                "table": [table_name],
                "diagnosis": [
                    "NO_UNRESOLVED_ROWS"
                ],
                "count": [0],
            }
        )

    return (
        df
        .group_by(
            "diagnosis"
        )
        .len()
        .rename(
            {
                "len": "count",
            }
        )
        .with_columns(
            pl.lit(
                table_name
            ).alias(
                "table"
            )
        )
        .select(
            [
                "table",
                "diagnosis",
                "count",
            ]
        )
        .sort(
            "count",
            descending=True,
        )
    )


def summarize_player_season_by_period(
    df: pl.DataFrame,
) -> pl.DataFrame:
    if df.is_empty():
        return pl.DataFrame(
            schema={
                "league": pl.String,
                "season": pl.String,
                "diagnosis": pl.String,
                "count": pl.Int64,
            }
        )

    return (
        df
        .group_by(
            [
                "league",
                "season",
                "diagnosis",
            ]
        )
        .len()
        .rename(
            {
                "len": "count",
            }
        )
        .sort(
            [
                "league",
                "season",
                "count",
            ],
            descending=[
                False,
                False,
                True,
            ],
        )
    )


def summarize_evidence(
    df: pl.DataFrame,
) -> pl.DataFrame:
    if df.is_empty():
        return pl.DataFrame(
            {
                "evidence_class": [
                    "NO_ROWS"
                ],
                "count": [0],
            }
        )

    return (
        df
        .group_by(
            "evidence_class"
        )
        .len()
        .rename(
            {
                "len": "count",
            }
        )
        .sort(
            "count",
            descending=True,
        )
    )


# ============================================================
# Console reporting
# ============================================================

def print_section(
    title: str,
):
    print(
        "\n"
        + "=" * 70
    )
    print(
        title
    )
    print(
        "=" * 70
    )


def print_diagnosis_summary(
    label: str,
    df: pl.DataFrame,
):
    print(
        f"\n{label}: "
        f"{df.height:,} unresolved row(s)"
    )

    if df.is_empty():
        return

    summary = (
        df
        .group_by(
            "diagnosis"
        )
        .len()
        .sort(
            "len",
            descending=True,
        )
    )

    for row in summary.iter_rows(
        named=True
    ):
        print(
            f"  {row['diagnosis']:<42} "
            f"{row['len']:>6,}"
        )


def print_player_season_period_summary(
    df: pl.DataFrame,
):
    if df.is_empty():
        return

    print(
        "\nPlayer-season unresolved rows by league/season:"
    )

    summary = (
        df
        .group_by(
            [
                "league",
                "season",
            ]
        )
        .len()
        .sort(
            [
                "league",
                "season",
            ]
        )
    )

    for row in summary.iter_rows(
        named=True
    ):
        print(
            f"  {row['league']:<6} "
            f"{row['season']:<8} "
            f"{row['len']:>6,}"
        )


def print_evidence_summary(
    candidate_evidence: pl.DataFrame,
):
    print(
        "\nCandidate evidence for rows where roster exists "
        "but player is unresolved:"
    )

    if candidate_evidence.is_empty():
        print(
            "  No candidate rows."
        )
        return

    summary = summarize_evidence(
        candidate_evidence
    )

    for row in summary.iter_rows(
        named=True
    ):
        print(
            f"  {row['evidence_class']:<52} "
            f"{row['count']:>6,}"
        )


# ============================================================
# Main
# ============================================================

def audit_all():
    ensure_validation_dir()

    print_section(
        "AUDITING HOSTEDSPORTS UNRESOLVED IDENTITIES"
    )

    teams = load_csv(
        FILES["teams"]
    )

    players = load_csv(
        FILES["players"]
    )

    rosters = load_csv(
        FILES["rosters"]
    )

    player_game_stats = load_csv(
        FILES[
            "player_game_stats"
        ]
    )

    player_season_stats = load_csv(
        FILES[
            "player_season_stats"
        ]
    )

    team_season_stats = load_csv(
        FILES[
            "team_season_stats"
        ]
    )

    print(
        "\nProcessed source counts:"
    )

    print(
        f"  teams:               "
        f"{teams.height:,}"
    )

    print(
        f"  players:             "
        f"{players.height:,}"
    )

    print(
        f"  rosters:             "
        f"{rosters.height:,}"
    )

    print(
        f"  player_game_stats:   "
        f"{player_game_stats.height:,}"
    )

    print(
        f"  player_season_stats: "
        f"{player_season_stats.height:,}"
    )

    print(
        f"  team_season_stats:   "
        f"{team_season_stats.height:,}"
    )

    player_season_audit = (
        audit_player_season_stats(
            player_season_stats,
            rosters,
            players,
            player_game_stats,
        )
    )

    player_game_audit = (
        audit_player_game_stats(
            player_game_stats,
            rosters,
            players,
        )
    )

    team_season_audit = (
        audit_team_season_stats(
            team_season_stats,
            teams,
        )
    )

    player_season_audit = add_final_disposition(
        player_season_audit
    )

    player_game_audit = add_final_disposition(
        player_game_audit
    )

    candidate_evidence = (
        build_candidate_evidence_output(
            player_season_audit,
            player_game_audit,
        )
    )

    source_player_id_evidence = (
        build_source_player_id_evidence_output(
            player_game_audit
        )
    )

    final_disposition_output_df = (
        build_final_disposition_output(
            player_season_audit,
            player_game_audit,
            team_season_audit,
        )
    )

    final_disposition_summary_df = (
        summarize_final_dispositions(
            final_disposition_output_df
        )
    )

    player_season_output = (
        VALIDATION_DATA_DIR
        / "unresolved_player_season_audit.csv"
    )

    player_game_output = (
        VALIDATION_DATA_DIR
        / "unresolved_player_game_audit.csv"
    )

    team_season_output = (
        VALIDATION_DATA_DIR
        / "unresolved_team_season_audit.csv"
    )

    candidate_evidence_output = (
        VALIDATION_DATA_DIR
        / "unresolved_player_candidate_evidence.csv"
    )

    source_player_id_evidence_output = (
        VALIDATION_DATA_DIR
        / "unresolved_source_player_id_evidence.csv"
    )

    final_disposition_output = (
        VALIDATION_DATA_DIR
        / "unresolved_final_disposition.csv"
    )

    final_disposition_summary_output = (
        VALIDATION_DATA_DIR
        / "unresolved_final_disposition_summary.csv"
    )

    player_season_audit.write_csv(
        player_season_output
    )

    player_game_audit.write_csv(
        player_game_output
    )

    team_season_audit.write_csv(
        team_season_output
    )

    candidate_evidence.write_csv(
        candidate_evidence_output
    )

    source_player_id_evidence.write_csv(
        source_player_id_evidence_output
    )

    final_disposition_output_df.write_csv(
        final_disposition_output
    )

    final_disposition_summary_df.write_csv(
        final_disposition_summary_output
    )

    summaries = [
        summarize_audit(
            "player_season_stats",
            player_season_audit,
        ),
        summarize_audit(
            "player_game_stats",
            player_game_audit,
        ),
        summarize_audit(
            "team_season_stats",
            team_season_audit,
        ),
    ]

    summary_df = pl.concat(
        summaries,
        how="diagonal_relaxed",
    )

    summary_output = (
        VALIDATION_DATA_DIR
        / "unresolved_summary.csv"
    )

    summary_df.write_csv(
        summary_output
    )

    period_summary = (
        summarize_player_season_by_period(
            player_season_audit
        )
    )

    period_output = (
        VALIDATION_DATA_DIR
        / "unresolved_player_season_by_period.csv"
    )

    period_summary.write_csv(
        period_output
    )

    print_section(
        "AUDIT RESULTS"
    )

    print_diagnosis_summary(
        "player_season_stats",
        player_season_audit,
    )

    print_player_season_period_summary(
        player_season_audit
    )

    print_diagnosis_summary(
        "player_game_stats",
        player_game_audit,
    )

    print_diagnosis_summary(
        "team_season_stats",
        team_season_audit,
    )

    print_evidence_summary(
        candidate_evidence
    )

    print(
        "\nFinal unresolved dispositions:"
    )

    if final_disposition_summary_df.is_empty():
        print(
            "  No unresolved rows."
        )
    else:
        for row in final_disposition_summary_df.iter_rows(
            named=True
        ):
            print(
                f"  {row['source_table']:<22} "
                f"{row['final_disposition']:<36} "
                f"{row['count']:>6,}"
            )

    print(
        "\nSource-player-ID evidence:"
    )

    print(
        f"  unresolved game rows with a previously resolved "
        f"source_player_id link: "
        f"{source_player_id_evidence.height:,}"
    )

    if not source_player_id_evidence.is_empty():
        unique_links = (
            source_player_id_evidence
            .select(
                [
                    "league",
                    "season",
                    "source_player_id",
                    "source_player_id_candidate_player_ids",
                ]
            )
            .unique()
            .height
        )

        print(
            f"  unique source-player-ID link groups: "
            f"{unique_links:,}"
        )

    print(
        "\nAudit files written:"
    )

    print(
        f"  {player_season_output}"
    )

    print(
        f"  {player_game_output}"
    )

    print(
        f"  {team_season_output}"
    )

    print(
        f"  {summary_output}"
    )

    print(
        f"  {period_output}"
    )

    print(
        f"  {candidate_evidence_output}"
    )

    print(
        f"  {source_player_id_evidence_output}"
    )

    print(
        f"  {final_disposition_output}"
    )

    print(
        f"  {final_disposition_summary_output}"
    )

    print(
        "\nImportant:"
    )

    print(
        "  audit.py does not assign or modify canonical IDs."
    )

    print(
        "  Evidence classes are investigation signals only."
    )

    print(
        "  No fuzzy match or inferred identity is written back "
        "to processed data."
    )

    print(
        "\nAudit finished."
    )


def main():
    audit_all()


if __name__ == "__main__":
    main()
