"""
mci.export

Handles writing parsed records to CSV and JSON.

Important:
- Parsing must preserve every digit exactly.
- Leading-zero cleanup is applied only during CSV export.
- Only approved numeric amount/rate fields should have leading zeros removed.
"""

import csv
import json
import logging
from decimal import Decimal
from typing import Any

LOGGER = logging.getLogger(__name__)



DEFAULT_ZERO_STRIP_FIELDS = {
    "DE4",   
    "DE5",   
    "DE6",   
    "DE9",   
    "DE10",  
}


def _safe_str(value: Any) -> str:
    """
    Convert any field value to a clean string for output.

    This does not remove leading zeros.
    Leading-zero cleanup is handled separately and only for approved fields.
    """
    if value is None:
        return ""

    if isinstance(value, bytes):
        return value.decode("latin-1")

    if isinstance(value, Decimal):
        return format(value, "f")

    if isinstance(value, (list, tuple, set)):
        return json.dumps([_safe_str(v) for v in value], ensure_ascii=False)

    if isinstance(value, dict):
        return json.dumps(
            {str(k): _safe_str(v) for k, v in value.items()},
            ensure_ascii=False,
        )

    return str(value)


def _strip_leading_zeros(value: str) -> str:
    """
    Remove leading zeros from a numeric-looking CSV value.

    Examples:
        "000000001234" -> "1234"
        "000000000000" -> "0"
        ""             -> ""
    """
    value = value.strip()

    if value == "":
        return ""

    sign = ""
    if value[0] in {"+", "-"}:
        sign = value[0]
        value = value[1:]

    stripped = value.lstrip("0")

    if stripped == "":
        stripped = "0"

    return sign + stripped


def _format_csv_value(
    field_name: str,
    value: Any,
    zero_strip_fields: set[str],
) -> str:
    """
    Format one field for CSV output.

    Do not strip zeros globally. Some numeric-looking fields are IDs,
    codes, PAN-related values, trace numbers, dates, or references.
    """
    text = _safe_str(value)

    if field_name in zero_strip_fields:
        return _strip_leading_zeros(text)

    return text


def _expand_de30(row: dict[str, str]) -> None:
    """
    Expand DE30 safely.

    DE30 is usually 24 digits:
    - first 12 digits  = original transaction amount
    - second 12 digits = original reconciliation amount

    Do not strip DE30 as one whole value because that destroys
    the internal 12+12 structure.
    """
    de30 = row.get("DE30", "")

    if not de30:
        return

    if len(de30) != 24 or not de30.isdigit():
        LOGGER.warning(
            "DE30 not expanded because expected 24 digits, got len=%d value=%r",
            len(de30),
            de30,
        )
        return

    row["DE30_ORIGINAL_TRANSACTION_AMOUNT"] = _strip_leading_zeros(de30[:12])
    row["DE30_ORIGINAL_RECONCILIATION_AMOUNT"] = _strip_leading_zeros(de30[12:24])


def _filter_record(
    record: dict,
    fields: list[str],
    zero_strip_fields: set[str],
) -> dict[str, str]:
    """
    Return a CSV-ready dict containing only the listed fields.

    This function keeps column order controlled by `fields`.
    """
    row: dict[str, str] = {}

    for field_name in fields:
        if field_name.startswith("DE30_ORIGINAL_"):
            continue

        row[field_name] = _format_csv_value(
            field_name,
            record.get(field_name, ""),
            zero_strip_fields,
        )

    _expand_de30(row)

    return {field: row.get(field, "") for field in fields}


def to_csv(
    path: str,
    records: list[dict],
    fields: list[str] | None = None,
    zero_strip_fields: set[str] | None = None,
    delimiter: str = ",",
    include_de30_expansion: bool = True,
) -> None:
    """
    Write records to a delimited CSV file.

    :param path: Output file path.
    :param records: List of parsed record dicts.
    :param fields: Ordered list of field names to include as columns.
    :param zero_strip_fields: Fields where leading zeros should be removed.
    :param delimiter: Default is pipe `|` for safer Arbutus-style import.
    :param include_de30_expansion: Adds derived DE30 amount columns if DE30 exists.
    """
    if not records:
        LOGGER.warning("No records to write to %s", path)
        return

    zero_strip_fields = zero_strip_fields or DEFAULT_ZERO_STRIP_FIELDS

    valid_records = [record for record in records if record]

    if not valid_records:
        LOGGER.warning("No valid records to write to %s", path)
        return

    if fields:
        all_fields = list(fields)
    else:
        all_fields = sorted({key for record in valid_records for key in record.keys()})

    if include_de30_expansion and "DE30" in all_fields:
        derived_fields = [
            "DE30_ORIGINAL_TRANSACTION_AMOUNT",
            "DE30_ORIGINAL_RECONCILIATION_AMOUNT",
        ]

        for field_name in derived_fields:
            if field_name not in all_fields:
                all_fields.append(field_name)

    rows = [
        _filter_record(record, all_fields, zero_strip_fields)
        for record in valid_records
    ]

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=all_fields,
            delimiter=delimiter,
            extrasaction="ignore",
            lineterminator="\n",
            quoting=csv.QUOTE_MINIMAL,
        )
        writer.writeheader()
        writer.writerows(rows)

    LOGGER.info("%d records written to %s", len(rows), path)


def to_json(path: str, records: list[dict]) -> None:
    """
    Write records to a JSON file.

    JSON output keeps values safe-stringified, but does not apply
    CSV-specific leading-zero cleanup.
    """
    safe_records = [
        {k: _safe_str(v) for k, v in record.items()}
        for record in records
        if record
    ]

    if not safe_records:
        LOGGER.warning("No records to write to %s", path)
        return

    with open(path, "w", encoding="utf-8") as f:
        json.dump(safe_records, f, indent=2, ensure_ascii=False, default=str)

    LOGGER.info("%d records written to %s", len(safe_records), path)