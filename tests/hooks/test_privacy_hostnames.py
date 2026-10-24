"""A method call such as ``ipmi.lan("print")`` is not an internal hostname literal (PIPE-GATES-R016.112)."""

from __future__ import annotations

import pytest

from pipelines_hooks.privacy.hosts import internal_endpoint_in_line


@pytest.mark.spec("PIPE-GATES-R016.112")
def test_a_called_method_is_not_a_hostname() -> None:
    assert not internal_endpoint_in_line('return ipmi.lan("print", target=t)')
    assert not internal_endpoint_in_line('"lan_print": lambda: ipmi.lan("print"),')
    assert internal_endpoint_in_line("url = http://a.lan:9180")
    assert internal_endpoint_in_line("host = ipmi.lan")
    assert internal_endpoint_in_line("see gitlab.arpa now")


@pytest.mark.spec("PIPE-GATES-R016.113")
def test_an_endpoint_route_literal_is_not_a_home_path() -> None:
    from pipelines_hooks.privacy.patterns import has_real_home_path

    assert not has_real_home_path('        endpoint = "/Users/AuthenticateByName"')
    assert not has_real_home_path("    endpoint='/Users/Me'")
    assert has_real_home_path('path = "/Users/jdoe/Documents"')
    assert has_real_home_path('cd "/Users/jdoe"')


@pytest.mark.spec("PIPE-GATES-R016.113")
def test_the_container_home_setting_is_not_a_home_path() -> None:
    from pipelines_hooks.privacy.patterns import has_real_home_path

    assert not has_real_home_path('home = "/home/gramps"')
    assert has_real_home_path('shell = "/home/gramps"')


@pytest.mark.spec("PIPE-GATES-R016.114")
def test_a_variable_reference_as_the_uri_secret_is_not_a_credential() -> None:
    from pipelines_hooks.privacy.patterns import credential_uri_leak

    ref = "$" + "{GITHUB_TOKEN}"
    url = "https://x-access-token:" + ref + "@github.com/"
    assert not credential_uri_leak("git config url." + url + ".insteadOf x")
    assert not credential_uri_leak("url = https://user:" + "$TOKEN" + "@host.internal/x")
    assert credential_uri_leak("url = https://user:" + "hunter2real" + "@host.internal/x")
