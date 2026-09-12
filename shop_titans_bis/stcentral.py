from __future__ import annotations

from bs4 import BeautifulSoup
import re
import requests

from .spreadsheet import GameCatalog


def download_bis_html(cfg: dict) -> tuple[str, str]:
    last = None

    for url in [cfg['stcentral_bis_url'], cfg.get('stcentral_fallback_url')]:
        if not url:
            continue

        try:
            r = requests.get(
                url,
                timeout=cfg.get('request_timeout_seconds', 30),
                headers={'User-Agent': 'shop-titans-bis-tracker/0.2'},
            )
            r.raise_for_status()

            if len(r.text) > 1000:
                return r.text, url
        except Exception as e:
            last = e

    raise RuntimeError(f'No se pudo descargar la página BiS de ST Central: {last}')


def parse_bis(html: str, catalog: GameCatalog):
    """Parse ST Central structure and delegate all domain meaning to catalog.

    ST Central tells us only which hero wrapper contains which equipment slot.
    Whether a hero/item is valid and how a promoted class is canonicalized comes
    entirely from the official Shop Titans spreadsheet.
    """
    soup = BeautifulSoup(html, 'html.parser')
    wrappers = soup.select('.hero-wrapper')
    if not wrappers:
        raise RuntimeError(
            'No se encontraron bloques .hero-wrapper en la página BiS de '
            'ST Central; su estructura puede haber cambiado.'
        )

    result: dict[str, dict] = {}
    unknown_items: list[tuple[str, str]] = []
    unknown_heroes: list[str] = []

    for wrapper in wrappers:
        heading = wrapper.select_one('.hero-class-banner h1')
        if not heading:
            continue

        raw_label = heading.get_text(' ', strip=True)
        hero = catalog.resolve_hero(raw_label)
        if not hero:
            unknown_heroes.append(raw_label)
            continue

        entry = result.setdefault(hero, {'observed_labels': set(), 'items': set()})
        entry['observed_labels'].add(raw_label)

        for slot in wrapper.select('.hero-equipment-slot'):
            title = slot.get('title', '')
            match = re.search(
                r'^\s*Tier\s+\d+\s+(.+?)\s*$',
                title,
                flags=re.IGNORECASE | re.MULTILINE,
            )
            if not match:
                continue

            displayed_name = match.group(1).strip()
            item = catalog.resolve_blueprint(displayed_name)
            if not item:
                unknown_items.append((raw_label, displayed_name))
                continue
            entry['items'].add(item)

    if unknown_heroes:
        values = ', '.join(sorted(set(unknown_heroes))[:10])
        raise RuntimeError(
            'ST Central contiene clases que no se pueden resolver contra la '
            f'hoja HEROES del spreadsheet oficial: {values}'
        )

    if unknown_items:
        details = ', '.join(f'{item} ({label})' for label, item in unknown_items[:10])
        if len(unknown_items) > 10:
            details += f', ... (+{len(unknown_items) - 10})'
        raise RuntimeError(
            'ST Central contiene objetos BiS que no aparecen en BLUEPRINTS '
            f'del spreadsheet oficial: {details}'
        )

    final = {}
    for hero, value in result.items():
        if not value['items']:
            continue
        final[hero] = {
            'label': catalog.hero_display_label(hero, value['observed_labels']),
            'items': sorted(value['items']),
        }

    if not final:
        raise RuntimeError('No se pudo extraer ningún objeto BiS de ST Central.')

    return final
