"""Parse every generated query with a real SPARQL parser.

The package itself needs no third-party libraries; this check is skipped when
rdflib is not installed. It catches syntax errors that string-matching tests
cannot -- worth having, because a broken template only shows up as an opaque
Virtuoso HTTP 400 otherwise.
"""

import unittest

try:
    from rdflib.plugins.sparql.parser import parseQuery
except ImportError:  # pragma: no cover - optional dependency
    parseQuery = None

from mem_lehrplan import queries

LP = "https://lp-sachsen.org/resource/522"
NODE = "https://lp-sachsen.org/resource/7052"
TYPE = "https://w3id.org/lehrplan/ontology/LP_0002113"

ALL_QUERIES = {
    "lehrplaene": queries.lehrplaene("Physik"),
    "lehrplaene_bundesland_limit": queries.lehrplaene("Physik", "Sachsen", limit=10),
    "descriptive_attributes": queries.descriptive_attributes([LP, NODE]),
    "matching_nodes": queries.matching_nodes(LP, ["Optik", "Licht und Sehen"]),
    "direct_parents": queries.direct_parents([NODE]),
    "class_roles": queries.class_roles([TYPE]),
    "predicate_audit": queries.predicate_audit([LP]),
    "schulfaecher": queries.schulfaecher(),
    "schulfaecher_bundesland": queries.schulfaecher("Sachsen"),
}


@unittest.skipUnless(parseQuery, "rdflib not installed")
class SparqlSyntaxTest(unittest.TestCase):
    def test_every_template_parses(self):
        for name, query in ALL_QUERIES.items():
            with self.subTest(query=name):
                parseQuery(query)


if __name__ == "__main__":
    unittest.main()
