from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .player import Player

ZOMBIE_DAMAGE = 1
MEDKIT_HEAL = 1


class ItemType(str, Enum):
    ZOMBIE = "zombie"
    MEDKIT = "medkit"
    WEAPON = "weapon"
    KEY = "key"
    FUEL = "fuel"

    @classmethod
    def from_string(cls, value: str) -> "ItemType":
        try:
            return cls(value)
        except ValueError as exc:
            raise ValueError(f"Unknown item type: {value}") from exc


@dataclass
class ItemResolution:
    """Result of applying an item to a player."""

    damage: int = 0
    healed: int = 0
    inventory_added: Optional[str] = None
    died: bool = False

    @property
    def affects_lives(self) -> bool:
        return self.damage > 0 or self.healed > 0 or self.died

    @property
    def inventory_changed(self) -> bool:
        return bool(self.inventory_added)


@dataclass(frozen=True)
class Item:
    item_type: ItemType

    def apply(self, player: Player) -> ItemResolution:
        if self.item_type is ItemType.ZOMBIE:
            damage = player.apply_damage(ZOMBIE_DAMAGE)
            return ItemResolution(damage=damage, died=not player.alive)
        if self.item_type is ItemType.MEDKIT:
            healed = player.heal(MEDKIT_HEAL)
            return ItemResolution(healed=healed, died=not player.alive)
        if self.item_type in (ItemType.WEAPON, ItemType.KEY, ItemType.FUEL):
            collected = player.collect_item(self.item_type)
            return ItemResolution(inventory_added=collected, died=not player.alive)
        raise ValueError(f"Unsupported item type: {self.item_type}")
