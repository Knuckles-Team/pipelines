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
    assert "animation:ocean-drift 12s" in html
    assert "animation-duration:16s" in html and "animation-duration:20s" in html
    assert 'store.get("arbora-arch-ocean-motion")!=="off"' in html
    assert 'enabled&&!document.hidden?"running":"paused"' in html
    assert 'document.addEventListener("visibilitychange",oceanMotionState)' in html
    assert "motionPreference.matches||transparencyPreference.matches||forcedColorsPreference.matches" in html
    assert ".ocean-wave{animation:none!important}" in html
    assert 'button.setAttribute("aria-pressed",String(enabled))' in html


@pytest.mark.spec("PIPE-PAGES-R042")
def test_light_reading_text_contrasts_over_deepest_wave_composite() -> None:
    block = TEMPLATE.read_text().split(":root{", 1)[1].split("}", 1)[0]
    tokens = dict(re.findall(r"(--[\w-]+):\s*(#[\da-f]{6})", block))
    # Conservative fully overlapping wave color under the 76% reading plate.
    composite = "#" + "".join(f"{round(0.76 * a + 0.24 * b):02x}" for a, b in zip((255, 255, 255), (0, 0, 0)))
    for token in ("--fg", "--muted", "--faint", "--accent"):
        assert _contrast(tokens[token], composite) >= 4.5, (token, composite)


def _blend(front, back, alpha):
    return tuple(round(a * alpha + b * (1 - alpha)) for a, b in zip(front, back))


def _hex(channels):
    return "#" + "".join(f"{c:02x}" for c in channels)


def _ocean_bounds(block):
    colors = [
        tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))
        for value in re.findall(r"--ocean-(?:top|bottom):#([\da-f]{6})", block)
    ]
    opacity = float(re.search(r"--wave-opacity:([.\d]+)", block)[1])
    # Actual two opaque SVG fill colors; max three overlapping layers over the body gradient.
    from urllib.parse import unquote

    svg = unquote(TEMPLATE.read_text().split("data:image/svg+xml,", 1)[1].split('")', 1)[0])
    fills = [tuple(int(value[i : i + 2], 16) for i in (0, 2, 4)) for value in re.findall(r'fill="#([\da-f]{6})"', svg)]
    assert len(fills) == 2 and len(colors) == 2
    candidates = colors[:]
    for _ in range(3):
        candidates += [_blend(fill, back, opacity) for fill in fills for back in candidates[:]]
    return [tuple(fn(c[i] for c in candidates) for i in range(3)) for fn in (min, max)]


@pytest.mark.spec("PIPE-PAGES-R042")
def test_node_text_status_counts_and_part_counts_contrast_over_wave_bounds() -> None:
    html = TEMPLATE.read_text()
    for selector in (":root{", ':root[data-theme="dark"]{'):
        block = html.split(selector, 1)[1].split("}", 1)[0]
        tokens = dict(re.findall(r"(--[\w-]+):\s*(#[\da-f]{6})", block))
        tints = re.findall(
            r"--t-[\w-]+:rgba\((\d+),(\d+),(\d+),([.\d]+)\)", html.split(":root{", 1)[1].split("}", 1)[0]
        )
        assert len(tints) == 9
        assert ".canvas{background:rgb(255 255 255 / .10)}" in html
        for ocean in _ocean_bounds(block):
            ocean = _blend((255, 255, 255), ocean, 0.10)
            # The brightest lane endpoint is the conservative dark-text bound;
            # light theme also tests its lowest-opacity endpoint below.
            lane_surfaces = []
            for lane_endpoint in ("top", "bottom"):
                lane = re.search(r"--lane-" + lane_endpoint + r":rgba\((\d+),(\d+),(\d+),([.\d]+)\)", block)
                assert lane
                lane_surfaces.append(_blend(tuple(int(lane[i]) for i in (1, 2, 3)), ocean, float(lane[4])))
            ocean = tuple((max if selector != ":root{" else min)(p[i] for p in lane_surfaces) for i in range(3))
            for endpoint in ("top", "bottom"):
                match = re.search(r"--node-" + endpoint + r":rgba\((\d+),(\d+),(\d+),([.\d]+)\)", block)
                assert match
                material = _blend(tuple(int(match[i]) for i in (1, 2, 3)), ocean, float(match[4]))
                surfaces = [material] + [_blend(tuple(map(int, tint[:3])), material, float(tint[3])) for tint in tints]
                for surface in surfaces:
                    for name, color in tokens.items():
                        if name in ("--fg", "--muted", "--faint", "--accent") or name.startswith(("--s-", "--l-")):
                            assert _contrast(color, _hex(surface)) >= 4.5, (selector, endpoint, name, _hex(surface))


@pytest.mark.spec("PIPE-PAGES-R042")
def test_header_status_badges_contrast_on_stacked_translucent_surfaces() -> None:
    html = TEMPLATE.read_text()
    for selector in (":root{", ':root[data-theme="dark"]{'):
        block = html.split(selector, 1)[1].split("}", 1)[0]
        tokens = dict(re.findall(r"(--[\w-]+):\s*(#[\da-f]{6})", block))
        for ocean in _ocean_bounds(block):
            for surface in ("--glass-chrome", "--glass-control"):
                match = re.search(re.escape(surface) + r":rgb\((\d+) (\d+) (\d+) / ([.\d]+)\)", block)
                ocean = _blend(tuple(int(match[i]) for i in (1, 2, 3)), ocean, float(match[4]))
            for name, color in tokens.items():
                if name == "--fg" or name.startswith("--s-"):
                    assert _contrast(color, _hex(ocean)) >= 4.5, (selector, name, _hex(ocean))


@pytest.mark.spec("PIPE-PAGES-R042")
def test_canvas_labels_have_neutral_reading_plates_not_faded_unprotected_text() -> None:
    source = TEMPLATE.read_text()
    for label in ("z[0]", "lp.label"):
        assert "mapLabel(" + label + ".toUpperCase()" in source
    assert "ctx.globalAlpha=alpha; mapLabel(" in source
    assert "ctx.fillStyle=C.opaque?C.surface:C.nodeTop;rr(" in source
    assert "ctx.globalAlpha=alpha*0.8; rr(x-w/2" not in source


@pytest.mark.spec("PIPE-PAGES-R042")
def test_glass_and_ordinary_buttons_use_neutral_white_or_smoke_not_blue_fill() -> None:
    html = TEMPLATE.read_text()
    for selector in (":root{", ':root[data-theme="dark"]{'):
        block = html.split(selector, 1)[1].split("}", 1)[0]
        for name in ("glass-reading", "glass-control", "glass-chrome", "button-neutral", "button-hover"):
            match = re.search(r"--" + name + r":rgb\((\d+) (\d+) (\d+) /", block)
            assert match
            channels = [int(match[i]) for i in (1, 2, 3)]
            assert max(channels) - min(channels) <= 3, (selector, name)
        for name in ("node-top", "node-bottom"):
            match = re.search(r"--" + name + r":rgba\((\d+),(\d+),(\d+),", block)
            assert match
            channels = [int(match[i]) for i in (1, 2, 3)]
            assert max(channels) - min(channels) <= 3, (selector, name)


@pytest.mark.spec("PIPE-PAGES-R042")
def test_abstract_wallpaper_is_native_bounded_and_no_photo_is_active() -> None:
    from scripts.architecture_explorer.build import template_source

    source = template_source()
    assert "/*__OCEAN__*/" not in source
    assert "data:image/webp" not in source
    assert "Abstract ocean: native vector layers" in source
    assert "ctx.strokeStyle=C.edgeHalo;ctx.lineWidth=lw+2;ctx.stroke()" in source
    assert "ctx.shadowBlur" not in source and "ctx.filter" not in source
    assert "if(!C.opaque && C.tint[n.layer])" in source
    assert "ctx.strokeStyle=col" not in source


@pytest.mark.spec("PIPE-PAGES-R042")
def test_connectors_have_neutral_contrast_halo_against_any_photo_pixel() -> None:
    html = TEMPLATE.read_text()
    for selector, backdrop in ((":root{", 0), (':root[data-theme="dark"]{', 255)):
        block = html.split(selector, 1)[1].split("}", 1)[0]
        edge = re.search(r"--edge:(#[\da-f]{6})", block)
        halo = re.search(r"--edge-halo:rgba\((\d+),(\d+),(\d+),([.\d]+)\)", block)
        assert edge and halo
        alpha = float(halo[4])
        composite = "#" + "".join(f"{round(int(halo[i]) * alpha + backdrop * (1 - alpha)):02x}" for i in (1, 2, 3))
        assert _contrast(edge[1], composite) >= 3


@pytest.mark.spec("PIPE-PAGES-R042")
def test_root_band_heading_fits_existing_gutter_without_truncation() -> None:
    source = TEMPLATE.read_text()
    assert "L.kids[L.loop.around]" in source
    assert "available/Math.max(1,ctx.measureText(text).width)" in source
    assert "mapLabel(text, right, sy+fs*0.6,fs)" in source


@pytest.mark.spec("PIPE-PAGES-R042")
def test_swimlanes_are_bounded_shared_glass_panes_not_new_layout_or_blur() -> None:
    source = TEMPLATE.read_text()
    bands = source.split("function drawBands(", 1)[1].split("function drawZones(", 1)[0]
    assert "laneY=sy+2" in bands and "laneH=Math.max(1,sh-4)" in bands
    assert "C.laneTop" in bands and "C.laneBottom" in bands and "C.laneEdge" in bands
    assert "ctx.filter" not in bands and "shadowBlur" not in bands
    assert "mapLabel(text, right, sy+fs*0.6,fs)" in bands
    assert 'laneW=Math.max(1,n.id==="root"?W-16:sw-8)' in bands
    assert 'const key=n.id==="root"?["person","entry","gateway","control","core","server"][i]:n.layer;' in bands
