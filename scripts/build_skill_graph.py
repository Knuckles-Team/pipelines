"""Build the cross-repo skill_graph corpus (RF-ADR-009 D1).

Generates one progressively-disclosed corpus -- Concepts, Components, and
ManPages, with typed links between them -- from each repo's own existing
registries and content manifests. Nothing here is hand-authored content: every
node is derived mechanically from a committed source file, named in that
node's ``sourcePath``. Implementation lives in the ``skill_graph`` package
next to this file; see ``skill_graph/__init__.py`` and each submodule's
docstring for the extraction strategy and known scope limits.

Two independent extraction strategies feed the corpus:

1. **Nav-derived** (``skill_graph/nav.py``, every repo that already opted
   into the shared MkDocs theme: ``epistemic-graph``, ``agent-utilities``,
   ``agent-connector-sdk``, ``graph-os``, ``agent-webui``,
   ``agent-terminal-ui``, ``geniusbot``). A repo's own ``mkdocs.yml``
   ``nav:`` tree is itself a committed, machine-readable registry of that
   repo's public documentation surface.
2. **Registry-derived** (``skill_graph/eg.py``, ``skill_graph/au.py``,
   repo-specific, richer where a repo has a dedicated machine registry
   beyond its docs nav): EG's ``architecture/component-registry.yml`` +
   ``contract/methods.json``; AU's ``docs/concepts.yaml`` pillars +
   ``deploy/release/prebundled-skills.catalog.json``. SDK, graph-os, and the
   three UI repos have no additional machine registry today, so only the
   nav-derived strategy applies to them -- named explicitly as a known scope
   limit, not silently skipped (see ``skill_graph/corpus.py``).

Usage::

    python build_skill_graph.py build --workspace <path to agent-packages>
    python build_skill_graph.py check --workspace <path to agent-packages>
    python build_skill_graph.py emit-repo --slug <repo> --workspace <path> --out <file>
    python build_skill_graph.py check-repo --slug <repo> --workspace <path> --out <file>

``build``/``check`` write or verify ``pages/{corpus.jsonld,concepts.md,
components.md,index.md}`` (relative to ``--root``, this repo's root).
``emit-repo``/``check-repo`` write or verify one repo's man-page-tier
reference page at ``--out``. Both directions are the same byte-stability
gate: ``check`` re-runs the generation into memory and fails if the
committed file(s) differ.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from skill_graph.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
