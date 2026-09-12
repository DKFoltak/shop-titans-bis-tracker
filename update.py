#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from shop_titans_bis.update import run


ROOT = Path(__file__).resolve().parent

parser = argparse.ArgumentParser(
    description='Actualiza y genera la galería BiS de Shop Titans'
)
parser.add_argument(
    '--offline',
    action='store_true',
    help='Regenera docs/index.html sin descargar fuentes nuevas',
)
args = parser.parse_args()

meta = run(ROOT, offline=args.offline)
print(f"OK: {meta['item_count']} objetos -> docs/index.html")
