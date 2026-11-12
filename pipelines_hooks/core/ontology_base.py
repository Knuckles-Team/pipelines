"""The one ontology base, defined once (constitution Article XXXIII).

Every ontology IRI is ``BASE + <module> + "#"``. Gates that name the core vocabulary
or the connector contract vocabulary derive the IRI here and never type it again.
"""

from __future__ import annotations

BASE = "https://knuckles-team.github.io/ontology/"
CORE_NS = f"{BASE}core#"
CORE_ONTOLOGY = f"{BASE}core"
CONTRACT_NS = f"{BASE}surface-contract#"
