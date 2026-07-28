"""Report tests.

The fixture deliberately contains a false positive ("Pflichtbereich Mechanik"
matches the keyword "Licht" only inside a word) and a node with no level, so the
precision and coverage sections have something to detect.
"""

import unittest

from mem_lehrplan import report


def _node(uri, label, rollen, stufen, quelle, klasse, eltern=()):
    return {
        "uri": uri,
        "label": label,
        "rollen": rollen,
        "klassen": [{"uri": f"https://onto/{klasse}", "label": klasse}],
        "stufen": stufen,
        "stufen_quelle": quelle,
        "eltern": [{"uri": "https://x/p", "label": e} for e in eltern],
    }


RESULT = {
    "abgerufen_am": "2026-07-28T12:00:00+00:00",
    "endpoint": "https://sparql.example.org/sparql/",
    "filter": {"fach": "physik", "bundesland": None, "stichwoerter": ["Optik", "Licht", "Fernrohr"]},
    "anzahl": {"lehrplaene": 2, "treffer": 3},
    "lehrplaene": [
        {
            "uri": "https://lp/1",
            "label": "Physik Oberschule",
            "bundesland": [{"uri": "https://b/sn", "label": "Sachsen"}],
            "schulart": [],
            "schulfach": [{"uri": "https://f/p", "label": "Physik"}],
            "stufen": {"schulstufe": [{"uri": "https://s/1", "label": "Sekundarbereich I"}]},
            "weitere": [],
            "treffer": [
                _node(
                    "https://n/1",
                    "Lernbereich 2: Optik",
                    ["themenbereich"],
                    {"schulstufe": [{"uri": "https://s/1", "label": "Sekundarbereich I"}]},
                    "lehrplan",
                    "Lernbereich (SN)",
                ),
                _node(
                    "https://n/2",
                    "Lichtbrechung an Linsen",
                    ["kompetenz"],
                    {"jahrgangsstufe": [{"uri": "https://j/7", "label": "Klassenstufe 7"}]},
                    "knoten",
                    "Lernziel und Lerninhalt (SN)",
                    ["Lernbereich 2: Optik"],
                ),
            ],
        },
        {
            "uri": "https://lp/2",
            "label": "Physik Gymnasium",
            "bundesland": [{"uri": "https://b/rp", "label": "Rheinland-Pfalz"}],
            "schulart": [],
            "schulfach": [{"uri": "https://f/p", "label": "Physik"}],
            "stufen": {},
            "weitere": [],
            "treffer": [
                _node("https://n/3", "Pflichtbereich Mechanik", ["unbekannt"], {}, "keine", "Neuartig (RP)"),
            ],
        },
    ],
    "diagnostik": {"lehrplan_praedikate": [], "klassen_ohne_rolle": ["https://onto/Neuartig (RP)"]},
}


class AggregationTest(unittest.TestCase):
    def test_per_bundesland(self):
        self.assertEqual(
            report.per_bundesland(RESULT),
            [("Rheinland-Pfalz", 1, 1), ("Sachsen", 1, 2)],
        )

    def test_role_counts(self):
        self.assertEqual(report.role_counts(RESULT)["themenbereich"], 1)
        self.assertEqual(report.role_counts(RESULT)["kompetenz"], 1)

    def test_level_coverage_by_source_and_kind(self):
        sources, kinds = report.level_coverage(RESULT)
        self.assertEqual(dict(sources), {"lehrplan": 1, "knoten": 1, "keine": 1})
        self.assertEqual(dict(kinds), {"schulstufe": 1, "jahrgangsstufe": 1})

    def test_keyword_precision_counts_substring_matches(self):
        counts = {keyword: count for keyword, count, _ in report.keyword_precision(RESULT)}
        # "Licht" matches "Lichtbrechung" and, wrongly, "Pflichtbereich".
        self.assertEqual(counts["Licht"], 2)
        self.assertEqual(counts["Optik"], 1)
        self.assertEqual(counts["Fernrohr"], 0)

    def test_unmatched_keywords(self):
        self.assertEqual(report.unmatched_keywords(RESULT), ["Fernrohr"])

    def test_suspicious_matches_flags_word_internal_only(self):
        flagged = report.suspicious_matches(RESULT)
        self.assertEqual([label for _, label in flagged], ["Pflichtbereich Mechanik"])

    def test_unclassified_classes(self):
        self.assertEqual(dict(report.unclassified_classes(RESULT)), {"Neuartig (RP)": 1})

    def test_top_lehrplaene_is_sorted_by_matches(self):
        self.assertEqual(report.top_lehrplaene(RESULT, 5)[0][2], 2)


class RenderTest(unittest.TestCase):
    def setUp(self):
        self.text = report.render(RESULT, top=5)

    def test_contains_all_sections(self):
        for heading in (
            "Nach Bundesland",
            "Rollenverteilung",
            "Bildungsstufen-Abdeckung",
            "Stichwort-Praezision",
            "Knotenklassen",
            "Beispiel-Kompetenzen",
        ):
            with self.subTest(heading=heading):
                self.assertIn(heading, self.text)

    def test_reports_the_false_positive(self):
        self.assertIn("Pflichtbereich Mechanik", self.text)

    def test_reports_missing_level_warning_when_no_levels_present(self):
        empty = {
            **RESULT,
            "anzahl": {"lehrplaene": 1, "treffer": 1},
            "lehrplaene": [{**RESULT["lehrplaene"][1]}],
        }
        self.assertIn("KEINE Stufen gefunden", report.render(empty, top=5))

    def test_output_is_ascii_only_so_windows_consoles_survive(self):
        skeleton = "\n".join(
            line for line in self.text.splitlines() if not any(ch.isalpha() and ord(ch) > 127 for ch in line)
        )
        skeleton.encode("ascii")


if __name__ == "__main__":
    unittest.main()
