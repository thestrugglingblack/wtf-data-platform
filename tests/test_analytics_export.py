"""
Tests for the analytics Parquet publishing layer.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import duckdb
import pytest


def load_export_module() -> ModuleType:
    """
    Load analytics/export.py without requiring analytics
    to be a Python package.
    """

    repo_root = Path(
        __file__
    ).resolve().parents[1]

    export_path = (
        repo_root
        / "analytics"
        / "export.py"
    )

    spec = importlib.util.spec_from_file_location(
        "analytics_export",
        export_path,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"Could not load {export_path}"
        )

    module = importlib.util.module_from_spec(
        spec
    )

    spec.loader.exec_module(
        module
    )

    return module


@pytest.fixture
def export_module() -> ModuleType:
    """
    Return the analytics export module.
    """

    return load_export_module()


@pytest.fixture
def duckdb_database(
    tmp_path: Path,
    export_module: ModuleType,
) -> Path:
    """
    Build a test DuckDB database containing all required marts.
    """

    database = (
        tmp_path
        / "analytics.duckdb"
    )

    connection = duckdb.connect(
        str(database)
    )

    try:
        connection.execute(
            "create schema main_marts"
        )

        for mart in export_module.ANALYTICS_MARTS:
            connection.execute(
                f"""
                create table main_marts.{mart} as
                select
                    'wfa'::varchar as league,
                    2025::bigint as season,
                    '{mart}'::varchar as test_value
                """
            )

    finally:
        connection.close()

    return database


def test_validate_marts_passes(
    export_module: ModuleType,
    duckdb_database: Path,
) -> None:
    """
    All required marts should validate.
    """

    connection = duckdb.connect(
        str(duckdb_database)
    )

    try:
        export_module.validate_marts(
            connection
        )

    finally:
        connection.close()


def test_validate_marts_raises_when_missing(
    export_module: ModuleType,
    tmp_path: Path,
) -> None:
    """
    Missing marts should block publication.
    """

    database = (
        tmp_path
        / "missing.duckdb"
    )

    connection = duckdb.connect(
        str(database)
    )

    try:
        connection.execute(
            "create schema main_marts"
        )

        with pytest.raises(
            RuntimeError,
            match="Analytics marts are missing",
        ):
            export_module.validate_marts(
                connection
            )

    finally:
        connection.close()


def test_export_mart_creates_parquet(
    export_module: ModuleType,
    duckdb_database: Path,
    tmp_path: Path,
) -> None:
    """
    A mart should be exported to Parquet with metadata.
    """

    output_dir = (
        tmp_path
        / "analytics"
    )

    output_dir.mkdir()

    connection = duckdb.connect(
        str(duckdb_database)
    )

    try:
        metadata = export_module.export_mart(
            connection,
            "mart_players",
            output_dir,
        )

    finally:
        connection.close()

    parquet_path = (
        output_dir
        / "mart_players.parquet"
    )

    assert parquet_path.exists()
    assert metadata["dataset"] == "mart_players"
    assert metadata["row_count"] == 1
    assert metadata["column_count"] == 3
    assert metadata["size_bytes"] > 0
    assert len(metadata["sha256"]) == 64


def test_write_manifest(
    export_module: ModuleType,
    tmp_path: Path,
) -> None:
    """
    Analytics manifest should contain release metadata.
    """

    output_dir = (
        tmp_path
        / "analytics"
    )

    output_dir.mkdir()

    manifest_path = export_module.write_manifest(
        output_dir=output_dir,
        release_version="v0.2.0",
        database_path=Path(
            "/tmp/analytics.duckdb"
        ),
        datasets=[
            {
                "dataset": "mart_players",
                "file": "mart_players.parquet",
                "row_count": 10,
            }
        ],
    )

    assert manifest_path.exists()

    manifest = json.loads(
        manifest_path.read_text(
            encoding="utf-8"
        )
    )

    assert (
        manifest["release_version"]
        == "v0.2.0"
    )

    assert manifest["dataset_count"] == 1

    assert (
        manifest["datasets"][0]["dataset"]
        == "mart_players"
    )