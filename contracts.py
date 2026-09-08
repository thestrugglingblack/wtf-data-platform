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

CONTRACT_VERSION = "2.0.0"


# ============================================================
# Contract Model
# ============================================================

@dataclass(frozen=True)
class DatasetContract:
    """
    Stable schema contract for one published dataset.

    Attributes
    ----------
    name:
        Canonical dataset name.

    description:
        Human-readable explanation of the dataset.

    grain:
        What one row represents.

    required_columns:
        Columns that must exist for publication.

    primary_key:
        Logical row identifier used for contract validation.

        Some historical/source-quality issues may still be surfaced as
        warnings by validate.py rather than being treated as structural
        publication failures.

    partition_columns:
        Columns used when publishing partitioned Parquet datasets.

    required_dtypes:
        Stable data types required for selected columns.

        Only core fields are locked here. Individual football statistic
        columns are intentionally not all contracted because historical
        HostedSports coverage varies.

    allow_additional_columns:
        Whether the dataset may contain columns that are not explicitly
        listed in required_columns or required_dtypes.
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
            "Canonical team records by league and season, including "
            "HostedSports team identifiers and organizational hierarchy."
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
            "Canonical player identity table derived from HostedSports "
            "roster data."
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
            "Player-to-team roster membership by league and season."
        ),
        grain=(
            "One row per league, season, team, and canonical player."
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
            "Canonical game schedule and result records."
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
            "date",
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
            "date": pl.Date,
            "visitor_team_name": pl.String,
            "home_team_name": pl.String,
        },
    ),

    # --------------------------------------------------------
    # Player Game Stats
    # --------------------------------------------------------
    "player_game_stats": DatasetContract(
        name="player_game_stats",
        description=(
            "Player-level game statistics with both HostedSports source "
            "player identifiers and canonical player identifiers where "
            "identity resolution is possible."
        ),
        grain=(
            "One row per league, season, game, team, and canonical player "
            "when player identity is resolved."
        ),
        required_columns=(
            "league",
            "season",
            "game_id",
            "date",
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
            "date": pl.Date,
            "team_id": pl.String,
            "team_name": pl.String,
            "source_player_id": pl.String,
            "player_id": pl.String,
            "player_name": pl.String,
        },
    ),

    # --------------------------------------------------------
    # Player Season Stats
    # --------------------------------------------------------
    "player_season_stats": DatasetContract(
        name="player_season_stats",
        description=(
            "Player-level season statistics merged across HostedSports "
            "offensive, defensive, scoring, and special-teams categories."
        ),
        grain=(
            "One row per league, season, team, and canonical player "
            "when player identity is resolved."
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
    # Team Season Stats
    # --------------------------------------------------------
    "team_season_stats": DatasetContract(
        name="team_season_stats",
        description=(
            "Team-level season statistics with canonical team identifiers "
            "where source team identity can be resolved."
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
            "League standings by season, including hierarchy, records, "
            "win percentage, scoring totals, and streak information."
        ),
        grain=(
            "One row per league, season, and team standing."
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
# Contract Access
# ============================================================

def get_contract(
    dataset: str,
) -> DatasetContract:
    """
    Return the schema contract for a dataset.

    Raises
    ------
    KeyError
        If the requested dataset is not part of the published WTF
        data product.
    """
    try:
        return DATASET_CONTRACTS[dataset]
    except KeyError as exc:
        supported = ", ".join(
            sorted(DATASET_CONTRACTS)
        )

        raise KeyError(
            f"Unknown dataset {dataset!r}. "
            f"Supported datasets: {supported}"
        ) from exc