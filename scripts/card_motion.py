"""Shared terminal-card motion, promoted from the approved local preview.

Content stays visible at rest; delayed step-start entries avoid floating-point
rounding at steps(1,end)'s final boundary. Snake boot shares the route clock,
so board reset, READY/GO and the eaten counter stay synchronized each loop.
"""
import re
import xml.etree.ElementTree as E
NS = 'http://www.w3.org/2000/svg'
E.register_namespace('', NS)

def tag(n):
    return n.tag.split('}')[-1]

def node(t, **attrs):
    return E.Element('{' + NS + '}' + t, {k: str(v) for k, v in attrs.items()})
CSS = """
.card-reveal {opacity:1;animation:card-on .01s step-start backwards;animation-delay:var(--delay,0s)}
.card-bar {transform-box:fill-box;transform-origin:left center;animation:card-grow .95s ease-out backwards;animation-delay:var(--delay,0s)}
.card-column {transform-box:fill-box;transform-origin:center bottom;animation:card-rise .95s ease-out backwards;animation-delay:var(--delay,0s)}
@keyframes card-on {from {opacity:0} to {opacity:1}}
/* A visible resting state avoids steps(1,end) rounding below the final step. */
.ok, .rv {opacity:1;animation-fill-mode:backwards;animation-timing-function:step-start}
@keyframes on {from {opacity:0} to {opacity:1}}
@keyframes card-grow {from {transform:scaleX(0)}}
@keyframes card-rise {from {transform:scaleY(0)}}
@media(prefers-reduced-motion:reduce){.card-reveal{opacity:1;animation:none!important}.card-bar,.card-column{animation:none!important}}
"""

def wrap(root, el, delay, cls='card-reveal'):
    """Delay a layer without replacing its existing sprite or snake animation."""
    i = list(root).index(el)
    root.remove(el)
    g = node('g', **{'class': cls, 'style': f'--delay:{delay * 2.2:.2f}s'})
    g.append(el)
    root.insert(i, g)

def arcade_boot(root, theme):
    """Reserve 3.4 seconds of every snake loop for board fill and READY/GO.

    Shift original fill/stroke events and counter timing together. Leave the
    route and its occupancy rules intact, including tail-escape effects.
    """
    boot = 3.4
    base_color = '#161b22' if theme == 'dark' else '#ebedf0'
    head_color = '#c9e4ff' if theme == 'dark' else '#54aeff'
    cells = [e for e in root if tag(e) == 'rect' and 208 <= float(e.get('y', 0)) <= 300 and (float(e.get('width', 0)) == 10)]
    if not cells:
        return
    xs = sorted({float(e.get('x')) for e in cells})
    xmin = min(xs)
    xmax = max(xs)
    orig = '\n'.join((e.text or '' for e in root if tag(e) == 'style'))
    match = re.search('animation:\\s*km\\d+_\\d+ ([\\d.]+)s', orig)
    if not match:
        return
    dur = float(match[1])
    total = dur + boot
    offset = boot / total * 100
    rules = []
    seed = None
    for style in [e for e in root if tag(e) == 'style']:

        def remap(m):
            nonlocal seed
            name, body = (m.group(1), m.group(2))
            if not re.fullmatch('[ks]m\\d+_\\d+|r\\d+', name):
                return m.group(0)
            if name.startswith('km') and re.search('0\\.000%\\s*\\{ fill:' + re.escape(head_color), body):
                seed = name[1:]
            body = re.sub('([\\d.]+)%', lambda n: f'{offset + float(n[1]) * dur / total:.5f}%', body)
            if name.startswith('km'):
                cls = name[1:]
                el = next((c for c in cells if c.get('class') == cls), None)
                if el is not None:
                    sweep = (0.75 + (float(el.get('x')) - xmin) / max(xmax - xmin, 1) * 1.3) / total * 100
                    body = f"0% {{fill:{base_color};}} {sweep:.5f}% {{fill:{base_color};}} {sweep + 0.01:.5f}% {{fill:{el.get('fill')};}} " + body
            elif name.startswith('r'):
                body = '0% {opacity:0;} ' + body
            else:
                body = '0% {stroke:transparent;} ' + body
            return '@keyframes ' + name + ' {' + body + '}'
        style.text = re.sub('@keyframes\\s+(\\w+)\\s*\\{((?:[^{}]|\\{[^{}]*\\})*)\\}', remap, style.text or '')
        style.text = re.sub('((?:km\\d+_\\d+|sm\\d+_\\d+|r\\d+) )' + re.escape(f'{dur:.1f}s'), lambda m: m[1] + f'{total:.3f}s', style.text)
    for e in cells:
        cls = e.get('class', '')
        if cls.startswith('h'):
            col = xs.index(float(e.get('x')))
            sweep = (0.75 + col / max(len(xs) - 1, 1) * 1.3) / total * 100
            key = f"boot{col}_{int(float(e.get('y')))}"
            rules.append(f"@keyframes {key} {{0%,{sweep:.5f}% {{fill:{base_color}}} {sweep + 0.01:.5f}%,100% {{fill:{e.get('fill')}}}}}")
            e.set('style', f'animation:{key} {total:.3f}s steps(1,end) infinite')
    if seed:
        e = next((e for e in cells if e.get('class') == seed))
        indicator = node('rect', x=e.get('x'), y=e.get('y'), width=10, height=10, rx=2, fill=head_color)
        indicator.set('class', 'arcade-seed')
        root.append(indicator)
        points = [(0, 0), (2.15, 1), (2.38, 0), (2.6, 1), (2.83, 0), (3.05, 1), (boot, 0), (total, 0)]
        rules.append('@keyframes arcade-seed {' + ' '.join((f'{t / total * 100:.5f}% {{opacity:{v}}}' for t, v in points)) + '}')
        rules.append(f'.arcade-seed {{opacity:0;animation:arcade-seed {total:.3f}s steps(1,end) infinite}}')
    ready = node('text', x=(xmin + xmax + 10) / 2, y=260, **{'text-anchor': 'middle', 'font-family': 'monospace', 'font-size': 12, 'font-weight': 700, 'fill': head_color, 'class': 'arcade-ready', 'stroke': '#0a0e14' if theme == 'dark' else '#ffffff', 'stroke-width': 4, 'paint-order': 'stroke'})
    ready.text = 'READY'
    root.append(ready)
    rules.append(f'@keyframes arcade-ready {{0%,{2.12 / total * 100:.5f}% {{opacity:0}} {2.13 / total * 100:.5f}%,{3.15 / total * 100:.5f}% {{opacity:1}} {3.16 / total * 100:.5f}%,100% {{opacity:0}}}}')
    rules.append(f'.arcade-ready {{opacity:0;animation:arcade-ready {total:.3f}s steps(1,end) infinite}}')
    go = node('text', **dict(ready.attrib))
    go.set('class', 'arcade-go')
    go.text = 'GO'
    root.append(go)
    rules.append(f'@keyframes arcade-go {{0%,{3.15 / total * 100:.5f}% {{opacity:0}} {3.16 / total * 100:.5f}% {{opacity:1}} {boot / total * 100:.5f}%,100% {{opacity:0}}}}')
    rules.append(f'.arcade-go {{opacity:0;animation:arcade-go {total:.3f}s steps(1,end) infinite}}')
    counter = next((e for e in root if tag(e) == 'text' and re.fullmatch('r\\d+', e.get('class', ''))), None)
    if counter is not None:
        zero = node('text', x=counter.get('x'), y=counter.get('y'), fill=counter.get('fill'), **{'font-size': '9.5', 'font-family': 'monospace', 'class': 'arcade-zero'})
        zero.text = '0/' + ''.join(counter.itertext()).split('/')[-1]
        root.append(zero)
        rules.append(f'@keyframes arcade-zero {{0% {{opacity:1}} {offset:.5f}%,100% {{opacity:0}}}}')
        rules.append(f'.arcade-zero {{animation:arcade-zero {total:.3f}s steps(1,end) infinite}}')
    rules.append('@media(prefers-reduced-motion:reduce){.arcade-seed,.arcade-ready,.arcade-go,.arcade-zero{display:none}rect{animation:none!important}}')
    style = node('style')
    style.text = '\n'.join(rules)
    root.append(style)

def animate_card(svg, kind, theme):
    """Add the approved motion while preserving content and canvas dimensions."""
    root = E.fromstring(svg)
    labels = {''.join(e.itertext()): float(e.get('y', 0)) for e in root if tag(e) == 'text'}
    tool_y = labels.get('BY TOOL', labels.get('按工具', 552))
    model_y = labels.get('TOP MODELS', labels.get('模型榜', 612))
    foot_y = float(root.get('viewBox').split()[-1]) - 44
    if kind == 'token':
        arcade_boot(root, theme)
    if kind == 'profile':
        for e in root.iter():
            if e.get('style') and 'animation-delay:' in e.get('style'):
                e.set('style', re.sub('animation-delay:([\\d.]+)s', lambda m: f'animation-delay:{float(m[1]) * 2.2:.3f}s', e.get('style')))
        for e in root:
            if tag(e) == 'style':
                e.text = (e.text or '').replace('growx .45s', 'growx .95s')
    for el in list(root):
        t = tag(el)
        if kind == 'profile':
            if t == 'text' and 40 < float(el.get('y', 0)) < 220:
                wrap(root, el, 0.12 + (float(el.get('y')) - 64) / 160 * 0.6)
            elif t == 'g' and 'translate(20,' in el.get('transform', ''):
                wrap(root, el, 0.05)
        elif kind == 'wall':
            if t == 'text' and float(el.get('y', 0)) > 40:
                wrap(root, el, 0.12 if el.get('class') == 'wcat' else 0.27 if el.get('class') == 'snlab' else 0.42 + (float(el.get('y')) - 82) * 0.008)
        elif kind == 'token' and t not in ('style', 'defs', 'clipPath'):
            children = list(el.iter())
            ys = [float(n.get('y', n.get('cy', n.get('y1', '0')))) for n in children if tag(n) not in ('clipPath', 'title')]
            y = max(ys, default=0)
            x = float(el.get('x', el.get('cx', '36')))
            if y <= 38:
                continue
            delay = 0.12 if y < 166 else 0.35 if y < 341 else 0.65 if y < 500 else 0.95 if y < tool_y - 4 else 1.05 if y < model_y - 14 else 1.25 if y < foot_y else 1.65
            cls = 'card-reveal'
            if t == 'rect' and 208 <= y <= 300:
                delay = 0.18 + max(0, x - 259) / 650 * 0.28
            elif t == 'rect' and 370 < y < 474:
                delay = 0.65 + max(0, x - 36) / 888 * 0.3
                cls = 'card-column'
            elif t == 'g' and any((tag(n) == 'rect' and float(n.get('height', 0)) == 10 for n in el)):
                cls = 'card-bar'
            wrap(root, el, delay, cls)
    style = node('style')
    style.text = CSS
    root.append(style)
    return E.tostring(root, encoding='unicode') + '\n'
