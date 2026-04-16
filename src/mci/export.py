"""
mci.export

Handles writing parsed records to CSV and JSON.
"""

import csv
import json
import logging

LOGGER = logging.getLogger(__name__)


def _safe_str(value) -> str:
    """Convert any field value to a clean string for output."""
    if isinstance(value, bytes):
        return value.decode("latin-1")
    return str(value) if value is not None else ""


def _filter_record(record: dict, fields: list[str]) -> dict:
    """Return a dict containing only the keys listed in fields."""
    return {f: _safe_str(record.get(f, "")) for f in fields}


# def to_csv(path: str, records: list[dict], fields: list[str]) -> None:
#     """
#     Write records to a pipe-delimited CSV file.

#     :param path:    Output file path.
#     :param records: List of parsed record dicts.
#     :param fields:  Ordered list of field names to include as columns.
#     """
#     if not records:
#         LOGGER.warning("No records to write to %s", path)
#         return

#     rows = [_filter_record(r, fields) for r in records if r]

#     with open(path, "w", newline="", encoding="utf-8") as f:
#         writer = csv.DictWriter(
#             f,
#             fieldnames=fields,
#             delimiter="|",
#             extrasaction="ignore",
#             lineterminator="\n",
#         )
#         writer.writeheader()
#         writer.writerows(rows)

#     LOGGER.info("%d records written to %s", len(rows), path)


def to_csv(path: str, records: list[dict], fields: list[str] | None = None) -> None:
    if not records:
        return

    # If config fields exist → use them (ORDERED)
    if fields:
        all_fields = fields
    else:
        # fallback: auto-discover
        all_fields = sorted({k for r in records for k in r.keys()})

    rows = []
    for r in records:
        rows.append({k: _safe_str(r.get(k, "")) for k in all_fields})

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=all_fields,
            delimiter=",",
            extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(rows)
def to_json(path: str, records: list[dict]) -> None:
    """
    Write records to a JSON file.

    :param path:    Output file path.
    :param records: List of parsed record dicts.
    """
    safe_records = [
        {k: _safe_str(v) for k, v in r.items()}
        for r in records
        if r
    ]

    with open(path, "w", encoding="utf-8") as f:
        json.dump(safe_records, f, indent=2, default=str)

    LOGGER.info("%d records written to %s", len(safe_records), path)