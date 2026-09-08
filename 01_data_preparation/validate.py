from __future__ import annotations

"""
Validate normalized HostedSports datasets.

Expected processed files:

    data/processed/
        teams.csv
        players.csv
        rosters.csv
        games.csv
        player_game_stats.csv
        player_season_stats.csv
        team_season_stats.csv
        standings.csv

Validation covers:

1. Structural validation
   - required files
   - required columns
   - logical-key uniqueness

2. Referential integrity
   - team, player, and game foreign keys

3. Domain sanity
   - nonnegative count/scoring fields where appropriate
   - valid win percentage ranges
   - home and visitor teams differ

4. Data-quality reporting
   - unresolved canonical IDs
   - duplicate logical player-game keys
   - missing scores

5. Raw-source audit
   - scan data/raw recursively for *.invalid.txt
   - classify raw invalid responses
   - preserve the raw-source audit in invalid_responses.csv

6. Recovery-aware validation
   - read data/validation/recovery_report.csv when present
   - distinguish repaired source defects from still-unrecovered defects
   - report successful recovery as INFO
   - warn only about outstanding recoverable candidates

Validation never repairs or rewrites raw source data.
"""

from dataclasses import dataclass, field
import ast
import json
from pathlib import Path
import re
from typing import Iterable

import polars as pl

from config import PROCESSED_DATA_DIR, RAW_DATA_DIR


# ============================================================
# Paths
# ============================================================

VALIDATION_DATA_DIR = PROCESSED_DATA_DIR.parent / "validation"
RECOVERED_DATA_DIR = RAW_DATA_DIR.parent / "recovered"
RECOVERY_REPORT_PATH = VALIDATION_DATA_DIR / "recovery_report.csv"


# ============================================================
# Constants
# ============================================================

EXPECTED_FILES = {
    "teams": "teams.csv",
    "players": "players.csv",
    "rosters": "rosters.csv",
    "games": "games.csv",
    "player_game_stats": "player_game_stats.csv",
    "player_season_stats": "player_season_stats.csv",
    "team_season_stats": "team_season_stats.csv",
    "standings": "standings.csv",
}


REQUIRED_COLUMNS = {
    "teams": {
        "league",
        "season",
        "team_id",
        "team_name",
    },
    "players": {
        "player_id",
        "player_name",
    },
    "rosters": {
        "league",
        "season",
        "team_id",
        "team_name",
        "player_id",
    },
    "games": {
        "league",
        "season",
        "game_id",
        "season_type",
        "week",
        "visitor_team_name",
        "home_team_name",
    },
    "player_game_stats": {
        "league",
        "season",
        "game_id",
        "team_id",
        "team_name",
        "source_player_id",
        "player_id",
        "player_name",
    },
    "player_season_stats": {
        "league",
        "season",
        "team_id",
        "player_id",
        "player_name",
        "team_name",
    },
    "team_season_stats": {
        "league",
        "season",
        "team_id",
        "team_name",
    },
    "standings": {
        "league",
        "season",
        "team_name",
        "wins",
        "losses",
        "ties",
        "win_pct",
    },
}


# Fields that should never be negative if present.
NONNEGATIVE_COLUMNS = {
    "games": {
        "visitor_score",
        "home_score",
    },

    # Yardage and "long" fields are intentionally excluded because football
    # plays can legitimately produce negative yardage.
    "player_game_stats": {
        "rushing_carries",
        "rushing_tds",
        "passing_attempts",
        "passing_completions",
        "passing_interceptions",
        "passing_tds",
        "receiving_catches",
        "receiving_tds",
        "scoring_tds",
        "scoring_pat1",
        "scoring_pat2",
        "scoring_fg",
        "scoring_safety",
        "tackles",
        "tackle_assists",
        "tackles_combined",
        "sacks",
        "tackles_for_loss",
        "interceptions",
        "interception_return_tds",
        "passes_deflected",
        "fumble_recoveries",
        "fumble_recovery_tds",
        "forced_fumbles",
        "kick_blocks",
        "kickoff_returns",
        "kickoff_return_tds",
        "punt_returns",
        "punt_return_tds",
        "fg_attempts",
        "fg_made",
        "pat_attempts",
        "pat_made",
        "punts",
        "punt_touchbacks",
    },

    "player_season_stats": {
        "passing_attempts",
        "passing_completions",
        "passing_tds",
        "passing_interceptions",
        "rushing_carries",
        "rushing_tds",
        "receiving_catches",
        "receiving_tds",
        "tackles",
        "tackle_assists",
        "tackles_combined",
        "sacks",
        "tackles_for_loss",
        "interceptions",
        "interception_return_tds",
        "passes_deflected",
        "fumble_recoveries",
        "fumble_recovery_tds",
        "forced_fumbles",
        "blocked_kicks",
        "kickoff_returns",
        "kickoff_return_tds",
        "punt_returns",
        "punt_return_tds",
        "fg_made",
        "fg_attempts",
        "pat_made",
        "pat_attempts",
        "punts",
        "punt_touchbacks",
        "total_points",
        "tds",
        "two_point_conversions",
        "safety",
    },

    # Team yardage and penalty yardage are intentionally excluded because
    # negative values can be meaningful under source conventions.
    "team_season_stats": {
        "total_points",
        "points_per_game",
        "first_downs",
        "first_downs_per_game",
        "total_points_allowed",
        "points_allowed_per_game",
        "penalties",
        "penalties_per_game",
    },

    "standings": {
        "wins",
        "losses",
        "ties",
        "points_for",
        "points_against",
        "win_pct",
    },
}


INVALID_RESPONSE_COLUMNS = [
    "league",
    "season",
    "endpoint",
    "resource_id",
    "reason",
    "recoverable",
    "recommended_action",
    "file",
    "size_bytes",
    "preview",
]


RECOVERY_REPORT_COLUMNS = [
    "source_file",
    "recovered_file",
    "league",
    "season",
    "endpoint",
    "resource_id",
    "category",
    "success",
    "recovery_rule",
    "parse_error",
    "source_size_bytes",
    "output_size_bytes",
]


# These raw-source categories are candidates for repair.py.
RECOVERY_CATEGORIES = {
    "VALID_JSON_MARKED_INVALID",
    "PYTHON_LITERAL",
    "MALFORMED_GAME_DATA",
    "MALFORMED_STANDINGS_DATA",
    "MALFORMED_JSON",
}


# ============================================================
# Validation Result Models
# ============================================================

@dataclass
class ValidationIssue:
    level: str
    table: str
    check: str
    message: str
    count: int | None = None


@dataclass
class ValidationReport:
    issues: list[ValidationIssue] = field(default_factory=list)

    def error(
        self,
        table: str,
        check: str,
        message: str,
        count: int | None = None,
    ):
        self.issues.append(
            ValidationIssue(
                level="ERROR",
                table=table,
                check=check,
                message=message,
                count=count,
            )
        )

    def warning(
        self,
        table: str,
        check: str,
        message: str,
        count: int | None = None,
    ):
        self.issues.append(
            ValidationIssue(
                level="WARNING",
                table=table,
                check=check,
                message=message,
                count=count,
            )
        )

    def info(
        self,
        table: str,
        check: str,
        message: str,
        count: int | None = None,
    ):
        self.issues.append(
            ValidationIssue(
                level="INFO",
                table=table,
                check=check,
                message=message,
                count=count,
            )
        )

    @property
    def error_count(self) -> int:
        return sum(
            issue.level == "ERROR"
            for issue in self.issues
        )

    @property
    def warning_count(self) -> int:
        return sum(
            issue.level == "WARNING"
            for issue in self.issues
        )


# ============================================================
# Loading
# ============================================================

def load_processed_tables(
    root: Path = PROCESSED_DATA_DIR,
) -> dict[str, pl.DataFrame]:
    """
    Load all expected processed CSV files.

    Missing files are omitted here and reported separately.
    """
    tables: dict[str, pl.DataFrame] = {}

    for table_name, filename in EXPECTED_FILES.items():
        path = root / filename

        if not path.exists():
            continue

        tables[table_name] = pl.read_csv(
            path,
            infer_schema_length=None,
            null_values=[
                "",
                "NULL",
                "null",
                "None",
            ],
            try_parse_dates=True,
        )

    return tables


def load_recovery_report(
    path: Path = RECOVERY_REPORT_PATH,
) -> pl.DataFrame:
    """
    Load repair.py's recovery report.

    An empty DataFrame is returned when repair.py has not produced a report.
    """
    schema = {
        "source_file": pl.String,
        "recovered_file": pl.String,
        "league": pl.String,
        "season": pl.String,
        "endpoint": pl.String,
        "resource_id": pl.String,
        "category": pl.String,
        "success": pl.Boolean,
        "recovery_rule": pl.String,
        "parse_error": pl.String,
        "source_size_bytes": pl.Int64,
        "output_size_bytes": pl.Int64,
    }

    if not path.exists():
        return pl.DataFrame(schema=schema)

    df = pl.read_csv(
        path,
        infer_schema_length=None,
        null_values=[
            "",
            "NULL",
            "null",
            "None",
        ],
    )

    # Keep the loader resilient to older/newer report versions.
    missing = [
        column
        for column in RECOVERY_REPORT_COLUMNS
        if column not in df.columns
    ]

    if missing:
        return pl.DataFrame(schema=schema)

    # CSV parsing normally infers success as Boolean. If not, normalize it.
    if df.schema.get("success") != pl.Boolean:
        df = df.with_columns(
            pl.col("success")
            .cast(pl.String)
            .str.to_lowercase()
            .is_in(["true", "1", "yes"])
            .alias("success")
        )

    return df.select(RECOVERY_REPORT_COLUMNS)


# ============================================================
# Generic Validation Helpers
# ============================================================

def validate_expected_files(
    tables: dict[str, pl.DataFrame],
    report: ValidationReport,
):
    for table_name in EXPECTED_FILES:
        if table_name not in tables:
            report.error(
                table=table_name,
                check="file_exists",
                message=(
                    "Missing processed file: "
                    f"{EXPECTED_FILES[table_name]}"
                ),
            )


def validate_required_columns(
    tables: dict[str, pl.DataFrame],
    report: ValidationReport,
):
    for table_name, required in REQUIRED_COLUMNS.items():
        if table_name not in tables:
            continue

        missing = sorted(
            required - set(tables[table_name].columns)
        )

        if missing:
            report.error(
                table=table_name,
                check="required_columns",
                message=(
                    "Missing required columns: "
                    + ", ".join(missing)
                ),
                count=len(missing),
            )


def count_duplicate_keys(
    df: pl.DataFrame,
    columns: list[str],
) -> int:
    """
    Count duplicate logical groups, not duplicate rows.
    """
    if any(
        column not in df.columns
        for column in columns
    ):
        return 0

    return (
        df
        .group_by(columns)
        .len()
        .filter(
            pl.col("len") > 1
        )
        .height
    )


def count_nulls(
    df: pl.DataFrame,
    column: str,
) -> int:
    if column not in df.columns:
        return 0

    return (
        df
        .filter(
            pl.col(column).is_null()
        )
        .height
    )


def validate_unique_key(
    df: pl.DataFrame,
    table: str,
    columns: list[str],
    report: ValidationReport,
    level: str = "ERROR",
):
    duplicate_groups = count_duplicate_keys(
        df,
        columns,
    )

    if duplicate_groups == 0:
        return

    message = (
        f"{duplicate_groups} duplicate logical key group(s) "
        f"for {columns}"
    )

    if level == "ERROR":
        report.error(
            table,
            "unique_key",
            message,
            duplicate_groups,
        )
    else:
        report.warning(
            table,
            "unique_key",
            message,
            duplicate_groups,
        )


def validate_nonnegative_columns(
    df: pl.DataFrame,
    table: str,
    columns: Iterable[str],
    report: ValidationReport,
):
    for column in sorted(columns):
        if column not in df.columns:
            continue

        dtype = df.schema[column]

        if not dtype.is_numeric():
            continue

        count = (
            df
            .filter(
                pl.col(column).is_not_null()
                & (pl.col(column) < 0)
            )
            .height
        )

        if count > 0:
            report.warning(
                table=table,
                check=f"nonnegative:{column}",
                message=(
                    f"{column} contains negative values."
                ),
                count=count,
            )


def validate_foreign_key(
    child: pl.DataFrame,
    parent: pl.DataFrame,
    child_columns: list[str],
    parent_columns: list[str],
    table: str,
    check: str,
    report: ValidationReport,
    allow_null: bool = False,
    level: str = "ERROR",
):
    """
    Validate a composite or single-column foreign-key relationship.
    """
    if any(
        column not in child.columns
        for column in child_columns
    ):
        return

    if any(
        column not in parent.columns
        for column in parent_columns
    ):
        return

    child_select = child.select(child_columns)

    if allow_null:
        null_condition = pl.any_horizontal(
            [
                pl.col(column).is_null()
                for column in child_columns
            ]
        )

        child_select = child_select.filter(
            ~null_condition
        )

    child_select = child_select.unique()

    parent_select = (
        parent
        .select(parent_columns)
        .unique()
        .rename(
            {
                parent_column: child_column
                for child_column, parent_column
                in zip(
                    child_columns,
                    parent_columns,
                )
            }
        )
    )

    missing = child_select.join(
        parent_select,
        on=child_columns,
        how="anti",
    )

    count = missing.height

    if count == 0:
        return

    message = (
        f"{count} foreign-key value(s) do not match parent table."
    )

    if level == "ERROR":
        report.error(
            table,
            check,
            message,
            count,
        )
    else:
        report.warning(
            table,
            check,
            message,
            count,
        )


# ============================================================
# Table-Specific Validation
# ============================================================

def validate_teams(
    df: pl.DataFrame,
    report: ValidationReport,
):
    validate_unique_key(
        df,
        "teams",
        [
            "league",
            "season",
            "team_id",
        ],
        report,
    )

    for column in [
        "league",
        "season",
        "team_id",
        "team_name",
    ]:
        null_count = count_nulls(
            df,
            column,
        )

        if null_count > 0:
            report.error(
                "teams",
                f"required_not_null:{column}",
                f"{column} contains null values.",
                null_count,
            )


def validate_players(
    df: pl.DataFrame,
    report: ValidationReport,
):
    validate_unique_key(
        df,
        "players",
        ["player_id"],
        report,
    )

    for column in [
        "player_id",
        "player_name",
    ]:
        null_count = count_nulls(
            df,
            column,
        )

        if null_count > 0:
            report.error(
                "players",
                f"required_not_null:{column}",
                f"{column} contains null values.",
                null_count,
            )


def validate_rosters(
    df: pl.DataFrame,
    report: ValidationReport,
):
    validate_unique_key(
        df,
        "rosters",
        [
            "league",
            "season",
            "team_id",
            "player_id",
        ],
        report,
    )

    for column in [
        "league",
        "season",
        "team_id",
        "player_id",
    ]:
        null_count = count_nulls(
            df,
            column,
        )

        if null_count > 0:
            report.error(
                "rosters",
                f"required_not_null:{column}",
                f"{column} contains null values.",
                null_count,
            )


def validate_games(
    df: pl.DataFrame,
    report: ValidationReport,
):
    validate_unique_key(
        df,
        "games",
        [
            "league",
            "season",
            "game_id",
        ],
        report,
    )

    for column in [
        "league",
        "season",
        "game_id",
        "home_team_name",
        "visitor_team_name",
    ]:
        null_count = count_nulls(
            df,
            column,
        )

        if null_count > 0:
            report.error(
                "games",
                f"required_not_null:{column}",
                f"{column} contains null values.",
                null_count,
            )

    if (
        "home_team_name" in df.columns
        and "visitor_team_name" in df.columns
    ):
        same_team = (
            df
            .filter(
                pl.col("home_team_name").is_not_null()
                & pl.col("visitor_team_name").is_not_null()
                & (
                    pl.col("home_team_name")
                    == pl.col("visitor_team_name")
                )
            )
            .height
        )

        if same_team > 0:
            report.error(
                "games",
                "home_visitor_different",
                (
                    "Games exist where home and visitor "
                    "team are identical."
                ),
                same_team,
            )

    missing_scores = 0

    if "home_score" in df.columns:
        missing_scores += count_nulls(
            df,
            "home_score",
        )

    if "visitor_score" in df.columns:
        missing_scores += count_nulls(
            df,
            "visitor_score",
        )

    if missing_scores > 0:
        report.info(
            "games",
            "missing_scores",
            (
                "Some schedule rows have missing scores. "
                "This may represent unplayed/unreported games."
            ),
            missing_scores,
        )

    validate_nonnegative_columns(
        df,
        "games",
        NONNEGATIVE_COLUMNS["games"],
        report,
    )


def validate_player_game_stats(
    df: pl.DataFrame,
    report: ValidationReport,
):
    # Canonical logical key where player_id is known.
    if "player_id" in df.columns:
        known = df.filter(
            pl.col("player_id").is_not_null()
        )

        validate_unique_key(
            known,
            "player_game_stats",
            [
                "league",
                "season",
                "game_id",
                "team_id",
                "player_id",
            ],
            report,
            level="WARNING",
        )

    # Source logical key only for unresolved rows.
    if (
        "source_player_id" in df.columns
        and "player_id" in df.columns
    ):
        unresolved = df.filter(
            pl.col("player_id").is_null()
            & pl.col("source_player_id").is_not_null()
        )

        validate_unique_key(
            unresolved,
            "player_game_stats",
            [
                "league",
                "season",
                "game_id",
                "team_id",
                "source_player_id",
            ],
            report,
            level="WARNING",
        )

    missing_canonical = count_nulls(
        df,
        "player_id",
    )

    if missing_canonical > 0:
        percentage = (
            missing_canonical
            / df.height
            * 100
            if df.height
            else 0
        )

        report.warning(
            "player_game_stats",
            "unresolved_player_id",
            (
                f"{missing_canonical} rows "
                f"({percentage:.2f}%) do not have a canonical player_id. "
                "source_player_id is preserved where available."
            ),
            missing_canonical,
        )

    validate_nonnegative_columns(
        df,
        "player_game_stats",
        NONNEGATIVE_COLUMNS[
            "player_game_stats"
        ],
        report,
    )


def validate_player_season_stats(
    df: pl.DataFrame,
    report: ValidationReport,
):
    missing_player = count_nulls(
        df,
        "player_id",
    )

    if missing_player > 0:
        percentage = (
            missing_player
            / df.height
            * 100
            if df.height
            else 0
        )

        report.warning(
            "player_season_stats",
            "unresolved_player_id",
            (
                f"{missing_player} rows "
                f"({percentage:.2f}%) do not have a canonical player_id."
            ),
            missing_player,
        )

    missing_team = count_nulls(
        df,
        "team_id",
    )

    if missing_team > 0:
        report.warning(
            "player_season_stats",
            "unresolved_team_id",
            (
                "Some player-season rows do not have "
                "a canonical team_id."
            ),
            missing_team,
        )

    if (
        "player_id" in df.columns
        and "team_id" in df.columns
    ):
        canonical = df.filter(
            pl.col("player_id").is_not_null()
            & pl.col("team_id").is_not_null()
        )

        validate_unique_key(
            canonical,
            "player_season_stats",
            [
                "league",
                "season",
                "team_id",
                "player_id",
            ],
            report,
            level="WARNING",
        )

    validate_nonnegative_columns(
        df,
        "player_season_stats",
        NONNEGATIVE_COLUMNS[
            "player_season_stats"
        ],
        report,
    )

    if "completion_pct" in df.columns:
        invalid = (
            df
            .filter(
                pl.col("completion_pct").is_not_null()
                & (
                    (pl.col("completion_pct") < 0)
                    | (pl.col("completion_pct") > 100)
                )
            )
            .height
        )

        if invalid > 0:
            report.warning(
                "player_season_stats",
                "completion_pct_range",
                (
                    "completion_pct contains values "
                    "outside [0, 100]."
                ),
                invalid,
            )


def validate_team_season_stats(
    df: pl.DataFrame,
    report: ValidationReport,
):
    if "team_id" in df.columns:
        canonical = df.filter(
            pl.col("team_id").is_not_null()
        )

        validate_unique_key(
            canonical,
            "team_season_stats",
            [
                "league",
                "season",
                "team_id",
            ],
            report,
            level="WARNING",
        )

    missing_team = count_nulls(
        df,
        "team_id",
    )

    if missing_team > 0:
        report.warning(
            "team_season_stats",
            "unresolved_team_id",
            (
                "Some team-season source records do not resolve "
                "to a canonical team_id."
            ),
            missing_team,
        )

    validate_nonnegative_columns(
        df,
        "team_season_stats",
        NONNEGATIVE_COLUMNS[
            "team_season_stats"
        ],
        report,
    )


def validate_standings(
    df: pl.DataFrame,
    report: ValidationReport,
):
    validate_nonnegative_columns(
        df,
        "standings",
        NONNEGATIVE_COLUMNS["standings"],
        report,
    )

    if "win_pct" in df.columns:
        invalid = (
            df
            .filter(
                pl.col("win_pct").is_not_null()
                & (
                    (pl.col("win_pct") < 0)
                    | (pl.col("win_pct") > 1)
                )
            )
            .height
        )

        if invalid > 0:
            report.error(
                "standings",
                "win_pct_range",
                "win_pct contains values outside [0, 1].",
                invalid,
            )

    # Standings are not guaranteed to exist for every league/season.
    if "league" in df.columns:
        leagues = set(
            df.get_column("league")
            .drop_nulls()
            .unique()
            .to_list()
        )

        if "wnfc" not in leagues:
            report.info(
                "standings",
                "league_coverage",
                (
                    "WNFC standings are absent from processed standings. "
                    "This is acceptable when raw standings responses "
                    "were invalid/unavailable."
                ),
            )


# ============================================================
# Referential Integrity
# ============================================================

def validate_referential_integrity(
    tables: dict[str, pl.DataFrame],
    report: ValidationReport,
):
    teams = tables.get("teams")
    players = tables.get("players")
    rosters = tables.get("rosters")
    games = tables.get("games")
    player_game_stats = tables.get(
        "player_game_stats"
    )
    player_season_stats = tables.get(
        "player_season_stats"
    )
    team_season_stats = tables.get(
        "team_season_stats"
    )

    if (
        rosters is not None
        and teams is not None
    ):
        validate_foreign_key(
            child=rosters,
            parent=teams,
            child_columns=[
                "league",
                "season",
                "team_id",
            ],
            parent_columns=[
                "league",
                "season",
                "team_id",
            ],
            table="rosters",
            check="team_fk",
            report=report,
        )

    if (
        rosters is not None
        and players is not None
    ):
        validate_foreign_key(
            child=rosters,
            parent=players,
            child_columns=[
                "player_id",
            ],
            parent_columns=[
                "player_id",
            ],
            table="rosters",
            check="player_fk",
            report=report,
        )

    if (
        player_game_stats is not None
        and teams is not None
    ):
        validate_foreign_key(
            child=player_game_stats,
            parent=teams,
            child_columns=[
                "league",
                "season",
                "team_id",
            ],
            parent_columns=[
                "league",
                "season",
                "team_id",
            ],
            table="player_game_stats",
            check="team_fk",
            report=report,
        )

    if (
        player_game_stats is not None
        and games is not None
    ):
        validate_foreign_key(
            child=player_game_stats,
            parent=games,
            child_columns=[
                "league",
                "season",
                "game_id",
            ],
            parent_columns=[
                "league",
                "season",
                "game_id",
            ],
            table="player_game_stats",
            check="game_fk",
            report=report,
        )

    if (
        player_game_stats is not None
        and players is not None
    ):
        validate_foreign_key(
            child=player_game_stats,
            parent=players,
            child_columns=[
                "player_id",
            ],
            parent_columns=[
                "player_id",
            ],
            table="player_game_stats",
            check="player_fk",
            report=report,
            allow_null=True,
        )

    if (
        player_season_stats is not None
        and teams is not None
    ):
        validate_foreign_key(
            child=player_season_stats,
            parent=teams,
            child_columns=[
                "league",
                "season",
                "team_id",
            ],
            parent_columns=[
                "league",
                "season",
                "team_id",
            ],
            table="player_season_stats",
            check="team_fk",
            report=report,
            allow_null=True,
        )

    if (
        player_season_stats is not None
        and players is not None
    ):
        validate_foreign_key(
            child=player_season_stats,
            parent=players,
            child_columns=[
                "player_id",
            ],
            parent_columns=[
                "player_id",
            ],
            table="player_season_stats",
            check="player_fk",
            report=report,
            allow_null=True,
        )

    if (
        team_season_stats is not None
        and teams is not None
    ):
        validate_foreign_key(
            child=team_season_stats,
            parent=teams,
            child_columns=[
                "league",
                "season",
                "team_id",
            ],
            parent_columns=[
                "league",
                "season",
                "team_id",
            ],
            table="team_season_stats",
            check="team_fk",
            report=report,
            allow_null=True,
        )


# ============================================================
# Raw Invalid-Response Validation
# ============================================================

def infer_invalid_file_metadata(
    path: Path,
    raw_root: Path,
) -> dict[str, str | None]:
    """
    Infer league, season, endpoint, and resource ID from an invalid path.
    """
    try:
        relative = path.relative_to(raw_root)
    except ValueError:
        relative = path

    parts = list(relative.parts)

    league = (
        parts[0].lower()
        if len(parts) >= 1
        else None
    )

    season = (
        parts[1]
        if len(parts) >= 2
        else None
    )

    known_endpoints = {
        "teams",
        "team_stats",
        "offensive_stats",
        "defensive_stats",
        "scoring_stats",
        "special_teams_stats",
        "schedule",
        "standings",
        "rosters",
        "games",
        "players",
        "player_stats",
        "stats",
    }

    endpoint = None
    resource_id = None

    stem = path.name.removesuffix(
        ".invalid.txt"
    )

    if len(parts) >= 4:
        candidate = parts[-2].lower()

        if candidate in known_endpoints:
            endpoint = candidate
            resource_id = stem

    if endpoint is None:
        endpoint = stem.lower()

    return {
        "league": league,
        "season": season,
        "endpoint": endpoint,
        "resource_id": resource_id,
    }


def classify_invalid_response(
    text: str,
    endpoint: str | None = None,
) -> str:
    """
    Classify an invalid raw response without changing it.
    """
    stripped = text.strip()

    if not stripped:
        return "EMPTY"

    lowered = stripped.lower()

    no_data_patterns = [
        "no data",
        "no records",
        "not found",
        "no roster",
        "no standings",
        "no stats",
        "no games",
        "nothing found",
        "does not exist",
        "doesn't exist",
        "not available",
        "unavailable",
        "have not yet published",
        "has not yet published",
        "have not published",
        "has not published",
        "not yet published",
        "no data avaiable yet",
        "no data available yet",
    ]

    if any(
        pattern in lowered
        for pattern in no_data_patterns
    ):
        return "NO_DATA"

    compact = re.sub(
        r"\s+",
        "",
        stripped,
    )

    # HostedSports historical empty player-stat defect:
    #     {"player_stat_totals": [ { ] }
    #
    # There is no useful player-stat record inside it, so this is not a
    # recoverable malformed JSON response.
    if (
        endpoint == "stats"
        and '"player_stat_totals"' in compact
        and compact.endswith("[{]}")
    ):
        return "EMPTY_PLAYER_STATS"

    html_patterns = [
        "<!doctype html",
        "<html",
        "<body",
        "<head",
        "</html>",
    ]

    if any(
        pattern in lowered
        for pattern in html_patterns
    ):
        return "HTML_RESPONSE"

    api_error_patterns = [
        "internal server error",
        "bad gateway",
        "service unavailable",
        "gateway timeout",
        "unauthorized",
        "forbidden",
        "too many requests",
        "rate limit",
        "error code",
        '"error"',
        "'error'",
        "exception",
        "traceback",
        "php warning",
        "php fatal",
    ]

    if any(
        pattern in lowered
        for pattern in api_error_patterns
    ):
        return "API_ERROR"

    try:
        json.loads(stripped)
    except json.JSONDecodeError:
        pass
    else:
        return "VALID_JSON_MARKED_INVALID"

    if stripped.startswith(
        ("{", "[", "(", "'", '"')
    ):
        try:
            parsed = ast.literal_eval(
                stripped
            )
        except (
            ValueError,
            SyntaxError,
            MemoryError,
            RecursionError,
        ):
            pass
        else:
            if isinstance(
                parsed,
                (
                    dict,
                    list,
                    tuple,
                    str,
                    int,
                    float,
                    bool,
                    type(None),
                ),
            ):
                return "PYTHON_LITERAL"

    if (
        stripped.startswith("{")
        or stripped.startswith("[")
        or (
            ":" in stripped
            and (
                '"' in stripped
                or "'" in stripped
            )
        )
    ):
        if endpoint == "games":
            return "MALFORMED_GAME_DATA"

        if endpoint == "standings":
            return "MALFORMED_STANDINGS_DATA"

        return "MALFORMED_JSON"

    printable_chars = sum(
        character.isprintable()
        or character in "\r\n\t"
        for character in stripped
    )

    printable_ratio = (
        printable_chars / len(stripped)
        if stripped
        else 0
    )

    if printable_ratio >= 0.95:
        return "TEXT_RESPONSE"

    return "UNKNOWN"


def invalid_response_recoverability(
    reason: str,
) -> tuple[bool, str]:
    """
    Return whether a raw invalid response is a repair candidate and the
    appropriate next action.

    Validation never performs repair.
    """
    mapping = {
        "EMPTY": (
            False,
            "No repair. Treat as missing source data.",
        ),
        "NO_DATA": (
            False,
            (
                "No repair. Source indicates data was "
                "not published/available."
            ),
        ),
        "EMPTY_PLAYER_STATS": (
            False,
            (
                "No repair. HostedSports returned its malformed "
                "empty player-stat payload."
            ),
        ),
        "HTML_RESPONSE": (
            False,
            (
                "Review endpoint response. Re-extract if HTML "
                "was unexpected."
            ),
        ),
        "API_ERROR": (
            False,
            "Retry extraction or investigate API/server failure.",
        ),
        "VALID_JSON_MARKED_INVALID": (
            True,
            (
                "Review extraction logic. Response is valid JSON "
                "and can be recovered without source changes."
            ),
        ),
        "PYTHON_LITERAL": (
            True,
            "Candidate for controlled recovery through repair.py.",
        ),
        "MALFORMED_GAME_DATA": (
            True,
            "Candidate for controlled recovery through repair.py.",
        ),
        "MALFORMED_STANDINGS_DATA": (
            True,
            "Candidate for controlled recovery through repair.py.",
        ),
        "MALFORMED_JSON": (
            True,
            (
                "Candidate for controlled recovery after "
                "inspecting the parse defect."
            ),
        ),
        "TEXT_RESPONSE": (
            False,
            (
                "Review manually. Plain text does not currently "
                "appear machine-recoverable."
            ),
        ),
        "UNKNOWN": (
            False,
            (
                "Manual review required before deciding whether "
                "recovery is possible."
            ),
        ),
    }

    return mapping.get(
        reason,
        (
            False,
            "Manual review required.",
        ),
    )


def sanitize_preview(
    text: str,
    max_length: int = 240,
) -> str:
    preview = re.sub(
        r"\s+",
        " ",
        text.strip(),
    )

    if len(preview) > max_length:
        preview = (
            preview[: max_length - 3]
            + "..."
        )

    return preview


def scan_invalid_responses(
    raw_root: Path = RAW_DATA_DIR,
) -> pl.DataFrame:
    """
    Scan data/raw recursively for *.invalid.txt and classify each file.
    """
    empty_schema = {
        "league": pl.String,
        "season": pl.String,
        "endpoint": pl.String,
        "resource_id": pl.String,
        "reason": pl.String,
        "recoverable": pl.Boolean,
        "recommended_action": pl.String,
        "file": pl.String,
        "size_bytes": pl.Int64,
        "preview": pl.String,
    }

    if not raw_root.exists():
        return pl.DataFrame(
            schema=empty_schema
        )

    records = []

    for path in sorted(
        raw_root.rglob("*.invalid.txt")
    ):
        try:
            text = path.read_text(
                encoding="utf-8",
                errors="replace",
            )
        except OSError as exc:
            text = (
                f"Unable to read file: {exc}"
            )

        metadata = infer_invalid_file_metadata(
            path,
            raw_root,
        )

        reason = classify_invalid_response(
            text,
            endpoint=metadata.get("endpoint"),
        )

        recoverable, recommended_action = (
            invalid_response_recoverability(
                reason
            )
        )

        records.append(
            {
                **metadata,
                "reason": reason,
                "recoverable": recoverable,
                "recommended_action": recommended_action,
                "file": str(path),
                "size_bytes": (
                    path.stat().st_size
                    if path.exists()
                    else 0
                ),
                "preview": sanitize_preview(
                    text
                ),
            }
        )

    if not records:
        return pl.DataFrame(
            schema=empty_schema
        )

    return (
        pl.DataFrame(
            records,
            infer_schema_length=None,
        )
        .select(
            INVALID_RESPONSE_COLUMNS
        )
    )


def write_invalid_response_report(
    invalid_df: pl.DataFrame,
    validation_dir: Path,
) -> Path:
    """
    Write the immutable raw-source invalid-response audit.
    """
    validation_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path = (
        validation_dir
        / "invalid_responses.csv"
    )

    invalid_df.write_csv(
        output_path
    )

    return output_path


# ============================================================
# Recovery-Aware Validation
# ============================================================

def recovery_candidate_rows(
    recovery_df: pl.DataFrame,
) -> pl.DataFrame:
    """
    Return only rows representing categories that repair.py was expected
    to attempt.
    """
    if recovery_df.is_empty():
        return recovery_df

    return recovery_df.filter(
        pl.col("category").is_in(
            sorted(RECOVERY_CATEGORIES)
        )
    )


def recovery_counts_by_category(
    invalid_df: pl.DataFrame,
    recovery_df: pl.DataFrame,
) -> list[dict]:
    """
    Build per-category candidate/recovered/outstanding counts.

    The raw invalid audit is the authority for how many candidates existed.
    recovery_report.csv is the authority for which attempts succeeded.
    """
    rows = []

    raw_counts = {}

    if not invalid_df.is_empty():
        raw_recoverable = (
            invalid_df
            .filter(
                pl.col("recoverable") == True
            )
            .group_by("reason")
            .len()
        )

        raw_counts = {
            row["reason"]: row["len"]
            for row in raw_recoverable.iter_rows(
                named=True
            )
        }

    candidate_df = recovery_candidate_rows(
        recovery_df
    )

    recovered_counts = {}
    attempted_counts = {}

    if not candidate_df.is_empty():
        attempted_summary = (
            candidate_df
            .group_by("category")
            .len()
        )

        attempted_counts = {
            row["category"]: row["len"]
            for row in attempted_summary.iter_rows(
                named=True
            )
        }

        recovered_summary = (
            candidate_df
            .filter(
                pl.col("success") == True
            )
            .group_by("category")
            .len()
        )

        recovered_counts = {
            row["category"]: row["len"]
            for row in recovered_summary.iter_rows(
                named=True
            )
        }

    categories = sorted(
        set(raw_counts)
        | set(attempted_counts)
        | set(recovered_counts)
    )

    for category in categories:
        candidates = raw_counts.get(
            category,
            0,
        )

        attempted = attempted_counts.get(
            category,
            0,
        )

        recovered = recovered_counts.get(
            category,
            0,
        )

        failed = max(
            attempted - recovered,
            0,
        )

        unattempted = max(
            candidates - attempted,
            0,
        )

        outstanding = (
            failed
            + unattempted
        )

        rows.append(
            {
                "category": category,
                "candidates": candidates,
                "attempted": attempted,
                "recovered": recovered,
                "failed": failed,
                "unattempted": unattempted,
                "outstanding": outstanding,
            }
        )

    return rows


def validate_invalid_responses(
    invalid_df: pl.DataFrame,
    recovery_df: pl.DataFrame,
    report: ValidationReport,
):
    """
    Add raw-source and recovery findings to the main validation report.

    Once a recovery report exists, successfully repaired source defects are
    INFO rather than WARNING. Only outstanding repair candidates remain
    warnings.
    """
    if invalid_df.is_empty():
        report.info(
            "raw_source",
            "invalid_responses",
            "No *.invalid.txt files were found.",
            0,
        )
        return

    report.info(
        "raw_source",
        "invalid_responses",
        (
            "Raw extraction contains invalid/unavailable responses. "
            "They remain preserved for auditability. "
            "See invalid_responses.csv."
        ),
        invalid_df.height,
    )

    reason_counts = (
        invalid_df
        .group_by("reason")
        .len()
        .sort(
            "len",
            descending=True,
        )
    )

    # Non-recoverable categories always describe source availability rather
    # than a broken processed pipeline.
    for row in reason_counts.iter_rows(
        named=True
    ):
        reason = row["reason"]
        count = row["len"]

        if reason in RECOVERY_CATEGORIES:
            continue

        if reason in {
            "NO_DATA",
            "EMPTY",
            "EMPTY_PLAYER_STATS",
            "TEXT_RESPONSE",
        }:
            report.info(
                "raw_source",
                f"invalid:{reason.lower()}",
                (
                    f"{count} raw invalid response(s) "
                    f"classified as {reason}."
                ),
                count,
            )
        else:
            report.warning(
                "raw_source",
                f"invalid:{reason.lower()}",
                (
                    f"{count} raw invalid response(s) "
                    f"classified as {reason}."
                ),
                count,
            )

    raw_recoverable_count = (
        invalid_df
        .filter(
            pl.col("recoverable") == True
        )
        .height
    )

    if recovery_df.is_empty():
        if raw_recoverable_count > 0:
            report.warning(
                "recovery",
                "repair_not_run",
                (
                    f"{raw_recoverable_count} recoverable raw response(s) "
                    "exist, but recovery_report.csv was not found. "
                    "Run repair.py before treating these candidates as resolved."
                ),
                raw_recoverable_count,
            )
        return

    category_rows = recovery_counts_by_category(
        invalid_df,
        recovery_df,
    )

    total_recovered = sum(
        row["recovered"]
        for row in category_rows
    )

    total_outstanding = sum(
        row["outstanding"]
        for row in category_rows
    )

    if total_recovered > 0:
        report.info(
            "recovery",
            "successful_recoveries",
            (
                f"{total_recovered} recoverable raw response(s) "
                "were repaired successfully and are available in "
                "data/recovered."
            ),
            total_recovered,
        )

    for row in category_rows:
        category = row["category"]
        recovered = row["recovered"]
        outstanding = row["outstanding"]

        if recovered > 0:
            report.info(
                "recovery",
                f"recovered:{category.lower()}",
                (
                    f"{recovered} {category} response(s) "
                    "were repaired successfully."
                ),
                recovered,
            )

        if outstanding > 0:
            report.warning(
                "recovery",
                f"unrecovered:{category.lower()}",
                (
                    f"{outstanding} {category} response(s) "
                    "remain unrecovered after the repair stage."
                ),
                outstanding,
            )

    if total_outstanding > 0:
        report.warning(
            "recovery",
            "unrecovered_repair_candidates",
            (
                f"{total_outstanding} recoverable raw response(s) "
                "remain unresolved after repair.py."
            ),
            total_outstanding,
        )
    else:
        report.info(
            "recovery",
            "repair_candidates_resolved",
            (
                "All recoverable raw-response candidates represented "
                "in the current source audit were repaired successfully."
            ),
            0,
        )


# ============================================================
# Human-Readable Summaries
# ============================================================

def print_table_summary(
    tables: dict[str, pl.DataFrame],
):
    print("\nProcessed table summary:")

    for table_name in EXPECTED_FILES:
        df = tables.get(
            table_name
        )

        if df is None:
            print(
                f"  ✗ {table_name}: missing"
            )
            continue

        print(
            f"  ✓ {table_name}: "
            f"{df.height:,} rows, "
            f"{df.width} columns"
        )


def print_invalid_response_summary(
    invalid_df: pl.DataFrame,
):
    """
    Print a compact raw invalid-response summary.

    Unlike normalize.py, validation intentionally owns the detailed source
    audit. Representative examples are shown by reason.
    """
    print("\nRaw invalid-response summary:")

    if invalid_df.is_empty():
        print(
            "  ✓ No *.invalid.txt files found."
        )
        return

    print(
        f"  ! Total invalid raw responses: "
        f"{invalid_df.height:,}"
    )

    recoverable_count = (
        invalid_df
        .filter(
            pl.col("recoverable") == True
        )
        .height
    )

    nonrecoverable_count = (
        invalid_df.height
        - recoverable_count
    )

    print(
        f"  ! Repair candidates in raw source: "
        f"{recoverable_count:,}"
    )

    print(
        f"  i Not recoverable / unavailable: "
        f"{nonrecoverable_count:,}"
    )

    reason_summary = (
        invalid_df
        .group_by("reason")
        .len()
        .sort(
            "len",
            descending=True,
        )
    )

    print("\n  By reason:")

    for row in reason_summary.iter_rows(
        named=True
    ):
        print(
            f"    {row['reason']:<28} "
            f"{row['len']:>6,}"
        )

    detail_summary = (
        invalid_df
        .group_by(
            [
                "league",
                "season",
                "endpoint",
                "reason",
            ]
        )
        .len()
        .sort(
            [
                "league",
                "season",
                "endpoint",
                "reason",
            ]
        )
    )

    print(
        "\n  By league / season / endpoint / reason:"
    )

    for row in detail_summary.iter_rows(
        named=True
    ):
        league = row["league"] or "unknown"
        season = row["season"] or "unknown"
        endpoint = row["endpoint"] or "unknown"
        reason = row["reason"] or "unknown"

        print(
            f"    {league:<6} "
            f"{season:<8} "
            f"{endpoint:<24} "
            f"{reason:<28} "
            f"{row['len']:>6,}"
        )

    print("\n  Representative examples:")

    reasons = (
        invalid_df
        .get_column("reason")
        .drop_nulls()
        .unique()
        .sort()
        .to_list()
    )

    for reason in reasons:
        samples = (
            invalid_df
            .filter(
                pl.col("reason") == reason
            )
            .select(
                [
                    "league",
                    "season",
                    "endpoint",
                    "file",
                    "preview",
                ]
            )
            .head(3)
        )

        print(
            f"\n    {reason}:"
        )

        for sample in samples.iter_rows(
            named=True
        ):
            print(
                "      "
                f"{sample['league'] or 'unknown'} | "
                f"{sample['season'] or 'unknown'} | "
                f"{sample['endpoint'] or 'unknown'}"
            )

            print(
                f"        file: {sample['file']}"
            )

            print(
                f"        preview: {sample['preview']}"
            )


def print_recovery_summary(
    invalid_df: pl.DataFrame,
    recovery_df: pl.DataFrame,
):
    """
    Print current repair status separately from the immutable raw audit.
    """
    print("\nRecovery summary:")

    raw_candidates = (
        invalid_df
        .filter(
            pl.col("recoverable") == True
        )
        .height
        if not invalid_df.is_empty()
        else 0
    )

    print(
        f"  Raw repair candidates: "
        f"{raw_candidates:,}"
    )

    if recovery_df.is_empty():
        print(
            "  ! recovery_report.csv not found."
        )

        if raw_candidates > 0:
            print(
                f"  ! Outstanding repair candidates: "
                f"{raw_candidates:,}"
            )

        return

    category_rows = recovery_counts_by_category(
        invalid_df,
        recovery_df,
    )

    total_attempted = sum(
        row["attempted"]
        for row in category_rows
    )

    total_recovered = sum(
        row["recovered"]
        for row in category_rows
    )

    total_outstanding = sum(
        row["outstanding"]
        for row in category_rows
    )

    print(
        f"  Repair candidates attempted: "
        f"{total_attempted:,}"
    )

    print(
        f"  ✓ Successfully recovered: "
        f"{total_recovered:,}"
    )

    print(
        f"  ! Still unrecovered: "
        f"{total_outstanding:,}"
    )

    if category_rows:
        print(
            "\n  By recovery category:"
        )

    for row in category_rows:
        print(
            f"    {row['category']:<28} "
            f"candidates={row['candidates']:>4,}  "
            f"recovered={row['recovered']:>4,}  "
            f"remaining={row['outstanding']:>4,}"
        )

    candidate_df = recovery_candidate_rows(
        recovery_df
    )

    failed = (
        candidate_df
        .filter(
            pl.col("success") == False
        )
        if not candidate_df.is_empty()
        else candidate_df
    )

    if not failed.is_empty():
        print(
            "\n  Unrecovered repair candidates:"
        )

        for row in failed.select(
            [
                "league",
                "season",
                "endpoint",
                "category",
                "source_file",
                "parse_error",
            ]
        ).iter_rows(
            named=True
        ):
            print(
                "    "
                f"{row['league'] or 'unknown'} | "
                f"{row['season'] or 'unknown'} | "
                f"{row['endpoint'] or 'unknown'} | "
                f"{row['category'] or 'unknown'}"
            )

            print(
                f"      file: {row['source_file']}"
            )

            if row["parse_error"]:
                print(
                    f"      reason: {row['parse_error']}"
                )


def print_validation_report(
    report: ValidationReport,
):
    print("\n" + "=" * 70)
    print("VALIDATION REPORT")
    print("=" * 70)

    if not report.issues:
        print(
            "✓ No validation issues found."
        )
        return

    level_order = {
        "ERROR": 0,
        "WARNING": 1,
        "INFO": 2,
    }

    issues = sorted(
        report.issues,
        key=lambda issue: (
            level_order.get(
                issue.level,
                99,
            ),
            issue.table,
            issue.check,
        ),
    )

    for issue in issues:
        marker = {
            "ERROR": "✗",
            "WARNING": "!",
            "INFO": "i",
        }.get(
            issue.level,
            "-",
        )

        count_suffix = (
            f" [{issue.count}]"
            if issue.count is not None
            else ""
        )

        print(
            f"{marker} "
            f"{issue.level:<7} "
            f"{issue.table:<22} "
            f"{issue.check:<38} "
            f"{issue.message}"
            f"{count_suffix}"
        )

    print("\n" + "-" * 70)

    print(
        f"Errors:   {report.error_count}"
    )

    print(
        f"Warnings: {report.warning_count}"
    )

    if report.error_count == 0:
        print(
            "\n✓ Validation completed without structural errors."
        )
    else:
        print(
            "\n✗ Validation found structural errors that should be "
            "reviewed before downstream analysis."
        )


# ============================================================
# Main Validation Pipeline
# ============================================================

def validate_all(
    root: Path = PROCESSED_DATA_DIR,
    raw_root: Path = RAW_DATA_DIR,
) -> ValidationReport:
    """
    Run processed-data, raw-source, and recovery-aware validation.
    """
    print("\n" + "=" * 70)
    print("VALIDATING HOSTEDSPORTS DATA")
    print("=" * 70)

    tables = load_processed_tables(
        root
    )

    print_table_summary(
        tables
    )

    report = ValidationReport()

    validate_expected_files(
        tables,
        report,
    )

    validate_required_columns(
        tables,
        report,
    )

    if "teams" in tables:
        validate_teams(
            tables["teams"],
            report,
        )

    if "players" in tables:
        validate_players(
            tables["players"],
            report,
        )

    if "rosters" in tables:
        validate_rosters(
            tables["rosters"],
            report,
        )

    if "games" in tables:
        validate_games(
            tables["games"],
            report,
        )

    if "player_game_stats" in tables:
        validate_player_game_stats(
            tables[
                "player_game_stats"
            ],
            report,
        )

    if "player_season_stats" in tables:
        validate_player_season_stats(
            tables[
                "player_season_stats"
            ],
            report,
        )

    if "team_season_stats" in tables:
        validate_team_season_stats(
            tables[
                "team_season_stats"
            ],
            report,
        )

    if "standings" in tables:
        validate_standings(
            tables["standings"],
            report,
        )

    validate_referential_integrity(
        tables,
        report,
    )

    invalid_df = scan_invalid_responses(
        raw_root
    )

    recovery_df = load_recovery_report(
        RECOVERY_REPORT_PATH
    )

    print_invalid_response_summary(
        invalid_df
    )

    print_recovery_summary(
        invalid_df,
        recovery_df,
    )

    validate_invalid_responses(
        invalid_df,
        recovery_df,
        report,
    )

    invalid_report_path = (
        write_invalid_response_report(
            invalid_df,
            VALIDATION_DATA_DIR,
        )
    )

    print(
        "\nInvalid response audit written to:"
    )

    print(
        f"  {invalid_report_path}"
    )

    if RECOVERY_REPORT_PATH.exists():
        print(
            "\nRecovery audit read from:"
        )

        print(
            f"  {RECOVERY_REPORT_PATH}"
        )

    print_validation_report(
        report
    )

    return report


def main():
    report = validate_all()

    # Exit non-zero only for structural validation errors.
    #
    # Source-quality warnings, unresolved historical IDs, and outstanding
    # repair candidates remain visible without making the validation process
    # fail as a program.
    if report.error_count > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
