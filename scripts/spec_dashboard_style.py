"""Drawing-sheet style: one inline stylesheet, light and dark paper, no external assets."""

TOKENS = (':root{--paper:#fbfbf9;--ink:#1c1f24;--rule:#c8ccd2;--soft:#e6e8eb;--muted:#6a707a;'
          '--blue:#1f5fbf;--fill:#e3ecf8;--red:#c4302b;--row:#f3f4f5;'
          '--sans:"IBM Plex Sans","Inter","Segoe UI",system-ui,sans-serif;'
          '--mono:"IBM Plex Mono","JetBrains Mono",ui-monospace,"SFMono-Regular",Menlo,Consolas,monospace}')
DARK = ('--paper:#15171a;--ink:#e4e5e2;--rule:#3b4047;--soft:#2a2e34;--muted:#9aa1ab;'
        '--blue:#79a8ff;--fill:#1d2b40;--red:#ff7a70;--row:#1b1e22')
THEME = (TOKENS + '@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){' + DARK + '}}'
         ':root[data-theme="dark"]{' + DARK + '}')

FRAME = ('*{box-sizing:border-box}html,body{margin:0;background:var(--paper);color:var(--ink)}'
         'body{font:13px/1.45 var(--sans);padding:16px}a{color:var(--blue)}'
         '.frame{position:relative;border:1px solid var(--rule);padding:22px;max-width:1760px;margin:0 auto}'
         '.zones{position:absolute;display:flex;font:10px var(--mono);color:var(--muted)}'
         '.zones span{flex:1;display:flex;align-items:center;justify-content:center}'
         '.zones.h{left:22px;right:22px;height:22px}.zones.h span+span{border-left:1px solid var(--rule)}'
         '.zones.v{top:22px;bottom:22px;width:22px;flex-direction:column}.zones.v span+span{border-top:1px solid var(--rule)}'
         '.top{top:0}.bottom{bottom:0}.left{left:0}.right{right:0}'
         '.sheet{border:1px solid var(--rule);padding:22px;display:grid;grid-template-columns:repeat(12,minmax(0,1fr));'
         'gap:22px;align-items:stretch}')

PANEL = ('.panel{grid-column:span 4;border:1px solid var(--ink);min-width:0;background:var(--paper)}'
         '.w3{grid-column:span 3}.w5{grid-column:span 5}.w6{grid-column:span 6}.w7{grid-column:span 7}'
         '.w9{grid-column:span 9}.w12{grid-column:span 12}'
         '.bar{display:flex;align-items:stretch;border-bottom:1px solid var(--ink);min-height:32px}'
         '.tab{background:var(--ink);color:var(--paper);font:600 13px var(--mono);width:32px;display:flex;'
         'align-items:center;justify-content:center;flex:none}'
         '.bar h2{font:600 15px var(--sans);margin:0;padding:6px 12px;flex:1;align-self:center}'
         '.cap{font:10.5px var(--mono);color:var(--muted);padding:0 12px;align-self:center;text-align:right}'
         '.body{padding:14px 16px}.note{color:var(--muted);font-size:11.5px;border-top:1px solid var(--soft);'
         'padding-top:8px;margin:12px 0 0}.note p{margin:0 0 3px}'
         '.mono,code{font-family:var(--mono);font-size:12px}.ok{color:var(--blue)}.no{color:var(--red)}'
         'h3{font:600 12.5px var(--sans);margin:14px 0 6px}h3:first-child{margin-top:0}')

TABLES = ('.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%}'
          'th{font:500 10.5px var(--mono);color:var(--muted);text-align:left;padding:6px 8px;'
          'border-bottom:1px solid var(--rule);white-space:nowrap}'
          'td{padding:6px 8px;border-bottom:1px solid var(--soft);vertical-align:top}'
          'tbody tr:nth-child(odd){background:var(--row)}td.n,th.n{text-align:right;font-family:var(--mono)}'
          '.specs small{display:block;color:var(--muted);font-size:12px}td.mono:first-child,.specs .mono,td:last-child .ok,td:last-child .no{white-space:nowrap}'
          'details{margin-top:10px;border-top:1px solid var(--soft);padding-top:8px}'
          'summary{cursor:pointer;font:600 12.5px var(--sans)}summary .mono{color:var(--muted);font-weight:400}')

TREE = ('.root{border:1px solid var(--blue);background:var(--fill);text-align:center;padding:8px;margin:0 auto;'
        'width:min(260px,100%)}.root b{display:block;font:600 15px var(--sans)}.root span{color:var(--muted);font-size:11.5px}'
        '.stem{height:14px;border-left:1px solid var(--ink);margin-left:50%}'
        '.branches{position:relative;display:grid;grid-template-columns:1fr 1fr;gap:16px;padding-top:14px}'
        '.branches:before{content:"";position:absolute;top:0;left:25%;right:25%;border-top:1px solid var(--ink)}'
        '.branches>div{position:relative}.branches>div:before{content:"";position:absolute;top:-14px;height:14px;left:50%;'
        'border-left:1px solid var(--ink)}'
        '.node{border:1px solid var(--ink);text-align:center;font-weight:600;padding:5px}'
        '.leaves{list-style:none;margin:6px 0 0 8px;padding:0 0 0 10px;border-left:1px solid var(--ink)}'
        '.leaves li{position:relative;padding:3px 0 3px 8px;display:flex;justify-content:space-between;gap:8px}'
        '.leaves li:before{content:"";position:absolute;left:-10px;top:12px;width:12px;border-top:1px solid var(--ink)}'
        '.leaves small{display:block;color:var(--muted);font-size:11px}')

LIMITS = ('.limit{margin:0 0 12px}.limit .head{display:flex;justify-content:space-between;gap:8px}'
          '.limit .head span{font:11.5px var(--mono);color:var(--blue);white-space:nowrap}'
          '.track{position:relative;height:12px;border:1px solid var(--rule);margin-top:4px}'
          '.track i{position:absolute;left:0;top:0;bottom:0;background:var(--fill);border-right:2px solid var(--blue)}'
          '.ticks{position:relative;height:16px;font:9.5px var(--mono);color:var(--muted)}'
          '.ticks span{position:absolute;top:2px;transform:translateX(-50%)}.ticks span:first-child{transform:none}'
          '.ticks span.end{transform:translateX(-100%)}')

CHARTS = ('.charts{display:grid;grid-template-columns:1fr 1fr;gap:6px 18px}figure{margin:0}'
          'figcaption{font:600 12px var(--sans);margin:4px 0}svg{width:100%;height:auto;display:block}'
          'svg text{font:9.5px var(--mono);fill:var(--muted)}.grid{stroke:var(--soft)}.axis{stroke:var(--rule)}'
          '.scope{stroke:var(--muted);stroke-dasharray:4 3;fill:none;stroke-width:1.2}'
          '.remain{stroke:var(--blue);fill:none;stroke-width:1.6}.vbar{fill:var(--fill);stroke:var(--blue);stroke-width:1}'
          '.timeline{position:relative;display:flex;justify-content:space-between;gap:6px;padding-top:10px}'
          '.timeline:before{content:"";position:absolute;left:6%;right:6%;top:44px;border-top:1px solid var(--ink)}'
          '.mile{flex:1;text-align:center;position:relative;font-size:11.5px;color:var(--muted)}'
          '.mile b{display:block;font:600 13px var(--mono);color:var(--ink);margin-bottom:10px}'
          '.mile i{display:block;width:11px;height:11px;border:1.5px solid var(--ink);border-radius:50%;'
          'background:var(--paper);margin:0 auto 8px}')

BLOCK = ('.block{grid-column:span 3;border:1px solid var(--ink);display:grid;grid-template-columns:1fr 1fr}'
         '.block div{padding:6px 10px;border-top:1px solid var(--ink);min-width:0;overflow-wrap:anywhere}'
         '.block div:nth-child(even){border-left:1px solid var(--ink)}.block .title{grid-column:span 2;border-top:0}'
         '.block small{display:block;font:10px var(--mono);color:var(--muted)}.block .title b{font-size:16px}')

PHONE = ('@media (max-width:1100px){.sheet{grid-template-columns:repeat(6,minmax(0,1fr))}'
         '.panel,.w3,.w5,.w6,.w7,.w9,.block{grid-column:span 6}}'
         '@media (max-width:620px){body{padding:16px 8px}.frame{padding:14px}.zones.h{left:14px;right:14px;height:14px}'
         '.zones.v{top:14px;bottom:14px;width:14px}.zones{font-size:8px}.sheet{padding:10px;gap:14px}'
         '.body{padding:12px}.charts,.branches{grid-template-columns:1fr}.timeline{flex-wrap:wrap}'
         '.timeline:before,.branches:before{display:none}.mile{flex:1 1 40%}.cap{display:none}}')

STYLE = '<style>' + THEME + FRAME + PANEL + TABLES + TREE + LIMITS + CHARTS + BLOCK + PHONE + '</style>'


def zones():
    """Drawing-sheet zone markers: columns 1-8 on top and bottom, rows A-D on the sides."""
    columns = ''.join(f'<span>{index}</span>' for index in range(1, 9))
    rows = ''.join(f'<span>{letter}</span>' for letter in 'ABCD')
    return ''.join(f'<div class="zones {axis} {side}" aria-hidden="true">{cells}</div>'
                   for axis, side, cells in [('h', 'top', columns), ('h', 'bottom', columns),
                                             ('v', 'left', rows), ('v', 'right', rows)])


def panel(letter, title, *, caption, body, width=''):
    """One lettered sheet panel. The caller escapes every argument."""
    return (f'<section class="panel {width}" aria-labelledby="panel-{letter}"><div class="bar">'
            f'<span class="tab">{letter}</span><h2 id="panel-{letter}">{title}</h2>'
            f'<span class="cap">{caption}</span></div><div class="body">{body}</div></section>')


def mark(positive, word):
    """A glyph plus a word, so the meaning never depends on colour alone."""
    glyph, css = ('&#10003;', 'ok') if positive else ('&#10005;', 'no')
    return f'<span class="{css}">{glyph} {word}</span>'
