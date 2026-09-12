from __future__ import annotations

import base64
import re
from pathlib import Path
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .util import norm, safe_filename


USER_AGENT = 'shop-titans-bis-tracker/0.1'
_STCENTRAL_ASSET_MAPS: dict[tuple[str | None, str | None], dict[str, str]] = {}
_OFFICIAL_RECENT_ASSET_MAP: dict[str, str] | None = None


def _image_type(data: bytes) -> tuple[str, str] | None:
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return '.png', 'image/png'
    if data.startswith(b'\xff\xd8\xff'):
        return '.jpg', 'image/jpeg'
    if len(data) >= 12 and data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return '.webp', 'image/webp'
    return None


def _download_image(url: str, timeout: int) -> tuple[bytes, str, str] | None:
    try:
        r = requests.get(
            url,
            timeout=timeout,
            headers={'User-Agent': USER_AGENT},
        )
        r.raise_for_status()

        image_type = _image_type(r.content)
        if not image_type:
            return None

        ext, mime = image_type
        return r.content, ext, mime
    except requests.RequestException:
        return None


def _real_image_url(raw_url: str, base_url: str) -> str | None:
    """
    Convert a normal image URL or a Next.js /_next/image wrapper into the
    underlying asset URL.
    """
    if not raw_url:
        return None

    absolute = urljoin(base_url, raw_url)
    parsed = urlparse(absolute)

    if parsed.path.endswith('/_next/image') or parsed.path == '/_next/image':
        wrapped = parse_qs(parsed.query).get('url')
        if not wrapped:
            return None
        return urljoin(base_url, unquote(wrapped[0]))

    return absolute


def _image_urls(img, base_url: str) -> list[str]:
    urls: list[str] = []

    for attr in ('src', 'data-src'):
        value = img.get(attr)
        if value:
            url = _real_image_url(value, base_url)
            if url:
                urls.append(url)

    srcset = img.get('srcset') or img.get('data-srcset')
    if srcset:
        for part in srcset.split(','):
            value = part.strip().split(' ', 1)[0]
            url = _real_image_url(value, base_url)
            if url:
                urls.append(url)

    # Preserve order while removing duplicates.
    return list(dict.fromkeys(urls))


def _stcentral_asset_map(cfg: dict, timeout: int) -> dict[str, str]:
    """
    Build blueprint-name -> image-URL from the actual BiS slots in ST Central.

    Do not require a specific URL prefix. Older assets often live below
    /fankit/Items/, while newer ones may use another source/path.
    """
    cache_key = (
        cfg.get('stcentral_bis_url'),
        cfg.get('stcentral_fallback_url'),
    )

    if cache_key in _STCENTRAL_ASSET_MAPS:
        return _STCENTRAL_ASSET_MAPS[cache_key]

    assets: dict[str, str] = {}

    for page_url in cache_key:
        if not page_url:
            continue

        try:
            r = requests.get(
                page_url,
                timeout=timeout,
                headers={'User-Agent': USER_AGENT},
            )
            r.raise_for_status()

            soup = BeautifulSoup(r.text, 'html.parser')

            for slot in soup.select('.hero-equipment-slot'):
                title = slot.get('title', '')
                match = re.search(
                    r'^\s*Tier\s+\d+\s+(.+?)\s*$',
                    title,
                    flags=re.IGNORECASE | re.MULTILINE,
                )
                if not match:
                    continue

                item_name = match.group(1).strip()
                item_norm = norm(item_name)

                candidates: list[tuple[int, str]] = []

                for index, img in enumerate(slot.find_all('img')):
                    alt_norm = norm(img.get('alt', ''))

                    for url in _image_urls(img, r.url):
                        path_norm = url.lower()

                        score = 0

                        # Strongest signals: exact alt or known item asset paths.
                        if alt_norm == item_norm:
                            score += 100
                        if '/fankit/items/' in path_norm:
                            score += 80
                        if '/assets/items/' in path_norm:
                            score += 80

                        # The main blueprint image is normally the first image
                        # inside the equipment slot.
                        score += max(0, 20 - index)

                        # Avoid obvious auxiliary icons where possible.
                        if any(
                            marker in path_norm
                            for marker in (
                                '/elements/',
                                '/spirits/',
                                '/affinit',
                                '/antique',
                                '/icons/tier',
                            )
                        ):
                            score -= 100

                        candidates.append((score, url))

                if candidates:
                    candidates.sort(key=lambda x: x[0], reverse=True)
                    assets.setdefault(item_norm, candidates[0][1])

            if assets:
                break

        except requests.RequestException:
            continue

    _STCENTRAL_ASSET_MAPS[cache_key] = assets
    return assets


def _find_stcentral_asset(name: str, cfg: dict, timeout: int) -> str | None:
    return _stcentral_asset_map(cfg, timeout).get(norm(name))


def _official_recent_asset_map(timeout: int) -> dict[str, str]:
    """
    Resolve recently introduced blueprints from Shop Titans' official
    'Recent' catalogue. This is especially useful when ST Central references
    a new item whose image path has not yet followed the older fankit layout.
    """
    global _OFFICIAL_RECENT_ASSET_MAP

    if _OFFICIAL_RECENT_ASSET_MAP is not None:
        return _OFFICIAL_RECENT_ASSET_MAP

    result: dict[str, str] = {}
    url = 'https://playshoptitans.com/blueprints/featured/new'

    try:
        r = requests.get(
            url,
            timeout=timeout,
            headers={'User-Agent': USER_AGENT},
        )
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')

        # Blueprint names are ordinary text in repeated cards. For each exact
        # text node, walk upwards until an item image (/assets/items/) appears.
        for text_node in soup.find_all(string=True):
            item_name = text_node.strip()
            if not item_name or len(item_name) > 100:
                continue

            node = text_node.parent

            for _ in range(8):
                if node is None:
                    break

                for img in node.find_all('img'):
                    for image_url in _image_urls(img, r.url):
                        if '/assets/items/' in image_url.lower():
                            result.setdefault(norm(item_name), image_url)
                            break
                    if norm(item_name) in result:
                        break

                if norm(item_name) in result:
                    break

                node = node.parent

    except requests.RequestException:
        pass

    _OFFICIAL_RECENT_ASSET_MAP = result
    return result


def _find_official_recent_asset(name: str, timeout: int) -> str | None:
    return _official_recent_asset_map(timeout).get(norm(name))


def _cache_image(
    name: str,
    data: bytes,
    ext: str,
    mime: str,
    cache_dir: Path,
) -> tuple[str, str]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / safe_filename(name, ext)
    path.write_bytes(data)
    return base64.b64encode(data).decode(), mime


def resolve_image(
    name: str,
    blueprint_raw: dict,
    slug_map: dict,
    cache_dir: Path,
    cfg: dict,
) -> tuple[str, str]:
    # 1. Existing cache wins.
    for ext, mime in (
        ('.webp', 'image/webp'),
        ('.png', 'image/png'),
        ('.jpg', 'image/jpeg'),
    ):
        path = cache_dir / safe_filename(name, ext)
        if path.exists():
            return base64.b64encode(path.read_bytes()).decode(), mime

    timeout = cfg.get('request_timeout_seconds', 30)

    # 2. Known slug / plausible asset identifier from spreadsheet.
    candidates: list[str] = []

    if name in slug_map:
        candidates.append(slug_map[name])

    for key, value in (blueprint_raw or {}).items():
        key_norm = key.lower()
        value = (value or '').strip()

        if (
            value
            and any(x in key_norm for x in ('id', 'key', 'asset', 'icon'))
            and len(value) < 80
            and ' ' not in value
        ):
            candidates.append(value)

    seen: set[str] = set()

    for slug in candidates:
        if slug in seen:
            continue
        seen.add(slug)

        url = cfg['official_asset_url_template'].format(slug=slug)
        downloaded = _download_image(url, timeout)

        if downloaded:
            data, ext, mime = downloaded
            slug_map[name] = slug
            return _cache_image(name, data, ext, mime, cache_dir)

    # 3. Discover the image dynamically from the exact ST Central BiS slot.
    asset_url = _find_stcentral_asset(name, cfg, timeout)

    if asset_url:
        downloaded = _download_image(asset_url, timeout)

        if downloaded:
            data, ext, mime = downloaded

            slug = Path(urlparse(asset_url).path).stem
            if slug:
                slug_map[name] = slug

            return _cache_image(name, data, ext, mime, cache_dir)

    # 4. New/recent blueprint: use the official Shop Titans Recent catalogue.
    asset_url = _find_official_recent_asset(name, timeout)

    if asset_url:
        downloaded = _download_image(asset_url, timeout)

        if downloaded:
            data, ext, mime = downloaded

            slug = Path(urlparse(asset_url).path).stem
            if slug:
                slug_map[name] = slug

            return _cache_image(name, data, ext, mime, cache_dir)

    raise RuntimeError(
        f'No se pudo resolver la imagen de {name!r} ni desde la caché, '
        'ni mediante el slug oficial, ni desde ST Central, ni desde el '
        'catálogo reciente oficial de Shop Titans.'
    )
