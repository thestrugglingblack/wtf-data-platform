from __future__ import annotations

"""
Recover safely repairable HostedSports raw responses.

This script reads *.invalid.txt files from data/raw and writes successfully
recovered JSON responses to data/recovered without modifying the original
raw files.

Recovery rules are intentionally conservative:

1. PYTHON_LITERAL
   - escape raw control characters that make JSON invalid
   - try json.loads()
   - if still invalid, try ast.literal_eval()
   - only write output if the result can be serialized as valid JSON

2. MALFORMED_GAME_DATA
   - repair HostedSports' malformed empty-array pattern:
         [ }]
     into:
         []
   - escape raw control characters
   - only write output if json.loads() succeeds

3. MALFORMED_STANDINGS_DATA
   - escape raw control characters
   - remove trailing commas before ] or }
   - optionally repair unmatched closing delimiters that occur only at EOF
   - optionally append missing closing delimiters only when the JSON parser
     fails at/near EOF and delimiter nesting can be determined safely
   - only write output if json.loads() succeeds

The original source remains immutable.

Outputs:

    data/recovered/
        <league>/<season>/...

    data/validation/
        recovery_report.csv

The recovery report records:
    - source file
    - recovered output file
    - detected category
    - recovery rule
    - success/failure
    - parse error
    - source/output sizes

Typical use:

    python3 repair.py
"""

from dataclasses import dataclass, asdict
import ast
import json
from pathlib import Path
import re
from typing import Any, Iterable

from config import RAW_DATA_DIR


# ============================================================
# Paths
# ============================================================

DATA_DIR = RAW_DATA_DIR.parent
RECOVERED_DATA_DIR = DATA_DIR / "recovered"
VALIDATION_DATA_DIR = DATA_DIR / "validation"
RECOVERY_REPORT_PATH = VALIDATION_DATA_DIR / "recovery_report.csv"


# ============================================================
# Models
# ============================================================

@dataclass
class RecoveryResult:
    source_file: str
    recovered_file: str | None
    league: str | None
    season: str | None
    endpoint: str | None
    resource_id: str | None
    category: str
    success: bool
    recovery_rule: str | None
    parse_error: str | None
    source_size_bytes: int
    output_size_bytes: int | None


# ============================================================
# Metadata helpers
# ============================================================

KNOWN_ENDPOINTS = {
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


def infer_invalid_file_metadata(
    path: Path,
    raw_root: Path = RAW_DATA_DIR,
) -> dict[str, str | None]:
    """
    Infer league, season, endpoint, and resource ID from an invalid-file path.
    """
    try:
        relative = path.relative_to(raw_root)
    except ValueError:
        relative = path

    parts = list(relative.parts)

    league = parts[0].lower() if len(parts) >= 1 else None
    season = parts[1] if len(parts) >= 2 else None

    endpoint = None
    resource_id = None

    stem = path.name.removesuffix(".invalid.txt")

    if len(parts) >= 4:
        candidate = parts[-2].lower()

        if candidate in KNOWN_ENDPOINTS:
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


# ============================================================
# Classification
# ============================================================

def classify_recovery_candidate(
    text: str,
    endpoint: str | None,
) -> str:
    """
    Classify only the categories repair.py knows how to attempt.

    This intentionally mirrors the useful recovery categories from validate.py
    without importing validate.py.
    """
    stripped = text.strip()

    if not stripped:
        return "UNSUPPORTED"

    compact = re.sub(r"\s+", "", stripped)

    if (
        endpoint == "stats"
        and '"player_stat_totals"' in compact
        and compact.endswith("[{]}")
    ):
        return "EMPTY_PLAYER_STATS"

    try:
        json.loads(stripped)
    except json.JSONDecodeError:
        pass
    else:
        return "VALID_JSON"

    if endpoint == "games":
        return "MALFORMED_GAME_DATA"

    if endpoint == "standings":
        return "MALFORMED_STANDINGS_DATA"

    if stripped.startswith(("{", "[", "(", "'", '"')):
        try:
            parsed = ast.literal_eval(stripped)
        except (ValueError, SyntaxError, MemoryError, RecursionError):
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

    # Some files classified by validate.py as PYTHON_LITERAL fail here because
    # raw tab/control characters break the literal before repair. Try again
    # after escaping raw controls.
    escaped = escape_raw_control_characters(stripped)

    if escaped != stripped:
        try:
            parsed = ast.literal_eval(escaped)
        except (ValueError, SyntaxError, MemoryError, RecursionError):
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

    return "UNSUPPORTED"


# ============================================================
# Generic text repair helpers
# ============================================================

def escape_raw_control_characters(text: str) -> str:
    """
    Escape raw control characters that are illegal inside JSON strings.

    HostedSports historical responses contain raw tabs inside some player
    names. json.loads() rejects those raw tab characters.

    This function only rewrites control characters that appear while inside
    a quoted JSON string. Whitespace outside strings is left unchanged.
    """
    output: list[str] = []
    in_string = False
    escaped = False

    replacements = {
        "\t": r"\t",
        "\n": r"\n",
        "\r": r"\r",
        "\b": r"\b",
        "\f": r"\f",
    }

    for char in text:
        if in_string:
            if escaped:
                output.append(char)
                escaped = False
                continue

            if char == "\\":
                output.append(char)
                escaped = True
                continue

            if char == '"':
                output.append(char)
                in_string = False
                continue

            if char in replacements:
                output.append(replacements[char])
                continue

            if ord(char) < 0x20:
                output.append(
                    "\\u"
                    + format(ord(char), "04x")
                )
                continue

            output.append(char)
            continue

        output.append(char)

        if char == '"':
            in_string = True
            escaped = False

    return "".join(output)


def remove_trailing_commas(text: str) -> str:
    """
    Remove commas that appear immediately before a closing ] or }.

    Example:
        [{"a": 1},]
    becomes:
        [{"a": 1}]
    """
    return re.sub(
        r",\s*(?=[}\]])",
        "",
        text,
    )


def repair_malformed_empty_arrays(text: str) -> str:
    """
    Repair HostedSports' malformed empty array representation.

    Examples:
        [ }]
        [   } ]
    become:
        []

    This rule is only intended for game responses.
    """
    return re.sub(
        r"\[\s*\}\s*\]",
        "[]",
        text,
    )


def json_loads_with_error(
    text: str,
) -> tuple[Any | None, str | None]:
    """
    Attempt json.loads and return (parsed, error_message).
    """
    try:
        return json.loads(text), None
    except json.JSONDecodeError as exc:
        error = (
            f"{exc.msg} "
            f"(line={exc.lineno}, column={exc.colno}, pos={exc.pos})"
        )
        return None, error


def is_error_near_eof(
    text: str,
    error: json.JSONDecodeError,
    tolerance: int = 12,
) -> bool:
    """
    Return True when the parse error is at or very near the end of the input.
    """
    return error.pos >= max(
        0,
        len(text.rstrip()) - tolerance,
    )


# ============================================================
# Delimiter analysis for standings
# ============================================================

OPEN_TO_CLOSE = {
    "{": "}",
    "[": "]",
}

CLOSE_TO_OPEN = {
    "}": "{",
    "]": "[",
}


def delimiter_stack(
    text: str,
) -> tuple[list[str], list[tuple[int, str]]]:
    """
    Analyze JSON-style delimiters while ignoring delimiters inside strings.

    Returns:
        stack:
            unmatched opening delimiters

        unmatched_closers:
            list of (position, closing_delimiter) that did not match
    """
    stack: list[str] = []
    unmatched_closers: list[tuple[int, str]] = []

    in_string = False
    escaped = False

    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
                continue

            if char == "\\":
                escaped = True
                continue

            if char == '"':
                in_string = False

            continue

        if char == '"':
            in_string = True
            escaped = False
            continue

        if char in OPEN_TO_CLOSE:
            stack.append(char)
            continue

        if char in CLOSE_TO_OPEN:
            expected_open = CLOSE_TO_OPEN[char]

            if stack and stack[-1] == expected_open:
                stack.pop()
            else:
                unmatched_closers.append(
                    (index, char)
                )

    return stack, unmatched_closers


def append_missing_closers(
    text: str,
) -> tuple[str, str | None]:
    """
    Append missing closing delimiters only when all existing closers are
    correctly nested.

    Returns:
        repaired_text, rule_description_or_none
    """
    stack, unmatched_closers = delimiter_stack(
        text
    )

    if unmatched_closers:
        return text, None

    if not stack:
        return text, None

    closers = "".join(
        OPEN_TO_CLOSE[opening]
        for opening in reversed(stack)
    )

    return (
        text.rstrip() + closers,
        f"append_missing_closers:{closers}",
    )


def trim_trailing_unmatched_closers(
    text: str,
) -> tuple[str, str | None]:
    """
    Conservatively trim unmatched closing delimiters only if they occur in the
    trailing suffix after the final structurally matched root document.

    This handles historical responses that contain extra ] or } delimiters
    after an otherwise complete JSON document.

    If unmatched closing delimiters occur in the middle of meaningful content,
    no repair is attempted.
    """
    stack: list[str] = []
    in_string = False
    escaped = False

    root_started = False
    root_complete_at: int | None = None

    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
                continue

            if char == "\\":
                escaped = True
                continue

            if char == '"':
                in_string = False

            continue

        if char == '"':
            in_string = True
            escaped = False
            continue

        if char in OPEN_TO_CLOSE:
            root_started = True
            stack.append(char)
            continue

        if char in CLOSE_TO_OPEN:
            if stack and stack[-1] == CLOSE_TO_OPEN[char]:
                stack.pop()

                if root_started and not stack:
                    root_complete_at = index
                continue

            # Unmatched closer before the root is complete means the structure
            # is ambiguous. Do not trim automatically.
            if root_complete_at is None:
                return text, None

    if root_complete_at is None:
        return text, None

    suffix = text[
        root_complete_at + 1:
    ]

    # Only whitespace, commas, and closing delimiters may be trimmed.
    if suffix and re.fullmatch(
        r"[\s,\]\}]*",
        suffix,
    ):
        trimmed = text[
            : root_complete_at + 1
        ]

        if trimmed != text:
            return (
                trimmed,
                "trim_trailing_extra_closers",
            )

    return text, None


# ============================================================
# Category-specific recovery
# ============================================================

def recover_python_literal(
    text: str,
) -> tuple[Any | None, str | None, str | None]:
    """
    Recover historical Python-literal-like responses.

    Returns:
        parsed_object,
        recovery_rule,
        error_message
    """
    escaped = escape_raw_control_characters(
        text
    )

    parsed, error = json_loads_with_error(
        escaped
    )

    if parsed is not None:
        rule = (
            "escape_raw_control_characters"
            if escaped != text
            else "json_parse"
        )
        return parsed, rule, None

    try:
        literal = ast.literal_eval(
            escaped
        )
    except (
        ValueError,
        SyntaxError,
        MemoryError,
        RecursionError,
    ) as exc:
        return (
            None,
            None,
            f"json_error={error}; literal_error={exc}",
        )

    if not isinstance(
        literal,
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
        return (
            None,
            None,
            (
                "ast.literal_eval returned unsupported "
                f"type {type(literal).__name__}"
            ),
        )

    # Convert tuples and other JSON-compatible Python values through json.
    try:
        serialized = json.dumps(
            literal,
            ensure_ascii=False,
        )
        parsed = json.loads(
            serialized
        )
    except (
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        return (
            None,
            None,
            f"literal serialization failed: {exc}",
        )

    rule = "ast_literal_eval"

    if escaped != text:
        rule = (
            "escape_raw_control_characters+"
            "ast_literal_eval"
        )

    return parsed, rule, None


def recover_malformed_game(
    text: str,
) -> tuple[Any | None, str | None, str | None]:
    """
    Recover HostedSports malformed game JSON.
    """
    candidate = escape_raw_control_characters(
        text
    )

    rules: list[str] = []

    if candidate != text:
        rules.append(
            "escape_raw_control_characters"
        )

    fixed_arrays = repair_malformed_empty_arrays(
        candidate
    )

    if fixed_arrays != candidate:
        rules.append(
            "repair_malformed_empty_arrays"
        )

    candidate = fixed_arrays

    parsed, error = json_loads_with_error(
        candidate
    )

    if parsed is None:
        return (
            None,
            "+".join(rules) or None,
            error,
        )

    return (
        parsed,
        "+".join(rules) or "json_parse",
        None,
    )


def _try_json_candidate(
    candidate: str,
    rule_names: Iterable[str],
) -> tuple[Any | None, str | None, str | None]:
    """
    Parse a candidate and format its rule label.
    """
    parsed, error = json_loads_with_error(
        candidate
    )

    return (
        parsed,
        "+".join(rule_names),
        error,
    )


def recover_malformed_standings(
    text: str,
) -> tuple[Any | None, str | None, str | None]:
    """
    Recover malformed standings data using conservative transformations.

    Strategy:
        1. escape raw control characters
        2. remove trailing commas before ] or }
        3. try JSON
        4. if parse failure is at EOF and delimiters are only missing at EOF,
           append the exact required closing delimiters
        5. if an otherwise complete root has only extra trailing closing
           delimiters/commas, trim that trailing suffix
        6. combinations of steps 2, 4, and 5 are tried, but output is accepted
           only if json.loads() succeeds

    No interior structural guessing is performed.
    """
    base = escape_raw_control_characters(
        text
    )

    base_rules: list[str] = []

    if base != text:
        base_rules.append(
            "escape_raw_control_characters"
        )

    # Candidate 1: base text.
    parsed, error = json_loads_with_error(
        base
    )

    if parsed is not None:
        return (
            parsed,
            "+".join(base_rules) or "json_parse",
            None,
        )

    # Candidate 2: remove trailing commas.
    no_trailing_commas = remove_trailing_commas(
        base
    )

    comma_rules = list(base_rules)

    if no_trailing_commas != base:
        comma_rules.append(
            "remove_trailing_commas"
        )

    parsed, comma_error = json_loads_with_error(
        no_trailing_commas
    )

    if parsed is not None:
        return (
            parsed,
            "+".join(comma_rules),
            None,
        )

    # Candidate 3: trim trailing unmatched closing delimiters after a complete
    # root document.
    trimmed, trim_rule = (
        trim_trailing_unmatched_closers(
            no_trailing_commas
        )
    )

    trim_rules = list(comma_rules)

    if trim_rule is not None:
        trim_rules.append(
            trim_rule
        )

        parsed, trim_error = (
            json_loads_with_error(
                trimmed
            )
        )

        if parsed is not None:
            return (
                parsed,
                "+".join(trim_rules),
                None,
            )
    else:
        trim_error = comma_error

    # Candidate 4: append missing closers, but only when the JSON parse failure
    # is at/near EOF. This avoids guessing about interior corruption.
    append_base = (
        trimmed
        if trim_rule is not None
        else no_trailing_commas
    )
    append_rules = (
        trim_rules
        if trim_rule is not None
        else comma_rules
    )

    try:
        json.loads(
            append_base
        )
    except json.JSONDecodeError as exc:
        if is_error_near_eof(
            append_base,
            exc,
        ):
            appended, append_rule = (
                append_missing_closers(
                    append_base
                )
            )

            if append_rule is not None:
                final_rules = (
                    list(append_rules)
                    + [append_rule]
                )

                parsed, append_error = (
                    json_loads_with_error(
                        appended
                    )
                )

                if parsed is not None:
                    return (
                        parsed,
                        "+".join(final_rules),
                        None,
                    )
            else:
                append_error = (
                    "delimiter structure is not safely "
                    "append-repairable"
                )
        else:
            append_error = (
                "parse error is not near EOF; "
                "automatic closer repair skipped"
            )
    else:
        # Should already have returned above, but keep this branch defensive.
        parsed = json.loads(
            append_base
        )
        return (
            parsed,
            "+".join(append_rules),
            None,
        )

    combined_error = (
        f"initial={error}; "
        f"after_trailing_commas={comma_error}; "
        f"after_trim={trim_error}; "
        f"append_attempt={append_error}"
    )

    return (
        None,
        None,
        combined_error,
    )


# ============================================================
# Output paths and writing
# ============================================================

def recovered_output_path(
    source_path: Path,
    raw_root: Path = RAW_DATA_DIR,
    recovered_root: Path = RECOVERED_DATA_DIR,
) -> Path:
    """
    Mirror the raw directory structure under data/recovered and convert
    *.invalid.txt to *.json.

    Examples:
        data/raw/wfa/2011/offensive_stats.invalid.txt
        -> data/recovered/wfa/2011/offensive_stats.json

        data/raw/wfa/2021/games/<id>.invalid.txt
        -> data/recovered/wfa/2021/games/<id>.json
    """
    relative = source_path.relative_to(
        raw_root
    )

    filename = relative.name.removesuffix(
        ".invalid.txt"
    ) + ".json"

    return (
        recovered_root
        / relative.parent
        / filename
    )


def write_recovered_json(
    parsed: Any,
    output_path: Path,
) -> int:
    """
    Serialize recovered data as canonical valid JSON.

    Returns output size in bytes.
    """
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    serialized = json.dumps(
        parsed,
        ensure_ascii=False,
        indent=2,
    ) + "\n"

    output_path.write_text(
        serialized,
        encoding="utf-8",
    )

    # Final safety check on what was actually written.
    json.loads(
        output_path.read_text(
            encoding="utf-8"
        )
    )

    return output_path.stat().st_size


# ============================================================
# Recovery pipeline
# ============================================================

def recover_file(
    source_path: Path,
    raw_root: Path = RAW_DATA_DIR,
    recovered_root: Path = RECOVERED_DATA_DIR,
) -> RecoveryResult:
    """
    Attempt recovery for one *.invalid.txt file.
    """
    metadata = infer_invalid_file_metadata(
        source_path,
        raw_root,
    )

    try:
        text = source_path.read_text(
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        return RecoveryResult(
            source_file=str(source_path),
            recovered_file=None,
            league=metadata["league"],
            season=metadata["season"],
            endpoint=metadata["endpoint"],
            resource_id=metadata["resource_id"],
            category="READ_ERROR",
            success=False,
            recovery_rule=None,
            parse_error=str(exc),
            source_size_bytes=0,
            output_size_bytes=None,
        )

    source_size = source_path.stat().st_size

    category = classify_recovery_candidate(
        text,
        metadata["endpoint"],
    )

    parsed: Any | None = None
    rule: str | None = None
    error: str | None = None

    if category == "PYTHON_LITERAL":
        parsed, rule, error = (
            recover_python_literal(
                text
            )
        )

    elif category == "MALFORMED_GAME_DATA":
        parsed, rule, error = (
            recover_malformed_game(
                text
            )
        )

    elif category == "MALFORMED_STANDINGS_DATA":
        parsed, rule, error = (
            recover_malformed_standings(
                text
            )
        )

    elif category == "VALID_JSON":
        # Do not duplicate a file that extraction marked invalid even though
        # it is already valid JSON. That condition should be reviewed in the
        # extraction pipeline instead.
        error = (
            "Source is already valid JSON. "
            "Review extraction logic rather than repairing it."
        )

    elif category == "EMPTY_PLAYER_STATS":
        error = (
            "HostedSports empty player-stat payload contains no "
            "recoverable player data."
        )

    else:
        error = (
            "No approved deterministic recovery rule "
            "for this response."
        )

    if parsed is None:
        return RecoveryResult(
            source_file=str(source_path),
            recovered_file=None,
            league=metadata["league"],
            season=metadata["season"],
            endpoint=metadata["endpoint"],
            resource_id=metadata["resource_id"],
            category=category,
            success=False,
            recovery_rule=rule,
            parse_error=error,
            source_size_bytes=source_size,
            output_size_bytes=None,
        )

    output_path = recovered_output_path(
        source_path,
        raw_root,
        recovered_root,
    )

    try:
        output_size = write_recovered_json(
            parsed,
            output_path,
        )
    except (
        OSError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        return RecoveryResult(
            source_file=str(source_path),
            recovered_file=None,
            league=metadata["league"],
            season=metadata["season"],
            endpoint=metadata["endpoint"],
            resource_id=metadata["resource_id"],
            category=category,
            success=False,
            recovery_rule=rule,
            parse_error=(
                f"Failed writing recovered JSON: {exc}"
            ),
            source_size_bytes=source_size,
            output_size_bytes=None,
        )

    return RecoveryResult(
        source_file=str(source_path),
        recovered_file=str(output_path),
        league=metadata["league"],
        season=metadata["season"],
        endpoint=metadata["endpoint"],
        resource_id=metadata["resource_id"],
        category=category,
        success=True,
        recovery_rule=rule,
        parse_error=None,
        source_size_bytes=source_size,
        output_size_bytes=output_size,
    )


def recover_all(
    raw_root: Path = RAW_DATA_DIR,
    recovered_root: Path = RECOVERED_DATA_DIR,
) -> list[RecoveryResult]:
    """
    Scan all invalid raw files and attempt only approved deterministic repairs.
    """
    results: list[RecoveryResult] = []

    files = sorted(
        raw_root.rglob(
            "*.invalid.txt"
        )
    )

    for index, path in enumerate(
        files,
        start=1,
    ):
        result = recover_file(
            path,
            raw_root,
            recovered_root,
        )
        results.append(
            result
        )

        if result.success:
            print(
                f"  ✓ {result.category:<28} "
                f"{path}"
            )

    return results


# ============================================================
# Recovery report
# ============================================================

REPORT_COLUMNS = [
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


def csv_escape(
    value: Any,
) -> str:
    """
    Minimal RFC-4180-compatible CSV escaping.
    """
    if value is None:
        text = ""
    elif isinstance(value, bool):
        text = (
            "true"
            if value
            else "false"
        )
    else:
        text = str(value)

    if any(
        character in text
        for character in [
            ",",
            '"',
            "\n",
            "\r",
        ]
    ):
        text = (
            '"'
            + text.replace(
                '"',
                '""',
            )
            + '"'
        )

    return text


def write_recovery_report(
    results: list[RecoveryResult],
    output_path: Path = RECOVERY_REPORT_PATH,
) -> Path:
    """
    Write the recovery audit CSV.
    """
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    lines = [
        ",".join(
            REPORT_COLUMNS
        )
    ]

    for result in results:
        record = asdict(
            result
        )

        lines.append(
            ",".join(
                csv_escape(
                    record[column]
                )
                for column in REPORT_COLUMNS
            )
        )

    output_path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    return output_path


# ============================================================
# Console summary
# ============================================================

def print_recovery_summary(
    results: list[RecoveryResult],
):
    """
    Print recovery counts grouped by category and outcome.
    """
    total = len(results)
    successful = sum(
        result.success
        for result in results
    )
    failed = total - successful

    print("\n" + "=" * 70)
    print("RECOVERY SUMMARY")
    print("=" * 70)

    print(
        f"Total invalid files scanned: {total:,}"
    )
    print(
        f"Successfully recovered:      {successful:,}"
    )
    print(
        f"Not recovered:               {failed:,}"
    )

    categories = sorted(
        {
            result.category
            for result in results
        }
    )

    print("\nBy category:")

    for category in categories:
        category_results = [
            result
            for result in results
            if result.category == category
        ]

        recovered = sum(
            result.success
            for result in category_results
        )

        print(
            f"  {category:<28} "
            f"{len(category_results):>6,} total | "
            f"{recovered:>6,} recovered | "
            f"{len(category_results) - recovered:>6,} unrecovered"
        )

    successful_rules: dict[str, int] = {}

    for result in results:
        if (
            result.success
            and result.recovery_rule
        ):
            successful_rules[
                result.recovery_rule
            ] = (
                successful_rules.get(
                    result.recovery_rule,
                    0,
                )
                + 1
            )

    if successful_rules:
        print(
            "\nSuccessful recovery rules:"
        )

        for rule, count in sorted(
            successful_rules.items(),
            key=lambda item: (
                -item[1],
                item[0],
            ),
        ):
            print(
                f"  {rule:<55} "
                f"{count:>6,}"
            )

    unrecovered_candidates = [
        result
        for result in results
        if (
            not result.success
            and result.category
            in {
                "PYTHON_LITERAL",
                "MALFORMED_GAME_DATA",
                "MALFORMED_STANDINGS_DATA",
            }
        )
    ]

    if unrecovered_candidates:
        print(
            "\nRecovery candidates still requiring review:"
        )

        for result in (
            unrecovered_candidates[:20]
        ):
            print(
                f"  ! {result.category:<28} "
                f"{result.source_file}"
            )
            if result.parse_error:
                print(
                    f"      {result.parse_error}"
                )

        if len(
            unrecovered_candidates
        ) > 20:
            print(
                f"  ... plus "
                f"{len(unrecovered_candidates) - 20:,} more"
            )


# ============================================================
# Main
# ============================================================

def main():
    print("\n" + "=" * 70)
    print("RECOVERING HOSTEDSPORTS RAW DATA")
    print("=" * 70)

    print(
        f"\nRaw source:       {RAW_DATA_DIR}"
    )
    print(
        f"Recovered output: {RECOVERED_DATA_DIR}"
    )

    print(
        "\nOriginal *.invalid.txt files will not be modified."
    )

    results = recover_all()

    report_path = write_recovery_report(
        results
    )

    print_recovery_summary(
        results
    )

    print(
        "\nRecovery audit written to:"
    )
    print(
        f"  {report_path}"
    )

    print(
        "\nRecovered JSON written under:"
    )
    print(
        f"  {RECOVERED_DATA_DIR}"
    )

    print(
        "\nNext step:"
    )
    print(
        "  Review recovery_report.csv, then update normalization only if "
        "recovered files should be included in the processed analytical layer."
    )


if __name__ == "__main__":
    main()