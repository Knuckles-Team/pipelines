"""Render the organization profile's component links (PIPE-PAGES-R014.5).

The organization site workflow runs this against ``profile/README.md`` of the hub repository. It writes one
level-1 link per entry of ``ecosystem_components()`` between the ``profile-links`` marker comments and keeps
no second component list. A component without a level-1 URL, or a profile without the marker block, is
refused: nothing is written and the exit status is 1.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spec_dashboard_drilldown import REPOS, anchor_for, ecosystem_components

BEGIN, END = "<!-- profile-links:begin -->", "<!-- profile-links:end -->"
BLOCK = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.S)


class ProfileLinkError(ValueError):
    """The block cannot be rendered; ``code`` is the refusal code of the seam contract."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code


def component_links() -> str:
    """One level-1 link per ecosystem component, in the shared list's order."""
    links = []
    for slug in ecosystem_components():
        url = anchor_for("repository", slug, slug)
        name = REPOS[slug][2]
        if not name or not url.startswith("https://"):
            raise ProfileLinkError("component-link-unresolved", f"component {slug!r} has no level-1 URL")
        links.append(f"**[{name}]({url})**")
    return "Components: " + " · ".join(links)


def render_profile_links(readme: str) -> str:
    """``readme`` with the marker block replaced by the component links."""
    if not BLOCK.search(readme):
        raise ProfileLinkError("profile-marker-missing", f"the profile has no {BEGIN} ... {END} block")
    block = f"{BEGIN}\n{component_links()}\n{END}"
    return BLOCK.sub(lambda _: block, readme, count=1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("readme", type=Path, help="profile/README.md of the organization hub repository")
    parser.add_argument("--write", action="store_true", help="rewrite the file; the default prints the result")
    arguments = parser.parse_args(argv)
    try:
        rendered = render_profile_links(arguments.readme.read_text(encoding="utf-8"))
    except (ProfileLinkError, OSError) as exc:
        print(f"render_profile_links: {exc}", file=sys.stderr)
        return 1
    if arguments.write:
        arguments.readme.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
