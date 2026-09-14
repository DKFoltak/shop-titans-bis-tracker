from pathlib import Path

from shop_titans_bis.sources import LOCAL_FILES


def test_local_source_file_names_are_stable():
    assert LOCAL_FILES == {
        'blueprints': 'BLUEPRINTS.csv',
        'heroes': 'HEROES.csv',
        'resource_bins': 'RESOURCE_BINS.csv',
        'quest_components': 'QUEST_COMPONENTS.csv',
        'full_moon_fusions': 'FULL_MOON_FUSIONS.csv',
    }
