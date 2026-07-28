"""Writers for the harvested result.

JSON keeps the full nesting; the CSV flattens to one row per matched node so the
level information sits next to each topic area and competency in a spreadsheet.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .vocab import STUFEN_PROPERTIES

CSV_COLUMNS = (
    "bundesland",
    "schulart",
    "schulfach",
    "lehrplan",
    *STUFEN_PROPERTIES,
    "stufen_quelle",
    "rollen",
    "klasse",
    "eltern",
    "knoten",
    "knoten_uri",
    "lehrplan_uri",
)


def write_json(result: dict, path: Path) -> None:
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def _labels(entries: list[dict[str, str]]) -> str:
    return " | ".join(entry.get("label") or entry["uri"] for entry in entries)


def flatten(result: dict) -> list[dict[str, str]]:
    rows = []
    for lehrplan in result["lehrplaene"]:
        for node in lehrplan["treffer"]:
            row = {
                "bundesland": _labels(lehrplan["bundesland"]),
                "schulart": _labels(lehrplan["schulart"]),
                "schulfach": _labels(lehrplan["schulfach"]),
                "lehrplan": lehrplan["label"],
                "stufen_quelle": node["stufen_quelle"],
                "rollen": "+".join(node["rollen"]),
                "klasse": _labels(node["klassen"]),
                "eltern": _labels(node["eltern"]),
                "knoten": node["label"],
                "knoten_uri": node["uri"],
                "lehrplan_uri": lehrplan["uri"],
            }
            for name in STUFEN_PROPERTIES:
                row[name] = _labels(node["stufen"].get(name, []))
            rows.append(row)
    return rows


def write_csv(result: dict, path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CSV_COLUMNS), delimiter=";")
        writer.writeheader()
        writer.writerows(flatten(result))
