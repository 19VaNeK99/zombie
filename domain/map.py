from __future__ import annotations

import random
from collections import deque
from typing import Dict, Iterable, Iterator, Optional, Sequence, Set, Tuple

from .item import Item, ItemType


class GameMap:
    """Aggregate that manages map state, revealed cells and item placement."""

    def __init__(
        self,
        size: int,
        item_counts: Dict[ItemType, int],
        *,
        rng: Optional[random.Random] = None,
    ) -> None:
        self.size = size
        self._item_counts = dict(item_counts)
        self._rng = rng or random
        self._revealed: Set[int] = set()
        self._items: Dict[int, Item] = {}
        self.reset_items()

    # ------------------------------------------------------------------
    # Special cells
    # ------------------------------------------------------------------
    def spawn_cell(self) -> int:
        """Return the dedicated spawn cell (bottom-left corner)."""
        return self.from_rc(self.size - 1, 0)

    def finish_cell(self) -> int:
        """Return the dedicated finish cell (top-right corner)."""
        return self.from_rc(0, self.size - 1)

    # ------------------------------------------------------------------
    # Geometry helpers
    # ------------------------------------------------------------------
    @property
    def total_cells(self) -> int:
        return self.size * self.size

    def clamp_cell(self, cell: int) -> int:
        return max(1, min(self.total_cells, cell))

    def to_rc(self, cell: int) -> Tuple[int, int]:
        idx = self.clamp_cell(cell) - 1
        return idx // self.size, idx % self.size

    def from_rc(self, row: int, col: int) -> int:
        row = max(0, min(self.size - 1, row))
        col = max(0, min(self.size - 1, col))
        return row * self.size + col + 1

    def translate(self, cell: int, dx: int, dy: int) -> int:
        r, c = self.to_rc(cell)
        return self.from_rc(r + dy, c + dx)

    def center_cell(self) -> int:
        mid = self.size // 2
        return self.from_rc(mid, mid)

    def _neighbors(self, cell: int) -> Iterable[int]:
        r, c = self.to_rc(cell)
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < self.size and 0 <= nc < self.size:
                yield self.from_rc(nr, nc)

    # ------------------------------------------------------------------
    # Items & revealed cells
    # ------------------------------------------------------------------
    def reset_items(self) -> None:
        self._items = self._generate_items()

    def reset_revealed(self) -> None:
        self._revealed.clear()

    def reset(self) -> None:
        self.reset_revealed()
        self.reset_items()

    def mark_revealed(self, cell: int) -> bool:
        if cell in self._revealed:
            return False
        self._revealed.add(cell)
        return True

    def revealed_snapshot(self) -> Sequence[int]:
        return tuple(sorted(self._revealed))

    def iter_items(self) -> Iterator[Tuple[int, Item]]:
        for cell, item in sorted(self._items.items()):
            yield cell, item

    def take_item(self, cell: int) -> Optional[Item]:
        return self._items.pop(cell, None)

    def place_item(self, cell: int, item: Item) -> None:
        self._items[cell] = item

    def nearest_revealed_cell(
        self,
        start: int,
        *,
        exclude: Optional[Set[int]] = None,
        occupied: Optional[Set[int]] = None,
    ) -> Optional[int]:
        exclude_set = set(exclude) if exclude else set()
        occupied_set = set(occupied) if occupied else set()
        visited: Set[int] = set()
        queue = deque([start])
        visited.add(start)

        while queue:
            cell = queue.popleft()
            if cell in self._revealed and cell not in exclude_set and cell not in occupied_set:
                return cell
            for neighbor in self._neighbors(cell):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        return None

    # ------------------------------------------------------------------
    # Spawn helpers
    # ------------------------------------------------------------------
    def first_free_start_cell(self, occupied: Iterable[int]) -> int:
        occupied_set = set(occupied)
        # Игроки всегда появляются в одной стартовой точке, поэтому занятость
        # остальных игроков не учитывается.
        return self.spawn_cell()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _generate_items(self) -> Dict[int, Item]:
        total_cells = self.total_cells
        forbidden = {self.center_cell(), self.spawn_cell(), self.finish_cell()}
        available_cells = [cell for cell in range(1, total_cells + 1) if cell not in forbidden]
        placements: Dict[int, Item] = {}

        for item_type, count in self._item_counts.items():
            if count <= 0 or not available_cells:
                continue

            count = min(count, len(available_cells))
            chosen = self._rng.sample(available_cells, count)
            for cell in chosen:
                placements[cell] = Item(item_type)
                available_cells.remove(cell)

        return placements
