from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

import requests


LOCAL_FILES = {
    'blueprints': 'BLUEPRINTS.csv',
    'heroes': 'HEROES.csv',
    'resource_bins': 'RESOURCE_BINS.csv',
    'quest_components': 'QUEST_COMPONENTS.csv',
    'full_moon_fusions': 'FULL_MOON_FUSIONS.csv',
}


def download_sources(root: Path, cfg: dict) -> dict[str, Path]:
    """Download the official spreadsheet tabs as raw local CSV files.

    This function only performs acquisition. It does not parse, normalize or
    reinterpret the CSV contents.
    """
    sheet_cfg = cfg.get('official_sheets', {})
    sheet_names = {
        'blueprints': sheet_cfg.get('blueprints', 'BLUEPRINTS'),
        'heroes': sheet_cfg.get('heroes', 'HEROES'),
        'resource_bins': sheet_cfg.get('resource_bins', 'RESOURCE BINS'),
        'quest_components': sheet_cfg.get('quest_components', 'QUEST COMPONENTS'),
        'full_moon_fusions': sheet_cfg.get('full_moon_fusions', 'FULL MOON FUSIONS'),
    }

    spreadsheet_id = cfg['official_spreadsheet_id']
    timeout = cfg.get('request_timeout_seconds', 30)
    source_dir = root / cfg.get('source_dir', 'source')
    source_dir.mkdir(parents=True, exist_ok=True)

    downloaded: dict[str, Path] = {}

    for role, sheet_name in sheet_names.items():
        url = (
            f'https://docs.google.com/spreadsheets/d/{spreadsheet_id}/gviz/tq'
            f'?tqx=out:csv&sheet={quote(sheet_name)}'
        )
        response = requests.get(
            url,
            timeout=timeout,
            headers={'User-Agent': 'shop-titans-bis-tracker/0.3'},
        )
        response.raise_for_status()

        if not response.content:
            raise RuntimeError(f'La hoja {sheet_name!r} se ha descargado vacía')

        output = source_dir / LOCAL_FILES[role]
        output.write_bytes(response.content)
        downloaded[role] = output
        print(f'{sheet_name}: {output} ({len(response.content)} bytes)')

    return downloaded
