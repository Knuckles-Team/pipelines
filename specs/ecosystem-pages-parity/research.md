# PIPE-PAGES — Research

## Resolved unknowns

- **Script policy.** The Canopy page needs scripts for its canvas map. PIPE-PAGES-R013.4 covers only the package diagrams of the spec-delivery pages and stays true. The page degrades to a `<noscript>` part list and static export files (PIPE-PAGES-R057.7).
- **Phase declaration.** PIPE-PAGES-R051.3 reads a `## Delivery phase` heading, which the plan template forbids. One line `Delivery phase: P<n>` in `plan.md` replaces it (PIPE-PAGES-R056.1).
- **Empty releases.** The published page lists no bundles because the site workflow does not check out `releases/`. The fix is a workflow row in the organization repository.
- **Priority edges.** `aggregate` in `scripts/architecture_explorer/delivery.py` keeps counts only. It returns a `dependents` map (PIPE-PAGES-R053.1).
- **Plan check on fetched text.** `check_plan` needs a checkout. A public text wrapper follows the plan-conformance gate (PIPE-PAGES-R054.2).

## Open questions

none
