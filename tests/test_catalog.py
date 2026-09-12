import textwrap

import pytest

from shop_titans_bis.spreadsheet import parse_game_catalog
from shop_titans_bis.stcentral import parse_bis


CFG = {
    'minimum_items': 2,
    'official_sheets': {
        'blueprints': 'BLUEPRINTS',
        'heroes': 'HEROES',
        'quest_components': 'QUEST COMPONENTS',
        'resource_bins': 'RESOURCE BINS',
    },
}


def _csv(text: str) -> str:
    return textwrap.dedent(text).strip() + '\n'


def _catalog():
    sheets = {
        'BLUEPRINTS': _csv('''
            Name,Type,Tier,Resource 1,Resource 1 Amount,Resource 2,Resource 2 Amount,Component,Amount Needed,Component Quality,Component,Amount Needed
            Shield of Test,Shield,15,Iron,100,Steel,50,Ancient Amber,4,---,Blaze Element,2
            Blaze Element,Enchantment,12,Steel,20,,,,Raw Obsidian,3,Normal,,
            Test Hat,Hat,14,Steel,10,,,,Raw Obsidian,2,Superior,,
        '''),
        'HEROES': _csv('''
            Class,Promoted Class,Preferred Weapon
            Knight,Lord,Axe
            Ranger,Warden,Bow
            Berserker,Jarl,Mace
        '''),
        'QUEST COMPONENTS': _csv('''
            Component,Quest
            Ancient Amber,Forest
            Raw Obsidian,Caves
        '''),
        'RESOURCE BINS': _csv('''
            IRON BIN,STEEL BIN
            Bin Level,Bin Level
            1,1
        '''),
    }
    return parse_game_catalog(sheets, CFG)


def test_catalog_is_derived_from_spreadsheet_values():
    catalog = _catalog()
    assert catalog.resources == ('Iron', 'Steel')
    assert catalog.resolve_blueprint('shield of test') == 'Shield of Test'
    assert catalog.resolve_material('Ancient Amber') == 'Ancient Amber'
    assert catalog.resolve_material('Blaze Element') == 'Blaze Element'
    assert catalog.resolve_material('Forest') is None


def test_duplicate_component_columns_are_preserved_and_quality_is_ignored():
    bp = _catalog().blueprints['Shield of Test']
    assert bp.resources == {'Iron': 100, 'Steel': 50}
    assert bp.components == {'Ancient Amber': 4, 'Blaze Element': 2}
    assert '---' not in bp.components
    assert 'Normal' not in bp.components
    assert 'Superior' not in bp.components


def test_resource_collection_is_data_driven_not_hardcoded():
    sheets = {
        'BLUEPRINTS': _csv('''
            Name,Type,Tier,Resource 1,Resource 1 Amount,Component,Amount Needed
            Lunar Test,Hat,20,Moon Dust,123,Ancient Amber,2
            Other Test,Hat,19,Moon Dust,50,Ancient Amber,1
        '''),
        'HEROES': _csv('''
            Class,Promoted Class
            Knight,Lord
        '''),
        'QUEST COMPONENTS': _csv('''
            Component
            Ancient Amber
        '''),
        'RESOURCE BINS': _csv('''
            MOON DUST BIN
            Bin Level
            1
        '''),
    }
    catalog = parse_game_catalog(sheets, CFG)
    assert catalog.resources == ('Moon Dust',)
    assert catalog.blueprints['Lunar Test'].resources == {'Moon Dust': 123}


def test_resource_must_be_validated_by_resource_bins():
    sheets = {
        'BLUEPRINTS': _csv('''
            Name,Type,Tier,Resource 1,Resource 1 Amount,Component,Amount Needed
            Lunar Test,Hat,20,Moon Dust,123,Ancient Amber,2
            Other Test,Hat,19,Moon Dust,50,Ancient Amber,1
        '''),
        'HEROES': _csv('''
            Class,Promoted Class
            Knight,Lord
        '''),
        'QUEST COMPONENTS': _csv('''
            Component
            Ancient Amber
        '''),
        'RESOURCE BINS': _csv('''
            IRON BIN
            Bin Level
            1
        '''),
    }
    with pytest.raises(RuntimeError, match='Moon Dust'):
        parse_game_catalog(sheets, CFG)


def test_promoted_heroes_resolve_from_heroes_sheet_without_hardcoded_map():
    catalog = _catalog()
    assert catalog.resolve_hero('Knight') == 'Knight'
    assert catalog.resolve_hero('Lord') == 'Knight'
    assert catalog.resolve_hero('Knight / Lord') == 'Knight'
    assert catalog.resolve_hero('Warden') == 'Ranger'
    assert catalog.resolve_hero('Jarl') == 'Berserker'
    assert catalog.resolve_hero('Axe') is None


def test_stcentral_only_supplies_bis_relationships():
    catalog = _catalog()
    html = '''
    <div class="hero-wrapper">
      <div class="hero-class-banner"><h1>Knight</h1></div>
      <div class="hero-equipment-slot" title="Tier 15 Shield of Test\nEnchanted with: Blaze Element"></div>
    </div>
    <div class="hero-wrapper">
      <div class="hero-class-banner"><h1>Lord</h1></div>
      <div class="hero-equipment-slot" title="Tier 15 Shield of Test\nEnchanted with: Blaze Element"></div>
    </div>
    '''
    parsed = parse_bis(html, catalog)
    assert list(parsed) == ['Knight']
    assert parsed['Knight']['items'] == ['Shield of Test']
    assert parsed['Knight']['label'] == 'Knight / Lord'


def test_unknown_component_aborts_instead_of_becoming_a_filter_value():
    sheets = {
        'BLUEPRINTS': _csv('''
            Name,Type,Tier,Resource 1,Resource 1 Amount,Component,Amount Needed,Component Quality
            Bad Item,Hat,15,Iron,10,Quality Chance,1,---
            Other Item,Hat,14,Iron,5,Ancient Amber,2,---
        '''),
        'HEROES': _csv('''
            Class,Promoted Class
            Knight,Lord
        '''),
        'QUEST COMPONENTS': _csv('''
            Component
            Ancient Amber
        '''),
        'RESOURCE BINS': _csv('''
            IRON BIN
            Bin Level
            1
        '''),
    }
    with pytest.raises(RuntimeError, match='Quality Chance'):
        parse_game_catalog(sheets, CFG)


def test_live_sheet_style_icon_only_resource_columns_are_mapped_from_resource_bins():
    # BLUEPRINTS' production-resource headers are blank because the live Google
    # Sheet uses icons. RESOURCE BINS supplies the resource names/order.
    sheets = {
        'BLUEPRINTS': _csv('''
            Name,Type,Tier,Required Worker,Worker Level,,,,,,,Component,Component Quality,Amount Needed
            Alpha Blade,Sword,15,Blacksmith,30,100,20,10,5,,,Ancient Amber,---,4
            Beta Blade,Sword,14,Blacksmith,29,80,15,8,3,,,Ancient Amber,---,2
        '''),
        'HEROES': _csv('''
            Class,Promoted Class
            Knight,Lord
        '''),
        'QUEST COMPONENTS': _csv('''
            Component
            Ancient Amber
        '''),
        # The real sheet lays parallel bin tables side-by-side. Reading the
        # furniture headings column-major gives the resource-column order.
        'RESOURCE BINS': _csv('''
            IRON BIN,,,STEEL BIN
            Bin Level,,,Bin Level
            1,,,1
            WOOD BIN,,,IRONWOOD BIN
            Bin Level,,,Bin Level
            1,,,1
        '''),
    }

    catalog = parse_game_catalog(sheets, CFG)
    assert catalog.resources == ('Iron', 'Wood', 'Steel', 'Ironwood')
    assert catalog.blueprints['Alpha Blade'].resources == {
        'Iron': 100,
        'Wood': 20,
        'Steel': 10,
        'Ironwood': 5,
    }
    assert catalog.blueprints['Alpha Blade'].components == {'Ancient Amber': 4}


def test_resource_display_spelling_is_recovered_from_blueprint_spent_text():
    sheets = {
        'BLUEPRINTS': _csv('''
            Name,Type,Tier,Required Worker,Worker Level,,,Component,Component Quality,Amount Needed,Crafting Upgrade 1,Crafting Upgrade 2
            Herb Test,Potion,10,Herbalist,20,200,30,Ancient Amber,---,2,-40 Herbs Spent,-6 Jewels Spent
            Herb Test 2,Potion,9,Herbalist,19,150,25,Ancient Amber,---,1,-30 Herbs Spent,-5 Jewels Spent
        '''),
        'HEROES': _csv('''
            Class,Promoted Class
            Druid,Arch Druid
        '''),
        'QUEST COMPONENTS': _csv('''
            Component
            Ancient Amber
        '''),
        'RESOURCE BINS': _csv('''
            HERB DRYER,,,JEWEL BIN
            Bin Level,,,Bin Level
            1,,,1
        '''),
    }

    catalog = parse_game_catalog(sheets, CFG)
    assert catalog.resources == ('Herbs', 'Jewels')
    assert catalog.blueprints['Herb Test'].resources == {'Herbs': 200, 'Jewels': 30}


def test_resource_bins_can_contain_resources_without_direct_blueprint_cost_columns():
    # RESOURCE BINS is the complete resource catalogue. Two resources below are
    # intentionally not referenced by BLUEPRINTS and therefore must not consume
    # one of the icon-only recipe amount columns.
    resource_names = [
        'Iron', 'Wood', 'Leather', 'Herbs', 'Steel', 'Ironwood',
        'Fabric', 'Oil', 'Ether', 'Jewels', 'Essence', 'Stardust',
        'Unused Alpha', 'Unused Beta',
    ]

    # Build 12 icon-only resource quantity columns plus separators. Every real
    # recipe resource is independently named in an authoritative "Spent" cell.
    headers = [
        'Name', 'Type', 'Tier',
        'Required Worker', 'Worker Level',
        '', '', '', '', '', '', '', '', '', '', '', '', '', '',
        'Component', 'Component Quality', 'Amount Needed',
        'Crafting Upgrade 1',
    ]
    row1 = [
        'Alpha', 'Sword', '15', 'Blacksmith', '30',
        '', '100', '90', '80', '70', '60', '50', '40', '30', '20', '10', '9', '8', '',
        'Ancient Amber', '---', '4', '-10 Iron Spent',
    ]
    row2 = [
        'Beta', 'Sword', '14', 'Blacksmith', '29',
        '', '90', '80', '70', '60', '50', '40', '30', '20', '10', '9', '8', '7', '',
        'Ancient Amber', '---', '2',
        '-10 Wood Spent / -10 Leather Spent / -10 Herbs Spent / -10 Steel Spent / '
        '-10 Ironwood Spent / -10 Fabric Spent / -10 Oil Spent / -10 Ether Spent / '
        '-10 Jewels Spent / -10 Essence Spent / -10 Stardust Spent',
    ]

    # Lay all 14 canonical resources out as separate furniture headings.
    bins_row = []
    for name in resource_names:
        bins_row.extend([f'{name.upper()} BIN', '', ''])

    import csv as _csv_module
    import io as _io
    def emit(rows):
        buf = _io.StringIO()
        w = _csv_module.writer(buf, lineterminator='\n')
        w.writerows(rows)
        return buf.getvalue()

    sheets = {
        'BLUEPRINTS': emit([headers, row1, row2]),
        'HEROES': _csv('''
            Class,Promoted Class
            Knight,Lord
        '''),
        'QUEST COMPONENTS': _csv('''
            Component
            Ancient Amber
        '''),
        'RESOURCE BINS': emit([bins_row]),
    }

    catalog = parse_game_catalog(sheets, CFG)
    assert len(catalog.resources) == 14
    assert catalog.blueprints['Alpha'].resources == {
        name: qty
        for name, qty in zip(resource_names[:12], [100, 90, 80, 70, 60, 50, 40, 30, 20, 10, 9, 8])
    }
    assert 'Unused Alpha' not in catalog.blueprints['Alpha'].resources
    assert 'Unused Beta' not in catalog.blueprints['Alpha'].resources


def test_live_heroes_parallel_card_layout_is_parsed_without_class_column():
    import csv as _csv_module
    import io as _io

    def emit(rows):
        buf = _io.StringIO()
        w = _csv_module.writer(buf, lineterminator='\n')
        w.writerows(rows)
        return buf.getvalue()

    width = 25
    def row(*pairs):
        values = [''] * width
        for col, value in pairs:
            values[col] = value
        return values

    heroes_rows = [
        row(
            (1, "FIGHTER CLASSES Hero stats listed take into account the hero's innate skill, where applicable."),
            (9, "ROGUE CLASSES Hero stats listed take into account the hero's innate skill, where applicable."),
            (17, "SPELLCASTER CLASSES Hero stats listed take into account the hero's innate skill, where applicable."),
        ),
        row((0, 'SOLDIER'), (1, 'ELEMENT'), (8, 'THIEF'), (9, 'ELEMENT'), (16, 'MAGE'), (17, 'ELEMENT')),
        row((0, 'Promotion'), (1, 'Mercenary'), (8, 'Promotion'), (9, 'Trickster'), (16, 'Promotion'), (17, 'Archmage')),
        row((0, 'KNIGHT'), (1, 'ELEMENT'), (8, 'WANDERER'), (9, 'ELEMENT'), (16, 'DRUID'), (17, 'ELEMENT')),
        row((0, 'Promotes to: Lord'), (8, 'Promotes to: Pathfinder'), (16, 'Promotes to: Arch Druid')),
        row((0, 'BERSERKER'), (1, 'ELEMENT'), (8, 'NINJA'), (9, 'ELEMENT'), (16, 'SPELLBLADE'), (17, 'ELEMENT')),
        row((0, 'Titan Soul Promotion'), (1, 'Jarl'), (8, 'Titan Soul Promotion'), (9, 'Sensei'), (16, 'Titan Soul Promotion'), (17, 'Spellknight')),
    ]

    sheets = {
        'BLUEPRINTS': _csv('''
            Name,Type,Tier,Resource 1,Resource 1 Amount,Component,Amount Needed
            Alpha,Sword,15,Iron,10,Ancient Amber,2
            Beta,Sword,14,Iron,5,Ancient Amber,1
        '''),
        'HEROES': emit(heroes_rows),
        'QUEST COMPONENTS': _csv('''
            Component
            Ancient Amber
        '''),
        'RESOURCE BINS': _csv('''
            IRON BIN
            Bin Level
            1
        '''),
    }

    catalog = parse_game_catalog(sheets, CFG)
    assert catalog.resolve_hero('Soldier') == 'Soldier'
    assert catalog.resolve_hero('Mercenary') == 'Soldier'
    assert catalog.resolve_hero('Lord') == 'Knight'
    assert catalog.resolve_hero('Pathfinder') == 'Wanderer'
    assert catalog.resolve_hero('Jarl') == 'Berserker'
    assert catalog.resolve_hero('Sensei') == 'Ninja'
    assert catalog.resolve_hero('Spellknight') == 'Spellblade'
    assert catalog.resolve_hero('ELEMENT') is None
    assert set(catalog.heroes) >= {'Soldier', 'Knight', 'Berserker', 'Thief', 'Wanderer', 'Ninja', 'Mage', 'Druid', 'Spellblade'}


def test_live_heroes_card_title_may_be_right_of_element_after_csv_merge_flattening():
    import csv as _csv_module
    import io as _io

    def emit(rows):
        buf = _io.StringIO()
        w = _csv_module.writer(buf, lineterminator='\n')
        w.writerows(rows)
        return buf.getvalue()

    width = 24
    def row(*pairs):
        values = [''] * width
        for col, value in pairs:
            values[col] = value
        return values

    # Simulate Google CSV flattening a merged visual card so the class title is
    # emitted to the right of ELEMENT instead of immediately to its left.
    heroes_rows = [
        row((0, 'FIGHTER CLASSES'), (8, 'ROGUE CLASSES'), (16, 'SPELLCASTER CLASSES')),
        row((0, 'ELEMENT'), (2, 'SOLDIER'), (8, 'ELEMENT'), (10, 'THIEF'), (16, 'ELEMENT'), (18, 'MAGE')),
        row((0, 'Promotion'), (1, 'Mercenary'), (8, 'Promotion'), (9, 'Trickster'), (16, 'Promotion'), (17, 'Archmage')),
        row((0, 'ELEMENT'), (2, 'KNIGHT'), (8, 'ELEMENT'), (10, 'WANDERER'), (16, 'ELEMENT'), (18, 'DRUID')),
        row((0, 'Promotes to: Lord'), (8, 'Promotes to: Pathfinder'), (16, 'Promotes to: Arch Druid')),
    ]

    sheets = {
        'BLUEPRINTS': _csv('''
            Name,Type,Tier,Resource 1,Resource 1 Amount,Component,Amount Needed
            Alpha,Sword,15,Iron,10,Ancient Amber,2
            Beta,Sword,14,Iron,5,Ancient Amber,1
        '''),
        'HEROES': emit(heroes_rows),
        'QUEST COMPONENTS': _csv('''
            Component
            Ancient Amber
        '''),
        'RESOURCE BINS': _csv('''
            IRON BIN
            Bin Level
            1
        '''),
    }

    catalog = parse_game_catalog(sheets, CFG)
    assert catalog.resolve_hero('Soldier') == 'Soldier'
    assert catalog.resolve_hero('Mercenary') == 'Soldier'
    assert catalog.resolve_hero('Lord') == 'Knight'
    assert catalog.resolve_hero('Trickster') == 'Thief'
    assert catalog.resolve_hero('Pathfinder') == 'Wanderer'
    assert catalog.resolve_hero('Archmage') == 'Mage'
