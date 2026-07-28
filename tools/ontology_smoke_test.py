#!/usr/bin/env python3
"""Run the full pipeline against a local graph instead of the MEM endpoint.

Loads the real ontology (lp-full.ttl) plus a handful of synthetic state-data
triples and executes the actual query templates through rdflib. This verifies
the parts that string-matching tests cannot: that the subClassOf* walk finds
Lehrpläne, and that the role classification matches the ontology's real OWL
axioms rather than an assumed shape.

Requires rdflib and a local copy of the ontology:

    pip install rdflib
    curl -O https://raw.githubusercontent.com/FWU-DE/lehrplan-ontologie/main/lp-full.ttl
    python tools/ontology_smoke_test.py lp-full.ttl

Note: rdflib evaluates SPARQL without reasoning, exactly like the Virtuoso
endpoint, so a pass here is meaningful. It is not a substitute for a real run --
only live data can confirm which properties the state graphs actually assert.
"""

from __future__ import annotations

import sys
from pathlib import Path

from rdflib import Graph

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mem_lehrplan.fetch import harvest  # noqa: E402

# Two encodings side by side. ex:522 uses the specific sub-properties
# (LP_0000026 / LP_0000047); ex:900 mirrors what the live endpoint actually
# returned: the generic super-property LP_0000024, where only the object's
# rdf:type reveals that it is a Jahrgangsstufe, a Niveaustufe, or -- via a
# sub-class of Bildungsgangniveau -- a level at all.
#
# Mirrors the Sachsen pattern: the Lehrplan over-asserts BFO_0000051 to every
# descendant (lp522 -> k1 as well as lb2 -> k1), which is what the real graphs do.
SYNTHETIC_DATA = """
@prefix lp:   <https://w3id.org/lehrplan/ontology/> .
@prefix obo:  <http://purl.obolibrary.org/obo/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix ex:   <https://lp-sachsen.org/resource/> .

ex:522 a lp:LP_0000818 ;
    rdfs:label "Physik Oberschule (SN)" ;
    lp:LP_0000537 ex:fach-physik ;
    lp:LP_0000029 ex:sachsen ;
    lp:LP_0000047 ex:sek1 ;
    obo:BFO_0000051 ex:7052, ex:7053, ex:9001 .

ex:7052 a lp:LP_0002113 ;
    rdfs:label "Lernbereich 2: Optik" ;
    obo:BFO_0000051 ex:7053 .

ex:7053 a lp:LP_0002115 ;
    rdfs:label "Lichtbrechung an Linsen und Prismen" ;
    lp:LP_0000026 ex:ks7 .

ex:9001 a lp:LP_0002113 ;
    rdfs:label "Lernbereich 3: Elektrizitaet" .

ex:900 a lp:LP_0000818 ;
    rdfs:label "Physik Sek I (Stil Berlin)" ;
    lp:LP_0000537 ex:fach-physik ;
    lp:LP_0000029 ex:sachsen ;
    lp:LP_0000024 ex:jgs8, ex:niveauC, ex:gymSek1 ;
    obo:BFO_0000051 ex:901 .

ex:901 a lp:LP_0002113 ;
    rdfs:label "Themenfeld: Optik und Licht" .

ex:jgs8    a lp:LP_0000009 ; rdfs:label "Jahrgangsstufe 8"@de .
ex:niveauC a lp:LP_0000443 ; rdfs:label "Niveaustufe C"@de .
ex:gymSek1 a lp:LP_0000069 ; rdfs:label "Gymnasialniveau Sek I"@de .

ex:fach-physik rdfs:label "Physik"@de .
ex:sachsen     rdfs:label "Sachsen"@de .
ex:sek1        rdfs:label "Sekundarbereich I"@de .
ex:ks7         rdfs:label "Klassenstufe 7"@de .
"""


class LocalClient:
    """SparqlClient-compatible facade over an in-memory rdflib graph."""

    endpoint = "local://rdflib"

    def __init__(self, graph: Graph) -> None:
        self.graph = graph

    def select(self, query: str) -> list[dict[str, str]]:
        result = self.graph.query(query)
        rows = []
        for row in result:
            rows.append(
                {str(var): str(row[var]) for var in result.vars if row[var] is not None}
            )
        return rows


def main(ontology_path: str) -> int:
    graph = Graph()
    print(f"loading {ontology_path} ...")
    graph.parse(ontology_path, format="turtle")
    graph.parse(data=SYNTHETIC_DATA, format="turtle")
    print(f"{len(graph)} triples")

    result = harvest(LocalClient(graph), fach="physik", stichwoerter=["Optik", "Licht", "Prisma"])

    failures = []

    def check(label: str, actual, expected) -> None:
        status = "ok  " if actual == expected else "FAIL"
        print(f"  [{status}] {label}: {actual!r}")
        if actual != expected:
            failures.append(f"{label}: expected {expected!r}, got {actual!r}")

    print("\nassertions:")
    check("Lehrplaene gefunden", result["anzahl"]["lehrplaene"], 2)
    by_label = {entry["label"]: entry for entry in result["lehrplaene"]}
    lehrplan = by_label["Physik Oberschule (SN)"]
    check("Bundesland", [entry["label"] for entry in lehrplan["bundesland"]], ["Sachsen"])
    check(
        "Schulstufe des Lehrplans",
        [entry["label"] for entry in lehrplan["stufen"].get("schulstufe", [])],
        ["Sekundarbereich I"],
    )
    # "Lernbereich 3: Elektrizitaet" must not match the optics keywords.
    check("Treffer (nur Optik)", result["anzahl"]["treffer"], 3)

    generic = by_label["Physik Sek I (Stil Berlin)"]
    stufen = generic["stufen"]
    check(
        "Jahrgangsstufe via LP_0000024",
        [entry["label"] for entry in stufen.get("jahrgangsstufe", [])],
        ["Jahrgangsstufe 8"],
    )
    check(
        "Niveaustufe via LP_0000024",
        [entry["label"] for entry in stufen.get("niveaustufe", [])],
        ["Niveaustufe C"],
    )
    check(
        "Bildungsgangniveau via Unterklasse",
        [entry["label"] for entry in stufen.get("bildungsgangniveau", [])],
        ["Gymnasialniveau Sek I"],
    )
    check("Erbt Stufen an den Knoten", generic["treffer"][0]["stufen_quelle"], "lehrplan")

    nodes = {node["label"]: node for node in lehrplan["treffer"]}
    check("Rolle Lernbereich", nodes["Lernbereich 2: Optik"]["rollen"], ["themenbereich"])
    check(
        "Rolle Kompetenz/Inhalt",
        nodes["Lichtbrechung an Linsen und Prismen"]["rollen"],
        ["kompetenz", "inhalt"],
    )
    kompetenz = nodes["Lichtbrechung an Linsen und Prismen"]
    check(
        "Jahrgangsstufe am Knoten",
        [entry["label"] for entry in kompetenz["stufen"].get("jahrgangsstufe", [])],
        ["Klassenstufe 7"],
    )
    check("Stufen-Quelle Knoten", kompetenz["stufen_quelle"], "knoten")
    check("Stufen-Quelle Lernbereich", nodes["Lernbereich 2: Optik"]["stufen_quelle"], "lehrplan")
    # The Lehrplan is also an asserted has-part parent; only the true parent may survive.
    check("direkter Elternknoten", [entry["label"] for entry in kompetenz["eltern"]], ["Lernbereich 2: Optik"])

    print("\nFAILED" if failures else "\nALL CHECKS PASSED")
    for failure in failures:
        print(f"  - {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
