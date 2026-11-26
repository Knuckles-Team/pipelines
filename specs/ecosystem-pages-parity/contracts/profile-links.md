# Profile component links seam

Provider: pipelines PIPE-PAGES-R014.5
Consumer: .github ORG-FRONT-R002.2

## Wire shape

`scripts/render_profile_links.py` renders the marker block of component links for the organization profile. It builds one level-1 link per entry of `ecosystem_components()` (`scripts/spec_dashboard_drilldown.py:14`). The organization site workflow runs it with `--write` on `profile/README.md` of the `.github` repository; it replaces the text between `<!-- profile-links:begin -->` and `<!-- profile-links:end -->`, markers the hub adds beside its spec-delivery block.

## Refusal codes

- `component-link-unresolved`: a component has no level-1 URL. The producer exits 1 and writes nothing.
- `profile-marker-missing`: a profile without the marker block is left unchanged and the producer exits 1.

## Authoritative types

The component list returned by `ecosystem_components()`. The `.github` repository keeps no second list.

## Test vectors

`tests/test_render_profile_links.py::test_profile_links_cover_components` holds the vectors on the pipelines side; the `.github` repository checks the written block with `tests/test_front_door.py::test_readme_spec_delivery_links_match_the_single_list`.
