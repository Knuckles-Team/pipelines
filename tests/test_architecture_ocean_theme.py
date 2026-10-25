"""Presentation-only ocean materials retain inexpensive, accessible map rendering."""

from pathlib import Path
import re

import pytest

TEMPLATE = Path(__file__).parents[1] / "scripts/architecture_explorer/template.html"


def _contrast(a: str, b: str) -> float:
    def luminance(value: str) -> float:
        channels = [int(value[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return sum(c * weight for c, weight in zip(linear, (0.2126, 0.7152, 0.0722)))

    low, high = sorted((luminance(a), luminance(b)))
    return (high + 0.05) / (low + 0.05)


@pytest.mark.spec("PIPE-PAGES-R042")
def test_ocean_text_and_status_palette_has_readable_contrast() -> None:
    html = TEMPLATE.read_text()
    for selector in (":root{", ':root[data-theme="dark"]{'):
        block = html.split(selector, 1)[1].split("}", 1)[0]
        tokens = dict(re.findall(r"(--[\w-]+):\s*(#[\da-f]{6})", block))
        for background in ("--sheet", "--surface", "--band-a", "--band-b"):
            for foreground in ("--fg", "--muted", "--faint", "--accent"):
                assert _contrast(tokens[foreground], tokens[background]) >= 4.5, (selector, foreground, background)
        statuses = [tokens[f"--s-{status}"] for status in ("verified", "landed", "specified", "retired")]
        assert len(set(statuses)) == 4
        for color in statuses:
            assert _contrast(color, tokens["--surface"]) >= 4.5


@pytest.mark.spec("PIPE-PAGES-R042")
def test_ocean_materials_have_no_network_fonts_or_expensive_node_effects() -> None:
    html = TEMPLATE.read_text()
    assert "fonts.googleapis.com" not in html
    assert "fonts.gstatic.com" not in html
    assert "header.top,.toolbar,.panel{backdrop-filter:blur(16px) saturate(115%)}" in html
    assert "ctx.filter" not in html
    assert "ctx.shadowBlur" not in html
    assert "--font-body:Inter,ui-sans-serif,system-ui" in html
    assert "material.addColorStop(0,C.opaque?C.surface:C.nodeTop)" in html
    assert "ctx.clearRect(0,0,W,H)" in html
    assert "ctx.globalAlpha=alpha*(0.10-0.05*op)" not in html
    assert "ctx.strokeStyle=col" not in html
    assert ".panel{background:var(--glass-reading)}" in html
    assert "data:image/svg+xml," in html
    assert "/*__INTER__*/" in html


@pytest.mark.spec("PIPE-PAGES-R042")
def test_ocean_preferences_have_opaque_reduced_motion_and_forced_color_fallbacks() -> None:
    html = TEMPLATE.read_text()
    assert "@media (prefers-reduced-transparency: reduce)" in html
    assert "@media (prefers-reduced-motion: reduce)" in html
    assert "transition:none!important;animation:none!important" in html
    assert "@media (forced-colors: active)" in html
    assert "--fg:CanvasText" in html and "--focus:Highlight" in html
    assert 'window.matchMedia(query).addEventListener("change",readColors)' in html
    assert 'opaque:window.matchMedia("(prefers-reduced-transparency: reduce)")' in html
    assert "select:focus-visible,summary:focus-visible,canvas:focus-visible" in html


@pytest.mark.spec("PIPE-PAGES-R042")
def test_ocean_primary_controls_are_translucent_unoutlined_and_touch_sized() -> None:
    html = TEMPLATE.read_text()
    assert "--button-neutral:rgb(" in html
    assert "border-color:transparent;box-shadow:none;border-radius:12px;min-height:44px" in html
    assert ".zoom .btn{width:44px;" in html
    assert ".btn,.chip,.kids button,.links button{border-color:ButtonText}" in html
    assert "outline:3px solid var(--focus)" in html


@pytest.mark.spec("PIPE-PAGES-R042")
def test_glass_uses_bundled_overstory_inter_and_sans_canvas_labels() -> None:
    from scripts.architecture_explorer.build import template_source

    source = template_source()
    assert "/*__INTER__*/" not in source
    assert "src:url(data:font/woff2;base64," in source
    assert (TEMPLATE.parent / "assets/Inter-LICENSE.txt").is_file()
    assert "Copyright (c) 2016 The Inter Project Authors" in source
    assert "SIL OPEN FONT LICENSE Version 1.1" in source
    assert "PREAMBLE" in source and "DISCLAIMER" in source
    drawing = source.split("function drawNode(", 1)[1].split("function drawInner(", 1)[0]
    assert "C.mono" not in drawing
    assert "C.body" in drawing and "C.display" in drawing
    assert "C.nodeTop" in drawing and "C.nodeBottom" in drawing


@pytest.mark.spec("PIPE-PAGES-R042")
def test_glass_reading_surfaces_protect_footer_and_search_contrast() -> None:
    html = TEMPLATE.read_text()
    assert '<div class="map-notes">' in html
    assert ".map-notes{padding:8px 12px;" in html
    assert ".search input::placeholder{color:var(--muted);opacity:1}" in html
    assert ".map-notes,.panel .ph{background:Canvas" in html


@pytest.mark.spec("PIPE-PAGES-R042")
def test_ocean_motion_is_shared_bounded_and_accessible() -> None:
    html = TEMPLATE.read_text()
    assert html.count('<span class="ocean-wave">') == 3
    assert 'class="ocean-scene" aria-hidden="true"' in html
    assert "pointer-events:none;contain:strict" in html
    assert "animation:ocean-drift 42s" in html
    assert "animation-duration:58s" in html and "animation-duration:73s" in html
    assert 'store.get("arbora-arch-ocean-motion")!=="off"' in html
    assert 'enabled&&!document.hidden?"running":"paused"' in html
    assert 'document.addEventListener("visibilitychange",oceanMotionState)' in html
    assert "motionPreference.matches||transparencyPreference.matches||forcedColorsPreference.matches" in html
    assert ".ocean-wave{animation:none!important}" in html
    assert 'button.setAttribute("aria-pressed",String(enabled))' in html
