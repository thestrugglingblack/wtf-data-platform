from __future__ import annotations

"""
Schema contracts for the WTF canonical data product.

A schema contract defines the agreement between the WTF data platform
and downstream consumers.

The contract defines:

1. Required columns
2. Required data types
3. Logical dataset grain
4. Logical primary key
5. Physical partitioning strategy

The exact schema of every published release is still captured in:

- manifest.json
- data_dictionary.json
- DATA_DICTIONARY.md
"""

from dataclasses import dataclass

import polars as pl


# ============================================================
# Contract Version
# ============================================================

CONTRACT_VERSION = "1.0.0"


# ============================================================
# Contract Model
# ============================================================

@dataclass(frozen=True)
class DatasetContract:
    """
    Defines the stable contract for one canonical dataset.

    Attributes
    ----------
    name:
        Canonical dataset name.

    description:
        Human-readable description of the dataset.

    grain:
        What one row represents.

    required_columns:
        Columns that must exist before the dataset can be published.

    primary_key:
        Intended logical key for the dataset.

    partition_columns:
        Columns used when physically partitioning the Parquet dataset.

    required_dtypes:
        Stable columns whose types must not silently change.

    allow_additional_columns:
        Whether columns outside the required contract may exist.
        This is intentionally True for WTF because historical
        HostedSports stat coverage varies.
    """

    name: str

    description: str

    grain: str

    required_columns: tuple[str, ...]

    primary_key: tuple[str, ...]

    partition_columns: tuple[str, ...]

    required_dtypes: dict[str, pl.DataType]

    allow_additional_columns: bool = True


# ============================================================
# Dataset Contracts
# ============================================================

DATASET_CONTRACTS: dict[str, DatasetContract] = {
    # --------------------------------------------------------
    # Teams
    # --------------------------------------------------------
    "teams": DatasetContract(
        name="teams",
        description=(
            "Canonical team-season reference data for WFA and WNFC teams."
        ),
        grain=(
            "One row per league, season, and team."
        ),
        required_columns=(
            "league",
            "season",
            "team_id",
            "team_name",
        ),
        primary_key=(
            "league",
            "season",
            "team_id",
        ),
        partition_columns=(
            "league",
            "season",
        ),
        required_dtypes={
            "league": pl.String,
            "season": pl.Int64,
            "team_id": pl.String,
            "team_name": pl.String,
        },
    ),

    # --------------------------------------------------------
    # Players
    # --------------------------------------------------------
    "players": DatasetContract(
        name="players",
        description=(
            "Canonical player reference table keyed by the "
            "HostedSports roster player identifier."
        ),
        grain=(
            "One row per canonical player."
        ),
        required_columns=(
            "player_id",
            "player_name",
        ),
        primary_key=(
            "player_id",
        ),
        partition_columns=(),
        required_dtypes={
            "player_id": pl.String,
            "player_name": pl.String,
        },
    ),

    # --------------------------------------------------------
    # Rosters
    # --------------------------------------------------------
    "rosters": DatasetContract(
        name="rosters",
        description=(
            "Player membership on a team for a specific league season."
        ),
        grain=(
            "One row per league, season, team, and player."
        ),
        required_columns=(
            "league",
            "season",
            "team_id",
            "team_name",
            "player_id",
        ),
        primary_key=(
            "league",
            "season",
            "team_id",
            "player_id",
        ),
        partition_columns=(
            "league",
            "season",
        ),
        required_dtypes={
            "league": pl.String,
            "season": pl.Int64,
            "team_id": pl.String,
            "team_name": pl.String,
            "player_id": pl.String,
        },
    ),

    # --------------------------------------------------------
    # Games
    # --------------------------------------------------------
    "games": DatasetContract(
        name="games",
        description=(
            "Canonical schedule and game-result table."
        ),
        grain=(
            "One row per league, season, and game."
        ),
        required_columns=(
            "league",
            "season",
            "game_id",
            "season_type",
            "week",
            "visitor_team_name",
            "home_team_name",
        ),
        primary_key=(
            "league",
            "season",
            "game_id",
        ),
        partition_columns=(
            "league",
            "season",
        ),
        required_dtypes={
            "league": pl.String,
            "season": pl.Int64,
            "game_id": pl.String,
            "season_type": pl.String,
            "week": pl.Int64,
            "visitor_team_name": pl.String,
            "home_team_name": pl.String,
        },
    ),

    # --------------------------------------------------------
    # Player Game Statistics
    # --------------------------------------------------------
    "player_game_stats": DatasetContract(
        name="player_game_stats",
        description=(
            "Player-level statistics for an individual game. "
            "source_player_id preserves the identifier supplied by the "
            "HostedSports game-stat endpoint while player_id contains "
            "the resolved canonical roster identifier when available."
        ),
        grain=(
            "One row per league, season, game, team, and player identity."
        ),
        required_columns=(
            "league",
            "season",
            "game_id",
            "team_id",
            "team_name",
            "source_player_id",
            "player_id",
            "player_name",
        ),
        primary_key=(
            "league",
            "season",
            "game_id",
            "team_id",
            "player_id",
        ),
        partition_columns=(
            "league",
            "season",
        ),
        required_dtypes={
            "league": pl.String,
            "season": pl.Int64,
            "game_id": pl.String,
            "team_id": pl.String,
            "team_name": pl.String,
            "source_player_id": pl.String,
            "player_id": pl.String,
            "player_name": pl.String,
        },
    ),

    # --------------------------------------------------------
    # Player Season Statistics
    # --------------------------------------------------------
    "player_season_stats": DatasetContract(
        name="player_season_stats",
        description=(
            "Merged player statistics across offensive, defensive, "
            "scoring, and special-teams season endpoints."
        ),
        grain=(
            "One row per league, season, team, and player identity."
        ),
        required_columns=(
            "league",
            "season",
            "team_id",
            "player_id",
            "player_name",
            "team_name",
        ),
        primary_key=(
            "league",
            "season",
            "team_id",
            "player_id",
        ),
        partition_columns=(
            "league",
            "season",
        ),
        required_dtypes={
            "league": pl.String,
            "season": pl.Int64,
            "team_id": pl.String,
            "player_id": pl.String,
            "player_name": pl.String,
            "team_name": pl.String,
        },
    ),

    # --------------------------------------------------------
    # Team Season Statistics
    # --------------------------------------------------------
    "team_season_stats": DatasetContract(
        name="team_season_stats",
        description=(
            "Team-level season statistics including scoring, yardage, "
            "first downs, penalties, and other available team metrics."
        ),
        grain=(
            "One row per league, season, and team."
        ),
        required_columns=(
            "league",
            "season",
            "team_id",
            "team_name",
        ),
        primary_key=(
            "league",
            "season",
            "team_id",
        ),
        partition_columns=(
            "league",
            "season",
        ),
        required_dtypes={
            "league": pl.String,
            "season": pl.Int64,
            "team_id": pl.String,
            "team_name": pl.String,
        },
    ),

    # --------------------------------------------------------
    # Standings
    # --------------------------------------------------------
    "standings": DatasetContract(
        name="standings",
        description=(
            "League standings with available hierarchy, records, "
            "points, and winning percentages."
        ),
        grain=(
            "One row per league, season, and standing team entry."
        ),
        required_columns=(
            "league",
            "season",
            "team_name",
            "wins",
            "losses",
            "ties",
            "win_pct",
        ),
        primary_key=(
            "league",
            "season",
            "team_name",
        ),
        partition_columns=(
            "league",
            "season",
        ),
        required_dtypes={
            "league": pl.String,
            "season": pl.Int64,
            "team_name": pl.String,
            "wins": pl.Int64,
            "losses": pl.Int64,
            "ties": pl.Int64,
            "win_pct": pl.Float64,
        },
    ),
}


# ============================================================
# Helpers
# ============================================================

def get_contract(
    dataset: str,
) -> DatasetContract:
    """
    Return the schema contract for a canonical dataset.

    Raises
    ------
    KeyError
        If the dataset is not part of the WTF canonical data product.
    """

    try:
        return DATASET_CONTRACTS[
            dataset
        ]

    except KeyError as exc:
        supported = ", ".join(
            sorted(
                DATASET_CONTRACTS
            )
        )

        raise KeyError(
            f"Unknown dataset '{dataset}'. "
            f"Supported datasets: {supported}"
        ) from exc