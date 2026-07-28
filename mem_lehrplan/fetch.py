"""Orchestration: query the endpoint and assemble linked records.

Sequence, one query per step (plus chunking for VALUES blocks):

    Lehrpläne -> descriptive attributes -> matching nodes -> node classes
              -> node attributes -> direct parents -> assembled records

Levels are attached twice: once per Lehrplan and once per node. Where a node
carries no level of its own it inherits the Lehrplan's, and ``stufen_quelle``
records which of the two applied -- so a downstream consumer never has to guess
whether "Jahrgangsstufe 7" was asserted on the competency or on the curriculum.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from . import queries
from .classify import build_class_index, node_roles
from .sparql import SparqlClient, chunked, collect_labelled
from .vocab import DESCRIPTIVE_PROPERTIES, ONTOLOGY, STUFEN_PROPERTIES

logger = logging.getLogger(__name__)

CHUNK_SIZE = 40

_PROPERTY_NAMES = {ONTOLOGY + pid: name for name, pid in DESCRIPTIVE_PROPERTIES.items()}


def _select_chunked(client: SparqlClient, build, uris: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for chunk in chunked(uris, CHUNK_SIZE):
        rows.extend(client.select(build(list(chunk))))
    return rows


def fetch_attributes(client: SparqlClient, uris: list[str]) -> dict[str, dict[str, list[dict[str, str]]]]:
    """Map each subject URI to its descriptive attributes, grouped by name."""
    rows = _select_chunked(client, queries.descriptive_attributes, uris)
    grouped: dict[str, dict[str, list[dict[str, str]]]] = {}
    for row in rows:
        name = _PROPERTY_NAMES.get(row.get("p", ""))
        subject = row.get("s")
        if not name or not subject:
            continue
        bucket = grouped.setdefault(subject, {}).setdefault(name, [])
        entry = {"uri": row["o"], "label": row.get("oLabel", "")}
        if entry not in bucket:
            bucket.append(entry)
    return grouped


def _stufen(attributes: dict[str, list[dict[str, str]]]) -> dict[str, list[dict[str, str]]]:
    return {name: attributes[name] for name in STUFEN_PROPERTIES if attributes.get(name)}


def fetch_nodes(client: SparqlClient, lehrplan_uri: str, keywords: list[str]) -> dict[str, dict]:
    """Matching descendants of one Lehrplan, with their class URIs collected."""
    nodes: dict[str, dict] = {}
    for row in client.select(queries.matching_nodes(lehrplan_uri, keywords)):
        node = nodes.setdefault(row["node"], {"uri": row["node"], "label": row.get("nodeLabel", ""), "typen": []})
        if row.get("type") and row["type"] not in node["typen"]:
            node["typen"].append(row["type"])
    return nodes


def fetch_parents(client: SparqlClient, node_uris: list[str]) -> dict[str, list[dict[str, str]]]:
    rows = _select_chunked(client, queries.direct_parents, node_uris)
    parents: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        bucket = parents.setdefault(row["node"], [])
        entry = {"uri": row["parent"], "label": row.get("parentLabel", "")}
        if entry not in bucket:
            bucket.append(entry)
    return parents


def _assemble_node(node: dict, index, attributes, parents, lehrplan_stufen) -> dict:
    own_stufen = _stufen(attributes.get(node["uri"], {}))
    return {
        "uri": node["uri"],
        "label": node["label"],
        "rollen": node_roles(node["typen"], index),
        "klassen": [{"uri": t, "label": index[t].label if t in index else ""} for t in node["typen"]],
        "stufen": own_stufen or lehrplan_stufen,
        "stufen_quelle": "knoten" if own_stufen else ("lehrplan" if lehrplan_stufen else "keine"),
        "eltern": parents.get(node["uri"], []),
    }


def harvest(
    client: SparqlClient,
    fach: str,
    stichwoerter: list[str],
    bundesland: str | None = None,
    limit: int | None = None,
) -> dict:
    """Collect all matching curricula with their topic areas and competencies."""
    lehrplan_rows = client.select(queries.lehrplaene(fach, bundesland, limit))
    lehrplaene = collect_labelled(lehrplan_rows, "lp", "lpLabel")
    logger.info("%d Lehrplan(e) fuer Fach-Stichwort %r", len(lehrplaene), fach)
    if not lehrplaene:
        return _result(fach, stichwoerter, bundesland, client.endpoint, [], {})

    lehrplan_uris = [entry["uri"] for entry in lehrplaene]
    lehrplan_attributes = fetch_attributes(client, lehrplan_uris)

    nodes_by_lehrplan = {}
    for uri in lehrplan_uris:
        nodes_by_lehrplan[uri] = fetch_nodes(client, uri, stichwoerter)
        logger.info("  %d Treffer in %s", len(nodes_by_lehrplan[uri]), uri)

    all_nodes = {uri: node for nodes in nodes_by_lehrplan.values() for uri, node in nodes.items()}
    node_uris = list(all_nodes)
    type_uris = sorted({t for node in all_nodes.values() for t in node["typen"]})

    index = build_class_index(_select_chunked(client, queries.class_roles, type_uris)) if type_uris else {}
    node_attributes = fetch_attributes(client, node_uris) if node_uris else {}
    parents = fetch_parents(client, node_uris) if node_uris else {}

    records = []
    for entry in lehrplaene:
        attributes = lehrplan_attributes.get(entry["uri"], {})
        lehrplan_stufen = _stufen(attributes)
        records.append(
            {
                "uri": entry["uri"],
                "label": entry["label"],
                "bundesland": attributes.get("bundesland", []),
                "schulfach": attributes.get("schulfach", []),
                "schulart": attributes.get("schulart", []),
                "stufen": lehrplan_stufen,
                "treffer": [
                    _assemble_node(node, index, node_attributes, parents, lehrplan_stufen)
                    for node in nodes_by_lehrplan[entry["uri"]].values()
                ],
            }
        )

    diagnostics = {
        "lehrplan_praedikate": collect_labelled(
            _select_chunked(client, queries.predicate_audit, lehrplan_uris), "p", "pLabel"
        ),
        "klassen_ohne_rolle": sorted(
            {info.uri for info in index.values() if not info.rollen}
        ),
    }
    return _result(fach, stichwoerter, bundesland, client.endpoint, records, diagnostics)


def _result(fach, stichwoerter, bundesland, endpoint, records, diagnostics) -> dict:
    return {
        "abgerufen_am": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "endpoint": endpoint,
        "filter": {"fach": fach, "bundesland": bundesland, "stichwoerter": stichwoerter},
        "anzahl": {
            "lehrplaene": len(records),
            "treffer": sum(len(record["treffer"]) for record in records),
        },
        "lehrplaene": records,
        "diagnostik": diagnostics,
    }
