import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_seed_contains_only_image_overrides():
    seed = json.loads((ROOT / 'data/seed.json').read_text(encoding='utf-8'))
    assert set(seed) <= {'image_slugs'}
    assert isinstance(seed.get('image_slugs', {}), dict)
