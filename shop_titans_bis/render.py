from __future__ import annotations
from pathlib import Path
from collections import Counter
from jinja2 import Environment, FileSystemLoader, select_autoescape


def render_site(root: Path, items: list, hero_labels: dict, metadata: dict):
    bc = Counter()
    sc = Counter()
    hc = Counter()
    for x in items:
        for k in x['resources']:
            bc[k] += 1
        for k in x['components']:
            sc[k] += 1
        for k in x['heroes']:
            hc[k] += 1

    env = Environment(
        loader=FileSystemLoader(root / 'templates'),
        autoescape=select_autoescape(['html', 'xml']),
    )
    tpl = env.get_template('index.html.j2')
    html = tpl.render(
        items=items,
        hero_labels=hero_labels,
        basic_counts=bc,
        special_counts=sc,
        hero_counts=hc,
        metadata=metadata,
    )
    (root / 'docs').mkdir(exist_ok=True)
    (root / 'docs/index.html').write_text(html, encoding='utf-8')
    (root / 'docs/.nojekyll').write_text('', encoding='utf-8')
