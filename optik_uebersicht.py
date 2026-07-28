#!/usr/bin/env python3
"""Build a structured Markdown overview from a harvested result file.

Groups every match as:

    Bildungsstufe  ->  Bundesland  ->  Klassenstufe  ->  Lehrplan  ->  Bereich

and lists the competencies and learning contents underneath.

    python optik_uebersicht.py optik_lehrplaene.json
    python optik_uebersicht.py optik_lehrplaene.json -o uebersicht.md --alle

Standalone by design: the file only needs the standard library and a result JSON,
so it can be copied next to any harvest output. That duplicates the word-boundary
check from ``mem_lehrplan/report.py``; the duplication is accepted deliberately in
exchange for the file being self-contained.

Two grouping keys are frequently absent from the source data -- several state
graphs assert neither Schulstufe nor Jahrgangsstufe. Both are therefore resolved
through a documented ladder (see ``resolve_schulstufe`` and
``resolve_klassenstufe``), and every heading states whether the value came from
the data or was derived from a curriculum title. The document ends with a
coverage table so its own reliability is visible.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

PRIMAR = "Primarstufe"
SEK_I = "Sekundarstufe I"
SEK_II = "Sekundarstufe II"
OHNE_STUFE = "Ohne Stufenzuordnung"
OHNE_KLASSE = "Ohne Klassenstufenangabe"

STUFEN_ORDER = [PRIMAR, SEK_I, SEK_II, OHNE_STUFE]

# Normalisation of the labels used in the ontology ("Sekundarbereich I") and in
# state curriculum titles ("Sekundarstufe II").
_STUFEN_LABELS = (
    (re.compile(r"primar|grundschul", re.I), PRIMAR),
    (re.compile(r"sekundar(bereich|stufe)?\s*(II|2)\b", re.I), SEK_II),
    (re.compile(r"sekundar(bereich|stufe)?\s*(I|1)\b", re.I), SEK_I),
)

# Curriculum titles that imply an educational level.
_TITEL_SEK_II = re.compile(
    r"oberstufe|sekundarstufe\s*(II|2)|leistungsfach|fachoberschule|berufliches\s+gymnasium|"
    r"gymnasiale\s+oberstufe|abitur",
    re.I,
)
_TITEL_SEK_I = re.compile(r"oberschule|mittelschule|realschule|hauptschule|f\u00f6rderschwerpunkt|sekundarstufe\s*(I|1)\b", re.I)
_TITEL_PRIMAR = re.compile(r"grundschule|primarstufe", re.I)

# Any standalone one- or two-digit number in range 1..13 counts as a grade.
# A pattern tied to ranges read "Physik 7-9/10" as 7 to 9 and lost the 10.
_GRADE = re.compile(r"\b(\d{1,2})\b")

# Word characters including German umlauts, for the compound boundary test.
_WORD = r"[\w\u00e4\u00f6\u00fc\u00c4\u00d6\u00dc\u00df]"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def labels(entries: list[dict]) -> list[str]:
    return [entry.get("label") or entry["uri"] for entry in entries]


def first_label(entries: list[dict]) -> str:
    found = labels(entries)
    return found[0] if found else ""


def is_noise(label: str, keywords: list[str]) -> bool:
    """True when every matching keyword sits buried inside a longer word.

    A match counts as genuine when the keyword touches a word boundary on either
    side. German compounds carry the topic word at either end -- "Lichtbrechung"
    at the front, "Wellenoptik" at the back -- and both are on topic. Only a
    keyword with word material on *both* sides is noise: "Licht" in
    "Wahlpflichtlernbereich", "Strahl" in "Waermestrahlung".
    """
    contained = [word for word in keywords if re.search(re.escape(word), label, re.I)]
    if not contained:
        return False
    return not any(
        re.search(rf"(?<!{_WORD}){re.escape(word)}|{re.escape(word)}(?!{_WORD})", label, re.I)
        for word in contained
    )


def _stufe_from_label(text: str) -> str | None:
    for pattern, name in _STUFEN_LABELS:
        if pattern.search(text):
            return name
    return None


def _stufe_from_grade(grade: int) -> str:
    if grade <= 4:
        return PRIMAR
    if grade <= 10:
        return SEK_I
    return SEK_II


def _grades_in(text: str) -> list[int]:
    """Grade numbers mentioned in a label or curriculum title."""
    return [int(match.group(1)) for match in _GRADE.finditer(text) if 1 <= int(match.group(1)) <= 13]


def resolve_schulstufe(node: dict, lehrplan: dict) -> tuple[str, str]:
    """Resolve the educational level, returning (name, provenance).

    Ladder, first hit wins:
      1. ``schulstufe`` asserted on the node or its Lehrplan
      2. derived from an asserted Jahrgangsstufe (1-4 / 5-10 / 11-13)
      3. derived from the curriculum title ("gymnasiale Oberstufe" -> Sek II)
      4. unresolved
    """
    for source, holder in (("Knoten", node), ("Lehrplan", lehrplan)):
        for label in labels(holder.get("stufen", {}).get("schulstufe", [])):
            name = _stufe_from_label(label)
            if name:
                return name, f"Daten ({source})"

    for holder in (node, lehrplan):
        for label in labels(holder.get("stufen", {}).get("jahrgangsstufe", [])):
            grades = _grades_in(label)
            if grades:
                return _stufe_from_grade(min(grades)), "abgeleitet aus Jahrgangsstufe"

    titel = lehrplan.get("label", "")
    if _TITEL_SEK_II.search(titel):
        return SEK_II, "abgeleitet aus Lehrplantitel"
    if _TITEL_PRIMAR.search(titel):
        return PRIMAR, "abgeleitet aus Lehrplantitel"
    if _TITEL_SEK_I.search(titel):
        return SEK_I, "abgeleitet aus Lehrplantitel"
    grades = _grades_in(titel)
    if grades:
        return _stufe_from_grade(min(grades)), "abgeleitet aus Lehrplantitel"
    return OHNE_STUFE, "nicht bestimmbar"


def resolve_klassenstufe(node: dict, lehrplan: dict) -> tuple[str, str]:
    """Resolve the grade level, returning (name, provenance).

    Ladder: asserted Jahrgangsstufe on the node, then on the Lehrplan, then a
    grade range parsed from the curriculum title, otherwise unresolved.
    """
    for source, holder in (("Knoten", node), ("Lehrplan", lehrplan)):
        found = labels(holder.get("stufen", {}).get("jahrgangsstufe", []))
        if found:
            return " / ".join(sorted(found)), f"Daten ({source})"

    grades = _grades_in(lehrplan.get("label", ""))
    if grades:
        low, high = min(grades), max(grades)
        name = f"Klassenstufe {low}" if low == high else f"Klassenstufen {low}\u2013{high}"
        return name, "abgeleitet aus Lehrplantitel"
    return OHNE_KLASSE, "nicht bestimmbar"


def sort_key_klassenstufe(name: str) -> tuple[int, str]:
    if name == OHNE_KLASSE:
        return (99, name)
    grades = _grades_in(name)
    return (min(grades) if grades else 98, name)


def build_tree(result: dict, include_noise: bool) -> tuple[dict, Counter]:
    """Nest matches as stufe -> land -> klassenstufe -> lehrplan -> bereich."""
    keywords = result["filter"]["stichwoerter"]
    tree: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(list)))))
    stats: Counter = Counter()

    for lehrplan in result["lehrplaene"]:
        land = first_label(lehrplan["bundesland"]) or "Ohne Bundesland"
        for node in lehrplan["treffer"]:
            stats["treffer_gesamt"] += 1
            if not include_noise and is_noise(node["label"], keywords):
                stats["ausgeschlossen"] += 1
                continue
            stufe, stufe_quelle = resolve_schulstufe(node, lehrplan)
            klasse, klasse_quelle = resolve_klassenstufe(node, lehrplan)
            stats[f"stufe:{stufe_quelle}"] += 1
            stats[f"klasse:{klasse_quelle}"] += 1
            stats["aufgenommen"] += 1
            bereich = first_label(node["eltern"]) or lehrplan["label"]
            tree[stufe][land][(klasse, klasse_quelle)][lehrplan["label"]][bereich].append(node)
    return tree, stats


def _role_marker(node: dict) -> str:
    mapping = {"themenbereich": "Themenbereich", "kompetenz": "Kompetenz", "inhalt": "Inhalt"}
    names = [mapping.get(role, role) for role in node["rollen"]]
    return " + ".join(names)


def _bereich_sections(bereiche: dict) -> list[str]:
    """Render the Bereich groups of one Lehrplan.

    A Themenbereich that heads its own group is not repeated as a bullet.
    """
    out: list[str] = []
    headers = set(bereiche)
    for bereich in sorted(bereiche):
        items = [
            node
            for node in bereiche[bereich]
            if not (node["label"] in headers and "themenbereich" in node["rollen"])
        ]
        if not items:
            continue
        out.append(f"**{bereich}**")
        out.append("")
        for node in sorted(items, key=lambda entry: entry["label"]):
            out.append(f"- {node['label']}  \n  *{_role_marker(node)}*")
        out.append("")
    return out


def render(result: dict, tree: dict, stats: Counter, include_noise: bool) -> str:
    out: list[str] = []
    add = out.append

    add("# Physik / Optik in den Lehrplänen der Bundesländer")
    add("")
    add("Themenbereiche, Kompetenzen und Inhalte aus dem MEM-Triplestore,")
    add("gegliedert nach Bildungsstufe, Bundesland und Klassenstufe.")
    add("")
    add(f"- Abruf: {result['abgerufen_am']}")
    add(f"- Endpoint: `{result['endpoint']}`")
    add(f"- Stichwörter: {', '.join(result['filter']['stichwoerter'])}")
    add(f"- Lehrpläne: {result['anzahl']['lehrplaene']}  ·  Treffer: {stats['treffer_gesamt']}")
    if not include_noise:
        add(
            f"- Aufgenommen: {stats['aufgenommen']}  ·  "
            f"Ausgeschlossen als Wortfragment-Treffer: {stats['ausgeschlossen']}"
        )
    add("")

    add("## Inhalt")
    add("")
    for stufe in STUFEN_ORDER:
        if stufe in tree:
            count = sum(
                len(nodes)
                for laender in tree[stufe].values()
                for klassen in laender.values()
                for bereiche in klassen.values()
                for nodes in bereiche.values()
            )
            anchor = stufe.lower().replace(" ", "-")
            add(f"- [{stufe}](#{anchor}) ({count} Einträge)")
    add("- [Datenlage](#datenlage)")
    add("")

    for stufe in STUFEN_ORDER:
        if stufe not in tree:
            continue
        add(f"## {stufe}")
        add("")
        for land in sorted(tree[stufe]):
            add(f"### {land}")
            add("")
            klassen = tree[stufe][land]
            for klasse, quelle in sorted(klassen, key=lambda item: sort_key_klassenstufe(item[0])):
                suffix = "" if quelle.startswith("Daten") else f" *({quelle})*"
                add(f"#### {klasse}{suffix}")
                add("")
                for lehrplan in sorted(klassen[(klasse, quelle)]):
                    add(f"*Lehrplan: {lehrplan}*")
                    add("")
                    out.extend(_bereich_sections(klassen[(klasse, quelle)][lehrplan]))

    add("## Datenlage")
    add("")
    add("Wie die beiden Gliederungsebenen zustande kamen:")
    add("")
    add("| Ebene | Herkunft | Einträge |")
    add("|---|---|---:|")
    for prefix, ebene in (("stufe:", "Bildungsstufe"), ("klasse:", "Klassenstufe")):
        for key in sorted(key for key in stats if key.startswith(prefix)):
            add(f"| {ebene} | {key.split(':', 1)[1]} | {stats[key]} |")
    add("")
    add('\u201eDaten\u201c bedeutet: im Triplestore als Jahrgangs- oder Schulstufe asserted.')
    add('\u201eAbgeleitet\u201c bedeutet: aus dem Lehrplantitel erschlossen \u2014 nachvollziehbar,')
    add("aber nicht durch die Quelldaten gedeckt. Bei Lehrplänen, die mehrere")
    add("Klassenstufen umfassen, ist die Zuordnung entsprechend grob.")
    add("")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="optik_uebersicht",
        description="Erzeugt aus einer Ergebnisdatei ein nach Bildungsstufe, Bundesland "
        "und Klassenstufe gegliedertes Markdown-Dokument.",
    )
    parser.add_argument("datei", type=Path, help="JSON-Datei aus mem_lehrplan.cli")
    parser.add_argument("-o", "--out", type=Path, default=Path("optik_uebersicht.md"), help="Ziel-Markdown")
    parser.add_argument(
        "--alle",
        action="store_true",
        help="Auch Treffer aufnehmen, in denen das Stichwort nur wortintern vorkommt "
        "(z. B. 'Licht' in 'Wahlpflichtbereich')",
    )
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    try:
        result = load(args.datei)
    except FileNotFoundError:
        print(f"Datei nicht gefunden: {args.datei}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as error:
        print(f"Keine gueltige JSON-Datei: {error}", file=sys.stderr)
        return 2

    tree, stats = build_tree(result, include_noise=args.alle)
    args.out.write_text(render(result, tree, stats, include_noise=args.alle), encoding="utf-8")

    print(f"{stats['aufgenommen']} von {stats['treffer_gesamt']} Treffern aufgenommen -> {args.out}")
    if stats["ausgeschlossen"]:
        print(f"{stats['ausgeschlossen']} als Wortfragment-Treffer ausgeschlossen (--alle nimmt sie mit auf)")
    unklar = stats["stufe:nicht bestimmbar"]
    if unklar:
        print(f"Hinweis: {unklar} Eintraege ohne bestimmbare Bildungsstufe")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
