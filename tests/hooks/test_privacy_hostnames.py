"""A method call such as ``ipmi.lan("print")`` is not an internal hostname literal (PIPE-GATES-R016.112)."""

from __future__ import annotations

import pytest

from pipelines_hooks.privacy.hosts import internal_endpoint_in_line

#: Deliberate leak examples are assembled at run time so the literal never sits in tracked source.
_LAN = "." + "lan"
_ARPA = "." + "arpa"
_INTERNAL = "." + "internal"
_USERS = "/" + "Users/"
_HOME = "/" + "home/"


@pytest.mark.spec("PIPE-GATES-R016.112")
def test_a_called_method_is_not_a_hostname() -> None:
    assert not internal_endpoint_in_line('return ipmi.lan("print", target=t)')
    assert not internal_endpoint_in_line('"lan_print": lambda: ipmi.lan("print"),')
    assert internal_endpoint_in_line(f"url = http://a{_LAN}:9180")
    assert internal_endpoint_in_line(f"host = ipmi{_LAN}")
    assert internal_endpoint_in_line(f"see gitlab{_ARPA} now")


@pytest.mark.spec("PIPE-GATES-R016.113")
def test_an_endpoint_route_literal_is_not_a_home_path() -> None:
    from pipelines_hooks.privacy.patterns import has_real_home_path

    assert not has_real_home_path(f'        endpoint = "{_USERS}AuthenticateByName"')
    assert not has_real_home_path(f"    endpoint='{_USERS}Me'")
    assert has_real_home_path(f'path = "{_USERS}jdoe/Documents"')
    assert has_real_home_path(f'cd "{_USERS}jdoe"')


@pytest.mark.spec("PIPE-GATES-R016.113")
def test_the_container_home_setting_is_not_a_home_path() -> None:
    from pipelines_hooks.privacy.patterns import has_real_home_path

    assert not has_real_home_path(f'home = "{_HOME}gramps"')
    assert has_real_home_path(f'shell = "{_HOME}gramps"')


@pytest.mark.spec("PIPE-GATES-R016.114")
def test_a_variable_reference_as_the_uri_secret_is_not_a_credential() -> None:
    from pipelines_hooks.privacy.patterns import credential_uri_leak

    ref = "$" + "{GITHUB_TOKEN}"
    url = "https://x-access-token:" + ref + "@github.com/"
    assert not credential_uri_leak("git config url." + url + ".insteadOf x")
    assert not credential_uri_leak("url = https://user:" + "$TOKEN" + "@host" + _INTERNAL + "/x")
    assert credential_uri_leak("url = https://user:" + "hunter2real" + "@host" + _INTERNAL + "/x")


@pytest.mark.spec("PIPE-GATES-R016.118")
def test_a_row_token_is_not_a_host_alias() -> None:
    from pipelines_hooks.privacy.patterns import machine_host_id_in_line

    for row in ('      "R138": {', '"row": "R153",', "R103-R117", "R101/R106/R116", "PIPE-CONNSPEC-R175 to R177"):
        assert not machine_host_id_in_line(row), row
    assert not machine_host_id_in_line('"tests/test_connector_consumer_r101_r115.py:72"')
    assert not machine_host_id_in_line("consumer_train_r153.json")
    for host in ("Deployed to " + "rw" + "710 today", "RW" + "710 box", "on R" + "820." + "arpa", "r" + "820 build"):
        assert machine_host_id_in_line(host), host


@pytest.mark.spec("PIPE-GATES-R016.118")
def test_a_repository_relative_persisted_path_is_not_a_machine_path() -> None:
    from pipelines_hooks.privacy.classify import classify_line

    def persisted(line: str) -> bool:
        return "persisted machine path" in classify_line(line, identifiers=frozenset(), deployment_doc=False)

    assert not persisted('"skill_path": "demo_mcp/skills/demo-mcp-development/SKILL.md",')
    assert not persisted('SOURCE_PATH = "${WORKSPACE}/x"')
    assert persisted('"skill_path": "/' + 'srv/checkouts/demo/SKILL.md",')
    assert persisted('"workspace_path": "~' + '/workspace"')
