"""Domain layer for the zombie game."""

from .player import Player, MoveResult
from .map import GameMap
from .item import Item, ItemResolution, ItemType, MEDKIT_HEAL, ZOMBIE_DAMAGE

__all__ = [
    "GameMap",
    "Item",
    "ItemResolution",
    "ItemType",
    "MEDKIT_HEAL",
    "MoveResult",
    "Player",
    "ZOMBIE_DAMAGE",
]
