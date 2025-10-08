from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Set, Tuple


@dataclass(frozen=True)
class MoveResult:
    """Result of a movement attempt."""

    success: bool
    reason: Optional[str] = None


class Player:
    """Domain entity that encapsulates player state and invariants."""

    MAX_LIVES: int = 9
    START_LIVES: int = 3

    def __init__(self, player_id: str, cell: int, *, lives: Optional[int] = None, inventory: Optional[Iterable[str]] = None) -> None:
        self.id = player_id
        self.cell = cell
        self.lives = lives if lives is not None else self.START_LIVES
        self._inventory: List[str] = list(inventory or [])
        self.finished = False

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------
    @property
    def alive(self) -> bool:
        return self.lives > 0

    @property
    def inventory(self) -> Tuple[str, ...]:
        return tuple(self._inventory)

    def inventory_snapshot(self) -> List[str]:
        return list(self._inventory)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def reset_for_new_game(self, *, cell: int, lives: Optional[int] = None) -> None:
        self.cell = cell
        self.lives = lives if lives is not None else self.START_LIVES
        self._inventory.clear()
        self.finished = False

    # ------------------------------------------------------------------
    # Movement
    # ------------------------------------------------------------------
    def attempt_move(
        self,
        *,
        dx: int,
        dy: int,
        target_cell: int,
        occupied: Set[int],
        shared_cells: Optional[Set[int]] = None,
    ) -> MoveResult:
        if self.finished:
            return MoveResult(success=False, reason="finished")

        if not self.alive:
            return MoveResult(success=False, reason="dead")

        if target_cell in occupied and (shared_cells is None or target_cell not in shared_cells):
            return MoveResult(success=False, reason="occupied")

        self.cell = target_cell
        return MoveResult(success=True)

    # ------------------------------------------------------------------
    # Health management
    # ------------------------------------------------------------------
    def apply_damage(self, amount: int) -> int:
        if amount < 0:
            raise ValueError("damage amount must be non-negative")

        before = self.lives
        self.lives = max(0, self.lives - amount)
        return before - self.lives

    def heal(self, amount: int) -> int:
        if amount < 0:
            raise ValueError("heal amount must be non-negative")

        before = self.lives
        self.lives = min(self.MAX_LIVES, self.lives + amount)
        return self.lives - before

    # ------------------------------------------------------------------
    # Inventory management
    # ------------------------------------------------------------------
    def add_item(self, item: str) -> None:
        self._inventory.append(item)

    def remove_item(self, item: str) -> bool:
        try:
            self._inventory.remove(item)
        except ValueError:
            return False
        return True

    def clear_inventory(self) -> None:
        self._inventory.clear()

    # ------------------------------------------------------------------
    # Presentation
    # ------------------------------------------------------------------
    def to_public(self) -> dict:
        return {
            "id": self.id,
            "cell": self.cell,
            "lives": self.lives,
            "alive": self.alive,
            "finished": self.finished,
            "inventory": self.inventory_snapshot(),
        }
