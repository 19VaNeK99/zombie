import json
import random
import uuid
from enum import Enum
from typing import Dict, List, Optional, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from domain import GameMap, ItemType, Player

# ===================== Настройки =====================
MAX_CLIENTS = 5
GRID_SIZE = 5

# --- Генерация предметов на карте ---
ITEM_COUNTS: Dict[ItemType, int] = {
    ItemType.ZOMBIE: 3,
    ItemType.MEDKIT: 2,
    ItemType.WEAPON: 2,
}

# --- Новые параметры автосмерти/опасности ---
HAZARD_ON_ENTER = True    # проверка опасности на входе в новую клетку
HAZARD_PROB = 0.25        # шанс срабатывания (25%)
HAZARD_DAMAGE = 1         # урон при срабатывании
# random.seed(42)         # при желании — зафиксировать сид для воспроизводимости

# ===================== Глобальное состояние комнаты =====================

active_connections: List[WebSocket] = []
players_by_ws: Dict[WebSocket, Player] = {}
players_by_id: Dict[str, Player] = {}
player_connections: Dict[str, WebSocket] = {}
class GamePhase(str, Enum):
    LOBBY = "lobby"
    PLAYING = "playing"


class GameState:
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


game_state = GameState()

game_map = GameMap(GRID_SIZE, ITEM_COUNTS, rng=random)


# ===================== Приложение =====================

app = FastAPI()

# ===================== Отправка =====================

async def send_json(ws: WebSocket, payload: Dict):
    await ws.send_text(json.dumps(payload, ensure_ascii=False))

async def broadcast_json(payload: Dict):
    txt = json.dumps(payload, ensure_ascii=False)
    for ws in list(active_connections):
        try:
            await ws.send_text(txt)
        except Exception:
            try:
                active_connections.remove(ws)
            except ValueError:
                pass

def get_player_ws(player: Player) -> Optional[WebSocket]:
    return player_connections.get(player.id)

async def notify_game_inactive(ws: WebSocket) -> None:
    await send_json(ws, {"t": "error", "code": "not_active", "reason": "game_not_active"})


async def send_full_state(player: Player) -> None:
    """Отправляет игроку полный снимок состояния."""
    ws = get_player_ws(player)
    if ws is None:
        return

    payload = {
        "t": "state",
        "n": GRID_SIZE,
        "revealed": list(game_map.revealed_snapshot()),
        "player": player.to_public(),
        "items": [
            {"cell": cell, "item": item.item_type.value}
            for cell, item in game_map.iter_items()
        ],
        "game_active": game_state.active,
        "game_phase": game_state.phase.value,
        "joinable": game_state.phase is GamePhase.LOBBY,
        "players": [p.to_public() for p in players_by_id.values()],
    }
    await send_json(ws, payload)


async def broadcast_player_snapshot(player: Player) -> None:
    """Шлёт всем актуальное состояние одного игрока."""
    await broadcast_json({
        "t": "player",
        "id": player.id,
        "cell": player.cell,
        "lives": player.lives,
        "alive": player.alive,
    })


async def broadcast_players_list() -> None:
    """Рассылает полный список игроков всем подключённым клиентам."""
    await broadcast_json({
        "t": "players",
        "players": [p.to_public() for p in players_by_id.values()],
    })


async def broadcast_game_status(state: str, *, by: Optional[str] = None) -> None:
    """Сообщает всем о смене статуса игры."""
    payload: Dict[str, object] = {
        "t": "game",
        "state": state,
        "active": game_state.active,
        "phase": game_state.phase.value,
        "joinable": game_state.phase is GamePhase.LOBBY,
    }
    if by is not None:
        payload["by"] = by
    await broadcast_json(payload)


async def adjust_player_lives(player: Player, amount: int) -> bool:
    """Применяет изменение жизней (>0 — урон, <0 — лечение)."""
    if amount == 0:
        return False

    died = False
    if amount > 0:
        damage = player.apply_damage(amount)
        died = damage > 0 and not player.alive
    else:
        player.heal(-amount)

    await broadcast_player_snapshot(player)
    if died:
        await broadcast_json({"t": "death", "id": player.id, "cell": player.cell})
    return died


async def resolve_cell_item(player: Player) -> None:
    """Применяет эффект предмета на текущей клетке (если есть)."""
    item = game_map.take_item(player.cell)
    if not item:
        return

    payload = {"t": "item", "cell": player.cell, "item": item.item_type.value, "by": player.id}
    await broadcast_json(payload)

    result = item.apply(player)
    if result.affects_lives:
        await broadcast_player_snapshot(player)
        if result.died:
            await broadcast_json({"t": "death", "id": player.id, "cell": player.cell})

    if result.inventory_changed:
        ws = get_player_ws(player)
        if ws is not None:
            await send_json(ws, {"t": "inventory", "items": player.inventory_snapshot()})


def occupied_cells(*, except_ws: Optional[WebSocket] = None) -> Set[int]:
    """Набор занятых клеток всеми игроками; можно исключить одного."""
    occ: Set[int] = set()
    for ws, player in players_by_ws.items():
        if except_ws is not None and ws is except_ws:
            continue
        occ.add(player.cell)
    return occ


async def restart_game(requester: Optional[Player] = None) -> None:
    """Полностью перезапускает игру: предметы, позиции, жизни."""
    game_map.reset()

    occupied: Set[int] = set()
    for player in sorted(players_by_id.values(), key=lambda p: p.id):
        cell = game_map.first_free_start_cell(occupied)
        player.reset_for_new_game(cell=cell)
        occupied.add(cell)
        game_map.mark_revealed(cell)

    game_state.reset()

    for player in list(players_by_id.values()):
        ws = get_player_ws(player)
        if ws is not None:
            await send_json(ws, {"t": "inventory", "items": player.inventory_snapshot()})

    for player in list(players_by_id.values()):
        await send_full_state(player)

    for player in list(players_by_id.values()):
        await broadcast_player_snapshot(player)

    await broadcast_players_list()

    await broadcast_game_status("ready", by=requester.id if requester else None)


# ===================== WebSocket =====================

@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    if game_state.phase is not GamePhase.LOBBY:
        await send_json(
            websocket,
            {
                "t": "error",
                "code": "game_in_progress",
                "reason": "game_already_started",
            },
        )
        await websocket.close()
        return

    if len(active_connections) >= MAX_CLIENTS:
        await websocket.send_text("Комната переполнена, соединение отклонено.")
        await websocket.close()
        return

    active_connections.append(websocket)

    pid = uuid.uuid4().hex[:8]
    start_cell = game_map.first_free_start_cell(occupied_cells())
    player = Player(player_id=pid, cell=start_cell)
    players_by_ws[websocket] = player
    players_by_id[player.id] = player
    player_connections[player.id] = websocket

    game_map.mark_revealed(start_cell)

    await send_full_state(player)
    await broadcast_player_snapshot(player)
    await broadcast_players_list()

    if game_state.active and player.alive:
        await resolve_cell_item(player)

    try:
        while True:
            raw = await websocket.receive_text()

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            mtype = msg.get("t")

            if mtype == "move":
                if not game_state.active:
                    await notify_game_inactive(websocket)
                    continue

                dx = int(msg.get("dx", 0))
                dy = int(msg.get("dy", 0))

                target_cell = game_map.translate(player.cell, dx, dy)
                move_result = player.attempt_move(
                    dx=dx,
                    dy=dy,
                    target_cell=target_cell,
                    occupied=occupied_cells(except_ws=websocket),
                )

                if not move_result.success:
                    await send_json(websocket, {"t": "error", "code": move_result.reason, "reason": move_result.reason})
                    continue

                newly = []
                if game_map.mark_revealed(player.cell):
                    newly.append(player.cell)

                await broadcast_player_snapshot(player)

                if newly:
                    await broadcast_json({"t": "reveal", "cells": newly})

                    if HAZARD_ON_ENTER and random.random() < HAZARD_PROB and player.alive:
                        died = await adjust_player_lives(player, HAZARD_DAMAGE)
                        if died:
                            continue

                if player.alive:
                    await resolve_cell_item(player)

            elif mtype == "damage":
                if not game_state.active:
                    await notify_game_inactive(websocket)
                    continue
                amount = int(msg.get("amount", 0))
                await adjust_player_lives(player, amount)

            elif mtype == "pickup":
                if not game_state.active:
                    await notify_game_inactive(websocket)
                    continue
                item = str(msg.get("item", "")).strip()
                if item:
                    player.add_item(item)
                    ws = get_player_ws(player)
                    if ws is not None:
                        await send_json(ws, {"t": "inventory", "items": player.inventory_snapshot()})

            elif mtype == "drop":
                if not game_state.active:
                    await notify_game_inactive(websocket)
                    continue
                item = str(msg.get("item", "")).strip()
                if player.remove_item(item):
                    ws = get_player_ws(player)
                    if ws is not None:
                        await send_json(ws, {"t": "inventory", "items": player.inventory_snapshot()})

            elif mtype == "start":
                if game_state.active:
                    await send_json(websocket, {"t": "error", "code": "already_started", "reason": "game_already_active"})
                    continue
                game_state.active = True
                game_state.phase = GamePhase.PLAYING
                await broadcast_game_status("started", by=player.id)
                for pl in list(players_by_id.values()):
                    await broadcast_player_snapshot(pl)
                for pl in list(players_by_id.values()):
                    if pl.alive:
                        await resolve_cell_item(pl)

            elif mtype == "restart":
                await restart_game(player)

    except WebSocketDisconnect:
        if websocket in active_connections:
            active_connections.remove(websocket)
        player = players_by_ws.pop(websocket, None)
        if player is not None:
            players_by_id.pop(player.id, None)
            player_connections.pop(player.id, None)
            await broadcast_players_list()
