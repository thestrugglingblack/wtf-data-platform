from __future__ import annotations

"""
Generate data dictionaries for WTF data-product releases.

Two versions are produced:

1. data_dictionary.json
   Machine-readable documentation.

2. DATA_DICTIONARY.md
   Human-readable documentation.

The dictionary is generated from the actual processed DataFrames.
"""

import json
from pathlib import Path
from typing import Any

import polars as pl

from contracts import (
    CONTRACT_VERSION,
    DATASET_CONTRACTS,
)


# ============================================================
# Known Column Descriptions
# ============================================================

COLUMN_DESCRIPTIONS: dict[str, str] = {
    # --------------------------------------------------------
    # Common identifiers
    # --------------------------------------------------------
    "league": (
        "League identifier. Currently wfa or wnfc."
    ),

    "season": (
        "Season year."
    ),

    # --------------------------------------------------------
    # Team fields
    # --------------------------------------------------------
    "team_id": (
        "Canonical HostedSports team identifier."
    ),

    "team_number": (
        "Source team number when published by HostedSports."
    ),

    "team_city": (
        "Team city or geographic label."
    ),

    "team_name": (
        "Team name as normalized from the source."
    ),

    "tier": (
        "WFA competitive tier when available."
    ),

    "conference": (
        "Conference assignment when available."
    ),

    "division": (
        "Division assignment when available."
    ),

    "region": (
        "Region assignment when available."
    ),

    # --------------------------------------------------------
    # Player fields
    # --------------------------------------------------------
    "player_id": (
        "Canonical player identifier resolved from roster data."
    ),

    "source_player_id": (
        "Player identifier supplied by the HostedSports game-stat "
        "response. This identifier uses a source namespace that may "
        "differ from the canonical roster player_id."
    ),

    "player_name": (
        "Player name as normalized from the source."
    ),

    "roster_number": (
        "Player uniform or roster number."
    ),

    "position": (
        "Player roster position when available."
    ),

    "height": (
        "Player height as reported by the source."
    ),

    "weight": (
        "Player weight as reported by the source."
    ),

    "school": (
        "Player school as reported by the source."
    ),

    "hometown": (
        "Player hometown as reported by the source."
    ),

    # --------------------------------------------------------
    # Game fields
    # --------------------------------------------------------
    "game_id": (
        "Canonical HostedSports game identifier."
    ),

    "season_type": (
        "Season classification such as regular or postseason "
        "when determinable."
    ),

    "week": (
        "Week number within the regular season or postseason sequence."
    ),

    "date": (
        "Game date."
    ),

    "visitor_team_name": (
        "Visiting team name."
    ),

    "visitor_score": (
        "Visiting team final or reported score."
    ),

    "home_team_name": (
        "Home team name."
    ),

    "home_score": (
        "Home team final or reported score."
    ),

    "opponent_id": (
        "Opponent team identifier in a player-game row."
    ),

    "opponent_name": (
        "Opponent team name in a player-game row."
    ),

    "home_away": (
        "Indicates whether the player's team was the home "
        "or visiting team."
    ),

    # --------------------------------------------------------
    # Standings
    # --------------------------------------------------------
    "wins": (
        "Number of wins."
    ),

    "losses": (
        "Number of losses."
    ),

    "ties": (
        "Number of ties."
    ),

    "win_pct": (
        "Winning percentage represented as a decimal from 0 to 1."
    ),

    "points_for": (
        "Points scored by the team."
    ),

    "points_against": (
        "Points allowed by the team."
    ),

    "home_record": (
        "Source-formatted home record."
    ),

    "away_record": (
        "Source-formatted away record."
    ),

    "conference_record": (
        "Source-formatted conference record."
    ),

    "division_record": (
        "Source-formatted division record."
    ),

    "nonconference_record": (
        "Source-formatted non-conference record."
    ),

    "nondivision_record": (
        "Source-formatted non-division record."
    ),

    "streak": (
        "Current or source-formatted winning or losing streak."
    ),

    "team_logo": (
        "Source URL for the team logo when available."
    ),

    # --------------------------------------------------------
    # Common passing statistics
    # --------------------------------------------------------
    "passing_attempts": (
        "Number of passing attempts."
    ),

    "passing_completions": (
        "Number of completed passes."
    ),

    "passing_yards": (
        "Passing yards."
    ),

    "passing_tds": (
        "Passing touchdowns."
    ),

    "passing_interceptions": (
        "Passes intercepted by the opposing defense."
    ),

    # --------------------------------------------------------
    # Common rushing statistics
    # --------------------------------------------------------
    "rushing_carries": (
        "Number of rushing attempts."
    ),

    "rushing_yards": (
        "Rushing yards."
    ),

    "rushing_tds": (
        "Rushing touchdowns."
    ),

    # --------------------------------------------------------
    # Common receiving statistics
    # --------------------------------------------------------
    "receiving_catches": (
        "Number of receptions."
    ),

    "receiving_yards": (
        "Receiving yards."
    ),

    "receiving_tds": (
        "Receiving touchdowns."
    ),

    # --------------------------------------------------------
    # Common defensive statistics
    # --------------------------------------------------------
    "tackles": (
        "Solo tackles or source-reported tackle count."
    ),

    "tackle_assists": (
        "Assisted tackles."
    ),

    "tackles_combined": (
        "Combined solo and assisted tackle total."
    ),

    "sacks": (
        "Quarterback sacks."
    ),

    "tackles_for_loss": (
        "Tackles resulting in offensive yardage loss."
    ),

    "interceptions": (
        "Defensive interceptions."
    ),

    "passes_deflected": (
        "Passes defended or deflected."
    ),

    "forced_fumbles": (
        "Fumbles forced by the defender."
    ),

    "fumble_recoveries": (
        "Fumbles recovered."
    ),

    # --------------------------------------------------------
    # Scoring
    # --------------------------------------------------------
    "total_points": (
        "Total individual or team points represented by the row."
    ),

    "tds": (
        "Total touchdowns."
    ),

    "two_point_conversions": (
        "Successful two-point conversions."
    ),

    "safety": (
        "Safeties recorded."
    ),

    # --------------------------------------------------------
    # Kicking / special teams
    # --------------------------------------------------------
    "fg_attempts": (
        "Field-goal attempts."
    ),

    "fg_made": (
        "Successful field goals."
    ),

    "pat_attempts": (
        "Point-after-touchdown attempts."
    ),

    "pat_made": (
        "Successful point-after-touchdown attempts."
    ),

    "punts": (
        "Number of punts."
    ),

    "kickoff_returns": (
        "Number of kickoff returns."
    ),

    "punt_returns": (
        "Number of punt returns."
    ),
}


# ============================================================
# Description Helpers
# ============================================================

def humanize_column_name(
    column: str,
) -> str:
    """
    Generate a fallback description for an undocumented stat column.

    Example
    -------
    receiving_long -> "Receiving long."
    """

    return (
        column
        .replace("_", " ")
        .capitalize()
        + "."
    )


def column_description(
    column: str,
) -> str:
    """
    Return the documented description for a column.

    Unknown statistical columns receive a humanized fallback description.
    """

    return COLUMN_DESCRIPTIONS.get(
        column,
        humanize_column_name(
            column
        ),
    )


# ============================================================
# Dictionary Builder
# ============================================================

def build_dictionary(
    tables: dict[str, pl.DataFrame],
) -> dict[str, Any]:
    """
    Build a machine-readable dictionary from actual release tables.
    """

    datasets: dict[str, Any] = {}

    for (
        dataset_name,
        contract,
    ) in DATASET_CONTRACTS.items():

        df = tables.get(
            dataset_name
        )

        if df is None:
            continue

        datasets[
            dataset_name
        ] = {
            "description": (
                contract.description
            ),
            "grain": (
                contract.grain
            ),
            "primary_key": list(
                contract.primary_key
            ),
            "partition_columns": list(
                contract.partition_columns
            ),
            "row_count": (
                df.height
            ),
            "column_count": (
                df.width
            ),
            "columns": [
                {
                    "name": column,
                    "dtype": str(
                        df.schema[
                            column
                        ]
                    ),
                    "required": (
                        column
                        in contract.required_columns
                    ),
                    "description": (
                        column_description(
                            column
                        )
                    ),
                }
                for column in df.columns
            ],
        }

    return {
        "contract_version": (
            CONTRACT_VERSION
        ),
        "datasets": datasets,
    }


# ============================================================
# JSON Dictionary
# ============================================================

def write_json_dictionary(
    dictionary: dict[str, Any],
    output_dir: Path,
) -> Path:
    """
    Write the machine-readable data dictionary.
    """

    path = (
        output_dir
        / "data_dictionary.json"
    )

    path.write_text(
        json.dumps(
            dictionary,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    return path


# ============================================================
# Markdown Dictionary
# ============================================================

def write_markdown_dictionary(
    dictionary: dict[str, Any],
    output_dir: Path,
) -> Path:
    """
    Write a human-readable Markdown data dictionary.
    """

    path = (
        output_dir
        / "DATA_DICTIONARY.md"
    )

    lines: list[str] = [
        "# WTF Data Dictionary",
        "",
        (
            "This document describes the datasets and columns "
            "contained in this WTF data release."
        ),
        "",
        (
            f"Schema contract version: "
            f"`{dictionary['contract_version']}`"
        ),
        "",
        (
            "Required fields come from the stable schema contracts. "
            "Optional statistics represent fields available in the "
            "specific HostedSports data included in this release."
        ),
        "",
    ]

    for (
        dataset_name,
        dataset,
    ) in dictionary[
        "datasets"
    ].items():

        lines.extend(
            [
                (
                    f"## `{dataset_name}`"
                ),
                "",
                dataset[
                    "description"
                ],
                "",
                (
                    "**Grain:** "
                    f"{dataset['grain']}"
                ),
                "",
                (
                    "**Primary key:** "
                    + ", ".join(
                        f"`{column}`"
                        for column
                        in dataset[
                            "primary_key"
                        ]
                    )
                ),
                "",
            ]
        )

        partition_columns = (
            dataset[
                "partition_columns"
            ]
        )

        if partition_columns:
            partition_text = (
                ", ".join(
                    f"`{column}`"
                    for column
                    in partition_columns
                )
            )

        else:
            partition_text = (
                "Not partitioned"
            )

        lines.extend(
            [
                (
                    "**Partitioned by:** "
                    f"{partition_text}"
                ),
                "",
                (
                    "**Release shape:** "
                    f"{dataset['row_count']:,} rows × "
                    f"{dataset['column_count']} columns"
                ),
                "",
                "| Column | Type | Required | Description |",
                "| --- | --- | --- | --- |",
            ]
        )

        for column in dataset[
            "columns"
        ]:
            description = (
                column[
                    "description"
                ]
                .replace(
                    "|",
                    r"\|",
                )
                .replace(
                    "\n",
                    " ",
                )
            )

            required = (
                "Yes"
                if column[
                    "required"
                ]
                else "No"
            )

            lines.append(
                f"| `{column['name']}` "
                f"| `{column['dtype']}` "
                f"| {required} "
                f"| {description} |"
            )

        lines.append(
            ""
        )

    path.write_text(
        "\n".join(
            lines
        ).rstrip()
        + "\n",
        encoding="utf-8",
    )

    return path


# ============================================================
# Public Writer
# ============================================================

def write_dictionary_files(
    tables: dict[str, pl.DataFrame],
    output_dir: Path,
) -> tuple[Path, Path]:
    """
    Generate both JSON and Markdown data dictionaries.

    Returns
    -------
    tuple[Path, Path]
        JSON path and Markdown path.
    """

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    dictionary = (
        build_dictionary(
            tables
        )
    )

    json_path = (
        write_json_dictionary(
            dictionary,
            output_dir,
        )
    )

    markdown_path = (
        write_markdown_dictionary(
            dictionary,
            output_dir,
        )
    )

    return (
        json_path,
        markdown_path,
    )