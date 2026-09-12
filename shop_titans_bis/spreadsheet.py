from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .util import norm


_NULL_VALUES = {'', '-', '---', 'n/a', 'na', 'none', 'null'}
_QTY_WORDS = ('amount', 'qty', 'quantity', 'count', 'number', 'needed', 'required')
_RECIPE_DOMAIN_WORDS = ('resource', 'component', 'material', 'precraft', 'ingredient')


@dataclass(frozen=True)
class SheetData:
    name: str
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    all_rows: tuple[tuple[str, ...], ...]


@dataclass
class Blueprint:
    name: str
    tier: int | None
    resources: dict[str, int]
    components: dict[str, int]
    raw: dict[str, str]


@dataclass(frozen=True)
class HeroInfo:
    canonical: str
    aliases: tuple[str, ...]


class GameCatalog:
    """Canonical game-domain data derived from the official spreadsheet.

    No hero, resource, component or blueprint collection is hardcoded here.
    The only fixed knowledge is spreadsheet *schema* (sheet roles/header words).
    """

    def __init__(
        self,
        *,
        blueprints: dict[str, Blueprint],
        resources: Iterable[str],
        quest_components: Iterable[str],
        fusion_components: Iterable[str],
        heroes: dict[str, HeroInfo],
        hero_aliases: dict[str, str],
        sheet_names: dict[str, str],
    ) -> None:
        self.blueprints = blueprints
        self.resources = tuple(dict.fromkeys(value for value in resources if value))
        self.quest_components = tuple(dict.fromkeys(value for value in quest_components if value))
        self.fusion_components = tuple(dict.fromkeys(value for value in fusion_components if value))
        self.components = tuple(dict.fromkeys((*self.quest_components, *self.fusion_components)))
        self.heroes = heroes
        self.hero_aliases = hero_aliases
        self.sheet_names = dict(sheet_names)

        self._blueprint_by_norm = {norm(name): name for name in blueprints}
        self._material_by_norm = {
            norm(name): name
            for name in (*self.resources, *self.components, *blueprints.keys())
            if name
        }

    def resolve_blueprint(self, value: str) -> str | None:
        return self._blueprint_by_norm.get(norm(value))

    def resolve_material(self, value: str) -> str | None:
        return self._material_by_norm.get(norm(value))

    def resolve_hero(self, value: str) -> str | None:
        """Resolve a ST Central hero label to the base class from HEROES.

        Composite labels are accepted only when all their parts resolve to the
        same canonical class.
        """
        direct = self.hero_aliases.get(norm(value))
        if direct:
            return direct

        parts = [p.strip() for p in re.split(r'\s*(?:/|→|->)\s*', value) if p.strip()]
        if len(parts) <= 1:
            return None

        resolved_parts = [self.hero_aliases.get(norm(part)) for part in parts]
        if any(value is None for value in resolved_parts):
            return None
        resolved = set(resolved_parts)
        return next(iter(resolved)) if len(resolved) == 1 else None

    def hero_display_label(self, canonical: str, observed_labels: Iterable[str] = ()) -> str:
        values: list[str] = [canonical]
        seen = {norm(canonical)}

        # Prefer aliases actually present in ST Central; they make the label
        # useful without guessing which spreadsheet columns mean "promotion".
        for label in observed_labels:
            for part in re.split(r'\s*(?:/|→|->)\s*', label):
                part = part.strip()
                if part and norm(part) not in seen and self.resolve_hero(part) == canonical:
                    values.append(part)
                    seen.add(norm(part))

        return ' / '.join(values)

    def snapshot(self) -> dict:
        return {
            'resources': list(self.resources),
            'quest_components': list(self.quest_components),
            'fusion_components': list(self.fusion_components),
            'components': list(self.components),
            'heroes': {
                key: {'aliases': list(info.aliases)}
                for key, info in sorted(self.heroes.items())
            },
            'blueprint_count': len(self.blueprints),
            'sheets': self.sheet_names,
        }


def _csv_matrix(text: str) -> list[list[str]]:
    return [[(cell or '').strip() for cell in row] for row in csv.reader(io.StringIO(text))]


def _sheet_from_csv(name: str, text: str) -> SheetData:
    """Load one exported CSV using row 1 as the authoritative header.

    Google has already flattened the visual formatting for us.  We therefore
    do not try to rediscover headers, merged cells or visual sections here.
    Duplicate/blank headers are intentionally preserved by position because
    BLUEPRINTS contains repeated Component columns and icon-only resource
    amount columns.
    """
    matrix = _csv_matrix(text)
    if not matrix:
        raise RuntimeError(f'La hoja {name!r} está vacía')

    headers = tuple(matrix[0])
    width = len(headers)
    if width == 0:
        raise RuntimeError(f'La hoja {name!r} no contiene cabeceras en la línea 1')

    rows: list[tuple[str, ...]] = []
    for raw in matrix[1:]:
        row = tuple((raw + [''] * width)[:width])
        if any(cell for cell in row):
            rows.append(row)

    return SheetData(
        name=name,
        headers=headers,
        rows=tuple(rows),
        all_rows=tuple(tuple(r) for r in matrix),
    )

def _int(value: str | None) -> int | None:
    if value is None:
        return None
    m = re.search(r'-?\d[\d,]*', str(value))
    return int(m.group(0).replace(',', '')) if m else None


def _pick_column(headers: tuple[str, ...], choices: tuple[str, ...], contains: tuple[str, ...] = ()) -> int | None:
    normalized = [norm(h) for h in headers]
    for choice in choices:
        if choice in normalized:
            return normalized.index(choice)
    for i, value in enumerate(normalized):
        if any(token in value for token in contains):
            return i
    return None


def _tokens(value: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", norm(value))
    out = set(words)
    for word in list(words):
        if word.endswith('s') and len(word) > 3:
            out.add(word[:-1])
    return out


def _recipe_pairs(headers: tuple[str, ...]) -> list[tuple[int, int, str]]:
    """Discover recipe material/quantity pairs from BLUEPRINTS schema.

    The *values* in these columns are game data and become the canonical
    resource/component names. Only schema words are fixed here. Column indices
    are preserved so repeated headers such as ``Component`` / ``Amount Needed``
    remain independent.
    """
    normalized = [norm(h) for h in headers]

    def is_name_column(value: str) -> bool:
        return (
            value
            and 'quality' not in value
            and not any(word in value for word in _QTY_WORDS)
            and any(word in value for word in _RECIPE_DOMAIN_WORDS)
        )

    name_indices = [i for i, value in enumerate(normalized) if is_name_column(value)]
    pairs: list[tuple[int, int, str]] = []

    for pos, i in enumerate(name_indices):
        header = normalized[i]
        role = 'resource' if 'resource' in header else 'component'
        numbers = re.findall(r'\d+', header)
        next_name = name_indices[pos + 1] if pos + 1 < len(name_indices) else len(headers)
        search_end = min(next_name, i + 8, len(headers))

        qty = None

        # Prefer a quantity column carrying the same numeric suffix, e.g.
        # Resource 2 -> Resource 2 Amount.
        if numbers:
            for j in range(i + 1, search_end):
                candidate = normalized[j]
                if 'quality' in candidate or not any(word in candidate for word in _QTY_WORDS):
                    continue
                if any(number in re.findall(r'\d+', candidate) for number in numbers):
                    qty = j
                    break

        # Repeated generic headers in the official sheet are commonly adjacent:
        # Component | Amount Needed | Component Quality | Component | ...
        if qty is None:
            for j in range(i + 1, search_end):
                candidate = normalized[j]
                if 'quality' not in candidate and any(word in candidate for word in _QTY_WORDS):
                    qty = j
                    break

        if qty is not None:
            pairs.append((i, qty, role))

    if not pairs:
        raise RuntimeError(
            'No se reconocen pares de material/cantidad en BLUEPRINTS. '
            f'Cabeceras: {list(headers)[:60]}'
        )
    return pairs


def _resource_furniture_name(cell: str) -> str | None:
    """Extract the resource name represented by a RESOURCE BINS furniture title.

    The official sheet names the furniture (for example ``<resource> Bin``)
    rather than exposing the resource names in BLUEPRINTS' blank icon headers.
    This function strips only the furniture/schema suffix; the resource value
    itself still comes from the spreadsheet.
    """
    text = ' '.join((cell or '').split())
    if not text:
        return None

    # RESOURCE BINS is laid out as several furniture tables. Headings may carry
    # extra text such as "Extra Bin Purchase Prices ...", so stop at the
    # furniture noun. These are schema/furniture terms, not game resource names.
    m = re.match(
        r"^(.+?)\s+(?:bin|dryer|pot|beacon|grinder)\b",
        text,
        flags=re.IGNORECASE,
    )
    if not m:
        return None

    name = m.group(1).strip(' -:')
    if not name or len(name) > 64:
        return None
    return name.title() if name.isupper() else name


def _singular_key(value: str) -> tuple[str, ...]:
    words = re.findall(r'[a-z0-9]+', norm(value))
    normalized: list[str] = []
    for word in words:
        # Generic plural normalization is used only for matching two labels
        # already present in the spreadsheet (e.g. furniture name vs. "Spent"
        # upgrade text); it never creates a game-domain collection by itself.
        if word.endswith('s') and len(word) > 3:
            word = word[:-1]
        normalized.append(word)
    return tuple(normalized)


def _resource_labels_from_blueprint_text(blueprints: SheetData) -> dict[tuple[str, ...], str]:
    """Discover canonical resource spellings from BLUEPRINTS upgrade text.

    Crafting/ascension cells contain phrases such as ``-43 <resource> Spent``.
    These provide textual resource labels even though the resource amount
    headers themselves are icon-only in the CSV.
    """
    counts: dict[tuple[str, ...], dict[str, int]] = {}
    for row in blueprints.rows:
        for cell in row:
            if not cell or 'spent' not in norm(cell):
                continue
            for match in re.finditer(
                r'-?\s*\d[\d,]*\s+(.+?)\s+Spent\b',
                cell,
                flags=re.IGNORECASE,
            ):
                label = match.group(1).strip(' -:')
                key = _singular_key(label)
                if not key:
                    continue
                bucket = counts.setdefault(key, {})
                bucket[label] = bucket.get(label, 0) + 1

    result: dict[tuple[str, ...], str] = {}
    for key, variants in counts.items():
        # Prefer the spelling used most often by the authoritative sheet; ties
        # are deterministic and do not depend on local configuration.
        result[key] = sorted(
            variants,
            key=lambda label: (-variants[label], label.casefold()),
        )[0]
    return result


def _resource_names_from_bins(resource_bins_csv: str, blueprints: SheetData) -> list[str]:
    """Return production resources in the structural order of RESOURCE BINS.

    RESOURCE BINS arranges resource furniture in parallel vertical tables
    (tier-1 resources in the first block, tier-2 in the next, and so on).
    BLUEPRINTS uses the same logical resource order for its icon-only amount
    columns. Reading headings column-major therefore recovers that order without
    embedding values such as Iron, Ether or Stardust in code.
    """
    matrix = _csv_matrix(resource_bins_csv)
    found: list[tuple[int, int, str]] = []

    for row_index, row in enumerate(matrix):
        for col_index, cell in enumerate(row):
            name = _resource_furniture_name(cell)
            if name:
                found.append((col_index, row_index, name))

    if not found:
        raise RuntimeError(
            'No se pudieron localizar los nombres de los recursos en RESOURCE BINS. '
            'Se esperaban cabeceras de mobiliario de recursos.'
        )

    # The sheet presents multiple resource tables side-by-side. Column-major
    # ordering follows each vertical group before moving to the next tier group.
    found.sort(key=lambda value: (value[0], value[1]))

    textual_labels = _resource_labels_from_blueprint_text(blueprints)

    resources: list[str] = []
    seen: set[str] = set()
    for _col, _row, furniture_base in found:
        # Prefer the exact resource spelling independently present in BLUEPRINTS
        # (e.g. Herbs/Jewels). If no "Spent" text exists for a new resource,
        # the RESOURCE BINS furniture base remains the authoritative fallback.
        name = textual_labels.get(_singular_key(furniture_base), furniture_base)
        key = norm(name)
        if key and key not in seen:
            seen.add(key)
            resources.append(name)

    if not resources:
        raise RuntimeError('RESOURCE BINS no produjo ningún recurso canónico')
    return resources


def _positive_numeric_column_stats(
    sheet: SheetData,
    start: int,
    end: int,
) -> list[tuple[int, int, int]]:
    """Return (column, positive_numeric_cells, non_numeric_cells)."""
    stats: list[tuple[int, int, int]] = []
    for column in range(start, end):
        numeric = 0
        non_numeric = 0
        for row in sheet.rows:
            value = row[column].strip() if column < len(row) else ''
            if not value or norm(value) in _NULL_VALUES:
                continue
            parsed = _int(value)
            if parsed is not None and parsed >= 0 and re.fullmatch(r'[\d,]+(?:\.0+)?', value):
                if parsed > 0:
                    numeric += 1
            else:
                non_numeric += 1
        stats.append((column, numeric, non_numeric))
    return stats


def _resource_amount_columns(
    blueprints: SheetData,
    resource_names: list[str],
) -> list[tuple[int, str]]:
    """Map BLUEPRINTS' icon-only resource amount columns to RESOURCE BINS.

    In the official CSV the resource header cells are blank because the Google
    Sheet uses icons there. The amount block is nevertheless structurally stable:
    it sits after the repeated Required Worker/Worker Level pairs and before the
    first Component column. Empty separator columns are discarded by inspecting
    the actual row values. RESOURCE BINS may contain additional game resources
    that are not direct blueprint costs, so the recipe subset is derived from
    resource references in BLUEPRINTS instead of requiring catalogue-size equality.
    """
    normalized = [norm(h) for h in blueprints.headers]

    worker_columns = [
        i for i, value in enumerate(normalized)
        if value in {'required worker', 'worker level'}
        or 'required worker' in value
        or 'worker level' in value
    ]
    component_columns = [
        i for i, value in enumerate(normalized)
        if value == 'component'
        or (value.startswith('component ') and 'quality' not in value)
    ]

    if not worker_columns or not component_columns:
        raise RuntimeError(
            'No se pudo delimitar el bloque de recursos de BLUEPRINTS mediante '
            'Required Worker/Worker Level y Component.'
        )

    start = max(worker_columns) + 1
    end = min(component_columns)
    if start >= end:
        raise RuntimeError(
            f'Bloque de recursos inválido en BLUEPRINTS: columnas {start}..{end - 1}'
        )

    stats = _positive_numeric_column_stats(blueprints, start, end)

    # A real resource column contains numeric quantities and no textual game
    # values. Separator columns contain no values at all. A textual column in
    # this region means the upstream schema changed and must not be guessed.
    textual = [(column, non_numeric) for column, _numeric, non_numeric in stats if non_numeric]
    if textual:
        raise RuntimeError(
            'Se encontraron columnas textuales inesperadas dentro del bloque de '
            f'recursos de BLUEPRINTS: {textual[:10]}'
        )

    columns = [column for column, numeric, _non_numeric in stats if numeric > 0]

    # RESOURCE BINS is the complete resource catalogue. BLUEPRINTS, however,
    # only exposes direct crafting-cost columns for the subset of resources that
    # can be consumed by blueprint recipes. Do not assume those two collections
    # have the same size. Derive the recipe subset independently from textual
    # ``<resource> Spent`` references already present in BLUEPRINTS itself.
    recipe_resource_names = list(resource_names)
    textual_labels: dict[tuple[str, ...], str] | None = None
    if len(columns) != len(resource_names):
        textual_labels = _resource_labels_from_blueprint_text(blueprints)
        recipe_resource_names = [
            resource
            for resource in resource_names
            if _singular_key(resource) in textual_labels
        ]

    if len(columns) != len(recipe_resource_names):
        detail = [
            {
                'column': column,
                'header': blueprints.headers[column],
                'positive_values': numeric,
            }
            for column, numeric, _non_numeric in stats
        ]
        textual_labels = textual_labels or _resource_labels_from_blueprint_text(blueprints)
        referenced = [
            resource
            for resource in resource_names
            if _singular_key(resource) in textual_labels
        ]
        not_referenced = [resource for resource in resource_names if resource not in referenced]
        raise RuntimeError(
            'No se pudo alinear el bloque de recursos directos de BLUEPRINTS con '
            'el catálogo completo de RESOURCE BINS: '
            f'columnas BLUEPRINTS={len(columns)}, '
            f'recursos RESOURCE BINS={len(resource_names)}, '
            f'recursos referenciados por BLUEPRINTS={len(referenced)}. '
            f'Referenciados={referenced}; no referenciados={not_referenced}. '
            f'Bloque analizado: {detail}'
        )

    return list(zip(columns, recipe_resource_names))

def _unique_raw(headers: tuple[str, ...], row: tuple[str, ...]) -> dict[str, str]:
    counts: dict[str, int] = {}
    result: dict[str, str] = {}
    for i, header in enumerate(headers):
        key = header or f'column_{i + 1}'
        counts[key] = counts.get(key, 0) + 1
        if counts[key] > 1:
            key = f'{key}#{counts[key]}'
        result[key] = row[i] if i < len(row) else ''
    return result


def _parse_named_values(
    sheet: SheetData,
    *,
    choices: tuple[str, ...],
    contains: tuple[str, ...] = (),
) -> set[str]:
    """Read the canonical names from one spreadsheet catalogue column.

    We intentionally do not collect arbitrary text from the sheet: descriptions,
    quest names and quality labels are not members of the component catalogue.
    """
    column = _pick_column(sheet.headers, choices, contains=contains)
    if column is None:
        raise RuntimeError(
            f'No se reconoce la columna de nombres en {sheet.name!r}: '
            f'{list(sheet.headers)[:30]}'
        )

    values: set[str] = set()
    for row in sheet.rows:
        value = row[column].strip() if column < len(row) else ''
        if value and norm(value) not in _NULL_VALUES:
            values.add(value)

    if not values:
        raise RuntimeError(f'No se pudo extraer ningún valor canónico de {sheet.name!r}')
    return values


def _parse_fusion_only_components(
    sheet: SheetData,
    quest_components: set[str],
) -> set[str]:
    """Return fusion components that are not already quest components.

    FULL MOON FUSIONS also contains fusion recipes for ordinary quest
    components.  Those are alternate acquisition methods, not new component
    identities.  Only Type=Component names absent from QUEST COMPONENTS extend
    the effective component catalogue (currently the Sigils).
    """
    name_col = _pick_column(sheet.headers, ('name',))
    type_col = _pick_column(sheet.headers, ('type',))
    if name_col is None or type_col is None:
        raise RuntimeError(
            f'No se reconocen las columnas Name/Type en {sheet.name!r}: ' + f'{list(sheet.headers)[:20]}'
        )

    quest_by_norm = {norm(value) for value in quest_components if value}
    result: set[str] = set()
    for row in sheet.rows:
        name = row[name_col].strip() if name_col < len(row) else ''
        type_value = row[type_col].strip() if type_col < len(row) else ''
        if not name or norm(type_value) != 'component':
            continue
        if norm(name) not in quest_by_norm:
            result.add(name)

    return result


_HERO_PROMOTION_RE = re.compile(
    r'^\s*(?P<promotion>.+?)\s*\(\s*(?P<base>.+?)\s+Class Promotion\s*\)\s*$',
    flags=re.IGNORECASE,
)


def _hero_name(value: str) -> str:
    value = ' '.join((value or '').split()).strip()
    return value.title() if value.isupper() else value


def _parse_heroes(sheet: SheetData) -> tuple[dict[str, HeroInfo], dict[str, str]]:
    # Current official HEROES.csv format. Row 1 contains three horizontal class
    # sections. Only those columns matter to this application:
    #   - base classes are uppercase labels (KNIGHT, RANGER, DARK KNIGHT, ...)
    #   - promotions explicitly encode their base class, e.g.
    #     LORD(Knight Class Promotion)
    # Everything else in the hero card is irrelevant for the current BiS
    # functionality and is intentionally ignored.
    class_columns = [
        i for i, header in enumerate(sheet.headers)
        if 'classes' in norm(header)
    ]
    if not class_columns:
        raise RuntimeError(
            f'No se localizaron bloques de clases en la cabecera de {sheet.name!r}: '
            f'{list(sheet.headers)}'
        )

    base_names: dict[str, str] = {}
    promotions: dict[str, list[str]] = {}

    for row in sheet.rows:
        for col in class_columns:
            label = row[col].strip() if col < len(row) else ''
            if not label or norm(label) in _NULL_VALUES:
                continue

            match = _HERO_PROMOTION_RE.fullmatch(label)
            if match:
                canonical = _hero_name(match.group('base'))
                promotion = _hero_name(match.group('promotion'))
                key = norm(canonical)
                base_names.setdefault(key, canonical)
                promotions.setdefault(key, []).append(promotion)
                continue

            # Base-class labels in the official CSV are uppercase. Other values
            # that appear in these same columns (Gold Hire Cost, Sword, etc.) are
            # card details and are not part of the class catalogue.
            if not label.isupper() or not any(ch.isalpha() for ch in label):
                continue

            canonical = _hero_name(label)
            base_names[norm(canonical)] = canonical

    if not base_names:
        raise RuntimeError(f'No se pudo extraer ninguna clase de {sheet.name!r}')

    heroes: dict[str, HeroInfo] = {}
    hero_aliases: dict[str, str] = {}

    for key, canonical in base_names.items():
        aliases = list(dict.fromkeys([canonical, *promotions.get(key, [])]))
        heroes[canonical] = HeroInfo(canonical, tuple(aliases))
        for alias in aliases:
            hero_aliases[norm(alias)] = canonical

    return heroes, hero_aliases


def _parse_blueprints(
    sheet: SheetData,
    recipe_pairs: list[tuple[int, int, str]],
    resource_columns: list[tuple[int, str]],
    resources: list[str],
    components: set[str],
    minimum_items: int,
) -> dict[str, Blueprint]:
    name_col = _pick_column(
        sheet.headers,
        ('name', 'blueprint name', 'item name'),
        contains=('blueprint name', 'item name'),
    )
    tier_col = _pick_column(
        sheet.headers,
        ('tier', 'item tier', 'blueprint tier'),
        contains=('tier',),
    )
    if name_col is None:
        raise RuntimeError(f'No se reconoce la columna Name en {sheet.name!r}')

    out: dict[str, Blueprint] = {}

    # First pass: every blueprint name is canonical spreadsheet data. This also
    # creates the catalogue used to validate precrafts in component fields.
    for row in sheet.rows:
        name = row[name_col].strip() if name_col < len(row) else ''
        if name and norm(name) not in _NULL_VALUES:
            out[name] = Blueprint(
                name=name,
                tier=_int(row[tier_col]) if tier_col is not None else None,
                resources={},
                components={},
                raw=_unique_raw(sheet.headers, row),
            )

    if len(out) < minimum_items:
        raise RuntimeError(
            f'Solo se pudieron leer {len(out)} blueprints; probablemente cambió la hoja oficial'
        )

    resource_by_norm = {norm(value): value for value in resources if value}
    component_by_norm = {
        norm(value): value
        for value in (*components, *out.keys())
        if value
    }

    # Second pass: recipe data. We classify each cell against the catalogues
    # obtained from the spreadsheet, not against hardcoded game values.
    for row in sheet.rows:
        name = row[name_col].strip() if name_col < len(row) else ''
        bp = out.get(name)
        if bp is None:
            continue

        # Resource names are represented by icons in BLUEPRINTS, so the CSV
        # carries only their quantities. The mapping to names comes from
        # RESOURCE BINS and the structurally discovered amount columns.
        for amount_col, canonical in resource_columns:
            qty = _int(row[amount_col] if amount_col < len(row) else '')
            if qty and qty > 0:
                bp.resources[canonical] = qty

        # Components/precrafts are textual and keep their explicit spreadsheet
        # columns. Repeated Component headers are preserved by position.
        for material_col, qty_col, role in recipe_pairs:
            if role == 'resource':
                # Compatibility with a future/alternate sheet revision that
                # explicitly exposes Resource-name columns.
                material = row[material_col].strip() if material_col < len(row) else ''
                qty = _int(row[qty_col] if qty_col < len(row) else '')
                if not material or not qty or qty <= 0:
                    continue
                canonical = resource_by_norm.get(norm(material))
                if canonical is None:
                    raise RuntimeError(
                        f'El blueprint {name!r} usa {material!r} en una columna Resource, '
                        'pero RESOURCE BINS no contiene ese recurso.'
                    )
                bp.resources[canonical] = qty
                continue

            material = row[material_col].strip() if material_col < len(row) else ''
            if not material or norm(material) in _NULL_VALUES:
                continue
            qty = _int(row[qty_col] if qty_col < len(row) else '')
            if not qty or qty <= 0:
                continue

            material_norm = norm(material)
            canonical = component_by_norm.get(material_norm)
            if canonical is None:
                resource = resource_by_norm.get(material_norm)
                if resource is not None:
                    bp.resources[resource] = qty
                    continue
                raise RuntimeError(
                    f'El blueprint {name!r} referencia el material {material!r}, '
                    'pero no existe en RESOURCE BINS, los catálogos de componentes ni BLUEPRINTS.'
                )
            bp.components[canonical] = qty

    return out

def parse_game_catalog(sheet_csvs: dict[str, str], cfg: dict) -> GameCatalog:
    names = cfg.get('official_sheets', {})
    required = {
        'blueprints': names.get('blueprints', cfg.get('official_blueprints_sheet', 'BLUEPRINTS')),
        'heroes': names.get('heroes', 'HEROES'),
        'quest_components': names.get('quest_components', 'QUEST COMPONENTS'),
        'resource_bins': names.get('resource_bins', 'RESOURCE BINS'),
        'full_moon_fusions': names.get('full_moon_fusions', 'FULL MOON FUSIONS'),
    }

    missing = [
        role for role, sheet_name in required.items()
        if role != 'full_moon_fusions' and sheet_name not in sheet_csvs
    ]
    if missing:
        raise RuntimeError(f'Faltan hojas del spreadsheet para construir el catálogo: {missing}')

    blueprints_sheet = _sheet_from_csv(required['blueprints'], sheet_csvs[required['blueprints']])
    heroes_sheet = _sheet_from_csv(required['heroes'], sheet_csvs[required['heroes']])
    quest_sheet = _sheet_from_csv(required['quest_components'], sheet_csvs[required['quest_components']])
    fusion_text = sheet_csvs.get(required['full_moon_fusions'])
    fusion_sheet = (
        _sheet_from_csv(required['full_moon_fusions'], fusion_text)
        if fusion_text is not None
        else None
    )

    recipe_pairs = _recipe_pairs(blueprints_sheet.headers)
    resources = _resource_names_from_bins(sheet_csvs[required['resource_bins']], blueprints_sheet)

    # The live official sheet uses icon-only amount columns. Tests and older/
    # alternate revisions may expose explicit Resource / Resource Amount pairs.
    # Support both without weakening validation against RESOURCE BINS.
    has_named_resource_pairs = any(role == 'resource' for _m, _q, role in recipe_pairs)
    resource_columns = (
        []
        if has_named_resource_pairs
        else _resource_amount_columns(blueprints_sheet, resources)
    )
    quest_components = _parse_named_values(
        quest_sheet,
        choices=('component', 'name', 'quest component'),
        contains=('component name',),
    )
    fusion_components = (
        _parse_fusion_only_components(fusion_sheet, quest_components)
        if fusion_sheet is not None
        else set()
    )
    components = set(quest_components) | set(fusion_components)
    heroes, hero_aliases = _parse_heroes(heroes_sheet)
    blueprints = _parse_blueprints(
        blueprints_sheet,
        recipe_pairs,
        resource_columns,
        resources,
        components,
        cfg.get('minimum_items', 20),
    )

    return GameCatalog(
        blueprints=blueprints,
        resources=resources,
        quest_components=quest_components,
        fusion_components=fusion_components,
        heroes=heroes,
        hero_aliases=hero_aliases,
        sheet_names=required,
    )


def load_game_catalog(root: Path, cfg: dict) -> GameCatalog:
    """Build the catalogue exclusively from the five local CSV snapshots.

    Acquisition is handled by ``shop_titans_bis.sources`` before this
    function is called. This parser itself never performs network I/O.
    """
    source_dir = root / cfg.get('source_dir', 'source')
    files = {
        'BLUEPRINTS': source_dir / 'BLUEPRINTS.csv',
        'HEROES': source_dir / 'HEROES.csv',
        'RESOURCE BINS': source_dir / 'RESOURCE_BINS.csv',
        'QUEST COMPONENTS': source_dir / 'QUEST_COMPONENTS.csv',
        'FULL MOON FUSIONS': source_dir / 'FULL_MOON_FUSIONS.csv',
    }

    missing = [str(path) for path in files.values() if not path.is_file()]
    if missing:
        raise RuntimeError(
            f'Faltan CSV locales del spreadsheet oficial: {missing}'
        )

    sheet_csvs = {
        sheet: path.read_text(encoding='utf-8-sig')
        for sheet, path in files.items()
    }
    return parse_game_catalog(sheet_csvs, cfg)

