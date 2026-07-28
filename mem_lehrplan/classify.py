"""Derive the didactic role of a curriculum node from its class.

The MEM ontology does not label nodes as "topic area" or "competency" directly.
It encodes the role twice over, and both encodings are needed because the
endpoint does no OWL reasoning:

1. ``LP_0000483`` ("has function specification") pinned via ``owl:hasValue``
   inside an anonymous intersection class -- used by competency and content
   classes such as "Kompetenzerwartung (BY)" or "Kompetenz (RP)".
2. A plain ``rdfs:subClassOf`` chain up to a CE core class -- used by
   structuring classes such as "Lernbereich (SN)" or "Themenfeld (BB)".

A class can carry more than one function; "Lernziel und Lerninhalt (SN)" is
both competency and content. Roles are therefore a set, rendered in a fixed
order so output is stable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .vocab import (
    CLASS_CE_BEREICH,
    CLASS_CE_INHALT,
    CLASS_CE_KOMPETENZ,
    FUNKTION_BEREICH,
    FUNKTION_INHALT,
    FUNKTION_KOMPETENZ,
    ONTOLOGY,
)

ROLE_THEMENBEREICH = "themenbereich"
ROLE_KOMPETENZ = "kompetenz"
ROLE_INHALT = "inhalt"
ROLE_UNBEKANNT = "unbekannt"

ROLE_ORDER = (ROLE_THEMENBEREICH, ROLE_KOMPETENZ, ROLE_INHALT)

_FUNCTION_ROLES = {
    FUNKTION_BEREICH: ROLE_THEMENBEREICH,
    FUNKTION_KOMPETENZ: ROLE_KOMPETENZ,
    FUNKTION_INHALT: ROLE_INHALT,
}

# The vocab constants are prefixed ("lp:LP_...") for query building; the
# endpoint returns full IRIs, so expand them here.
_CE_ROLES = {
    ONTOLOGY + CLASS_CE_BEREICH.removeprefix("lp:"): ROLE_THEMENBEREICH,
    ONTOLOGY + CLASS_CE_KOMPETENZ.removeprefix("lp:"): ROLE_KOMPETENZ,
    ONTOLOGY + CLASS_CE_INHALT.removeprefix("lp:"): ROLE_INHALT,
}


@dataclass
class ClassInfo:
    """What is known about one node class."""

    uri: str
    label: str = ""
    funktionen: set[str] = field(default_factory=set)
    ce_superclasses: set[str] = field(default_factory=set)

    @property
    def rollen(self) -> list[str]:
        """Roles of this class, in fixed order; empty means unknown."""
        roles = {_FUNCTION_ROLES[f] for f in self.funktionen if f in _FUNCTION_ROLES}
        roles |= {_CE_ROLES[c] for c in self.ce_superclasses if c in _CE_ROLES}
        return [role for role in ROLE_ORDER if role in roles]


def build_class_index(rows: list[dict[str, str]]) -> dict[str, ClassInfo]:
    """Fold the result of :func:`queries.class_roles` into one entry per class.

    A node may be typed with a CE core class directly. That zero-length case
    cannot be a branch of the query's sub-class UNION -- a UNION branch cannot
    reference variables bound outside it -- so it is resolved here.
    """
    index: dict[str, ClassInfo] = {}
    for row in rows:
        uri = row.get("type")
        if not uri:
            continue
        info = index.setdefault(uri, ClassInfo(uri=uri))
        if uri in _CE_ROLES:
            info.ce_superclasses.add(uri)
        if not info.label and row.get("typeLabel"):
            info.label = row["typeLabel"]
        if row.get("funktion"):
            info.funktionen.add(row["funktion"])
        if row.get("ceSuper"):
            info.ce_superclasses.add(row["ceSuper"])
    return index


def node_roles(type_uris: list[str], index: dict[str, ClassInfo]) -> list[str]:
    """Merge the roles of all classes a node is typed with."""
    roles: set[str] = set()
    for uri in type_uris:
        info = index.get(uri)
        if info:
            roles.update(info.rollen)
    ordered = [role for role in ROLE_ORDER if role in roles]
    return ordered or [ROLE_UNBEKANNT]
