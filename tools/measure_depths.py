#!/usr/bin/env python3
"""Re-measure the path-length bounds declared in ``mem_lehrplan.vocab``.

The queries replace SPARQL transitive paths with bounded UNIONs because Virtuoso
runs out of transitive temp memory otherwise. Those bounds must stay above the
real depth of the ontology, so re-run this after an ontology update:

    curl -O https://raw.githubusercontent.com/FWU-DE/lehrplan-ontologie/main/lp-full.ttl
    python tools/measure_depths.py lp-full.ttl

Parses Turtle with a regex rather than rdflib on purpose: only named
``rdfs:subClassOf`` edges between LP_* terms matter here, and this keeps the tool
dependency-free.
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict, deque

ROOTS = {
    "LP_0000438": "Lehrplan",
    "LP_0000349": "CE-Bereich",
    "LP_0000263": "CE-Kompetenzspezifikation",
    "LP_0000332": "CE-Lerninhalt",
}

BLOCK = re.compile(r"\n###\s+https://w3id\.org/lehrplan/ontology/(LP_\d+)\n(.*?)(?=\n###\s|\Z)", re.S)
SUBCLASS_SECTION = re.compile(r"rdfs:subClassOf(.*?)(?:;\s*rdfs:label|;\s*rdfs:comment|;\s*skos:|\.\s*$)", re.S)
INTERSECTION = re.compile(r"rdfs:subClassOf \[ owl:intersectionOf \((.*?)\)\s*;", re.S)


def subclass_children(text: str) -> dict[str, set[str]]:
    children: dict[str, set[str]] = defaultdict(set)
    for match in BLOCK.finditer(text):
        child, body = match.group(1), match.group(2)
        section = SUBCLASS_SECTION.search(body)
        if not section:
            continue
        for parent in re.findall(r"ontology:(LP_\d+)", section.group(1)):
            children[parent].add(child)
    return children


def max_depth(children: dict[str, set[str]], root: str) -> tuple[int, int]:
    """Return (number of sub-classes, maximum depth) below ``root``."""
    seen = {root: 0}
    queue = deque([root])
    while queue:
        node = queue.popleft()
        for child in children.get(node, ()):
            if child not in seen:
                seen[child] = seen[node] + 1
                queue.append(child)
    return len(seen) - 1, max(seen.values())


def max_list_length(text: str) -> int:
    lengths = [
        len(re.findall(r"ontology:LP_\d+|rdf:type owl:Restriction", match.group(1)))
        for match in INTERSECTION.finditer(text)
    ]
    return max(lengths) if lengths else 0


def main(path: str) -> int:
    text = open(path, encoding="utf-8").read()
    children = subclass_children(text)
    print(f"{'class':32} {'sub-classes':>12} {'max depth':>10}")
    for iri, label in ROOTS.items():
        count, depth = max_depth(children, iri)
        print(f"{label + ' ' + iri:32} {count:12d} {depth:10d}")
    print(f"\nlongest owl:intersectionOf list: {max_list_length(text)} members")
    print("\nBounds in vocab.py must be >= these values.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
