import random
from enum import Enum
from typing import Dict, Iterable, List, Optional, Set, Tuple

from domain import GameMap, Item, ItemResolution, ItemType, Player


class GamePhase(str, Enum):
    LOBBY = "lobby"
    PLAYING = "playing"


class GameState:
    """Singleton-like state describing current game phase and activity."""

    _instance: Optional["GameState"] = None

    def __new__(cls) -> "GameState":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.active = False
            cls._instance.phase = GamePhase.LOBBY
        return cls._instance

    def reset(self) -> None:
        self.active = False
        self.phase = GamePhase.LOBBY


class GameLogic:
    """Encapsulates game-related business logic independent from transport."""

    def __init__(
        self,
        grid_size: int,
        item_counts: Dict[ItemType, int],
        *,
        hazard_on_enter: bool = True,
        hazard_prob: float = 0.25,
        hazard_damage: int = 1,
        rng: random.Random = random,
    ) -> None:
        self.grid_size = grid_size
        self.item_counts = item_counts
        self.hazard_on_enter = hazard_on_enter
        self.hazard_prob = hazard_prob
        self.hazard_damage = hazard_damage
        self.rng = rng

        self.state = GameState()
        self.game_map = GameMap(grid_size, item_counts, rng=rng)
        self.players: Dict[str, Player] = {}

    def list_players(self) -> List[Player]:
        return list(self.players.values())

    def add_player(self, player_id: str) -> Player:
        cell = self.game_map.first_free_start_cell(self.occupied_cells())
        player = Player(player_id=player_id, cell=cell)
        self.players[player.id] = player
        self.game_map.mark_revealed(cell)
        return player

    def remove_player(self, player_id: str) -> Optional[Player]:
        player = self.players.pop(player_id, None)
        return player

    def get_player(self, player_id: str) -> Optional[Player]:
        return self.players.get(player_id)

    def occupied_cells(self, exclude_player_id: Optional[str] = None) -> Set[int]:
        occupied: Set[int] = set()
        for pid, player in self.players.items():
            if exclude_player_id is not None and pid == exclude_player_id:
                continue
            occupied.add(player.cell)
        return occupied

    def translate_cell(self, cell: int, dx: int, dy: int) -> int:
        return self.game_map.translate(cell, dx, dy)

    def mark_revealed(self, cell: int) -> bool:
        return self.game_map.mark_revealed(cell)

    def revealed_snapshot(self) -> Iterable[int]:
        return self.game_map.revealed_snapshot()

    def iter_items(self) -> Iterable[Tuple[int, Item]]:
        return self.game_map.iter_items()

    def should_trigger_hazard(self) -> bool:
        if not self.hazard_on_enter:
            return False
        return self.rng.random() < self.hazard_prob

    def adjust_player_lives(self, player: Player, amount: int) -> bool:
        if amount == 0:
            return False

        died = False
        if amount > 0:
            damage = player.apply_damage(amount)
            died = damage > 0 and not player.alive
        else:
            player.heal(-amount)
        return died

    def resolve_cell_item(self, player: Player) -> Optional[Tuple[Item, ItemResolution]]:
        item = self.game_map.take_item(player.cell)
        if not item:
            return None
        result = item.apply(player)
        return item, result

    def restart_game(self) -> List[Player]:
        self.game_map.reset()

        occupied: Set[int] = set()
        for player in sorted(self.players.values(), key=lambda p: p.id):
            cell = self.game_map.first_free_start_cell(occupied)
            player.reset_for_new_game(cell=cell)
            occupied.add(cell)
            self.game_map.mark_revealed(cell)

        self.state.reset()
        return list(self.players.values())

    def start_game(self) -> None:
        self.state.active = True
        self.state.phase = GamePhase.PLAYING


__all__ = ["GameLogic", "GamePhase", "GameState"]
