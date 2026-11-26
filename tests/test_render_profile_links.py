"""The profile component links come from the one shared component list."""

from scripts import render_profile_links as producer
from scripts.spec_dashboard_drilldown import anchor_for, ecosystem_components

PROFILE = f"# Org\n\n{producer.BEGIN}\nstale\n{producer.END}\n\nafter\n"


# spec: PIPE-PAGES-R014.5
def test_profile_links_cover_components():
    rendered = producer.render_profile_links(PROFILE)
    for slug in ecosystem_components():
        assert f"]({anchor_for('repository', slug, slug)})" in rendered
    assert "stale" not in rendered and rendered.startswith("# Org") and rendered.endswith("after\n")
    assert producer.render_profile_links(rendered) == rendered  # repeatable
    assert rendered.count("](") == len(ecosystem_components())


def test_missing_marker_and_unresolved_component_are_refused(tmp_path, monkeypatch, capsys):
    readme = tmp_path / "README.md"
    readme.write_text("# Org\nno block\n")
    assert producer.main([str(readme), "--write"]) == 1
    assert readme.read_text() == "# Org\nno block\n"
    readme.write_text(PROFILE)
    monkeypatch.setitem(producer.REPOS, "medulla", ("medulla", "", ""))
    assert producer.main([str(readme), "--write"]) == 1
    assert "component-link-unresolved" in capsys.readouterr().err
    assert readme.read_text() == PROFILE
    monkeypatch.undo()
    assert producer.main([str(readme), "--write"]) == 0
    assert "profile-links:begin" in readme.read_text() and "Components:" in readme.read_text()
