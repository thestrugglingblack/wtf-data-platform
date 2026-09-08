from __future__ import annotations

"""
Publish validated WTF datasets as a versioned Parquet data product.

Example
-------

    python publish.py --version 0.1.0


Output
------

    data/releases/
        latest.json

        v0.1.0/
            manifest.json
            schema_contracts.json
            data_dictionary.json
            DATA_DICTIONARY.md

            datasets/
                teams.parquet
                players.parquet
                rosters.parquet
                games.parquet
                player_game_stats.parquet
                player_season_stats.parquet
                team_season_stats.parquet
                standings.parquet

            partitions/
                teams/
                    league=wfa/
                        season=2026/
                            data.parquet

                games/
                    league=wnfc/
                        season=2026/
                            data.parquet

                player_game_stats/
                    league=wfa/
                        season=2026/
                            data.parquet


Two Parquet representations are intentionally produced.

datasets/
    Full canonical table files.

partitions/
    League/season-partitioned analytical layout.

The full files allow wtf-py to consume releases without needing to know
about the physical partition structure.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
from typing import Any

import polars as pl

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PREPARATION_DIR = PROJECT_ROOT / "01_data_preparation"

for module_dir in (
    PROJECT_ROOT,
    PREPARATION_DIR,
):
    if str(module_dir) not in sys.path:
        sys.path.insert(0, str(module_dir))

from config import (
    LATEST_RELEASE_FILE,
    PROCESSED_DATA_DIR,
    RELEASES_DATA_DIR,
)

from contracts import (
    CONTRACT_VERSION,
    DATASET_CONTRACTS,
    DatasetContract,
)

from data_dictionary import (
    write_dictionary_files,
)

from validate import (
    validate_all,
)


# ============================================================
# Constants
# ============================================================

RELEASE_VERSION_PATTERN = re.compile(
    r"^v?\d+\.\d+\.\d+"
    r"(?:[-+][0-9A-Za-z.-]+)?$"
)


# ============================================================
# Exceptions
# ============================================================

class PublicationError(
    RuntimeError
):
    """
    Raised when processed data cannot safely be published.
    """


# ============================================================
# Version Helpers
# ============================================================

def normalize_release_version(
    version: str,
) -> str:
    """
    Normalize a semantic version into WTF release format.

    Examples
    --------

    0.1.0
        becomes v0.1.0

    v1.2.0
        remains v1.2.0
    """

    version = (
        version.strip()
    )

    if not RELEASE_VERSION_PATTERN.fullmatch(
        version
    ):
        raise PublicationError(
            "Release version must use semantic-version format. "
            "Examples: '0.1.0' or 'v0.1.0'."
        )

    if not version.startswith(
        "v"
    ):
        version = (
            f"v{version}"
        )

    return version


# ============================================================
# Hashing
# ============================================================

def sha256_file(
    path: Path,
) -> str:
    """
    Calculate the SHA-256 checksum for a published file.
    """

    digest = (
        hashlib.sha256()
    )

    with path.open(
        "rb"
    ) as file:
        for chunk in iter(
            lambda: file.read(
                1024 * 1024
            ),
            b"",
        ):
            digest.update(
                chunk
            )

    return (
        digest.hexdigest()
    )


# ============================================================
# Processed Data Loading
# ============================================================

def load_processed_tables(
    root: Path = PROCESSED_DATA_DIR,
) -> dict[str, pl.DataFrame]:
    """
    Load the canonical processed datasets.

    Parquet is preferred if it exists.

    CSV is used as the current fallback because normalize.py currently
    publishes canonical processed CSV files.
    """

    tables: dict[
        str,
        pl.DataFrame,
    ] = {}

    for dataset_name in (
        DATASET_CONTRACTS
    ):
        csv_path = (
            root
            / f"{dataset_name}.csv"
        )

        parquet_path = (
            root
            / f"{dataset_name}.parquet"
        )

        if parquet_path.exists():
            df = (
                pl.read_parquet(
                    parquet_path
                )
            )

        elif csv_path.exists():
            df = (
                pl.read_csv(
                    csv_path,
                    infer_schema_length=None,
                    null_values=[
                        "",
                        "NULL",
                        "null",
                        "None",
                    ],
                    try_parse_dates=True,
                )
            )

        else:
            raise PublicationError(
                f"Missing processed dataset '{dataset_name}'. "
                f"Expected either:\n"
                f"  {parquet_path}\n"
                f"or\n"
                f"  {csv_path}"
            )

        tables[
            dataset_name
        ] = df

    return tables


# ============================================================
# Contract Validation
# ============================================================

def dtype_matches(
    actual: pl.DataType,
    expected: pl.DataType,
) -> bool:
    """
    Determine whether an actual Polars type satisfies the contract.

    Integer width differences are treated as compatible.

    For example:

        Int32 vs Int64

    does not constitute a breaking schema change for the data product.
    """

    if actual == expected:
        return True

    integer_types = {
        pl.Int8,
        pl.Int16,
        pl.Int32,
        pl.Int64,
        pl.UInt8,
        pl.UInt16,
        pl.UInt32,
        pl.UInt64,
    }

    if (
        actual in integer_types
        and expected in integer_types
    ):
        return True

    return False


def validate_contract(
    df: pl.DataFrame,
    contract: DatasetContract,
) -> list[str]:
    """
    Validate one DataFrame against its schema contract.

    Returns
    -------
    list[str]
        Empty when the contract passes.
        Otherwise contains human-readable errors.
    """

    errors: list[str] = []

    # --------------------------------------------------------
    # Required columns
    # --------------------------------------------------------

    missing_columns = sorted(
        set(
            contract.required_columns
        )
        - set(
            df.columns
        )
    )

    if missing_columns:
        errors.append(
            "missing required column(s): "
            + ", ".join(
                missing_columns
            )
        )

    # --------------------------------------------------------
    # Required types
    # --------------------------------------------------------

    for (
        column,
        expected_dtype,
    ) in (
        contract
        .required_dtypes
        .items()
    ):
        if column not in df.columns:
            continue

        actual_dtype = (
            df.schema[
                column
            ]
        )

        if not dtype_matches(
            actual_dtype,
            expected_dtype,
        ):
            errors.append(
                f"column '{column}' "
                f"has dtype {actual_dtype}; "
                f"expected {expected_dtype}"
            )

    # --------------------------------------------------------
    # Primary-key duplicate check
    # --------------------------------------------------------

    if contract.primary_key:
        available_key_columns = [
            column
            for column
            in contract.primary_key
            if column in df.columns
        ]

        if len(
            available_key_columns
        ) == len(
            contract.primary_key
        ):
            key_df = df

            # ------------------------------------------------
            # Historical source-quality exceptions
            # ------------------------------------------------
            #
            # validate.py already distinguishes these known
            # source-quality conditions from structural failures.
            #
            # Null canonical IDs should not turn an already-known
            # warning into a Phase 2 structural publication failure.
            #

            if contract.name in {
                "player_game_stats",
                "player_season_stats",
                "team_season_stats",
            }:
                key_df = (
                    df.filter(
                        pl.all_horizontal(
                            [
                                pl.col(
                                    column
                                ).is_not_null()
                                for column
                                in contract.primary_key
                            ]
                        )
                    )
                )

            duplicate_groups = (
                key_df
                .group_by(
                    list(
                        contract.primary_key
                    )
                )
                .len()
                .filter(
                    pl.col(
                        "len"
                    ) > 1
                )
                .height
            )

            # These datasets currently contain known historical
            # duplicate/source-identity warnings managed by validate.py.
            #
            # We preserve those warnings instead of redefining them
            # here as publication errors.
            warning_only_datasets = {
                "player_game_stats",
                "player_season_stats",
                "team_season_stats",
            }

            if (
                duplicate_groups > 0
                and contract.name
                not in warning_only_datasets
            ):
                errors.append(
                    f"{duplicate_groups} duplicate "
                    f"primary-key group(s) for "
                    f"{list(contract.primary_key)}"
                )

    return errors


def enforce_contracts(
    tables: dict[str, pl.DataFrame],
) -> None:
    """
    Validate all canonical tables against their contracts.

    Raises
    ------
    PublicationError
        When one or more schema contracts fail.
    """

    failures: list[str] = []

    for (
        dataset_name,
        contract,
    ) in DATASET_CONTRACTS.items():

        df = tables[
            dataset_name
        ]

        errors = (
            validate_contract(
                df,
                contract,
            )
        )

        for error in errors:
            failures.append(
                f"{dataset_name}: {error}"
            )

    if failures:
        formatted = "\n".join(
            f"  - {failure}"
            for failure
            in failures
        )

        raise PublicationError(
            "Schema-contract validation failed:\n"
            f"{formatted}"
        )


# ============================================================
# Contract Metadata
# ============================================================

def contracts_to_json() -> dict[str, Any]:
    """
    Convert Python schema contracts into serializable metadata.
    """

    datasets: dict[
        str,
        Any,
    ] = {}

    for (
        name,
        contract,
    ) in DATASET_CONTRACTS.items():

        datasets[
            name
        ] = {
            "description": (
                contract.description
            ),
            "grain": (
                contract.grain
            ),
            "required_columns": list(
                contract.required_columns
            ),
            "primary_key": list(
                contract.primary_key
            ),
            "partition_columns": list(
                contract.partition_columns
            ),
            "required_dtypes": {
                column: str(
                    dtype
                )
                for (
                    column,
                    dtype,
                ) in (
                    contract
                    .required_dtypes
                    .items()
                )
            },
            "allow_additional_columns": (
                contract.allow_additional_columns
            ),
        }

    return {
        "contract_version": (
            CONTRACT_VERSION
        ),
        "datasets": datasets,
    }


def write_schema_contracts(
    release_dir: Path,
) -> Path:
    """
    Write schema_contracts.json into the release.
    """

    path = (
        release_dir
        / "schema_contracts.json"
    )

    path.write_text(
        json.dumps(
            contracts_to_json(),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    return path


# ============================================================
# Partition Helpers
# ============================================================

def partition_value(
    value: object,
) -> str:
    """
    Convert a partition value into a directory-safe string.
    """

    if value is None:
        return "__NULL__"

    return str(
        value
    )


# ============================================================
# Dataset Publishing
# ============================================================

def publish_dataset(
    dataset_name: str,
    df: pl.DataFrame,
    contract: DatasetContract,
    release_dir: Path,
) -> dict[str, Any]:
    """
    Publish one canonical dataset.

    Produces:

    1. A complete Parquet file under datasets/
    2. Partitioned Parquet files under partitions/ when applicable
    3. Metadata used by manifest.json
    """

    datasets_dir = (
        release_dir
        / "datasets"
    )

    partitions_dir = (
        release_dir
        / "partitions"
        / dataset_name
    )

    datasets_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # Full canonical Parquet
    # --------------------------------------------------------

    flat_path = (
        datasets_dir
        / f"{dataset_name}.parquet"
    )

    df.write_parquet(
        flat_path,
        compression="zstd",
        statistics=True,
    )

    partition_records: list[
        dict[str, Any]
    ] = []

    # --------------------------------------------------------
    # Partitioned Parquet
    # --------------------------------------------------------

    if contract.partition_columns:
        missing_partition_columns = [
            column
            for column
            in contract.partition_columns
            if column not in df.columns
        ]

        if missing_partition_columns:
            raise PublicationError(
                f"{dataset_name}: missing "
                f"partition column(s): "
                + ", ".join(
                    missing_partition_columns
                )
            )

        partitions_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        partition_columns = list(
            contract.partition_columns
        )

        groups = (
            df.partition_by(
                partition_columns,
                maintain_order=True,
                as_dict=True,
            )
        )

        for (
            raw_key,
            partition_df,
        ) in groups.items():

            if isinstance(
                raw_key,
                tuple,
            ):
                key = raw_key

            else:
                key = (
                    raw_key,
                )

            partition_path = (
                partitions_dir
            )

            partition_values: dict[
                str,
                Any,
            ] = {}

            for (
                column,
                value,
            ) in zip(
                partition_columns,
                key,
            ):
                partition_values[
                    column
                ] = value

                partition_path = (
                    partition_path
                    / (
                        f"{column}="
                        f"{partition_value(value)}"
                    )
                )

            partition_path.mkdir(
                parents=True,
                exist_ok=True,
            )

            parquet_path = (
                partition_path
                / "data.parquet"
            )

            partition_df.write_parquet(
                parquet_path,
                compression="zstd",
                statistics=True,
            )

            partition_records.append(
                {
                    "partition": (
                        partition_values
                    ),
                    "rows": (
                        partition_df.height
                    ),
                    "path": str(
                        parquet_path.relative_to(
                            release_dir
                        )
                    ),
                    "sha256": (
                        sha256_file(
                            parquet_path
                        )
                    ),
                    "size_bytes": (
                        parquet_path
                        .stat()
                        .st_size
                    ),
                }
            )

    # --------------------------------------------------------
    # Dataset metadata
    # --------------------------------------------------------

    return {
        "name": (
            dataset_name
        ),
        "description": (
            contract.description
        ),
        "grain": (
            contract.grain
        ),
        "rows": (
            df.height
        ),
        "columns": (
            df.width
        ),
        "schema": {
            column: str(
                dtype
            )
            for (
                column,
                dtype,
            ) in (
                df.schema.items()
            )
        },
        "primary_key": list(
            contract.primary_key
        ),
        "partition_columns": list(
            contract.partition_columns
        ),
        "flat_file": {
            "path": str(
                flat_path.relative_to(
                    release_dir
                )
            ),
            "sha256": (
                sha256_file(
                    flat_path
                )
            ),
            "size_bytes": (
                flat_path
                .stat()
                .st_size
            ),
        },
        "partitions": (
            partition_records
        ),
    }


# ============================================================
# Release Manifest
# ============================================================

def write_manifest(
    release_dir: Path,
    version: str,
    dataset_metadata: list[
        dict[str, Any]
    ],
    validation_errors: int,
    validation_warnings: int,
) -> Path:
    """
    Write the release manifest.

    The manifest acts as the official receipt for a WTF data release.
    """

    total_rows = sum(
        dataset[
            "rows"
        ]
        for dataset
        in dataset_metadata
    )

    total_files = sum(
        1
        + len(
            dataset[
                "partitions"
            ]
        )
        for dataset
        in dataset_metadata
    )

    manifest = {
        "product": (
            "wtf-data"
        ),
        "release_version": (
            version
        ),
        "contract_version": (
            CONTRACT_VERSION
        ),
        "generated_at": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
        "format": (
            "parquet"
        ),
        "compression": (
            "zstd"
        ),
        "partition_strategy": [
            "league",
            "season",
        ],
        "summary": {
            "datasets": len(
                dataset_metadata
            ),
            "rows": (
                total_rows
            ),
            "parquet_files": (
                total_files
            ),
        },
        "validation": {
            "errors": (
                validation_errors
            ),
            "warnings": (
                validation_warnings
            ),
            "publication_rule": (
                "A release is blocked when structural validation errors "
                "are present. Known source-quality warnings remain visible "
                "but do not block publication."
            ),
        },
        "datasets": (
            dataset_metadata
        ),
    }

    path = (
        release_dir
        / "manifest.json"
    )

    path.write_text(
        json.dumps(
            manifest,
            indent=2,
            sort_keys=True,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )

    return path


# ============================================================
# Latest Release Pointer
# ============================================================

def write_latest_pointer(
    version: str,
    release_dir: Path,
) -> Path:
    """
    Update data/releases/latest.json.

    Existing releases remain immutable.

    latest.json simply tells downstream consumers which successfully
    published version should currently be treated as the default.
    """

    RELEASES_DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    pointer = {
        "release_version": (
            version
        ),
        "release_path": str(
            release_dir.relative_to(
                RELEASES_DATA_DIR
            )
        ),
        "manifest": str(
            (
                release_dir
                / "manifest.json"
            ).relative_to(
                RELEASES_DATA_DIR
            )
        ),
        "updated_at": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
    }

    LATEST_RELEASE_FILE.write_text(
        json.dumps(
            pointer,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    return (
        LATEST_RELEASE_FILE
    )


# ============================================================
# Full Release Publishing
# ============================================================

def publish_release(
    version: str,
    *,
    processed_root: Path = PROCESSED_DATA_DIR,
    releases_root: Path = RELEASES_DATA_DIR,
    force: bool = False,
) -> Path:
    """
    Publish a complete WTF data-product release.

    Publication occurs only when:

    1. validate.py reports zero structural errors
    2. every dataset exists
    3. every dataset satisfies its Phase 2 schema contract

    Parameters
    ----------
    version:
        Semantic release version such as 0.1.0.

    processed_root:
        Directory containing normalized canonical tables.

    releases_root:
        Destination for versioned data releases.

    force:
        Delete and rebuild an existing version.
        Intended for publication-code development only.

    Returns
    -------
    Path
        Path to the completed release.
    """

    version = (
        normalize_release_version(
            version
        )
    )

    release_dir = (
        releases_root
        / version
    )

    # --------------------------------------------------------
    # Protect immutable releases
    # --------------------------------------------------------

    if release_dir.exists():
        if not force:
            raise PublicationError(
                f"Release {version} already exists at:\n"
                f"{release_dir}\n\n"
                "Published releases are immutable by default.\n"
                "Use --force only while developing the publisher."
            )

        shutil.rmtree(
            release_dir
        )

    print(
        "\n"
        + "=" * 72
    )

    print(
        f"PUBLISHING WTF DATA PRODUCT {version}"
    )

    print(
        "=" * 72
    )

    # --------------------------------------------------------
    # Phase 1 validation gate
    # --------------------------------------------------------

    print(
        "\nRunning validation gate..."
    )

    validation_report = (
        validate_all(
            root=processed_root
        )
    )

    if (
        validation_report.error_count
        > 0
    ):
        raise PublicationError(
            "Publication blocked because "
            "structural validation errors exist."
        )

    print(
        "\n✓ Structural validation passed."
    )

    if (
        validation_report.warning_count
        > 0
    ):
        print(
            f"! {validation_report.warning_count} "
            "validation warning(s) will be "
            "recorded in the release manifest."
        )

    # --------------------------------------------------------
    # Load canonical tables
    # --------------------------------------------------------

    print(
        "\nLoading processed datasets..."
    )

    tables = (
        load_processed_tables(
            processed_root
        )
    )

    # --------------------------------------------------------
    # Phase 2 schema-contract gate
    # --------------------------------------------------------

    print(
        "\nChecking schema contracts..."
    )

    enforce_contracts(
        tables
    )

    print(
        "✓ Schema contracts passed."
    )

    # --------------------------------------------------------
    # Create release
    # --------------------------------------------------------

    release_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    try:
        # ----------------------------------------------------
        # Schema contract file
        # ----------------------------------------------------

        schema_contract_path = (
            write_schema_contracts(
                release_dir
            )
        )

        print(
            "\n✓ Schema contracts written:"
        )

        print(
            f"  {schema_contract_path}"
        )

        # ----------------------------------------------------
        # Data dictionaries
        # ----------------------------------------------------

        (
            dictionary_json_path,
            dictionary_markdown_path,
        ) = (
            write_dictionary_files(
                tables,
                release_dir,
            )
        )

        print(
            "\n✓ Data dictionaries written:"
        )

        print(
            f"  {dictionary_json_path}"
        )

        print(
            f"  {dictionary_markdown_path}"
        )

        # ----------------------------------------------------
        # Parquet datasets
        # ----------------------------------------------------

        print(
            "\nPublishing Parquet datasets..."
        )

        dataset_metadata: list[
            dict[str, Any]
        ] = []

        for (
            dataset_name,
            contract,
        ) in (
            DATASET_CONTRACTS.items()
        ):
            metadata = (
                publish_dataset(
                    dataset_name,
                    tables[
                        dataset_name
                    ],
                    contract,
                    release_dir,
                )
            )

            dataset_metadata.append(
                metadata
            )

            print(
                f"✓ {dataset_name}: "
                f"{metadata['rows']:,} rows, "
                f"{metadata['columns']} columns, "
                f"{len(metadata['partitions'])} "
                "partition(s)"
            )

        # ----------------------------------------------------
        # Manifest
        # ----------------------------------------------------

        manifest_path = (
            write_manifest(
                release_dir,
                version,
                dataset_metadata,
                validation_report.error_count,
                validation_report.warning_count,
            )
        )

        print(
            "\n✓ Release manifest written:"
        )

        print(
            f"  {manifest_path}"
        )

        # ----------------------------------------------------
        # latest.json
        # --------------------------------------------------------
        #
        # Only update the configured production releases root.
        #
        # This prevents tests using temporary directories from
        # overwriting the real data/releases/latest.json.
        #

        if (
            releases_root.resolve()
            == RELEASES_DATA_DIR.resolve()
        ):
            latest_path = (
                write_latest_pointer(
                    version,
                    release_dir,
                )
            )

            print(
                "\n✓ Latest release pointer updated:"
            )

            print(
                f"  {latest_path}"
            )

    except Exception:
        # ----------------------------------------------------
        # Atomic publication behavior
        # --------------------------------------------------------
        #
        # Never leave behind a partially published release.
        #

        if release_dir.exists():
            shutil.rmtree(
                release_dir
            )

        raise

    # --------------------------------------------------------
    # Success summary
    # --------------------------------------------------------

    print(
        "\n"
        + "-" * 72
    )

    print(
        "WTF DATA PRODUCT PUBLICATION COMPLETE"
    )

    print(
        "-" * 72
    )

    print(
        f"Release version: {version}"
    )

    print(
        f"Release path:    {release_dir}"
    )

    print(
        f"Manifest:        "
        f"{release_dir / 'manifest.json'}"
    )

    print(
        f"Data dictionary: "
        f"{release_dir / 'DATA_DICTIONARY.md'}"
    )

    print(
        f"wtf-py path:     "
        f"{release_dir / 'datasets'}"
    )

    print(
        "-" * 72
    )

    return (
        release_dir
    )


# ============================================================
# CLI
# ============================================================

def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments.
    """

    parser = (
        argparse.ArgumentParser(
            description=(
                "Publish validated WTF datasets "
                "as a versioned Parquet data product."
            )
        )
    )

    parser.add_argument(
        "--version",
        required=True,
        help=(
            "Semantic data release version. "
            "Example: 0.1.0"
        ),
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Replace an existing release. "
            "Use only while developing the publisher."
        ),
    )

    return (
        parser.parse_args()
    )


# ============================================================
# Main
# ============================================================

def main() -> None:
    """
    CLI entry point.
    """

    args = (
        parse_args()
    )

    publish_release(
        args.version,
        force=args.force,
    )


if __name__ == "__main__":
    main()