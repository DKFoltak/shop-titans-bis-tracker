from __future__ import annotations
import hashlib, json, re
from pathlib import Path


def norm(s: str) -> str:
    s=(s or '').strip().lower()
    s=s.replace('→','/').replace('–','-').replace('—','-')
    s=re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def read_json(path: Path, default=None):
    if not path.exists(): return default
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False)+"\n", encoding='utf-8')


def safe_filename(name: str, ext: str='.webp') -> str:
    base=re.sub(r'[^A-Za-z0-9._-]+','_',name).strip('_') or 'item'
    return base+ext
