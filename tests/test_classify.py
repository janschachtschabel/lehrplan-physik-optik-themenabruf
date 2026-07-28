"""Role classification tests.

The fixtures mirror real patterns found in lp-full.ttl:

* Kompetenzerwartung (BY) LP_0002049 -> intersection with LP_0000483 hasValue
  LP_0000479 (Kompetenzbeschreibungsfunktion)
* Lernbereich (SN) LP_0002113 -> plain subClassOf chain up to CE-Bereich
* Lernziel und Lerninhalt (SN) LP_0002115 -> both function individuals
"""

import unittest

from mem_lehrplan.classify import build_class_index, node_roles

ONTO = "https://w3id.org/lehrplan/ontology/"
KOMPETENZ_FUNKTION = ONTO + "LP_0000479"
INHALT_FUNKTION = ONTO + "LP_0000480"
CE_BEREICH = ONTO + "LP_0000349"

ROWS = [
    {"type": ONTO + "LP_0002049", "typeLabel": "Kompetenzerwartung (BY)", "funktion": KOMPETENZ_FUNKTION},
    {"type": ONTO + "LP_0002113", "typeLabel": "Lernbereich (SN)", "ceSuper": CE_BEREICH},
    {"type": ONTO + "LP_0002113", "typeLabel": "Lernbereich (SN)", "ceSuper": ONTO + "LP_0002113"},
    {"type": ONTO + "LP_0002115", "typeLabel": "Lernziel und Lerninhalt (SN)", "funktion": KOMPETENZ_FUNKTION},
    {"type": ONTO + "LP_0002115", "typeLabel": "Lernziel und Lerninhalt (SN)", "funktion": INHALT_FUNKTION},
    {"type": ONTO + "LP_9999999", "typeLabel": "Etwas Neues (XY)"},
]


class ClassIndexTest(unittest.TestCase):
    def setUp(self):
        self.index = build_class_index(ROWS)

    def test_rows_are_folded_into_one_entry_per_class(self):
        self.assertEqual(len(self.index), 4)
        self.assertEqual(self.index[ONTO + "LP_0002113"].label, "Lernbereich (SN)")

    def test_function_individual_yields_competency_role(self):
        self.assertEqual(self.index[ONTO + "LP_0002049"].rollen, ["kompetenz"])

    def test_ce_superclass_yields_topic_role(self):
        self.assertEqual(self.index[ONTO + "LP_0002113"].rollen, ["themenbereich"])

    def test_two_functions_yield_two_roles_in_fixed_order(self):
        self.assertEqual(self.index[ONTO + "LP_0002115"].rollen, ["kompetenz", "inhalt"])

    def test_unmapped_class_has_no_role(self):
        self.assertEqual(self.index[ONTO + "LP_9999999"].rollen, [])


class NodeRoleTest(unittest.TestCase):
    def setUp(self):
        self.index = build_class_index(ROWS)

    def test_roles_of_multiple_types_are_merged(self):
        self.assertEqual(
            node_roles([ONTO + "LP_0002113", ONTO + "LP_0002049"], self.index),
            ["themenbereich", "kompetenz"],
        )

    def test_unknown_type_falls_back_to_marker(self):
        self.assertEqual(node_roles([ONTO + "LP_9999999"], self.index), ["unbekannt"])

    def test_untyped_node_falls_back_to_marker(self):
        self.assertEqual(node_roles([], self.index), ["unbekannt"])


if __name__ == "__main__":
    unittest.main()
