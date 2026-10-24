"""Auth rules R1-R14: ``<pkg>/auth.py`` becomes one ``client_factory(...)`` declaration (PIPE-GATES-R016.68-.81).

The SDK ``client_factory`` builds a governed ``httpx.Client``; a connector's own ``Api(...)`` constructor stays
connector-owned. So ``auth.py`` is rewritten only when the whole file has the one simple pre-migration shape, exactly one
scheme rule matches it, and the ``Api`` class already accepts a governed client (a ``client`` / ``http_client``
parameter, every other parameter defaulted). Every other file gets one review item naming the rule that detected the
scheme, the PROPOSED one-line declaration and the reason, so the review list is a ready worklist. A file matching no
scheme rule or several gets one ``no scheme rule / several rules`` item. Env names only; no value is ever read.

Rewrite output keeps ``get_client()`` returning the connector's ``Api`` so no call site changes::

    get_http_client = client_factory(url_env="P_URL", auth=Bearer(env="P_TOKEN"), tls="p")
    close_client = get_http_client.close      # only when the old module held a global singleton


    def get_client() -> Api:
        return Api(client=get_http_client())

The modifier rules (R7 R8 R9 R10 R12 R14) are decided by the same analysis; they fire only as part of a rewrite that
succeeds, and a modifier shape that is not exact is the blocker the scheme rule reports under the modifier's id.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

from .base import Ctx, rule

SCHEME_RULES = ("auth.r1", "auth.r2", "auth.r3", "auth.r4", "auth.r5", "auth.r6", "auth.r11", "auth.r13")
MODIFIER_RULES = ("auth.r12", "auth.r7", "auth.r8", "auth.r9", "auth.r10", "auth.r14")
ORDER: tuple[str, ...] = SCHEME_RULES + MODIFIER_RULES

_URL_KW = {"url", "base_url", "instance_url", "host"}
_SECRET_KW = {"token", "access_token", "api_key", "apikey", "key", "bearer_token"}
_USER_KW = {"username", "user"}
_HEADER_NAMES = {"x-api-key", "x-auth-token", "private-token"}
_QUERY_NAMES = {"token", "apikey", "api_key"}
_DELEGATION_NAMES = {"enable_delegation", "DelegationSettings", "exchange_token", "current_user_token"}
_CLIENT_PARAMS = ("client", "http_client")
_ALLOWED_TOP = (ast.Import, ast.ImportFrom)


@dataclass
class Analysis:
    """What ``auth.py`` is: scheme matches, blockers (rule id, reason) and the declaration to propose."""

    path: str
    matches: list[str] = field(default_factory=list)
    blockers: list[tuple[str, str]] = field(default_factory=list)
    declaration: str = ""
    candidates: list[str] = field(default_factory=list)
    mods: list[str] = field(default_factory=list)
    text: str = ""  # the rewritten file, set only when nothing blocks


def _consts(tree: ast.AST) -> list[str]:
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.append(node.value)
    return out


def _plain_consts(tree: ast.AST) -> list[str]:
    """String constants that are not fragments of an f-string."""
    inner = {id(v) for n in ast.walk(tree) if isinstance(n, ast.JoinedStr) for v in n.values}
    return [
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in inner
    ]


def _names(tree: ast.AST) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            out.add(node.id)
        elif isinstance(node, ast.Attribute):
            out.add(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.add(node.name)
        elif isinstance(node, ast.alias):
            out.add(node.name.split(".")[-1])
    return out


def _parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return None


def _api_sources(ctx: Ctx) -> list[Path]:
    files = (
        [ctx.pkg / "api_client.py"] + sorted((ctx.pkg / "api").glob("*.py"))
        if (ctx.pkg / "api").is_dir()
        else [ctx.pkg / "api_client.py"]
    )
    return [p for p in files if p.is_file()]


def _import_map(tree: ast.Module, ctx: Ctx, here: Path) -> dict[str, tuple[Path, str]]:
    """local name -> (module file, original name) for ``from <pkg...> import X [as Y]`` in ``here``."""
    out: dict[str, tuple[Path, str]] = {}
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom) or not node.module and not node.level:
            continue
        if node.level:
            base = here.parent
            for _ in range(node.level - 1):
                base = base.parent
            parts = (node.module or "").split(".") if node.module else []
            target = base.joinpath(*parts)
        else:
            parts = (node.module or "").split(".")
            if parts[0] != ctx.pkg_name:
                continue
            target = ctx.root.joinpath(*parts)
        file = target.with_suffix(".py") if target.with_suffix(".py").is_file() else target / "__init__.py"
        for alias in node.names:
            out[alias.asname or alias.name] = (file, alias.name)
    return out


def _find_init(ctx: Ctx, file: Path, name: str, depth: int = 0) -> ast.FunctionDef | None | str:
    """The ``__init__`` a class would run (left-to-right base search); ``"?"`` when it cannot be resolved."""
    if depth > 6 or not file.is_file():
        return "?"
    tree = _parse(file)
    if tree is None:
        return "?"
    imports = _import_map(tree, ctx, file)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                    return item
            for base in node.bases:
                if not isinstance(base, ast.Name):
                    return "?"
                if base.id in imports:
                    bfile, bname = imports[base.id]
                    found = _find_init(ctx, bfile, bname, depth + 1)
                else:
                    found = _find_init(ctx, file, base.id, depth + 1)
                if found != "?" and found is not None:
                    return found
                if found == "?":
                    return "?"
            return None
        if isinstance(node, ast.ImportFrom) and any((a.asname or a.name) == name for a in node.names):
            if name in imports:
                return _find_init(ctx, imports[name][0], imports[name][1], depth + 1)
    return "?"


def _client_param(ctx: Ctx, auth_tree: ast.Module, auth_file: Path, api_name: str) -> tuple[str, str]:
    """(parameter name, "") when the Api ctor takes a governed client; ("", reason) otherwise."""
    imports = _import_map(auth_tree, ctx, auth_file)
    if api_name not in imports:
        return "", f"cannot locate the {api_name} class"
    file, original = imports[api_name]
    init = _find_init(ctx, file, original)
    if init in ("?", None):
        return "", f"cannot resolve the {api_name} constructor"
    assert isinstance(init, ast.FunctionDef)
    args = init.args
    positional = [a.arg for a in args.posonlyargs + args.args][1:]
    n_req = len(positional) - len(args.defaults)
    required = positional[:n_req] + [a.arg for a, d in zip(args.kwonlyargs, args.kw_defaults) if d is None]
    allnames = positional + [a.arg for a in args.kwonlyargs]
    sig = ", ".join(a for a in allnames if a != "self")
    param = next((p for p in _CLIENT_PARAMS if p in allnames), "")
    if not param:
        return "", f"Api ctor takes {sig or 'no parameters'}, not a governed httpx.Client"
    others = [r for r in required if r != param]
    if others:
        return "", f"Api ctor requires {', '.join(others)} besides the governed client"
    return param, ""


def _setting_call(node: ast.AST) -> tuple[str, str] | None:
    """``setting("ENV"[, default])`` -> (ENV, unparsed default)."""
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "setting"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
        and not node.keywords
        and len(node.args) <= 2
    ):
        default = ast.unparse(node.args[1]) if len(node.args) == 2 else "None"
        return node.args[0].value, default
    return None


def _tls_call(node: ast.AST) -> tuple[str, bool] | None:
    """``resolve_tls_profile("name")`` -> (name, has extra selector args)."""
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "resolve_tls_profile"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    ):
        return node.args[0].value, bool(node.keywords or len(node.args) > 1)
    return None


def _walk_body(stmts: list[ast.stmt], out: list[ast.stmt], flags: dict[str, bool]) -> None:
    for st in stmts:
        if isinstance(st, ast.Global):
            flags["global"] = True
        elif (
            isinstance(st, ast.If)
            and isinstance(st.test, ast.Compare)
            and isinstance(st.test.left, ast.Name)
            and st.test.left.id == "_client"
            and not st.orelse
        ):
            flags["singleton"] = True
            _walk_body(st.body, out, flags)
        elif isinstance(st, ast.Try):
            _walk_body(st.body, out, flags)
            for handler in st.handlers:
                if not (len(handler.body) == 1 and isinstance(handler.body[0], ast.Raise)):
                    out.append(handler)  # type: ignore[arg-type]
        else:
            out.append(st)


def _is_guard(st: ast.stmt) -> bool:
    return isinstance(st, ast.If) and not st.orelse and len(st.body) == 1 and isinstance(st.body[0], ast.Raise)


def _wire_evidence(ctx: Ctx, auth_tree: ast.Module) -> dict[str, object]:
    """What the connector's HTTP code does with a secret, from string constants only."""
    trees = [auth_tree] + [t for p in _api_sources(ctx) if (t := _parse(p)) is not None]
    consts: list[str] = []
    plain: list[str] = []
    names: set[str] = set()
    for t in trees:
        consts += _consts(t)
        plain += _plain_consts(t)
        names |= _names(t)
    text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in _api_sources(ctx))
    ev: dict[str, object] = {}
    ev["bearer"] = any(c.startswith("Bearer") for c in consts)
    ev["token_prefix"] = any(c.startswith("Token ") for c in consts)
    ev["headers"] = sorted({c for c in consts if c.lower() in _HEADER_NAMES})
    ev["query"] = sorted(set(re.findall(r"params\s*(?:=\s*(?:dict\()?\{|\[)\s*[\"'](token|apikey|api_key)[\"']", text)))
    ev["basic"] = bool(names & {"HTTPBasicAuth", "BasicAuth", "b64encode"}) or any(
        c.startswith("Basic ") for c in consts
    )
    ev["login_paths"] = sorted({c for c in plain if re.fullmatch(r"/[\w/.-]*login[\w/.-]*", c)})
    ev["login_fragments"] = sorted(
        {c for c in consts if re.fullmatch(r"/[\w/.-]*login[\w/.-]*", c)} - set(ev["login_paths"])
    )  # type: ignore[arg-type]
    ev["cc"] = "client_credentials" in consts
    ev["refresh"] = "refresh_token" in consts
    ev["token_urls"] = sorted({c for c in consts if c.startswith("http") and re.search(r"/(oauth2?/)?token\b", c)})
    ev["session"] = "configure_requests_session" in names
    return ev


def analyse(ctx: Ctx) -> Analysis | None:
    """None when there is no ``auth.py`` or it is already migrated; otherwise the full analysis."""
    path = ctx.pkg / "auth.py"
    if not path.is_file():
        return None
    rel = ctx.rel(path)
    src = path.read_text(encoding="utf-8")
    if "client_factory(" in src:
        return None
    tree = _parse(path)
    an = Analysis(path=rel)
    if tree is None:
        an.blockers.append(("auth.r13", "auth.py does not parse"))
        return an
    cache = ctx.options.setdefault("_auth_analysis", {})
    if cache.get("src") == src and "an" in cache:
        return cache["an"]  # type: ignore[no-any-return]
    _analyse_into(ctx, an, tree, path, src)
    ctx.options["_auth_analysis"] = {"src": src, "an": an}
    return an


_CRED_ENV = (
    ("secret", re.compile(r"(API_?KEY|ACCESS_TOKEN|API_TOKEN|_TOKEN$|_KEY$)")),
    ("password", re.compile(r"PASSWORD")),
    ("user", re.compile(r"(USERNAME|_USER$)")),
    ("client_secret", re.compile(r"CLIENT_SECRET")),
    ("client_id", re.compile(r"CLIENT_ID")),
    ("refresh", re.compile(r"REFRESH_TOKEN")),
)
_KW_ROLE = {
    **dict.fromkeys(_SECRET_KW, "secret"),
    **dict.fromkeys(_USER_KW, "user"),
    "password": "password",
    "client_id": "client_id",
    "client_secret": "client_secret",
    "refresh_token": "refresh",
}
_HEADER_CANON = {"x-api-key": "X-API-Key", "x-auth-token": "X-Auth-Token", "private-token": "PRIVATE-TOKEN"}
_IGNORED_SETTING = re.compile(r"(TLS_PROFILE|ENABLE_DELEGATION|^OIDC_|^AUDIENCE$|^DELEGATED_SCOPES$)")


def _env_for(role: str, settings: dict[str, str]) -> str:
    """The setting that feeds ``role`` (fleet naming: ``<P>_API_KEY``, ``<P>_USERNAME``, ...)."""
    pattern = dict(_CRED_ENV)[role]
    found = [env for env in settings if pattern.search(env) and not (role == "secret" and "REFRESH" in env)]
    return found[0] if len(found) == 1 else ""


def _facts(tree: ast.Module) -> tuple[dict[str, str], list[str], list[tuple[str, set[str]]]]:
    """(setting env -> default, tls names, [(constructor name, keyword names)]) anywhere in the module."""
    settings: dict[str, str] = {}
    tls: list[str] = []
    calls: list[tuple[str, set[str]]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        sc = _setting_call(node)
        if sc:
            settings.setdefault(sc[0], sc[1])
            continue
        if isinstance(node.func, ast.Name) and node.func.id == "setting" and node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                settings.setdefault(first.value, "None")
        tc = _tls_call(node)
        if tc:
            tls.append(tc[0])
        elif isinstance(node.func, ast.Name) and node.func.id[:1].isupper():
            calls.append((node.func.id, {k.arg for k in node.keywords if k.arg}))
    return settings, tls, calls


def _analyse_into(ctx: Ctx, an: Analysis, tree: ast.Module, path: Path, src: str) -> None:
    """Tolerant facts decide the scheme and the proposal; the strict simple shape decides the rewrite."""
    blockers = an.blockers
    docstring = ast.get_docstring(tree)
    names_all = _names(tree)
    settings, tls_names, calls = _facts(tree)
    api_imports = _import_map(tree, ctx, path)
    api_calls = [(n, kws) for n, kws in calls if n in api_imports]
    api_name = api_calls[0][0] if api_calls else ""
    kwargs: set[str] = set().union(*(k for _n, k in api_calls)) if api_calls else set()
    tls_name = tls_names[0] if len(set(tls_names)) == 1 else ""

    if any(
        isinstance(n, ast.Assign) and isinstance(n.value, ast.Call) and ast.unparse(n.value.func) == "threading.local"
        for n in tree.body
    ):
        blockers.append(("auth.r7", "per-thread delegation holder: delete it and set delegation=True by hand"))
    if names_all & _DELEGATION_NAMES:
        blockers.append(("auth.r8", "delegation wrapper functions: delete them and set delegation=True by hand"))
    if "Session" in names_all and "configure_requests_session" in names_all:
        blockers.append(("auth.r10", "hand-configured requests session in auth.py: delete it by hand"))
    if names_all & {"get_instance", "get_instances", "instances"} or "instance" in {
        a.arg for f in tree.body if isinstance(f, ast.FunctionDef) for a in f.args.args
    }:
        blockers.append(("shape", "multi-tenant instances (get_client selects a configured tenant)"))
    if len(set(tls_names)) > 1:
        blockers.append(("auth.r9", f"several TLS profile names: {', '.join(sorted(set(tls_names)))}"))
    if not api_name:
        blockers.append(("shape", "no Api(...) construction found"))

    roles: dict[str, str] = {}
    extra: list[str] = []
    for kw in sorted(kwargs):
        if kw in _URL_KW or kw in {"tls_profile", "debug"}:
            continue
        if kw == "allow_plaintext":
            continue
        role = _KW_ROLE.get(kw)
        if role:
            roles[role] = _env_for(role, settings)
        else:
            hint = [e for e in settings if kw.upper() in e]
            extra.append(f"{kw} ({hint[0]})" if hint else kw)
    if extra:
        blockers.append(("shape", f"extra required setting {', '.join(extra)}"))
    url_envs = [e for e in settings if re.search(r"(_URL|_BASE_URL|_HOST)$", e)]
    url_env = url_envs[0] if len(url_envs) == 1 else ""
    plaintext = [e for e in settings if "PLAINTEXT" in e]
    plaintext_env = plaintext[0] if len(plaintext) == 1 else ""
    if plaintext_env:
        an.mods.append("auth.r14")
    if url_env and settings[url_env] not in ("None", "''", '""'):
        blockers.append(("shape", f"{url_env} has default {settings[url_env]}; client_factory requires the setting"))
    if url_env and not tls_name and len(set(tls_names)) <= 1:
        blockers.append(("auth.r9", 'no resolve_tls_profile(...) call; client_factory needs tls="<name>"'))
    elif tls_name:
        an.mods.append("auth.r9")
    unknown = [
        e
        for e in settings
        if e not in roles.values() and e not in (url_env, plaintext_env) and not _IGNORED_SETTING.search(e)
    ]
    known_extra = {e for e in settings if any(f"({e})" in x for x in extra)}
    unknown = [e for e in unknown if e not in known_extra]
    if unknown and not extra:
        blockers.append(("shape", f"extra required setting {', '.join(sorted(unknown))}"))
    if roles and not all(roles.values()):
        blockers.append(("shape", "a credential setting cannot be matched to its Api argument"))

    # --- scheme ---
    ev = _wire_evidence(ctx, tree)
    kinds = set(roles)
    decl = ""
    cands: list[str] = []
    matches: list[str] = []
    if not kinds:
        matches.append("auth.r13")
        decl = "NoAuth()"
    elif kinds == {"secret"}:
        env = roles["secret"] or "<SECRET_ENV>"
        if ev["bearer"]:
            matches.append("auth.r1")
            cands.append(f'Bearer(env="{env}")')
            decl = decl or cands[-1]
        headers = [_HEADER_CANON.get(str(h).lower(), h) for h in ev["headers"]]  # type: ignore[attr-defined]
        if headers or ev["token_prefix"]:
            hs = headers + (["Authorization"] if ev["token_prefix"] else [])
            if len(hs) == 1:
                prefix = ', prefix="Token "' if hs[0] == "Authorization" else ""
                cands.append(f'ApiKey(env="{env}", header="{hs[0]}"{prefix})')
                decl = decl or cands[-1]
            else:
                cands.append(f'ApiKey(env="{env}", header="<one of {", ".join(map(str, hs))}>")')
                decl = decl or cands[-1]
            matches.append("auth.r2")
        if ev["query"]:
            cands.append(f'ApiKey(env="{env}", query="{ev["query"][0]}")')  # type: ignore[index]
            decl = decl or cands[-1]
            matches.append("auth.r3")
    elif kinds == {"user", "password"}:
        user, pw = roles["user"] or "<USER_ENV>", roles["password"] or "<PASSWORD_ENV>"
        paths = ev["login_paths"]
        if ev["basic"]:
            matches.append("auth.r4")
            cands.append(f'Basic(user_env="{user}", password_env="{pw}")')
            decl = decl or cands[-1]
        frags = ev["login_fragments"]
        if paths or frags:
            matches.append("auth.r11")
            lp = paths[0] if len(paths) == 1 else "<login path>"  # type: ignore[index]
            if not paths:
                lp = f"<api root>{frags[0]}"  # type: ignore[index]
                blockers.append(
                    ("auth.r11", "login path only appears inside an f-string, so its API root prefix is unknown")
                )
            cands.append(f'SessionLogin(login_path="{lp}", user_env="{user}", password_env="{pw}")')
            decl = decl or cands[-1]
    elif kinds == {"client_id", "client_secret"} and ev["cc"]:
        matches.append("auth.r5")
        urls = ev["token_urls"]
        tu = urls[0] if len(urls) == 1 else "<token url>"  # type: ignore[index]
        decl = f'ClientCredentials(client_id_env="{roles["client_id"]}", secret_env="{roles["client_secret"]}", token_url="{tu}")'
        if len(urls) != 1:
            blockers.append(("auth.r5", "token URL is not one literal absolute URL in the connector"))
    elif ({"refresh"} <= kinds <= {"refresh", "client_id", "client_secret"}) and ev["refresh"]:
        matches.append("auth.r6")
        urls = ev["token_urls"]
        tu = urls[0] if len(urls) == 1 else "<token url>"  # type: ignore[index]
        parts = [f'refresh_env="{roles["refresh"]}"']
        if "client_id" in roles:
            parts.append(f'client_id_env="{roles["client_id"]}"')
        if "client_secret" in roles:
            parts.append(f'secret_env="{roles["client_secret"]}"')
        decl = f'RefreshToken({", ".join(parts)}, token_url="{tu}")'
        if len(urls) != 1:
            blockers.append(("auth.r6", "token URL is not one literal absolute URL in the connector"))
    an.matches = matches
    an.declaration = decl
    an.candidates = cands
    if len(matches) != 1:
        return

    # --- the Api constructor stays connector-owned ---
    if api_name and (url_env or matches[0] != "auth.r13"):
        param, reason = _client_param(ctx, tree, path, api_name)
        if not param:
            blockers.append((matches[0], reason))
    else:
        param = ""
    if matches[0] == "auth.r13" and not url_env:
        an.declaration = "delete auth.py"
    if blockers:
        return

    # --- strict: only the simple get_client shape is rewritten ---
    why = _strict_shape(tree, path)
    if why:
        blockers.append(("shape", f"auth.py is not the simple get_client shape ({why})"))
        return
    if matches[0] == "auth.r13" and not url_env:
        an.declaration = "delete auth.py"
        return
    flags = _singleton(tree)
    if flags:
        an.mods.append("auth.r12")
    an.text = _render(docstring, matches[0], decl, url_env, tls_name, plaintext_env, flags, param, api_name, path, ctx)


def _singleton(tree: ast.Module) -> bool:
    fn = next((f for f in tree.body if isinstance(f, ast.FunctionDef) and f.name == "get_client"), None)
    return fn is not None and any(isinstance(n, ast.Global) for n in ast.walk(fn))


def _strict_shape(tree: ast.Module, path: Path) -> str:
    """ "" when the module is exactly docstring, imports, logger, ``_client`` and one plain ``get_client()``."""
    for n in tree.body:
        ok = (
            isinstance(n, _ALLOWED_TOP)
            or (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))
            or (isinstance(n, ast.FunctionDef) and n.name == "get_client")
            or (
                isinstance(n, ast.Assign)
                and len(n.targets) == 1
                and isinstance(n.targets[0], ast.Name)
                and n.targets[0].id in {"logger", "_client"}
            )
        )
        if not ok:
            return f"defines {getattr(n, 'name', None) or ast.unparse(n)[:30]}"
    fns = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    if len(fns) != 1:
        return "several functions"
    fn = fns[0]
    if fn.args.args or fn.args.kwonlyargs or fn.args.posonlyargs:
        return "get_client takes parameters"
    flat: list[ast.stmt] = []
    flags: dict[str, bool] = {}
    _walk_body(fn.body, flat, flags)
    api_calls = 0
    for st in flat:
        if isinstance(st, ast.Expr) and isinstance(st.value, ast.Constant):
            continue
        if _is_guard(st):
            continue
        if isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name):
            value = st.value
            if _setting_call(value):
                continue
            if isinstance(value, ast.Call) and isinstance(value.func, ast.Name):
                if _tls_call(value):
                    if _tls_call(value)[1]:  # type: ignore[index]
                        return "TLS profile selector arguments"
                    continue
                if value.func.id[:1].isupper():
                    api_calls += 1
                    if not _plain_kwargs(value):
                        return "Api(...) arguments are not plain settings"
                    continue
        if isinstance(st, ast.Return):
            value = st.value
            if isinstance(value, ast.Name) and value.id == "_client":
                continue
            if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id[:1].isupper():
                api_calls += 1
                if not _plain_kwargs(value):
                    return "Api(...) arguments are not plain settings"
                continue
        return f"line {st.lineno}: {ast.unparse(st)[:40]}"
    return "" if api_calls == 1 else "no single Api(...) construction"


def _plain_kwargs(call: ast.Call) -> bool:
    if call.args:
        return False
    return all(isinstance(k.value, ast.Name) or _tls_call(k.value) for k in call.keywords)


def _render(
    docstring: str | None,
    scheme: str,
    decl: str,
    url_env: str,
    tls: str,
    plaintext_env: str,
    singleton: bool,
    param: str,
    api_name: str,
    path: Path,
    ctx: Ctx,
) -> str:
    cls = decl.split("(")[0]
    api_import = next(
        (
            ast.unparse(n)
            for n in ast.parse(path.read_text(encoding="utf-8")).body
            if isinstance(n, ast.ImportFrom) and any((a.asname or a.name) == api_name for a in n.names)
        ),
        "",
    )
    api_import = re.sub(r"^from \S+ import .*$", lambda m: m.group(0), api_import)
    doc = docstring.strip() if docstring else f"Authentication for {ctx.pkg_name}."
    lines = [
        f'"""{doc}"""',
        "",
        f"from agent_connector_sdk.auth.declare import {cls}, client_factory",
        "",
        api_import,
        "",
    ]
    lines.append("get_http_client = client_factory(")
    lines.append(f'    url_env="{url_env}",')
    lines.append(f"    auth={decl},")
    lines.append(f'    tls="{tls}",')
    if plaintext_env:
        lines.append(f'    allow_plaintext_env="{plaintext_env}",')
    lines.append(")")
    if singleton:
        lines.append("close_client = get_http_client.close")
    lines += [
        "",
        "",
        f"def get_client() -> {api_name}:",
        '    """The connector Api over the governed, declared HTTP client."""',
    ]
    lines.append(f"    return {api_name}({param}=get_http_client())")
    return "\n".join(lines) + "\n"


def _importers(ctx: Ctx) -> list[str]:
    hits: list[str] = []
    for base in (ctx.pkg, ctx.root / "tests"):
        if not base.is_dir():
            continue
        for p in base.rglob("*.py"):
            if p == ctx.pkg / "auth.py":
                continue
            if re.search(
                rf"\b{re.escape(ctx.pkg_name)}\.auth\b|from \.auth import|from \. import auth",
                p.read_text(encoding="utf-8", errors="replace"),
            ):
                hits.append(ctx.rel(p))
    return hits


def _scheme(ctx: Ctx, rule_id: str) -> None:
    an = analyse(ctx)
    if an is None:
        return
    if len(an.matches) != 1:
        if rule_id == SCHEME_RULES[0]:
            why = "several rules (" + ", ".join(an.matches) + ")" if an.matches else "no scheme rule"
            detail = f"no scheme rule / several rules: {why}"
            if len(an.candidates) > 1:
                detail += "; candidates: " + " | ".join(an.candidates)
            if an.blockers:
                detail += "; " + "; ".join(f"{r}: {t}" for r, t in an.blockers)
            ctx.note(rule_id, detail, an.path)
        return
    if an.matches[0] != rule_id:
        return
    if an.blockers or not (an.text or an.declaration == "delete auth.py"):
        own = [t for r, t in an.blockers if r in (rule_id, "shape")]
        other = sorted({r for r, _ in an.blockers if r not in (rule_id, "shape")})
        why = "; ".join(own) or ("blocked by " + ", ".join(other) if other else "not exact")
        ctx.note(rule_id, f"proposed {an.declaration or '?'}: {why}", an.path)
        return
    if an.declaration == "delete auth.py":
        users = _importers(ctx)
        if users:
            ctx.note(rule_id, f"proposed delete auth.py but it is imported by {', '.join(users[:3])}", an.path)
            return
        ctx.delete(an.path, rule_id)
        return
    ctx.write(an.path, an.text, rule_id)
    for mod in an.mods:
        if mod not in ctx.applied:
            ctx.applied.append(mod)


def _make(rule_id: str):
    def fn(ctx: Ctx) -> None:
        _scheme(ctx, rule_id)

    fn.__name__ = rule_id.replace(".", "_")
    return rule(rule_id)(fn)


for _rid in SCHEME_RULES:
    _make(_rid)


def _modifier(ctx: Ctx, rule_id: str) -> None:
    """Modifier rules are decided inside the rewrite; here they only report a blocker they own once."""
    an = analyse(ctx)
    if an is None or len(an.matches) != 1:
        return
    owned = [t for r, t in an.blockers if r == rule_id]
    if owned:
        ctx.note(rule_id, f"proposed {an.declaration}: " + "; ".join(owned), an.path)


def _make_modifier(rule_id: str):
    def fn(ctx: Ctx) -> None:
        _modifier(ctx, rule_id)

    fn.__name__ = rule_id.replace(".", "_")
    return rule(rule_id)(fn)


for _rid in MODIFIER_RULES:
    _make_modifier(_rid)
