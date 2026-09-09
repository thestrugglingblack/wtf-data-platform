"""
Export dbt analytics marts from DuckDB to versioned Parquet files.

The analytics layer is published alongside the canonical datasets:

data/
└── releases/
    └── <release_version>/
        ├── datasets/
        └── analytics/
            ├── mart_players.parquet
            ├── mart_player_game_logs.parquet
            ├── mart_player_season_stats.parquet
            ├── mart_qb_season_stats.parquet
            ├── mart_player_career_stats.parquet
            ├── mart_team_season_summary.parquet
            └── analytics_manifest.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import duckdb


ANALYTICS_SCHEMA = "main_marts"

ANALYTICS_MARTS = (
    "mart_players",
    "mart_player_game_logs",
    "mart_player_season_stats",
    "mart_qb_season_stats",
    "mart_player_career_stats",
    "mart_team_season_summary",
)


def get_repo_root() -> Path:
    """
    Return the root directory of wtf-data-platform.
    """

    return Path(__file__).resolve().parents[1]


def get_analytics_dir() -> Path:
    """
    Return the dbt analytics project directory.
    """

    return get_repo_root() / "analytics"


def get_dbt_project_path() -> Path:
    """
    Return the dbt_project.yml path.
    """

    return get_analytics_dir() / "dbt_project.yml"


def read_release_version() -> str:
    """
    Read release_version from analytics/dbt_project.yml.

    Example:

    vars:
      release_version: "v0.2.0"
    """

    path = get_dbt_project_path()

    if not path.exists():
        raise FileNotFoundError(
            f"Could not find dbt project file: {path}"
        )

    text = path.read_text(encoding="utf-8")

    match = re.search(
        r'release_version:\s*["\']?([^"\'\s]+)',
        text,
    )

    if match is None:
        raise ValueError(
            "Could not determine release_version from "
            f"{path}. Expected a vars.release_version value."
        )

    return match.group(1)


def discover_duckdb_path(
    database_path: Optional[Path] = None,
) -> Path:
    """
    Locate the DuckDB database used by dbt.

    A database path may be supplied explicitly. Otherwise, the analytics
    directory is searched for .duckdb files.
    """

    if database_path is not None:
        path = database_path.expanduser().resolve()

        if not path.exists():
            raise FileNotFoundError(
                f"DuckDB database does not exist: {path}"
            )

        return path

    candidates = sorted(
        get_analytics_dir().glob("*.duckdb")
    )

    if not candidates:
        raise FileNotFoundError(
            "Could not automatically locate a DuckDB database in "
            f"{get_analytics_dir()}. "
            "Pass --database /path/to/database.duckdb."
        )

    if len(candidates) > 1:
        formatted = "\n".join(
            f"  - {path}"
            for path in candidates
        )

        raise RuntimeError(
            "Multiple DuckDB databases were found. "
            "Pass --database explicitly:\n"
            f"{formatted}"
        )

    return candidates[0].resolve()


def get_release_dir(
    release_version: str,
) -> Path:
    """
    Return the requested versioned release directory.
    """

    return (
        get_repo_root()
        / "data"
        / "releases"
        / release_version
    )


def get_output_dir(
    release_version: str,
) -> Path:
    """
    Return the analytics output directory.
    """

    return (
        get_release_dir(release_version)
        / "analytics"
    )


def sha256_file(
    path: Path,
) -> str:
    """
    Calculate a SHA-256 checksum for a file.
    """

    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def sql_string(
    value: str,
) -> str:
    """
    Escape a string for use inside a DuckDB SQL string literal.
    """

    return value.replace("'", "''")


def validate_marts(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    """
    Ensure every expected core mart exists.
    """

    rows = connection.execute(
        """
        select table_name
        from information_schema.tables
        where table_schema = ?
        """,
        [ANALYTICS_SCHEMA],
    ).fetchall()

    available = {
        row[0]
        for row in rows
    }

    missing = [
        mart
        for mart in ANALYTICS_MARTS
        if mart not in available
    ]

    if missing:
        raise RuntimeError(
            "Analytics marts are missing from DuckDB: "
            + ", ".join(missing)
            + ". Run `dbt run --select marts` first."
        )


def get_columns(
    connection: duckdb.DuckDBPyConnection,
    mart: str,
) -> List[Dict[str, str]]:
    """
    Return column names and DuckDB types for a mart.
    """

    rows = connection.execute(
        f"""
        describe
        select *
        from {ANALYTICS_SCHEMA}.{mart}
        """
    ).fetchall()

    return [
        {
            "name": row[0],
            "type": row[1],
        }
        for row in rows
    ]


def get_row_count(
    connection: duckdb.DuckDBPyConnection,
    mart: str,
) -> int:
    """
    Return row count for a mart.
    """

    row = connection.execute(
        f"""
        select count(*)
        from {ANALYTICS_SCHEMA}.{mart}
        """
    ).fetchone()

    if row is None:
        return 0

    return int(row[0])


def export_mart(
    connection: duckdb.DuckDBPyConnection,
    mart: str,
    output_dir: Path,
) -> Dict[str, object]:
    """
    Export one mart to Parquet and return manifest metadata.
    """

    output_path = (
        output_dir
        / f"{mart}.parquet"
    )

    if output_path.exists():
        output_path.unlink()

    escaped_output = sql_string(
        str(output_path)
    )

    connection.execute(
        f"""
        copy (
            select *
            from {ANALYTICS_SCHEMA}.{mart}
        )
        to '{escaped_output}'
        (
            format parquet,
            compression zstd
        )
        """
    )

    row_count = get_row_count(
        connection,
        mart,
    )

    columns = get_columns(
        connection,
        mart,
    )

    return {
        "dataset": mart,
        "relation": (
            f"{ANALYTICS_SCHEMA}.{mart}"
        ),
        "file": output_path.name,
        "row_count": row_count,
        "column_count": len(columns),
        "columns": columns,
        "size_bytes": output_path.stat().st_size,
        "sha256": sha256_file(output_path),
    }


def write_manifest(
    output_dir: Path,
    release_version: str,
    database_path: Path,
    datasets: List[Dict[str, object]],
) -> Path:
    """
    Write analytics_manifest.json.
    """

    manifest = {
        "release_version": release_version,
        "analytics_schema": ANALYTICS_SCHEMA,
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "source_database": str(database_path),
        "dataset_count": len(datasets),
        "datasets": datasets,
    }

    path = (
        output_dir
        / "analytics_manifest.json"
    )

    temporary_path = path.with_suffix(
        ".json.tmp"
    )

    temporary_path.write_text(
        json.dumps(
            manifest,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    temporary_path.replace(path)

    return path


def publish_analytics(
    database_path: Optional[Path] = None,
    release_version: Optional[str] = None,
) -> Path:
    """
    Export all core analytics marts to the versioned release.
    """

    version = (
        release_version
        or read_release_version()
    )

    database = discover_duckdb_path(
        database_path
    )

    release_dir = get_release_dir(
        version
    )

    if not release_dir.exists():
        raise FileNotFoundError(
            f"Release does not exist: {release_dir}. "
            "Publish the canonical data product first."
        )

    datasets_dir = (
        release_dir
        / "datasets"
    )

    if not datasets_dir.exists():
        raise FileNotFoundError(
            "Canonical datasets directory does not exist: "
            f"{datasets_dir}"
        )

    output_dir = get_output_dir(
        version
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    connection = duckdb.connect(
        str(database)
    )

    try:
        validate_marts(
            connection
        )

        published = []

        for mart in ANALYTICS_MARTS:
            print(
                f"Publishing {mart}..."
            )

            metadata = export_mart(
                connection,
                mart,
                output_dir,
            )

            published.append(
                metadata
            )

            print(
                "  "
                f"{metadata['row_count']:,} rows -> "
                f"{metadata['file']}"
            )

        manifest_path = write_manifest(
            output_dir=output_dir,
            release_version=version,
            database_path=database,
            datasets=published,
        )

    finally:
        connection.close()

    print()
    print(
        f"Analytics release published: {output_dir}"
    )
    print(
        f"Manifest: {manifest_path}"
    )

    return output_dir


def build_parser() -> argparse.ArgumentParser:
    """
    Build the command-line argument parser.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Export WTF dbt analytics marts "
            "to versioned Parquet files."
        )
    )

    parser.add_argument(
        "--database",
        type=Path,
        default=None,
        help=(
            "Path to the DuckDB database. "
            "If omitted, analytics/*.duckdb "
            "is auto-detected."
        ),
    )

    parser.add_argument(
        "--release",
        default=None,
        help=(
            "Release version to publish. "
            "Defaults to vars.release_version "
            "in dbt_project.yml."
        ),
    )

    return parser


def main() -> None:
    """
    CLI entrypoint.
    """

    parser = build_parser()
    args = parser.parse_args()

    publish_analytics(
        database_path=args.database,
        release_version=args.release,
    )


if __name__ == "__main__":
    main()