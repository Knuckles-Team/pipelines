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

    svgs = re.findall(r'data:image/svg\+xml,([^"\s]+)', TEMPLATE.read_text())
    fills = [
        tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))
        for svg in svgs
        for value in re.findall(r'fill="#([\da-f]{6})"', unquote(svg))
    ]
    assert len(fills) == 6 and len(colors) == 2
    # The three cached color layers only transform/fade. Include no wave, both
    # opacity extrema and the intermediate keyframe for every overlapping layer.
    candidates = colors[:]
    for _ in range(3):
        candidates += [
            _blend(fill, back, opacity * phase)
            for fill in fills
            for phase in (0.55, 0.775, 1)
            for back in candidates[:]
        ]
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
def test_canvas_labels_use_neutral_glyph_halos_instead_of_plates() -> None:
    source = TEMPLATE.read_text()
    assert 'caption(n,"zone",z[0]' in source
    assert 'caption(n,"loop",lp.label' in source
    assert "ctx.globalAlpha=a.alpha;ctx.strokeStyle=C.opaque?C.surface:C.edgeHalo" in source
    assert "ctx.strokeText(a.text,x,y)" in source
    assert "function mapLabel(" not in source


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
    assert "available/Math.max(1,...labels.map(text=>ctx.measureText(text).width))" in source
    assert 'caption(n,"band",text,left,sy+5,fs,alpha' in source


@pytest.mark.spec("PIPE-PAGES-R042")
def test_swimlanes_use_only_quiet_gutter_typography_and_short_markers() -> None:
    source = TEMPLATE.read_text()
    bands = source.split("function drawBands(", 1)[1].split("function drawZones(", 1)[0]
    assert "C.laneTop" not in source and "--lane-top" not in source
    assert "createLinearGradient" not in bands and "mapLabel(" not in bands and "rr(" not in bands
    assert 'caption(n,"band",text,left,sy+5,fs,alpha' in bands and "text=labels[i]" in bands
    assert "const fs=headingSize" in bands and "headingSize=Math.min(11,sw0*0.024)" in bands
    assert "sh*0.14" not in bands
    assert 'ctx.font="500 "+fs+"px "+C.display' in bands
    assert "ctx.strokeText(a.text,x,y)" in source
    assert "ctx.strokeStyle=C.opaque?C.surface:C.edgeHalo" in source
    assert "ctx.fillRect(x-12,y+a.fs*.5,7,1.5)" in source
    assert 'const key=n.id==="root"?["person","entry","gateway","control","core","server"][i]:n.layer;' in bands


@pytest.mark.spec("PIPE-PAGES-R042")
def test_gutter_heading_contrast_through_neutral_glyph_halo() -> None:
    html = TEMPLATE.read_text()
    for selector in (":root{", ':root[data-theme="dark"]{'):
        block = html.split(selector, 1)[1].split("}", 1)[0]
        fg = re.search(r"--fg:(#[\da-f]{6})", block)[1]
        halo = re.search(r"--edge-halo:rgba\((\d+),(\d+),(\d+),([.\d]+)\)", block)
        for ocean in _ocean_bounds(block):
            canvas = _blend((255, 255, 255), ocean, 0.10)
            background = _blend(tuple(int(halo[i]) for i in (1, 2, 3)), canvas, float(halo[4]))
            assert _contrast(fg, _hex(background)) >= 4.5


@pytest.mark.spec("PIPE-PAGES-R042")
def test_count_track_is_metric_based_and_bar_inset_is_capped() -> None:
    source = TEMPLATE.read_text()
    assert "barY=sy+sh-Math.max(3,Math.min(5,sh*0.04))" in source
    assert "countBaseline=barY-Math.max(1,countMetrics.actualBoundingBoxDescent||0)-3" in source
    assert "drawRich(countsLine(n),cx,countBaseline,sw-fc)" in source
    assert "by=barY, bh=barHeight" in source
    assert "by=sy+sh-Math.max(3,sh*0.06)" not in source


@pytest.mark.spec("PIPE-PAGES-R042")
def test_all_map_annotations_share_collision_aware_text_only_paint() -> None:
    source = TEMPLATE.read_text()
    assert "function mapLabel(" not in source
    zones = source.split("function drawZones(", 1)[1].split("function countsLine(", 1)[0]
    assert "toUpperCase()" not in zones
    assert "ctx.fillText(" not in zones
    for kind in ("zone", "loop", "flow"):
        assert f'caption(n,"{kind}",' in zones
    painter = source.split("function paintAnnotations(){", 1)[1].split("// Overview bands", 1)[0]
    assert "rr(" not in painter and "ctx.fill()" not in painter
    assert "annotationClear(r,used)" in painter
    assert 'placement:"deferred"' in painter and 'placement:"canvas"' in painter
    assert "fitText(" not in painter and "toUpperCase" not in painter
    assert 'reason:"space"' in painter and 'reason:"scale"' in painter
    assert 'id="annotations"' not in source and 'id="annotation-jump"' not in source


@pytest.mark.spec("PIPE-PAGES-R042")
def test_annotation_intersections_handle_segments_cards_and_labels() -> None:
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("node unavailable")
    source = TEMPLATE.read_text()
    functions = source.split("function intersects(", 1)[1].split("function caption(", 1)[0]
    script = (
        "function intersects("
        + functions
        + """
const assert=require('node:assert/strict');
let W=100,H=100,annotationRects=[],annotationSegments=[];
const box=[20,20,20,10];
for(const [a,b] of [[[0,25],[80,25]],[[25,0],[25,80]],[[0,0],[80,80]],[[25,25],[25,25]]])assert(segmentHitsRect(a,b,box));
for(const [a,b] of [[[0,0],[10,10]],[[0,31],[80,31]],[[41,0],[41,80]]])assert(!segmentHitsRect(a,b,box));
assert(annotationClear(box,[]));
annotationRects=[[25,25,30,30]];assert(!annotationClear(box,[]));
annotationRects=[];assert(!annotationClear(box,[[18,19,10,10]]));
// Two glyph halos need clearance on both labels, not just the incoming label.
assert(!annotationClear(box,[[45,20,20,10]]));
assert(annotationClear(box,[[49,20,20,10]]));
annotationSegments=[[[0,25],[100,25]]];assert(!annotationClear(box,[]));
assert(!annotationClear([-1,20,10,10],[]));
"""
    )
    subprocess.run([node, "-e", script], check=True, capture_output=True, text=True)


@pytest.mark.spec("PIPE-PAGES-R042")
def test_captions_are_native_progressive_and_full_text_stays_in_existing_details() -> None:
    source = TEMPLATE.read_text()
    assert "annotation-rail" not in source and "annotation-jump" not in source
    assert "Map annotations" not in source
    assert '"External systems and connectors":"External Integrations"' in source
    assert '"Self-evolution loop: evaluate, promote, roll back":"Self-Evolution"' in source
    assert "a.fs<9" in source
    assert "a.text.length>36" in source
    assert 'placement:"deferred"' in source
    assert "function diagramContext(n)" in source
    assert "Diagram context: " in source
    assert "text.push(L.loop.label)" in source and "text.push(z[0])" in source
    assert 'class:"desc",text:n.description+' in source
    assert 'el("h3",{text:"Wired with"})' in source


@pytest.mark.spec("PIPE-PAGES-R042")
def test_native_caption_scale_and_collision_deferral_preserve_original_copy() -> None:
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("node unavailable")
    source = TEMPLATE.read_text()
    functions = "function intersects(" + source.split("function intersects(", 1)[1].split("// Overview bands", 1)[0]
    script = (
        """
const assert=require('node:assert/strict');
let W=500,H=300,annotations=[],annotationRects=[],annotationSegments=[],annotationEvidence=[],dirty=false;
const $=()=>({addEventListener(){}}),C={display:'Inter',edgeHalo:'#fff',fg:'#222'},ink=[];
const ctx={save(){},restore(){},measureText:t=>({width:t.length*6,actualBoundingBoxAscent:0,actualBoundingBoxDescent:10}),strokeText(){},fillText:t=>ink.push(t),fillRect(){}};
"""
        + functions
        + """
const n={id:'test'};
caption(n,'flow','facts',100,100,4,1);paintAnnotations();
assert.equal(annotationEvidence[0].reason,'scale');assert.deepEqual(ink,[]);
annotations=[];caption(n,'flow','facts',100,100,10,1);paintAnnotations();
assert.equal(annotationEvidence[0].placement,'canvas');assert.deepEqual(ink,['facts']);
annotations=[];ink.length=0;annotationRects=[[90,50,100,100]];
caption(n,'flow','facts',100,100,10,1);paintAnnotations();
assert.equal(annotationEvidence[0].reason,'space');assert.deepEqual(ink,[]);
annotations=[];annotationRects=[];
caption(n,'loop','Self-evolution loop: evaluate, promote, roll back',100,100,11,1);paintAnnotations();
assert.equal(annotationEvidence[0].text,'Self-Evolution');
assert.equal(annotationEvidence[0].fullText,'Self-evolution loop: evaluate, promote, roll back');
assert.deepEqual(ink,['Self-Evolution']);
"""
    )
    subprocess.run([node, "-e", script], check=True, capture_output=True, text=True)


@pytest.mark.spec("PIPE-PAGES-R042")
def test_annotation_paint_restores_canvas_styles_between_repeated_frames() -> None:
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("node unavailable")
    source = TEMPLATE.read_text()
    functions = "function intersects(" + source.split("function intersects(", 1)[1].split("// Overview bands", 1)[0]
    script = (
        """
const assert=require('node:assert/strict');
let W=500,H=300,annotations=[],annotationRects=[],annotationSegments=[],annotationEvidence=[],dirty=false;
const $=()=>({addEventListener(){}}),C={display:'Inter',edgeHalo:'#fff',fg:'#222'},ink=[],stack=[];
const keys=['font','textAlign','textBaseline','globalAlpha','strokeStyle','fillStyle','lineWidth','lineJoin'];
const styles=()=>Object.fromEntries(keys.map(key=>[key,ctx[key]]));
const ctx={font:'13px sans-serif',textAlign:'center',textBaseline:'alphabetic',globalAlpha:.7,strokeStyle:'#123',fillStyle:'#456',lineWidth:2,lineJoin:'miter',
 save(){stack.push(styles());},restore(){Object.assign(this,stack.pop());},
 measureText:t=>({width:t.length*6,actualBoundingBoxAscent:0,actualBoundingBoxDescent:10}),strokeText(){},fillText(t,x,y){ink.push({t,x,y,styles:styles()});},fillRect(){}};
"""
        + functions
        + """
caption({id:'test'},'loop','Self-evolution loop: evaluate, promote, roll back',100,100,11,1);
const original=styles();paintAnnotations();
assert.deepEqual(styles(),original);assert.equal(stack.length,0);
const first=JSON.stringify({ink,labels:annotationEvidence});ink.length=0;paintAnnotations();
assert.equal(JSON.stringify({ink,labels:annotationEvidence}),first);
assert.deepEqual(styles(),original);assert.equal(ctx.lineJoin,'miter');assert.equal(stack.length,0);
ctx.measureText=()=>{throw Error('measurement failed');};
assert.throws(()=>paintAnnotations(),/measurement failed/);assert.deepEqual(styles(),original);assert.equal(stack.length,0);
"""
    )
    subprocess.run([node, "-e", script], check=True, capture_output=True, text=True)


@pytest.mark.spec("PIPE-PAGES-R042")
def test_progress_fills_contrast_on_actual_tinted_glass_and_have_distinct_hues() -> None:
    import colorsys

    source = TEMPLATE.read_text()
    tints = re.findall(r"--t-[\w-]+:rgba\((\d+),(\d+),(\d+),([.\d]+)\)", source.split(":root{", 1)[1].split("}", 1)[0])
    for selector in (":root{", ':root[data-theme="dark"]{'):
        block = source.split(selector, 1)[1].split("}", 1)[0]
        tokens = dict(re.findall(r"(--[\w-]+):\s*(#[\da-f]{6})", block))
        colors = [tokens[f"--p-{state}"] for state in ("verified", "landed", "specified", "retired")]
        hues = []
        for color in colors:
            rgb = tuple(int(color[i : i + 2], 16) / 255 for i in (1, 3, 5))
            hue, saturation, _ = colorsys.rgb_to_hsv(*rgb)
            assert saturation >= 0.14
            hues.append(hue * 360)
            assert _contrast(color, tokens["--surface"]) >= 3
        for i, hue in enumerate(hues):
            for other in hues[i + 1 :]:
                assert min(abs(hue - other), 360 - abs(hue - other)) >= 35
        for ocean in _ocean_bounds(block):
            canvas = _blend((255, 255, 255), ocean, 0.10)
            for endpoint in ("top", "bottom"):
                match = re.search(r"--node-" + endpoint + r":rgba\((\d+),(\d+),(\d+),([.\d]+)\)", block)
                material = _blend(tuple(int(match[i]) for i in (1, 2, 3)), canvas, float(match[4]))
                surfaces = [material] + [_blend(tuple(map(int, tint[:3])), material, float(tint[3])) for tint in tints]
                for surface in surfaces:
                    for color in colors:
                        assert _contrast(color, _hex(surface)) >= 3, (selector, endpoint, color, _hex(surface))
    assert "ctx.fillStyle=C.progress[s]" in source
    assert 'C.progress[s]=g("--p-"+s.toLowerCase())' in source
    assert "--p-verified:CanvasText; --p-landed:Highlight;" in source


@pytest.mark.spec("PIPE-PAGES-R042")
def test_top_level_progress_growth_preserves_bottom_edge_and_metric_count_gap() -> None:
    source = TEMPLATE.read_text()
    assert 'topLevel=parentOf[n.id]==="root"' in source
    assert "barHeight=baseBarHeight*(topLevel?1.65:1)" in source
    assert "barY=sy+sh-Math.max(3,Math.min(5,sh*0.04))-(barHeight-baseBarHeight)" in source
    assert "countBaseline=barY-Math.max(1,countMetrics.actualBoundingBoxDescent||0)-3" in source
    for height in (15, 32, 44, 84, 194, 600, 2000):
        base = max(1.5, min(3, height * 0.02))
        old_top = height - max(3, min(5, height * 0.04))
        thick = base * 1.65
        new_top = old_top - (thick - base)
        assert new_top + thick == pytest.approx(old_top + base)
        assert thick / base == pytest.approx(1.65)
        assert new_top >= 0


@pytest.mark.spec("PIPE-PAGES-R042")
def test_progress_summary_is_a_full_name_responsive_color_key() -> None:
    source = TEMPLATE.read_text()
    assert "repeat(auto-fit,minmax(min(100%,145px),1fr))" in source
    assert ".stat .total{grid-column:1/-1}" in source
    assert ".stat span{overflow:visible;white-space:normal;overflow-wrap:normal}" in source
    assert '"aria-label":"Progress status legend and counts"' in source
    assert 'text:"Progress status · color key"' in source
    for state in ("Verified", "Landed", "Specified", "Retired"):
        assert '"' + state + '"' in source
    assert 'class:"status-swatch","aria-hidden":"true"' in source


@pytest.mark.spec("PIPE-PAGES-R042")
def test_ocean_color_variance_is_backdrop_only_slow_compositor_opacity() -> None:
    source = TEMPLATE.read_text()
    assert "ocean-tide 48s ease-in-out infinite alternate" in source
    assert "animation-duration:16s,56s" in source and "animation-duration:20s,64s" in source
    assert "@keyframes ocean-tide{from{opacity:calc(var(--wave-opacity)*.55)}to{opacity:var(--wave-opacity)}}" in source
    assert "hue-rotate" not in source
    assert source.count("data:image/svg+xml,") == 3
    assert ':root[data-ocean-motion="running"] .ocean-wave{animation-play-state:running}' in source
    assert ".ocean-wave{animation:none!important}" in source
