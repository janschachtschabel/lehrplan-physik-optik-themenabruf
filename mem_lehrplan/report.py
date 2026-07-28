"""Evaluate a harvested result file.

Answers the questions that matter after a run: how much was found per state,
whether the educational levels actually arrived, how precise the keyword filter
was, and which node classes could not be classified.

Pure analysis over the JSON -- no endpoint access, so it can be re-run freely on
an existing file.

    python -m mem_lehrplan.report optik_lehrplaene.json
    python -m mem_lehrplan.report optik_lehrplaene.json --md bericht.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from .vocab import STUFEN_PROPERTIES

SAMPLE_COUNT = 3


def _labels(entries: list[dict[str, str]]) -> str:
    return " | ".join(entry.get("label") or entry["uri"] for entry in entries) or "-"


def _nodes(result: dict):
    """Yield (lehrplan, node) for every match."""
    for lehrplan in result["lehrplaene"]:
        for node in lehrplan["treffer"]:
            yield lehrplan, node


def per_bundesland(result: dict) -> list[tuple[str, int, int]]:
    curricula: Counter = Counter()
    matches: Counter = Counter()
    for lehrplan in result["lehrplaene"]:
        land = _labels(lehrplan["bundesland"])
        curricula[land] += 1
        matches[land] += len(lehrplan["treffer"])
    return [(land, curricula[land], matches[land]) for land in sorted(curricula)]


def role_counts(result: dict) -> Counter:
    return Counter("+".join(node["rollen"]) for _, node in _nodes(result))


def level_coverage(result: dict) -> tuple[Counter, Counter]:
    """Return (matches by level source, matches by level kind)."""
    sources: Counter = Counter()
    kinds: Counter = Counter()
    for _, node in _nodes(result):
        sources[node["stufen_quelle"]] += 1
        for kind in STUFEN_PROPERTIES:
            if node["stufen"].get(kind):
                kinds[kind] += 1
    return sources, kinds


def keyword_precision(result: dict) -> list[tuple[str, int, list[str]]]:
    """Per keyword: how many labels it matched, plus sample labels.

    Recomputed client-side with the same case-insensitive substring semantics as
    the SPARQL filter. Substring matching has no word boundary, so this is where
    false positives become visible -- "Licht" also matches "Pflicht".
    """
    keywords = result["filter"]["stichwoerter"]
    labels = [node["label"] for _, node in _nodes(result)]
    report = []
    for keyword in keywords:
        pattern = re.compile(re.escape(keyword), re.IGNORECASE)
        hits = [label for label in labels if pattern.search(label)]
        report.append((keyword, len(hits), hits[:SAMPLE_COUNT]))
    return sorted(report, key=lambda item: -item[1])


def unmatched_keywords(result: dict) -> list[str]:
    return [keyword for keyword, count, _ in keyword_precision(result) if count == 0]


def suspicious_matches(result: dict) -> list[tuple[str, str]]:
    """Matches that no keyword explains as a standalone word.

    A label is flagged when every keyword it contains is buried inside a longer
    word, touching no word boundary on either side -- e.g. "Licht" in
    "Wahlpflichtlernbereich". Compounds carrying the keyword at either end
    ("Lichtbrechung", "Wellenoptik") are on topic and stay unflagged. Heuristic,
    meant for review rather than automatic removal.
    """
    keywords = result["filter"]["stichwoerter"]
    word = r"[\w\u00e4\u00f6\u00fc\u00c4\u00d6\u00dc\u00df]"
    plain = {k: re.compile(re.escape(k), re.IGNORECASE) for k in keywords}
    touching = {
        k: re.compile(rf"(?<!{word}){re.escape(k)}|{re.escape(k)}(?!{word})", re.IGNORECASE) for k in keywords
    }
    flagged = []
    for lehrplan, node in _nodes(result):
        label = node["label"]
        contained = [k for k in keywords if plain[k].search(label)]
        if contained and not any(touching[k].search(label) for k in contained):
            flagged.append((lehrplan["label"], label))
    return flagged


def class_usage(result: dict) -> Counter:
    counter: Counter = Counter()
    for _, node in _nodes(result):
        for entry in node["klassen"]:
            counter[entry.get("label") or entry["uri"]] += 1
    return counter


def unclassified_classes(result: dict) -> Counter:
    """Node classes whose role could not be derived, by frequency."""
    unknown = set(result["diagnostik"].get("klassen_ohne_rolle", []))
    counter: Counter = Counter()
    for _, node in _nodes(result):
        for entry in node["klassen"]:
            if entry["uri"] in unknown:
                counter[entry.get("label") or entry["uri"]] += 1
    return counter


def top_lehrplaene(result: dict, limit: int) -> list[tuple[str, str, int]]:
    ranked = [
        (_labels(lehrplan["bundesland"]), lehrplan["label"], len(lehrplan["treffer"]))
        for lehrplan in result["lehrplaene"]
    ]
    return sorted(ranked, key=lambda item: -item[2])[:limit]


def samples(result: dict, limit: int) -> list[dict[str, str]]:
    rows = []
    for lehrplan, node in _nodes(result):
        if node["rollen"] == ["kompetenz"] or "kompetenz" in node["rollen"]:
            rows.append(
                {
                    "land": _labels(lehrplan["bundesland"]),
                    "stufe": " ".join(
                        _labels(node["stufen"][kind]) for kind in STUFEN_PROPERTIES if node["stufen"].get(kind)
                    )
                    or "-",
                    "eltern": _labels(node["eltern"]),
                    "knoten": node["label"],
                }
            )
        if len(rows) >= limit:
            break
    return rows


def render(result: dict, top: int) -> str:
    out: list[str] = []
    add = out.append

    def section(title: str) -> None:
        add("")
        add(title)
        add("-" * len(title))

    counts = result["anzahl"]
    add(f"MEM-Optik Auswertung   abgerufen {result['abgerufen_am']}")
    add(f"Endpoint: {result['endpoint']}")
    add(f"Filter:   Fach='{result['filter']['fach']}'  Bundesland={result['filter']['bundesland']}")
    add(f"Gesamt:   {counts['lehrplaene']} Lehrplaene, {counts['treffer']} Treffer")

    section("Nach Bundesland")
    add(f"{'Bundesland':<28}{'Lehrplaene':>11}{'Treffer':>9}")
    for land, curricula, matches in per_bundesland(result):
        add(f"{land[:27]:<28}{curricula:>11}{matches:>9}")

    section("Rollenverteilung")
    total = max(counts["treffer"], 1)
    for role, count in role_counts(result).most_common():
        add(f"{role:<28}{count:>11}{100 * count / total:>8.1f}%")

    section("Bildungsstufen-Abdeckung")
    sources, kinds = level_coverage(result)
    for source in ("knoten", "lehrplan", "keine"):
        count = sources.get(source, 0)
        add(f"Quelle {source:<21}{count:>11}{100 * count / total:>8.1f}%")
    if kinds:
        add("")
        for kind, count in kinds.most_common():
            add(f"  {kind:<26}{count:>11}")
    else:
        add("")
        add("  KEINE Stufen gefunden - siehe diagnostik.lehrplan_praedikate")

    section("Stichwort-Praezision")
    add(f"{'Stichwort':<20}{'Treffer':>8}  Beispiele")
    for keyword, count, examples in keyword_precision(result):
        joined = " / ".join(example[:38] for example in examples) if examples else ""
        add(f"{keyword:<20}{count:>8}  {joined}")
    leer = unmatched_keywords(result)
    if leer:
        add("")
        add(f"ohne Treffer: {', '.join(leer)}")

    flagged = suspicious_matches(result)
    section("Verdaechtige Treffer (Stichwort nur wortintern)")
    if flagged:
        add(f"{len(flagged)} Treffer, in denen kein Stichwort als Wortanfang vorkommt:")
        for lehrplan, label in flagged[:top]:
            add(f"  [{lehrplan[:24]:<24}] {label[:70]}")
        if len(flagged) > top:
            add(f"  ... und {len(flagged) - top} weitere")
    else:
        add("keine")

    section("Knotenklassen")
    for label, count in class_usage(result).most_common(top):
        add(f"{label[:44]:<46}{count:>8}")
    unknown = unclassified_classes(result)
    if unknown:
        add("")
        add("ohne erkennbare Rolle:")
        for label, count in unknown.most_common():
            add(f"  {label[:42]:<44}{count:>8}")

    section(f"Top {top} Lehrplaene nach Treffern")
    for land, label, count in top_lehrplaene(result, top):
        add(f"{count:>6}  [{land[:20]:<20}] {label[:52]}")

    section("Beispiel-Kompetenzen")
    for row in samples(result, SAMPLE_COUNT * 2):
        add(f"  {row['land'][:14]:<15}{row['stufe'][:18]:<19}{row['knoten'][:56]}")
        add(f"  {'':<15}{'in:':<19}{row['eltern'][:56]}")

    add("")
    return "\n".join(out)


def render_markdown(result: dict, top: int) -> str:
    return "# MEM-Optik Auswertung\n\n```\n" + render(result, top) + "\n```\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mem-optik-report", description="Wertet eine Ergebnisdatei von mem_lehrplan.cli aus."
    )
    parser.add_argument("datei", type=Path, help="JSON-Datei aus dem Abruf")
    parser.add_argument("--top", type=int, default=10, help="Laenge der Ranglisten (Default: 10)")
    parser.add_argument("--md", type=Path, help="Bericht zusaetzlich als Markdown speichern")
    args = parser.parse_args(argv)

    # Windows consoles are not always UTF-8; curriculum labels contain umlauts.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    try:
        result = json.loads(args.datei.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"Datei nicht gefunden: {args.datei}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as error:
        print(f"Keine gueltige JSON-Datei: {error}", file=sys.stderr)
        return 2

    print(render(result, args.top))
    if args.md:
        args.md.write_text(render_markdown(result, args.top), encoding="utf-8")
        print(f"Markdown geschrieben: {args.md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
