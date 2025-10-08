import random
from enum import Enum
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set, Tuple

from domain import GameMap, Item, ItemResolution, ItemType, Player


class GamePhase(str, Enum):
    LOBBY = "lobby"
    PLAYING = "playing"


@dataclass(frozen=True)
class PlayerFinishResult:
    finished: bool
    inventory_changed: bool = False
    reason: Optional[str] = None


class GameState:
    """Singleton-like state describing current game phase and activity."""

    _instance: Optional["GameState"] = None

    def __new__(cls) -> "GameState":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.active = False
            cls._instance.phase = GamePhase.LOBBY
            cls._instance.turn_order = []
            cls._instance.current_turn_index = -1
            cls._instance.current_turn_player_id: Optional[str] = None
            cls._instance.steps_remaining = 0
        return cls._instance

    def reset(self) -> None:
        self.active = False
        self.phase = GamePhase.LOBBY
        self.turn_order = []
        self.current_turn_index = -1
        self.current_turn_player_id = None
        self.steps_remaining = 0


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
        self.door_unlocked = False
        self.finish_required_items: Tuple[str, ...] = ("key", "fuel")

    # ------------------------------------------------------------------
    # Special cells
    # ------------------------------------------------------------------
    @property
    def spawn_cell(self) -> int:
        return self.game_map.spawn_cell()

    @property
    def finish_cell(self) -> int:
        return self.game_map.finish_cell()

    def is_spawn_cell(self, cell: int) -> bool:
        return cell == self.spawn_cell

    def is_finish_cell(self, cell: int) -> bool:
        return cell == self.finish_cell

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
        if player is not None:
            self.handle_player_inactive(player)
        return player

    def get_player(self, player_id: str) -> Optional[Player]:
        return self.players.get(player_id)

    def occupied_cells(self, exclude_player_id: Optional[str] = None) -> Set[int]:
        occupied: Set[int] = set()
        for pid, player in self.players.items():
            if exclude_player_id is not None and pid == exclude_player_id:
                continue
            if not player.finished:
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
        self.door_unlocked = False

        occupied: Set[int] = set()
        for player in sorted(self.players.values(), key=lambda p: p.id):
            cell = self.game_map.first_free_start_cell(occupied)
            player.reset_for_new_game(cell=cell)
            occupied.add(cell)
            self.game_map.mark_revealed(cell)

        self.state.reset()
        return list(self.players.values())

    def start_game(self) -> None:
        self.door_unlocked = False
        self.state.active = True
        self.state.phase = GamePhase.PLAYING
        self.state.turn_order = []
        self.state.current_turn_index = -1
        self.state.current_turn_player_id = None
        self.state.steps_remaining = 0

    # ------------------------------------------------------------------
    # Turn management
    # ------------------------------------------------------------------
    def roll_turn_length(self) -> int:
        return int(self.rng.randint(1, 4))

    def start_turn_cycle(self) -> Optional[Player]:
        self.state.turn_order = [
            player.id for player in self.players.values() if player.alive and not player.finished
        ]
        self.state.current_turn_index = -1
        self.state.current_turn_player_id = None
        self.state.steps_remaining = 0
        if not self.state.turn_order:
            return None
        return self._advance_to_next_turn()

    def _advance_to_next_turn(self) -> Optional[Player]:
        if not self.state.turn_order:
            self.state.current_turn_index = -1
            self.state.current_turn_player_id = None
            self.state.steps_remaining = 0
            return None

        for _ in range(len(self.state.turn_order)):
            self.state.current_turn_index = (self.state.current_turn_index + 1) % len(self.state.turn_order)
            player_id = self.state.turn_order[self.state.current_turn_index]
            player = self.players.get(player_id)
            if player and player.alive and not player.finished:
                self.state.current_turn_player_id = player_id
                self.state.steps_remaining = self.roll_turn_length()
                return player

        self.state.current_turn_index = -1
        self.state.current_turn_player_id = None
        self.state.steps_remaining = 0
        return None

    def consume_step(self, player: Player, *, force_end: bool = False, spend: bool = True) -> Optional[Player]:
        if self.state.current_turn_player_id != player.id:
            return None

        if spend and self.state.steps_remaining > 0:
            self.state.steps_remaining -= 1

        if force_end:
            self.state.steps_remaining = 0

        if self.state.steps_remaining <= 0:
            return self._advance_to_next_turn()

        return player

    def is_player_turn(self, player: Player) -> bool:
        return self.state.current_turn_player_id == player.id

    def handle_player_inactive(self, player: Player) -> None:
        player_id = player.id
        if player_id not in self.state.turn_order:
            return

        idx = self.state.turn_order.index(player_id)
        self.state.turn_order.pop(idx)

        if idx < self.state.current_turn_index:
            self.state.current_turn_index -= 1
        elif idx == self.state.current_turn_index:
            self.state.current_turn_index -= 1
            self.state.current_turn_player_id = None
            self.state.steps_remaining = 0
            if self.state.active:
                self._advance_to_next_turn()

    def turn_snapshot(self) -> Dict[str, object]:
        return {
            "current": self.state.current_turn_player_id,
            "remaining": self.state.steps_remaining,
            "order": list(self.state.turn_order),
        }

    def can_player_finish(self, player: Player) -> bool:
        if self.door_unlocked:
            return True
        inventory = set(player.inventory)
        return all(item in inventory for item in self.finish_required_items)

    def mark_player_finished(self, player: Player) -> PlayerFinishResult:
        if player.finished:
            return PlayerFinishResult(finished=False, reason="already_finished")

        if not self.can_player_finish(player):
            return PlayerFinishResult(finished=False, reason="missing_items")

        inventory_changed = False
        if not self.door_unlocked:
            for item in self.finish_required_items:
                removed = player.remove_item(item)
                inventory_changed = inventory_changed or removed
            self.door_unlocked = True

        player.finished = True
        return PlayerFinishResult(finished=True, inventory_changed=inventory_changed)

    def all_players_resolved(self) -> bool:
        if not self.players:
            return False
        for player in self.players.values():
            if player.alive and not player.finished:
                return False
        return True

    def finalize_if_complete(self) -> bool:
        if not self.state.active:
            return False
        if not self.all_players_resolved():
            return False
        self.state.active = False
        self.state.phase = GamePhase.LOBBY
        self.state.turn_order = []
        self.state.current_turn_index = -1
        self.state.current_turn_player_id = None
        self.state.steps_remaining = 0
        return True


__all__ = ["PlayerFinishResult", "GameLogic", "GamePhase", "GameState"]
