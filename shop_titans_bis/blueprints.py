"""Compatibility exports for the spreadsheet-backed game catalogue.

The original project parsed BLUEPRINTS in isolation from this module. The
canonical implementation now lives in :mod:`shop_titans_bis.spreadsheet`
because recipes, heroes, resources and components are cross-validated across
multiple sheets of the same official workbook.
"""
from .spreadsheet import Blueprint, GameCatalog, load_game_catalog, parse_game_catalog

__all__ = ['Blueprint', 'GameCatalog', 'load_game_catalog', 'parse_game_catalog']
