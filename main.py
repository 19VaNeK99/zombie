import json
import random
import uuid
from typing import Dict, List, Optional, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from domain import ItemType, Player
from game_logic import GameLogic, GamePhase

# ===================== Настройки =====================
MAX_CLIENTS = 5
GRID_SIZE = 5

# --- Генерация предметов на карте ---
ITEM_COUNTS = {
    ItemType.ZOMBIE: 3,
    ItemType.MEDKIT: 2,
    ItemType.WEAPON: 2,
}

# --- Новые параметры автосмерти/опасности ---
HAZARD_ON_ENTER = True
HAZARD_PROB = 0.25
HAZARD_DAMAGE = 1

# ===================== Глобальное состояние =====================

logic = GameLogic(
    GRID_SIZE,
    ITEM_COUNTS,
    hazard_on_enter=HAZARD_ON_ENTER,
    hazard_prob=HAZARD_PROB,
    hazard_damage=HAZARD_DAMAGE,
    rng=random,
)

active_connections: List[WebSocket] = []
players_by_ws: Dict[WebSocket, Player] = {}
player_connections: Dict[str, WebSocket] = {}

# ===================== Приложение =====================

app = FastAPI()


# ===================== Отправка =====================

async def send_json(ws: WebSocket, payload: Dict) -> None:
    await ws.send_text(json.dumps(payload, ensure_ascii=False))


def get_player_ws(player: Player) -> Optional[WebSocket]:
    return player_connections.get(player.id)


async def broadcast_json(payload: Dict) -> None:
    txt = json.dumps(payload, ensure_ascii=False)
    for ws in list(active_connections):
        try:
            await ws.send_text(txt)
        except Exception:
            try:
                active_connections.remove(ws)
            except ValueError:
                pass


async def notify_game_inactive(ws: WebSocket) -> None:
    await send_json(ws, {"t": "error", "code": "not_active", "reason": "game_not_active"})


async def send_full_state(player: Player) -> None:
    """Отправляет игроку полный снимок состояния."""
    ws = get_player_ws(player)
    if ws is None:
        return

    payload = {
        "t": "state",
        "n": logic.grid_size,
        "spawn": logic.spawn_cell,
        "finish": logic.finish_cell,
        "revealed": list(logic.revealed_snapshot()),
        "player": player.to_public(),
        "items": [
            {"cell": cell, "item": item.item_type.value}
            for cell, item in logic.iter_items()
        ],
        "game_active": logic.state.active,
        "game_phase": logic.state.phase.value,
        "joinable": logic.state.phase is GamePhase.LOBBY,
        "players": [p.to_public() for p in logic.list_players()],
        "turn": logic.turn_snapshot(),
    }
    await send_json(ws, payload)


async def broadcast_player_snapshot(player: Player) -> None:
    """Шлёт всем актуальное состояние одного игрока."""
    await broadcast_json(
        {
            "t": "player",
            "id": player.id,
            "cell": player.cell,
            "lives": player.lives,
            "alive": player.alive,
            "finished": player.finished,
        }
    )


async def broadcast_players_list() -> None:
    """Рассылает полный список игроков всем подключённым клиентам."""
    await broadcast_json(
        {
            "t": "players",
            "players": [p.to_public() for p in logic.list_players()],
        }
    )


async def broadcast_game_status(state: str, *, by: Optional[str] = None) -> None:
    """Сообщает всем о смене статуса игры."""
    payload: Dict[str, object] = {
        "t": "game",
        "state": state,
        "active": logic.state.active,
        "phase": logic.state.phase.value,
        "joinable": logic.state.phase is GamePhase.LOBBY,
    }
    if by is not None:
        payload["by"] = by
    await broadcast_json(payload)


async def broadcast_player_finish(player: Player) -> None:
    await broadcast_json({"t": "finish", "id": player.id, "cell": player.cell})


async def broadcast_turn_info() -> None:
    await broadcast_json({"t": "turn", **logic.turn_snapshot()})


async def finalize_game_if_needed(*, trigger: Optional[Player] = None) -> None:
    if logic.finalize_if_complete():
        await broadcast_game_status("completed", by=trigger.id if trigger else None)
        await broadcast_turn_info()


async def apply_life_change(player: Player, amount: int) -> bool:
    """Применяет изменение жизней и сообщает об этом."""
    died = logic.adjust_player_lives(player, amount)
    await broadcast_player_snapshot(player)
    if died:
        await broadcast_json({"t": "death", "id": player.id, "cell": player.cell})
    return died


async def handle_cell_item(player: Player) -> bool:
    """Применяет эффект предмета на текущей клетке (если есть)."""
    resolved = logic.resolve_cell_item(player)
    if not resolved:
        return False

    item, result = resolved
    payload = {"t": "item", "cell": player.cell, "item": item.item_type.value, "by": player.id}
    await broadcast_json(payload)

    died = False
    if result.affects_lives:
        await broadcast_player_snapshot(player)
        if result.died:
            await broadcast_json({"t": "death", "id": player.id, "cell": player.cell})
            died = True

    if result.inventory_changed:
        ws = get_player_ws(player)
        if ws is not None:
            await send_json(ws, {"t": "inventory", "items": player.inventory_snapshot()})

    return died


def occupied_cells(*, except_ws: Optional[WebSocket] = None) -> Set[int]:
    """Набор занятых клеток всеми игроками; можно исключить одного."""
    exclude_player_id: Optional[str] = None
    if except_ws is not None:
        player = players_by_ws.get(except_ws)
        if player is not None:
            exclude_player_id = player.id
    return logic.occupied_cells(exclude_player_id=exclude_player_id)


async def perform_restart(requester: Optional[Player] = None) -> None:
    """Полностью перезапускает игру: предметы, позиции, жизни."""
    players = logic.restart_game()

    for player in players:
        ws = get_player_ws(player)
        if ws is not None:
            await send_json(ws, {"t": "inventory", "items": player.inventory_snapshot()})

    for player in players:
        await send_full_state(player)

    for player in players:
        await broadcast_player_snapshot(player)

    await broadcast_players_list()

    await broadcast_game_status("ready", by=requester.id if requester else None)
    await broadcast_turn_info()


# ===================== WebSocket =====================


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    if logic.state.phase is not GamePhase.LOBBY:
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
    player = logic.add_player(pid)
    players_by_ws[websocket] = player
    player_connections[player.id] = websocket

    await send_full_state(player)
    await broadcast_player_snapshot(player)
    await broadcast_players_list()

    if logic.state.active and player.alive:
        died = await handle_cell_item(player)
        if died:
            await finalize_game_if_needed(trigger=player)
        elif player.finished:
            await broadcast_players_list()
            await broadcast_player_finish(player)

    try:
        while True:
            raw = await websocket.receive_text()

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            mtype = msg.get("t")

            if mtype == "move":
                if not logic.state.active:
                    await notify_game_inactive(websocket)
                    continue

                if not logic.is_player_turn(player):
                    await send_json(
                        websocket,
                        {"t": "error", "code": "not_your_turn", "reason": "not_your_turn"},
                    )
                    continue

                async def conclude_move(force_end: bool, *, remove_from_turn: bool) -> None:
                    if logic.state.active:
                        logic.consume_step(player, force_end=force_end)
                    if remove_from_turn:
                        logic.handle_player_inactive(player)
                    await broadcast_turn_info()

                dx = int(msg.get("dx", 0))
                dy = int(msg.get("dy", 0))

                target_cell = logic.translate_cell(player.cell, dx, dy)
                move_result = player.attempt_move(
                    dx=dx,
                    dy=dy,
                    target_cell=target_cell,
                    occupied=occupied_cells(except_ws=websocket),
                    shared_cells={logic.spawn_cell},
                )

                if not move_result.success:
                    await send_json(websocket, {"t": "error", "code": move_result.reason, "reason": move_result.reason})
                    continue

                newly: List[int] = []
                if logic.mark_revealed(player.cell):
                    newly.append(player.cell)

                finished_now = False
                if logic.is_finish_cell(player.cell):
                    finished_now = logic.mark_player_finished(player)

                await broadcast_player_snapshot(player)

                if newly:
                    await broadcast_json({"t": "reveal", "cells": newly})

                    if player.alive and logic.should_trigger_hazard():
                        died = await apply_life_change(player, logic.hazard_damage)
                        if died:
                            await conclude_move(force_end=True, remove_from_turn=True)
                            await finalize_game_if_needed(trigger=player)
                            continue

                if player.alive:
                    if finished_now:
                        await broadcast_player_finish(player)
                        await broadcast_players_list()
                        await conclude_move(force_end=True, remove_from_turn=True)
                        await finalize_game_if_needed(trigger=player)
                        continue
                    died_from_item = await handle_cell_item(player)
                    if died_from_item:
                        await conclude_move(force_end=True, remove_from_turn=True)
                        await finalize_game_if_needed(trigger=player)
                        continue
                    if player.finished:
                        await broadcast_players_list()
                        await broadcast_player_finish(player)
                        await conclude_move(force_end=True, remove_from_turn=True)
                        await finalize_game_if_needed(trigger=player)
                        continue

                await conclude_move(force_end=False, remove_from_turn=False)

            elif mtype == "damage":
                if not logic.state.active:
                    await notify_game_inactive(websocket)
                    continue
                amount = int(msg.get("amount", 0))
                died = await apply_life_change(player, amount)
                if died:
                    if logic.state.active and logic.is_player_turn(player):
                        logic.consume_step(player, force_end=True, spend=False)
                    logic.handle_player_inactive(player)
                    await broadcast_turn_info()
                    await finalize_game_if_needed(trigger=player)

            elif mtype == "pickup":
                if not logic.state.active:
                    await notify_game_inactive(websocket)
                    continue
                item = str(msg.get("item", "")).strip()
                if item:
                    player.add_item(item)
                    ws = get_player_ws(player)
                    if ws is not None:
                        await send_json(ws, {"t": "inventory", "items": player.inventory_snapshot()})

            elif mtype == "drop":
                if not logic.state.active:
                    await notify_game_inactive(websocket)
                    continue
                item = str(msg.get("item", "")).strip()
                if player.remove_item(item):
                    ws = get_player_ws(player)
                    if ws is not None:
                        await send_json(ws, {"t": "inventory", "items": player.inventory_snapshot()})

            elif mtype == "start":
                if logic.state.active:
                    await send_json(websocket, {"t": "error", "code": "already_started", "reason": "game_already_active"})
                    continue
                logic.start_game()
                await broadcast_game_status("started", by=player.id)
                for pl in logic.list_players():
                    await broadcast_player_snapshot(pl)
                for pl in logic.list_players():
                    if pl.alive:
                        died_from_item = await handle_cell_item(pl)
                        if died_from_item:
                            await finalize_game_if_needed(trigger=pl)
                        elif pl.finished:
                            await broadcast_players_list()
                            await broadcast_player_finish(pl)
                if logic.state.active:
                    logic.start_turn_cycle()
                await broadcast_turn_info()
                await finalize_game_if_needed(trigger=player)

            elif mtype == "restart":
                await perform_restart(player)

    except WebSocketDisconnect:
        if websocket in active_connections:
            active_connections.remove(websocket)
        stored_player = players_by_ws.pop(websocket, None)
        if stored_player is not None:
            logic.remove_player(stored_player.id)
            player_connections.pop(stored_player.id, None)
            await broadcast_players_list()
            await broadcast_turn_info()
