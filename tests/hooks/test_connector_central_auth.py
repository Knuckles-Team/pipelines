"""Auth rules R1-R14 on synthetic connectors (PIPE-GATES-R016.68-.81)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipelines_hooks.hygiene.connector_central import auth
from pipelines_hooks.hygiene.connector_central.base import RULES, make_ctx

PYPROJECT = """[project]
name = "demo-mcp"
version = "1.0.0"
[project.entry-points."agent_connector_sdk.connector"]
demo-mcp = "demo_mcp:connector"
"""

# The Api accepts a governed client; every other parameter is defaulted.
API_OK = """class Api:
    def __init__(self, client=None, url=None, token=None, debug=False):
        self.client = client
{wire}
"""
API_LEGACY = """class Api:
    def __init__(self, url, token, workspace_slug, tls_profile=None):
        self.url = url
{wire}
"""

HEAD = '''"""Demo auth."""

import logging

from agent_connector_sdk.config import setting
from agent_connector_sdk.tls.resolve import resolve_tls_profile

from demo_mcp.api_client import Api

logger = logging.getLogger(__name__)
'''


def _auth(body: str, head: str = HEAD) -> str:
    return head + "\n\n" + body


def _bearer_body(extra_kw: str = "", singleton: bool = False) -> str:
    call = f'Api(url=url, token=token{extra_kw}, tls_profile=resolve_tls_profile("demo"))'
    if singleton:
        return f"""_client = None


def get_client():
    global _client
    if _client is None:
        url = setting("DEMO_URL")
        token = setting("DEMO_TOKEN")
        if not url:
            raise RuntimeError("DEMO_URL is required")
        _client = {call}
    return _client
"""
    return f"""def get_client():
    url = setting("DEMO_URL")
    token = setting("DEMO_TOKEN")
    if not url:
        raise RuntimeError("DEMO_URL is required")
    return {call}
"""


def _repo(tmp_path: Path, auth_src: str | None, api_src: str, importer: str = "") -> Path:
    root = tmp_path / "demo-mcp"
    pkg = root / "demo_mcp"
    pkg.mkdir(parents=True)
    (root / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "api_client.py").write_text(api_src, encoding="utf-8")
    if auth_src is not None:
        (pkg / "auth.py").write_text(auth_src, encoding="utf-8")
    if importer:
        (pkg / "tools.py").write_text(importer, encoding="utf-8")
    return root


def _run(root: Path, *rules: str):
    ctx = make_ctx(root)
    assert ctx is not None
    for rid in rules or auth.ORDER:
        RULES[rid](ctx)
    return ctx


def _text(root: Path) -> str:
    return (root / "demo_mcp" / "auth.py").read_text(encoding="utf-8")


def _wire(src: str) -> str:
    return "\n".join("    " + line for line in src.splitlines())


def _api(wire: str, template: str = API_OK) -> str:
    return template.format(wire=_wire(wire))


def _assert_rewritten(root: Path, decl: str, tls: str = "demo") -> str:
    text = _text(root)
    compile(text, "auth.py", "exec")
    assert f"auth={decl}," in text
    assert f'tls="{tls}",' in text
    assert 'url_env="DEMO_URL",' in text
    assert "return Api(client=get_http_client())" in text
    assert "setting(" not in text
    return text


def test_order_covers_every_rule() -> None:
    assert set(auth.ORDER) == {f"auth.r{i}" for i in range(1, 15)}
    assert len(auth.ORDER) == 14


# spec: PIPE-GATES-R016.68 — reviewed existing assertion binding
@pytest.mark.spec("PIPE-GATES-R016.68")
def test_r1_bearer_rewrite(tmp_path: Path) -> None:
    root = _repo(tmp_path, _auth(_bearer_body()), _api('H = {"Authorization": f"Bearer {token}"}'))
    ctx = _run(root)
    _assert_rewritten(root, 'Bearer(env="DEMO_TOKEN")')
    assert "auth.r1" in ctx.applied
    assert not ctx.review.items


@pytest.mark.spec("PIPE-GATES-R016.68")
def test_r1_unmatched_shape_goes_to_review_untouched(tmp_path: Path) -> None:
    api = _api('H = {"Authorization": f"Bearer {token}"}', API_LEGACY)
    src = _auth(_bearer_body())
    root = _repo(tmp_path, src, api)
    ctx = _run(root)
    assert _text(root) == src
    (item,) = [i for i in ctx.review.items if i["step"] == "auth.r1"]
    assert 'Bearer(env="DEMO_TOKEN")' in item["detail"]
    assert "not a governed httpx.Client" in item["detail"]
    assert not item["blocking"]


# spec: PIPE-GATES-R016.69 — reviewed existing assertion binding
@pytest.mark.spec("PIPE-GATES-R016.69")
def test_r2_api_key_header_rewrite(tmp_path: Path) -> None:
    root = _repo(tmp_path, _auth(_bearer_body()), _api('H = {"X-API-Key": token}'))
    ctx = _run(root)
    _assert_rewritten(root, 'ApiKey(env="DEMO_TOKEN", header="X-API-Key")')
    assert "auth.r2" in ctx.applied


@pytest.mark.spec("PIPE-GATES-R016.69")
def test_r2_authorization_token_prefix_and_extra_setting_review(tmp_path: Path) -> None:
    root = _repo(tmp_path, _auth(_bearer_body()), _api('H = {"Authorization": f"Token {token}"}'))
    _run(root)
    _assert_rewritten(root, 'ApiKey(env="DEMO_TOKEN", header="Authorization", prefix="Token ")')
    body = _bearer_body(", workspace_slug=slug").replace(
        '    token = setting("DEMO_TOKEN")',
        '    token = setting("DEMO_TOKEN")\n    slug = setting("DEMO_WORKSPACE_SLUG")',
    )
    root2 = _repo(tmp_path / "b", _auth(body), _api('H = {"X-API-Key": token}', API_LEGACY))
    ctx = _run(root2)
    (item,) = [i for i in ctx.review.items if i["step"] == "auth.r2"]
    assert "extra required setting workspace_slug (DEMO_WORKSPACE_SLUG)" in item["detail"]
    assert 'ApiKey(env="DEMO_TOKEN", header="X-API-Key")' in item["detail"]


# spec: PIPE-GATES-R016.70 — reviewed existing assertion binding
@pytest.mark.spec("PIPE-GATES-R016.70")
def test_r3_api_key_query_rewrite(tmp_path: Path) -> None:
    root = _repo(tmp_path, _auth(_bearer_body()), _api('P = dict(params={"token": token})'))
    ctx = _run(root)
    _assert_rewritten(root, 'ApiKey(env="DEMO_TOKEN", query="token")')
    assert "auth.r3" in ctx.applied


@pytest.mark.spec("PIPE-GATES-R016.70")
def test_r3_default_url_goes_to_review(tmp_path: Path) -> None:
    src = _auth(_bearer_body().replace('setting("DEMO_URL")', 'setting("DEMO_URL", "https://x.example")'))
    root = _repo(tmp_path, src, _api('P = dict(params={"token": token})'))
    ctx = _run(root)
    assert _text(root) == src
    assert any("has default" in i["detail"] and i["step"] == "auth.r3" for i in ctx.review.items)


BASIC_BODY = """def get_client():
    url = setting("DEMO_URL")
    user = setting("DEMO_USERNAME")
    pw = setting("DEMO_PASSWORD")
    return Api(url=url, username=user, password=pw, tls_profile=resolve_tls_profile("demo"))
"""
API_BASIC = API_OK.replace("token=None", "username=None, password=None")


# spec: PIPE-GATES-R016.71 — reviewed existing assertion binding
@pytest.mark.spec("PIPE-GATES-R016.71")
def test_r4_basic_rewrite(tmp_path: Path) -> None:
    root = _repo(tmp_path, _auth(BASIC_BODY), _api("import requests\nA = requests.auth.HTTPBasicAuth(1, 2)", API_BASIC))
    ctx = _run(root)
    _assert_rewritten(root, 'Basic(user_env="DEMO_USERNAME", password_env="DEMO_PASSWORD")')
    assert "auth.r4" in ctx.applied


@pytest.mark.spec("PIPE-GATES-R016.71")
def test_r4_and_r11_evidence_is_several_rules(tmp_path: Path) -> None:
    api = _api('A = BasicAuth\nL = "/api/login"', API_BASIC)
    src = _auth(BASIC_BODY)
    root = _repo(tmp_path, src, api)
    ctx = _run(root)
    assert _text(root) == src
    (item,) = ctx.review.items
    assert item["step"] == "auth.r1" and "several rules" in item["detail"]


CC_BODY = """def get_client():
    url = setting("DEMO_URL")
    cid = setting("DEMO_CLIENT_ID")
    secret = setting("DEMO_CLIENT_SECRET")
    return Api(url=url, client_id=cid, client_secret=secret, tls_profile=resolve_tls_profile("demo"))
"""
API_CC = API_OK.replace("token=None", "client_id=None, client_secret=None")


# spec: PIPE-GATES-R016.72 — reviewed existing assertion binding
@pytest.mark.spec("PIPE-GATES-R016.72")
def test_r5_client_credentials_rewrite(tmp_path: Path) -> None:
    wire = 'B = {"grant_type": "client_credentials"}\nU = "https://idp.example/oauth2/token"'
    root = _repo(tmp_path, _auth(CC_BODY), _api(wire, API_CC))
    ctx = _run(root)
    _assert_rewritten(
        root,
        'ClientCredentials(client_id_env="DEMO_CLIENT_ID", secret_env="DEMO_CLIENT_SECRET", '  # sanitizer:ignore - synthetic fixture env names, no secret value
        'token_url="https://idp.example/oauth2/token")',
    )
    assert "auth.r5" in ctx.applied


@pytest.mark.spec("PIPE-GATES-R016.72")
def test_r5_without_a_literal_token_url_goes_to_review(tmp_path: Path) -> None:
    src = _auth(CC_BODY)
    root = _repo(tmp_path, src, _api('B = {"grant_type": "client_credentials"}', API_CC))
    ctx = _run(root)
    assert _text(root) == src
    assert any(i["step"] == "auth.r5" and "token URL" in i["detail"] for i in ctx.review.items)


RT_BODY = """def get_client():
    url = setting("DEMO_URL")
    rt = setting("DEMO_REFRESH_TOKEN")
    cid = setting("DEMO_CLIENT_ID")
    return Api(url=url, refresh_token=rt, client_id=cid, tls_profile=resolve_tls_profile("demo"))
"""
API_RT = API_OK.replace("token=None", "refresh_token=None, client_id=None")


# spec: PIPE-GATES-R016.73 — reviewed existing assertion binding
@pytest.mark.spec("PIPE-GATES-R016.73")
def test_r6_refresh_token_rewrite(tmp_path: Path) -> None:
    wire = 'B = {"grant_type": "refresh_token"}\nU = "https://login.example/services/oauth2/token"'
    root = _repo(tmp_path, _auth(RT_BODY), _api(wire, API_RT))
    ctx = _run(root)
    _assert_rewritten(
        root,
        'RefreshToken(refresh_env="DEMO_REFRESH_TOKEN", client_id_env="DEMO_CLIENT_ID", '
        'token_url="https://login.example/services/oauth2/token")',
    )
    assert "auth.r6" in ctx.applied


@pytest.mark.spec("PIPE-GATES-R016.73")
def test_r6_two_token_urls_go_to_review(tmp_path: Path) -> None:
    wire = 'B = "refresh_token"\nU = "https://a.example/oauth2/token"\nV = "https://b.example/oauth2/token"'
    src = _auth(RT_BODY)
    root = _repo(tmp_path, src, _api(wire, API_RT))
    ctx = _run(root)
    assert _text(root) == src
    assert any(i["step"] == "auth.r6" and "token URL" in i["detail"] for i in ctx.review.items)


DELEGATING = """import threading

local = threading.local()


def enable_delegation():
    return True


def get_client():
    url = setting("DEMO_URL")
    token = setting("DEMO_TOKEN")
    return Api(url=url, token=token, tls_profile=resolve_tls_profile("demo"))
"""


@pytest.mark.spec("PIPE-GATES-R016.74")
def test_r7_delegation_holder_is_review_with_delegation_proposal(tmp_path: Path) -> None:
    src = _auth(DELEGATING)
    root = _repo(tmp_path, src, _api('H = {"Authorization": f"Bearer {token}"}'))
    ctx = _run(root)
    assert _text(root) == src
    assert any(i["step"] == "auth.r7" and "delegation=True" in i["detail"] for i in ctx.review.items)


@pytest.mark.spec("PIPE-GATES-R016.75")
def test_r8_delegation_wrappers_are_review(tmp_path: Path) -> None:
    src = _auth(DELEGATING.replace("local = threading.local()\n", ""))
    root = _repo(tmp_path, src, _api('H = {"Authorization": f"Bearer {token}"}'))
    ctx = _run(root)
    assert _text(root) == src
    assert any(i["step"] == "auth.r8" for i in ctx.review.items)
    assert not any(i["step"] == "auth.r7" for i in ctx.review.items)


# spec: PIPE-GATES-R016.76 — reviewed existing assertion binding
@pytest.mark.spec("PIPE-GATES-R016.76")
def test_r9_tls_profile_becomes_tls_name(tmp_path: Path) -> None:
    root = _repo(tmp_path, _auth(_bearer_body()), _api('H = {"Authorization": f"Bearer {token}"}'))
    ctx = _run(root)
    assert 'tls="demo"' in _text(root) and "resolve_tls_profile" not in _text(root)
    assert "auth.r9" in ctx.applied


@pytest.mark.spec("PIPE-GATES-R016.76")
def test_r9_missing_tls_profile_is_review(tmp_path: Path) -> None:
    src = _auth(_bearer_body().replace(', tls_profile=resolve_tls_profile("demo")', ""))
    root = _repo(tmp_path, src, _api('H = {"Authorization": f"Bearer {token}"}'))
    ctx = _run(root)
    assert _text(root) == src
    assert any(i["step"] == "auth.r9" and "tls=" in i["detail"] for i in ctx.review.items)


@pytest.mark.spec("PIPE-GATES-R016.77")
def test_r10_hand_configured_session_is_review(tmp_path: Path) -> None:
    body = """def get_client():
    import requests

    session = requests.Session()
    profile = resolve_tls_profile("demo")
    profile.configure_requests_session(session)
    return Api(url=setting("DEMO_URL"), token=setting("DEMO_TOKEN"))
"""
    src = _auth(body)
    root = _repo(tmp_path, src, _api('H = {"Authorization": f"Bearer {token}"}'))
    ctx = _run(root)
    assert _text(root) == src
    assert any(i["step"] == "auth.r10" for i in ctx.review.items)


LOGIN_BODY = BASIC_BODY


@pytest.mark.spec("PIPE-GATES-R016.78")
def test_r11_session_login_rewrite(tmp_path: Path) -> None:
    root = _repo(tmp_path, _auth(LOGIN_BODY), _api('L = "/api/v2/auth/login"', API_BASIC))
    ctx = _run(root)
    _assert_rewritten(
        root,
        'SessionLogin(login_path="/api/v2/auth/login", user_env="DEMO_USERNAME", password_env="DEMO_PASSWORD")',
    )
    assert "auth.r11" in ctx.applied


@pytest.mark.spec("PIPE-GATES-R016.78")
def test_r11_two_login_paths_still_matches_r11_but_proposes_placeholder(tmp_path: Path) -> None:
    src = _auth(LOGIN_BODY)
    root = _repo(tmp_path, src, _api('L = "/a/login"\nM = "/b/login"', API_BASIC))
    ctx = _run(root)
    assert _text(root) == src or "login_path=" in _text(root)
    if _text(root) == src:
        assert any(i["step"] == "auth.r11" for i in ctx.review.items)


# spec: PIPE-GATES-R016.79 — reviewed existing assertion binding
@pytest.mark.spec("PIPE-GATES-R016.79")
def test_r12_singleton_becomes_factory_with_close_alias(tmp_path: Path) -> None:
    root = _repo(tmp_path, _auth(_bearer_body(singleton=True)), _api('H = {"Authorization": f"Bearer {token}"}'))
    ctx = _run(root)
    text = _assert_rewritten(root, 'Bearer(env="DEMO_TOKEN")')
    assert "close_client = get_http_client.close" in text
    assert "global" not in text and "_client = None" not in text
    assert "auth.r12" in ctx.applied


@pytest.mark.spec("PIPE-GATES-R016.79")
def test_r12_non_singleton_has_no_close_alias(tmp_path: Path) -> None:
    root = _repo(tmp_path, _auth(_bearer_body()), _api('H = {"Authorization": f"Bearer {token}"}'))
    ctx = _run(root)
    assert "close_client" not in _text(root)
    assert "auth.r12" not in ctx.applied


# spec: PIPE-GATES-R016.80 — reviewed existing assertion binding
@pytest.mark.spec("PIPE-GATES-R016.80")
def test_r13_local_tool_without_url_deletes_unused_auth(tmp_path: Path) -> None:
    body = "def get_client():\n    return Api()\n"
    root = _repo(tmp_path, _auth(body), _api("pass"))
    ctx = _run(root)
    assert not (root / "demo_mcp" / "auth.py").exists()
    assert "demo_mcp/auth.py" in ctx.deleted and "auth.r13" in ctx.applied


@pytest.mark.spec("PIPE-GATES-R016.80")
def test_r13_noauth_for_public_api_with_url_only(tmp_path: Path) -> None:
    body = """def get_client():
    url = setting("DEMO_URL")
    return Api(url=url, tls_profile=resolve_tls_profile("demo"))
"""
    root = _repo(tmp_path, _auth(body), _api("pass"))
    ctx = _run(root)
    _assert_rewritten(root, "NoAuth()")
    assert "auth.r13" in ctx.applied


@pytest.mark.spec("PIPE-GATES-R016.80")
def test_r13_imported_auth_is_not_deleted(tmp_path: Path) -> None:
    body = "def get_client():\n    return Api()\n"
    root = _repo(tmp_path, _auth(body), _api("pass"), importer="from demo_mcp.auth import get_client\n")
    ctx = _run(root)
    assert (root / "demo_mcp" / "auth.py").exists()
    assert any(i["step"] == "auth.r13" and "imported by" in i["detail"] for i in ctx.review.items)


# spec: PIPE-GATES-R016.81 — reviewed existing assertion binding
@pytest.mark.spec("PIPE-GATES-R016.81")
def test_r14_allow_plaintext_setting_becomes_env_name(tmp_path: Path) -> None:
    body = _bearer_body(", allow_plaintext=plain").replace(
        '    token = setting("DEMO_TOKEN")',
        '    token = setting("DEMO_TOKEN")\n    plain = setting("DEMO_ALLOW_PLAINTEXT")',
    )
    root = _repo(tmp_path, _auth(body), _api('H = {"Authorization": f"Bearer {token}"}'))
    ctx = _run(root)
    text = _text(root)
    assert 'allow_plaintext_env="DEMO_ALLOW_PLAINTEXT",' in text
    assert "auth.r14" in ctx.applied


@pytest.mark.spec("PIPE-GATES-R016.81")
def test_r14_unknown_extra_flag_is_review(tmp_path: Path) -> None:
    body = _bearer_body(", verify=flag").replace(
        '    token = setting("DEMO_TOKEN")', '    token = setting("DEMO_TOKEN")\n    flag = setting("DEMO_VERIFY")'
    )
    src = _auth(body)
    root = _repo(tmp_path, src, _api('H = {"Authorization": f"Bearer {token}"}'))
    ctx = _run(root)
    assert _text(root) == src
    assert any("extra required setting" in i["detail"] for i in ctx.review.items)


@pytest.mark.spec("PIPE-GATES-R016.68")
def test_no_scheme_rule_is_one_review_item(tmp_path: Path) -> None:
    src = _auth(_bearer_body())
    root = _repo(tmp_path, src, _api("pass"))
    ctx = _run(root)
    assert _text(root) == src
    (item,) = ctx.review.items
    assert "no scheme rule" in item["detail"]


@pytest.mark.spec("PIPE-GATES-R016.80")
def test_no_auth_py_is_silent(tmp_path: Path) -> None:
    root = _repo(tmp_path, None, _api("pass"))
    ctx = _run(root)
    assert not ctx.review.items and not ctx.changed and not ctx.deleted


@pytest.mark.spec("PIPE-GATES-R016.68")
def test_second_run_changes_nothing(tmp_path: Path) -> None:
    root = _repo(tmp_path, _auth(_bearer_body(singleton=True)), _api('H = {"Authorization": f"Bearer {token}"}'))
    _run(root)
    after = _text(root)
    ctx = _run(root)
    assert _text(root) == after
    assert not ctx.changed and not ctx.review.items
