"""Plant-and-fire tests for BUG-CX-EXEMPT-SCORE: the exhaustive-dispatch
exemption used to be folded into the compared cyclomatic VALUE (an exempt row
was hard-zeroed before the before/after comparison), so a function that was
exempt-over-cap at HEAD and was simplified below the cap -- the exemption no
longer applying, since ``exhaustive_dispatch_exempt`` never grants it to an
at-or-under-cap function -- read as a jump from a fabricated 0 to its real
value, and was reported WORSE. Simplifying a function until it no longer
needed the exemption was the one thing the gate could not tell from making it
worse.

Every case here runs the real ``complexity-staged`` gate, the real pinned
``cccc``, and the real exhaustive-dispatch rule against a real git repository
(the shared ``repo``/``Repo`` fixtures from ``tests/hooks/conftest.py``) --
nothing here is mocked.

``handle_shex_validate`` is the real function from epistemic-graph's
``src/server/handlers/rdf.rs``: the base from commit ``e25c73fb`` (cyclomatic
11 / cognitive 11, over the cyclomatic cap, exempt) and the after from lane
F3a's held working-tree fix at
``/var/tmp/l9/eg-f3a/rdf.rs.worktree.bak`` (cyclomatic 9 / cognitive 10, under
both caps, not exempt) -- the exact edit this class of bug wrongly blocked.
"""

from __future__ import annotations

from tests.hooks.conftest import Repo, branchy

HANDLE_SHEX_VALIDATE_COMMON = """
async fn handle_shex_validate(
    req_id: u64,
    graph_name: &str,
    core: &Arc<GraphCore>,
    schema: String,
    data_graph: String,
    shape_map: Vec<[String; 2]>,
) -> Response {
    let schema = match eg_shex::Schema::from_shexj(&schema) {
        Ok(s) => s,
        Err(e) => return Response::err(req_id, format!("ShexValidate: bad schema: {e}")),
    };
    let data = if data_graph.trim().is_empty() {
        let exported = eg_rdf::mapping::export_triples(core, graph_name);
        match exported {
            Ok(triples) => {
                let mut g = eg_shex::Graph::new();
                for t in &triples {
                    g.insert(t);
                }
                g
            }
            Err(e) => {
                return Response::err(req_id, format!("ShexValidate: export live graph: {e}"))
            }
        }
    } else {
        match eg_shex::graph_from_turtle(&data_graph) {
            Ok(g) => g,
            Err(e) => return Response::err(req_id, format!("ShexValidate: bad data graph: {e}")),
        }
    };
    let pairs: Vec<(&str, &str)> = shape_map
        .iter()
        .map(|p| (p[0].as_str(), p[1].as_str()))
        .collect();
    let map = eg_shex::ShapeMap::from_iri_pairs(&pairs);
    let report = eg_shex::validate(&schema, &data, &map);
"""

HANDLE_SHEX_VALIDATE_BASE = HANDLE_SHEX_VALIDATE_COMMON + """\
    match serde_json::to_value(&report) {
        Ok(v) => Response::ok(req_id, ResultPayload::Json(v)),
        Err(e) => Response::err(req_id, format!("ShexValidate: serialize report: {e}")),
    }
}
"""

HANDLE_SHEX_VALIDATE_SIMPLIFIED = HANDLE_SHEX_VALIDATE_COMMON + """\
    Response::ok(
        req_id,
        ResultPayload::of::<eg_types::result_contract::reasoning::ShexValidate>(shex_report_wire(
            report,
        )),
    )
}
"""


def _dispatch(arms: int, extra: str = "") -> str:
    """A flat, exhaustive Rust dispatch over ``arms`` variants (``extra``
    inserted into the first arm's body, keeping the arm count fixed)."""
    first = f"        Kind::V0 => {{{extra}\n            0\n        }}\n" if extra else "        Kind::V0 => 0,\n"
    rest = "".join(f"        Kind::V{index} => {index},\n" for index in range(1, arms))
    return f"pub fn dispatch_kind(kind: Kind, flag: bool, other: bool) -> u8 {{\n    match kind {{\n{first}{rest}    }}\n}}\n"


def test_exempt_over_cap_to_non_exempt_under_cap_passes(repo: Repo) -> None:
    repo.commit({"pkg/rdf.rs": HANDLE_SHEX_VALIDATE_BASE})
    repo.stage({"pkg/rdf.rs": HANDLE_SHEX_VALIDATE_SIMPLIFIED})
    assert repo.run("complexity-staged") == 0


def test_non_exempt_under_cap_to_over_cap_fails(repo: Repo) -> None:
    repo.commit({"pkg/classify.py": branchy("classify", 6)})
    repo.stage({"pkg/classify.py": branchy("classify", 11)})
    assert repo.run("complexity-staged") == 1


def test_exempt_function_growing_non_arm_complexity_fails(repo: Repo) -> None:
    # 11 flat arms (cyclomatic 12, residual 1) -> same 11 arms but the first
    # arm's body grows real (non-dispatch) branching (cyclomatic 14, residual
    # 3): still exempt on both sides (cognitive stays under the cap), but the
    # growth is not "purely added arms".
    repo.commit({"pkg/dispatch.rs": _dispatch(11)})
    grown = _dispatch(11, extra="\n            if flag {\n                if other {\n                    return 9;\n                }\n            }")
    repo.stage({"pkg/dispatch.rs": grown})
    assert repo.run("complexity-staged") == 1


def test_exempt_function_adding_exhaustive_arms_passes(repo: Repo) -> None:
    # 11 arms -> 13 arms, nothing else changed: cyclomatic rises (arms are not
    # free in the raw count) but the residual -- what this gate judges -- does
    # not, because the growth is purely added match arms.
    repo.commit({"pkg/dispatch.rs": _dispatch(11)})
    repo.stage({"pkg/dispatch.rs": _dispatch(13)})
    assert repo.run("complexity-staged") == 0


def test_new_over_cap_function_fails(repo: Repo) -> None:
    repo.stage({"pkg/classify.py": branchy("classify", 11)})
    assert repo.run("complexity-staged") == 1


def test_exempt_function_losing_exhaustiveness_still_fails(repo: Repo) -> None:
    """Not one of the five required cases, but the scenario the old scheme's
    zero-vs-raw jump happened to catch: an exempt dispatcher that grows a
    catch-all arm leaves the accepted class while staying over the cap. Must
    still fail under the corrected rule, which never zeroes an exempt row."""
    repo.commit({"pkg/dispatch.rs": _dispatch(11)})
    broken = _dispatch(11).replace(
        "        Kind::V0 => 0,\n", "        Kind::V0 => 0,\n        other => other as u8,\n"
    )
    repo.stage({"pkg/dispatch.rs": broken})
    assert repo.run("complexity-staged") == 1
