"""Verified IRIs from the MEM Lehrplan ontology.

Every IRI in this module was checked against lp-base.ttl / lp-full.ttl of
https://github.com/FWU-DE/lehrplan-ontologie. Do not add entries here from
memory -- grep the TTL first. The Virtuoso endpoint performs no RDFS/OWL
reasoning, so sub-properties and sub-classes must be named explicitly in
queries; that is why this list is exhaustive rather than relying on the
super-property LP_0000024 ("wird beschrieben von").
"""

ONTOLOGY = "https://w3id.org/lehrplan/ontology/"

PREFIXES = """PREFIX lp:   <https://w3id.org/lehrplan/ontology/>
PREFIX obo:  <http://purl.obolibrary.org/obo/>
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX owl:  <http://www.w3.org/2002/07/owl#>"""

# Classes
CLASS_LEHRPLAN = "lp:LP_0000438"          # Lehrplan (abstract; states use sub-classes)
CLASS_CE_BEREICH = "lp:LP_0000349"        # CE-Bereich          -> Themenbereich
CLASS_CE_KOMPETENZ = "lp:LP_0000263"      # CE-Kompetenzspezifikation
CLASS_CE_INHALT = "lp:LP_0000332"         # CE-Lerninhalt

CE_SUPERCLASSES = (CLASS_CE_BEREICH, CLASS_CE_KOMPETENZ, CLASS_CE_INHALT)

# Structure
HAS_PART = "obo:BFO_0000051"              # the tree edge; lp:LP_0000008 is unused in state graphs
PROP_FUNKTION = "lp:LP_0000483"           # "has function specification"

# Function individuals that carry the didactic role of a class
FUNKTION_KOMPETENZ = ONTOLOGY + "LP_0000479"   # Kompetenzbeschreibungsfunktion
FUNKTION_INHALT = ONTOLOGY + "LP_0000480"      # Lerninhaltsbeschreibungsfunktion
FUNKTION_BEREICH = ONTOLOGY + "LP_0000497"     # Bereichsfunktion

# Context properties of a Lehrplan (and of most nodes below it)
KONTEXT_PROPERTIES = {
    "bundesland": "LP_0000029",
    "schulfach": "LP_0000537",
    "schulart": "LP_0000812",
}

# Level ("Bildungsstufe") properties. All five are sub-properties of
# LP_0000024 and must be queried individually -- no reasoning at the endpoint.
STUFEN_PROPERTIES = {
    "jahrgangsstufe": "LP_0000026",        # range LP_0000009 Jahrgangsstufe
    "schulstufe": "LP_0000047",            # range LP_0000020 Primarstufe / Sek I / Sek II
    "niveaustufe": "LP_0000578",           # range LP_0000443 (BE/BB Niveaustufen)
    "bildungsgangniveau": "LP_0000833",    # range LP_0000028
    "niveau": "LP_0000840",                # range LP_0000037
}

DESCRIPTIVE_PROPERTIES = {**KONTEXT_PROPERTIES, **STUFEN_PROPERTIES}

# Default keyword set for the optics topic. Deliberately broad: curriculum
# wording differs per state ("Optik" in SN, "Licht und Sehen" in BY, ...).
OPTIK_STICHWOERTER = (
    "Optik",
    "Licht",
    "Linse",
    "Spiegel",
    "Reflexion",
    "Brechung",
    "Strahl",
    "Abbildung",
    "Farbe",
    "Lupe",
    "Fernrohr",
    "Mikroskop",
    "Prisma",
    "Sehen",
    "Auge",
    "Schatten",
    "Beleuchtung",
)

DEFAULT_ENDPOINT = "https://sparql.mem.edufeed.org/sparql/"

# Path length bounds replacing SPARQL transitive paths ("*").
#
# Virtuoso answers an unbound transitive path joined against the instance data
# with "Exceeded 1000000000 bytes in transitive temp memory" (HTTP 500), so the
# closures are expanded into bounded UNIONs instead. The bounds below were
# measured on lp-full.ttl and set one step above the measurement as margin:
#
#   Lehrplan LP_0000438            16 sub-classes, max depth 1
#   CE-Bereich LP_0000349         160 sub-classes, max depth 3
#   CE-Kompetenzspezifikation      13 sub-classes, max depth 1
#   CE-Lerninhalt                   1 sub-class,   max depth 1
#   owl:intersectionOf lists       at most 7 members
#
# Re-measure with tools/measure_depths.py after an ontology update.
MAX_LEHRPLAN_SUBCLASS_DEPTH = 2
MAX_CE_SUBCLASS_DEPTH = 4
MAX_INTERSECTION_LIST_LENGTH = 8
