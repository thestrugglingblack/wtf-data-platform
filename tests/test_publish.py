from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT),
    )


import polars as pl
import pytest

from contracts import (
    DATASET_CONTRACTS,
)

from publish import (
    PublicationError,
    dtype_matches,
    normalize_release_version,
    publish_dataset,
    sha256_file,
    validate_contract,
)


# ============================================================
# Release Version Tests
# ============================================================

def test_normalize_release_version_without_v() -> None:
    """
    Versions without a leading v should receive one.
    """

    result = normalize_release_version(
        "0.1.0"
    )

    assert result == "v0.1.0"


def test_normalize_release_version_with_v() -> None:
    """
    Existing leading v should remain unchanged.
    """

    result = normalize_release_version(
        "v1.2.3"
    )

    assert result == "v1.2.3"


def test_invalid_release_version_raises() -> None:
    """
    Non-semantic versions should not be accepted.
    """

    with pytest.raises(
        PublicationError
    ):
        normalize_release_version(
            "phase-two"
        )


def test_invalid_release_version_missing_patch_raises() -> None:
    """
    Versions must contain major, minor, and patch components.
    """

    with pytest.raises(
        PublicationError
    ):
        normalize_release_version(
            "0.1"
        )


# ============================================================
# Data-Type Tests
# ============================================================

def test_exact_dtype_matches() -> None:
    """
    Identical Polars types should satisfy the contract.
    """

    assert dtype_matches(
        pl.String,
        pl.String,
    )


def test_integer_widths_are_compatible() -> None:
    """
    Int32 vs Int64 should not be treated as a breaking schema change.
    """

    assert dtype_matches(
        pl.Int32,
        pl.Int64,
    )


def test_incompatible_dtype_fails() -> None:
    """
    String should not satisfy an integer contract.
    """

    assert not dtype_matches(
        pl.String,
        pl.Int64,
    )


# ============================================================
# Schema Contract Tests
# ============================================================

def test_team_contract_accepts_valid_frame() -> None:
    """
    A correctly shaped team table should pass its contract.
    """

    df = pl.DataFrame(
        {
            "league": [
                "wfa",
            ],
            "season": [
                2026,
            ],
            "team_id": [
                "team-1",
            ],
            "team_name": [
                "Example Team",
            ],
        },
        schema={
            "league": pl.String,
            "season": pl.Int64,
            "team_id": pl.String,
            "team_name": pl.String,
        },
    )

    errors = validate_contract(
        df,
        DATASET_CONTRACTS[
            "teams"
        ],
    )

    assert errors == []


def test_team_contract_rejects_missing_column() -> None:
    """
    Required fields must exist before publication.
    """

    df = pl.DataFrame(
        {
            "league": [
                "wfa",
            ],
            "season": [
                2026,
            ],
            "team_id": [
                "team-1",
            ],
        },
        schema={
            "league": pl.String,
            "season": pl.Int64,
            "team_id": pl.String,
        },
    )

    errors = validate_contract(
        df,
        DATASET_CONTRACTS[
            "teams"
        ],
    )

    assert any(
        "team_name" in error
        for error in errors
    )


def test_team_contract_rejects_wrong_dtype() -> None:
    """
    Contracted stable types should not silently change.
    """

    df = pl.DataFrame(
        {
            "league": [
                "wfa",
            ],
            "season": [
                "2026",
            ],
            "team_id": [
                "team-1",
            ],
            "team_name": [
                "Example Team",
            ],
        },
        schema={
            "league": pl.String,
            "season": pl.String,
            "team_id": pl.String,
            "team_name": pl.String,
        },
    )

    errors = validate_contract(
        df,
        DATASET_CONTRACTS[
            "teams"
        ],
    )

    assert any(
        "season" in error
        and "dtype" in error
        for error in errors
    )


def test_team_contract_rejects_duplicate_primary_key() -> None:
    """
    Duplicate team logical keys should fail the data-product contract.
    """

    df = pl.DataFrame(
        {
            "league": [
                "wfa",
                "wfa",
            ],
            "season": [
                2026,
                2026,
            ],
            "team_id": [
                "team-1",
                "team-1",
            ],
            "team_name": [
                "Example Team",
                "Example Team",
            ],
        },
        schema={
            "league": pl.String,
            "season": pl.Int64,
            "team_id": pl.String,
            "team_name": pl.String,
        },
    )

    errors = validate_contract(
        df,
        DATASET_CONTRACTS[
            "teams"
        ],
    )

    assert any(
        "duplicate" in error
        for error in errors
    )


# ============================================================
# Parquet Publishing Tests
# ============================================================

def test_publish_dataset_writes_full_parquet(
    tmp_path: Path,
) -> None:
    """
    Every dataset should receive a complete Parquet representation.
    """

    df = pl.DataFrame(
        {
            "league": [
                "wfa",
            ],
            "season": [
                2026,
            ],
            "team_id": [
                "team-1",
            ],
            "team_name": [
                "Example Team",
            ],
        },
        schema={
            "league": pl.String,
            "season": pl.Int64,
            "team_id": pl.String,
            "team_name": pl.String,
        },
    )

    publish_dataset(
        "teams",
        df,
        DATASET_CONTRACTS[
            "teams"
        ],
        tmp_path,
    )

    expected = (
        tmp_path
        / "datasets"
        / "teams.parquet"
    )

    assert expected.exists()


def test_publish_dataset_writes_partitioned_parquet(
    tmp_path: Path,
) -> None:
    """
    League/season datasets should receive Hive-style partitions.
    """

    df = pl.DataFrame(
        {
            "league": [
                "wfa",
                "wfa",
                "wnfc",
            ],
            "season": [
                2025,
                2026,
                2026,
            ],
            "team_id": [
                "team-a",
                "team-b",
                "team-c",
            ],
            "team_name": [
                "Team A",
                "Team B",
                "Team C",
            ],
        },
        schema={
            "league": pl.String,
            "season": pl.Int64,
            "team_id": pl.String,
            "team_name": pl.String,
        },
    )

    metadata = publish_dataset(
        "teams",
        df,
        DATASET_CONTRACTS[
            "teams"
        ],
        tmp_path,
    )

    wfa_2025 = (
        tmp_path
        / "partitions"
        / "teams"
        / "league=wfa"
        / "season=2025"
        / "data.parquet"
    )

    wfa_2026 = (
        tmp_path
        / "partitions"
        / "teams"
        / "league=wfa"
        / "season=2026"
        / "data.parquet"
    )

    wnfc_2026 = (
        tmp_path
        / "partitions"
        / "teams"
        / "league=wnfc"
        / "season=2026"
        / "data.parquet"
    )

    assert wfa_2025.exists()
    assert wfa_2026.exists()
    assert wnfc_2026.exists()

    assert len(
        metadata[
            "partitions"
        ]
    ) == 3


def test_players_are_not_partitioned(
    tmp_path: Path,
) -> None:
    """
    players.parquet should remain global because the canonical
    players table has no league/season grain.
    """

    df = pl.DataFrame(
        {
            "player_id": [
                "player-1",
                "player-2",
            ],
            "player_name": [
                "Player One",
                "Player Two",
            ],
        },
        schema={
            "player_id": pl.String,
            "player_name": pl.String,
        },
    )

    metadata = publish_dataset(
        "players",
        df,
        DATASET_CONTRACTS[
            "players"
        ],
        tmp_path,
    )

    full_file = (
        tmp_path
        / "datasets"
        / "players.parquet"
    )

    assert full_file.exists()

    assert (
        metadata[
            "partitions"
        ]
        == []
    )

    assert (
        metadata[
            "partition_columns"
        ]
        == []
    )


# ============================================================
# Checksum Tests
# ============================================================

def test_published_file_has_sha256(
    tmp_path: Path,
) -> None:
    """
    Published dataset metadata should include a SHA-256 checksum.
    """

    df = pl.DataFrame(
        {
            "league": [
                "wfa",
            ],
            "season": [
                2026,
            ],
            "team_id": [
                "team-1",
            ],
            "team_name": [
                "Example Team",
            ],
        },
        schema={
            "league": pl.String,
            "season": pl.Int64,
            "team_id": pl.String,
            "team_name": pl.String,
        },
    )

    metadata = publish_dataset(
        "teams",
        df,
        DATASET_CONTRACTS[
            "teams"
        ],
        tmp_path,
    )

    checksum = metadata[
        "flat_file"
    ][
        "sha256"
    ]

    assert len(
        checksum
    ) == 64


def test_sha256_file_is_stable(
    tmp_path: Path,
) -> None:
    """
    Identical file contents should always produce the same checksum.
    """

    path = (
        tmp_path
        / "test.txt"
    )

    path.write_text(
        "WTF data product",
        encoding="utf-8",
    )

    first = sha256_file(
        path
    )

    second = sha256_file(
        path
    )

    assert first == second


def test_partition_metadata_contains_checksums(
    tmp_path: Path,
) -> None:
    """
    Each individual partition should receive a checksum.
    """

    df = pl.DataFrame(
        {
            "league": [
                "wfa",
                "wnfc",
            ],
            "season": [
                2026,
                2026,
            ],
            "team_id": [
                "team-1",
                "team-2",
            ],
            "team_name": [
                "Example WFA",
                "Example WNFC",
            ],
        },
        schema={
            "league": pl.String,
            "season": pl.Int64,
            "team_id": pl.String,
            "team_name": pl.String,
        },
    )

    metadata = publish_dataset(
        "teams",
        df,
        DATASET_CONTRACTS[
            "teams"
        ],
        tmp_path,
    )

    assert all(
        len(
            partition[
                "sha256"
            ]
        )
        == 64
        for partition in metadata[
            "partitions"
        ]
    )