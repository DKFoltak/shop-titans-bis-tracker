from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .changelog import diff, render_entry
from .images import resolve_image
from .render import render_site
from .sources import download_sources
from .spreadsheet import load_game_catalog
from .stcentral import download_bis_html, parse_bis
from .util import read_json, write_json


def _offline_hero_labels(bis: list[dict]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for item in bis:
        heroes = item.get('heroes', [])
        hero_labels = item.get('hero_labels', [])
        for i, hero in enumerate(heroes):
            labels.setdefault(hero, hero_labels[i] if i < len(hero_labels) else hero)
    return labels


def run(root: Path, offline: bool = False):
    cfg = read_json(root / 'config.json', {})
    seed = read_json(root / 'data/seed.json', {})
    old_bis = read_json(root / 'data/bis.json', [])
    old_recipes = read_json(root / 'data/recipes.json', {})
    old_catalog = read_json(root / 'data/catalog.json', {})
    old_metadata = read_json(root / 'data/metadata.json', {})
    slug_map = dict(seed.get('image_slugs', {}))

    catalog = None
    if offline:
        bis = old_bis
        recipes = old_recipes
        catalog_snapshot = old_catalog
        hero_labels = _offline_hero_labels(bis)
        source_url = 'offline committed snapshot'
        bp_by_name = {}
    else:
        download_sources(root, cfg)
        catalog = load_game_catalog(root, cfg)
        bp_by_name = catalog.blueprints
        catalog_snapshot = catalog.snapshot()

        bis_html, source_url = download_bis_html(cfg)
        hero_map = parse_bis(bis_html, catalog)

        item_heroes: dict[str, set[str]] = {}
        hero_labels = {hero: entry['label'] for hero, entry in hero_map.items()}
        for hero, entry in hero_map.items():
            for name in entry['items']:
                item_heroes.setdefault(name, set()).add(hero)

        if len(item_heroes) < cfg.get('minimum_items', 20):
            raise RuntimeError(
                f'Solo se extrajeron {len(item_heroes)} objetos BiS; '
                'no se sustituye el snapshot válido'
            )

        bis = []
        recipes = {}
        for name in sorted(item_heroes):
            bp = bp_by_name.get(name)
            if not bp:
                raise RuntimeError(f'BiS sin blueprint oficial: {name}')
            heroes = sorted(item_heroes[name])
            bis.append({
                'name': name,
                'tier': bp.tier,
                'heroes': heroes,
                'hero_labels': [hero_labels[h] for h in heroes],
            })
            recipes[name] = {
                'tier': bp.tier,
                'resources': bp.resources,
                'components': bp.components,
            }

        unresolved = [
            x['name'] for x in bis
            if not recipes[x['name']]['resources'] and not recipes[x['name']]['components']
        ]
        if unresolved and cfg.get('strict', True):
            raise RuntimeError(f'Recetas vacías para {len(unresolved)} objetos: {unresolved[:8]}')

        # Semantic guardrails derived from the same authoritative workbook.
        # A parser regression such as Component Quality -> "---" can no longer
        # silently reach the generated page.
        resource_set = set(catalog.resources)
        for name, recipe in recipes.items():
            unknown_resources = set(recipe['resources']) - resource_set
            if unknown_resources:
                raise RuntimeError(f'Recursos no presentes en el catálogo oficial para {name}: {sorted(unknown_resources)}')
            for material in recipe['components']:
                if catalog.resolve_material(material) is None:
                    raise RuntimeError(f'Componente no presente en el catálogo oficial para {name}: {material}')

    items = []
    for b in bis:
        name = b['name']
        rec = recipes[name]
        raw = getattr(bp_by_name.get(name), 'raw', {}) if not offline else {}
        b64, mime = resolve_image(name, raw, slug_map, root / 'assets-cache', cfg)
        items.append({
            **b,
            'resources': rec.get('resources', {}),
            'components': rec.get('components', {}),
            'image_data': f'data:{mime};base64,{b64}',
        })

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    changes = (
        diff(old_bis, bis, old_recipes, recipes)
        if not offline else
        {'added': [], 'removed': [], 'hero_changes': [], 'recipe_changes': []}
    )
    data_changed = (
        bis != old_bis or recipes != old_recipes or catalog_snapshot != old_catalog
    ) if not offline else False

    if offline:
        metadata = old_metadata or {
            'snapshot_date': '2026-08-11',
            'item_count': len(items),
            'bis_source': source_url,
            'spreadsheet_id': cfg['official_spreadsheet_id'],
        }
    elif data_changed:
        metadata = {
            'generated_at_utc': now,
            'item_count': len(items),
            'bis_source': source_url,
            'spreadsheet_id': cfg['official_spreadsheet_id'],
            'catalog': {
                'blueprints': catalog_snapshot.get('blueprint_count', 0),
                'heroes': len(catalog_snapshot.get('heroes', {})),
                'resources': len(catalog_snapshot.get('resources', [])),
                'quest_components': len(catalog_snapshot.get('quest_components', [])),
            },
        }
    else:
        metadata = old_metadata or {
            'generated_at_utc': now,
            'item_count': len(items),
            'bis_source': source_url,
            'spreadsheet_id': cfg['official_spreadsheet_id'],
        }

    if not offline and data_changed:
        entry = render_entry(changes, now[:10])
        if entry:
            p = root / 'CHANGELOG.md'
            old = p.read_text(encoding='utf-8') if p.exists() else '# Historial de cambios\n\n'
            p.write_text(
                old.split('\n', 2)[0] + '\n\n' + entry + '\n'.join(old.split('\n')[2:]).lstrip(),
                encoding='utf-8',
            )
        write_json(root / 'data/bis.json', bis)
        write_json(root / 'data/recipes.json', recipes)
        write_json(root / 'data/catalog.json', catalog_snapshot)
        write_json(root / 'data/metadata.json', metadata)

    if not offline:
        # seed.json is now exclusively for exceptional image information. Game
        # domain collections/labels are never persisted here as source of truth.
        seed.pop('hero_labels', None)
        seed['image_slugs'] = slug_map
        write_json(root / 'data/seed.json', seed)

    render_site(root, items, hero_labels, metadata)
    return metadata
