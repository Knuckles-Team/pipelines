"""Site navigation for the spec-delivery page: skip link, header bar, repository menu."""

import html

if __package__:
    from .spec_dashboard_drilldown import anchor_for, ecosystem_components
else:
    from spec_dashboard_drilldown import anchor_for, ecosystem_components

__all__ = ["skip_link", "site_nav"]


def skip_link():
    return '<a class="skip" href="#main">Skip to main content</a>'


def repository_item(repo, current):
    mark = ' aria-current="true"' if repo == current else ""
    return f'<li><a href="{html.escape(anchor_for("repository", repo, repo))}"{mark}>{html.escape(repo)}</a></li>'


def site_nav(repository):
    """Return the Site landmark; links come from the one core repository list."""
    name = repository.split("/")[-1]
    items = "".join(repository_item(repo, name) for repo in ecosystem_components())
    return (
        '<nav aria-label="Site" class="site"><a class="brand" href="../">' + html.escape(name) + "</a>"
        '<a href="../">Documentation</a><a href="" aria-current="page">Spec delivery</a>'
        '<details class="repos"><summary>Repositories</summary><ul>' + items + "</ul></details></nav>"
    )
