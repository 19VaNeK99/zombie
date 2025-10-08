import asyncio
import json
import random
import uuid
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Set, Tuple

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from contextlib import asynccontextmanager

# ===================== Настройки =====================
MAX_CLIENTS = 5
GRID_SIZE = 5
BROADCAST_INTERVAL = 1

# --- Генерация предметов на карте ---
ITEM_COUNTS = {
    "zombie": 3,
    "medkit": 2,
    "weapon": 2,
}
ZOMBIE_DAMAGE = 1
MEDKIT_HEAL = 1

# --- Новые параметры автосмерти/опасности ---
HAZARD_ON_ENTER = True    # проверка опасности на входе в новую клетку
HAZARD_PROB     = 0.25    # шанс срабатывания (25%)
HAZARD_DAMAGE   = 1       # урон при срабатывании
# random.seed(42)         # при желании — зафиксировать сид для воспроизводимости

# ===================== Утилиты сетки =====================

def to_rc(cell: int) -> Tuple[int, int]:
    """1..N^2 -> (r,c) 0-индексация, с защитой границ."""
    n = GRID_SIZE
    i = max(1, min(n * n, cell)) - 1
    return i // n, i % n

def from_rc(r: int, c: int) -> int:
    """(r,c) -> 1..N^2 с защитой границ."""
    n = GRID_SIZE
    r = max(0, min(n - 1, r))
    c = max(0, min(n - 1, c))
    return r * n + c + 1

def clamp_cell(cell: int) -> int:
    return max(1, min(GRID_SIZE * GRID_SIZE, cell))

def center_cell() -> int:
    """Центр сетки: для нечётных размеров это настоящий центр, для чётных — одну из центральных."""
    mid = GRID_SIZE // 2
    return from_rc(mid, mid)

# ===================== Модель игрока =====================

@dataclass
class Player:
    id: str
    ws: WebSocket
    cell: int
    lives: int = 3
    inventory: List[str] = field(default_factory=list)

    @property
    def alive(self) -> bool:
        return self.lives >= 1

    def to_public(self) -> Dict:
        """Что рассылаем клиентам: без ws и лишнего."""
        return {
            "id": self.id,
            "cell": self.cell,
            "lives": self.lives,
            "alive": self.alive,
            "inventory": list(self.inventory),
        }

    def try_move(self, dx: int, dy: int, occupied_without_self: Set[int]) -> Tuple[bool, Optional[str]]:
        """
        Пытается сдвинуть игрока на dx,dy.
        Возвращает (ok, reason). reason = 'dead' | 'occupied' | None.
        """
        if not self.alive:
            return False, "dead"

        r, c = to_rc(self.cell)
        r += dy
        c += dx
        target = from_rc(r, c)

        if target in occupied_without_self:
            return False, "occupied"

        self.cell = target
        return True, None

# ===================== Глобальное состояние комнаты =====================

active_connections: List[WebSocket] = []
players_by_ws: Dict[WebSocket, Player] = {}
players_by_id: Dict[str, Player] = {}
revealed: Set[int] = set()  # общие открытые клетки
items_on_map: Dict[int, str] = {}
game_active: bool = False


def generate_items() -> Dict[int, str]:
    """Случайно распределяет предметы по клеткам."""
    total_cells = GRID_SIZE * GRID_SIZE
    available_cells = [cell for cell in range(1, total_cells + 1) if cell != center_cell()]
    placements: Dict[int, str] = {}

    for item, count in ITEM_COUNTS.items():
        if count <= 0 or not available_cells:
            continue

        count = min(count, len(available_cells))
        chosen = random.sample(available_cells, count)
        for cell in chosen:
            placements[cell] = item
            available_cells.remove(cell)

    return placements


def reset_items() -> None:
    """Пересоздаёт предметы на карте (вызывается при старте)."""
    global items_on_map
    items_on_map = generate_items()


reset_items()

# ===================== Бот-петля (опционально) =====================

async def broadcast_bot_loop():
    """Пример «бота», который шлёт индекс клетки 1..N^2 по кругу строкой."""
    idx = 1
    while True:
        await asyncio.sleep(BROADCAST_INTERVAL)
        if not game_active:
            continue
        msg = str(idx)
        idx = idx + 1 if idx < GRID_SIZE * GRID_SIZE else 1
        # Шлём всем — клиент может воспринимать это как движение бота
        for ws in list(active_connections):
            try:
                await ws.send_text(msg)
            except Exception:
                try:
                    active_connections.remove(ws)
                except ValueError:
                    pass

# ===================== Жизненный цикл приложения =====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Запускаем «бота», если он нужен
    asyncio.create_task(broadcast_bot_loop())
    yield
    # graceful shutdown при необходимости

app = FastAPI(lifespan=lifespan)

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


async def notify_game_inactive(ws: WebSocket) -> None:
    await send_json(ws, {"t": "error", "code": "not_active", "reason": "game_not_active"})


async def send_full_state(player: Player) -> None:
    """Отправляет игроку полный снимок состояния."""
    payload = {
        "t": "state",
        "n": GRID_SIZE,
        "revealed": sorted(revealed),
        "player": player.to_public(),
        "items": [
            {"cell": cell, "item": item}
            for cell, item in sorted(items_on_map.items())
        ],
        "game_active": game_active,
        "players": [p.to_public() for p in players_by_id.values()],
    }
    await send_json(player.ws, payload)


async def broadcast_player_snapshot(player: Player) -> None:
    """Шлёт всем актуальное состояние одного игрока."""
    await broadcast_json({
        "t": "player",
        "id": player.id,
        "cell": player.cell,
        "lives": player.lives,
        "alive": player.alive,
    })


async def broadcast_game_status(state: str, *, by: Optional[str] = None) -> None:
    """Сообщает всем о смене статуса игры."""
    payload: Dict[str, object] = {"t": "game", "state": state, "active": game_active}
    if by is not None:
        payload["by"] = by
    await broadcast_json(payload)


async def restart_game(requester: Optional[Player] = None) -> None:
    """Полностью перезапускает игру: предметы, позиции, жизни."""
    global revealed, game_active

    revealed.clear()
    reset_items()

    occupied: Set[int] = set()
    for pl in sorted(players_by_id.values(), key=lambda x: x.id):
        cell = first_free_start_cell(occupied_override=occupied)
        pl.cell = cell
        pl.lives = 3
        pl.inventory.clear()
        occupied.add(cell)
        revealed.add(cell)

    game_active = False

    # Разослать актуальное состояние всем игрокам
    for pl in list(players_by_id.values()):
        await send_json(pl.ws, {"t": "inventory", "items": pl.inventory})

    for pl in list(players_by_id.values()):
        await send_full_state(pl)

    for pl in list(players_by_id.values()):
        await broadcast_player_snapshot(pl)

    await broadcast_game_status("ready", by=requester.id if requester else None)

# ===================== Вспомогалки =====================

async def apply_damage(player: "Player", amount: int) -> bool:
    """
    Применяет урон (>0) или хил (<0). Возвращает died=True, если игрок умер в этот момент.
    Тут же рассылаем обновлённое состояние игрока.
    """
    if amount == 0:
        return False

    if amount > 0:
        player.lives = max(0, player.lives - amount)
    else:
        # Примерный максимум хп, можешь вынести в константу
        player.lives = min(player.lives - amount, 9)

    # Сообщаем всем новое состояние игрока
    await broadcast_player_snapshot(player)

    if not player.alive:
        # Умер прямо сейчас — рассылаем отдельное событие (для эффектов)
        await broadcast_json({"t": "death", "id": player.id, "cell": player.cell})
        return True

    return False


async def resolve_cell_item(player: "Player") -> None:
    """Применяет эффект предмета на текущей клетке (если есть)."""
    cell = player.cell
    item = items_on_map.pop(cell, None)
    if not item:
        return

    payload = {"t": "item", "cell": cell, "item": item, "by": player.id}

    if item == "zombie":
        await broadcast_json(payload)
        await apply_damage(player, ZOMBIE_DAMAGE)
    elif item == "medkit":
        await broadcast_json(payload)
        await apply_damage(player, -MEDKIT_HEAL)
    elif item == "weapon":
        player.inventory.append("weapon")
        await broadcast_json(payload)
        await send_json(player.ws, {"t": "inventory", "items": player.inventory})

def occupied_cells(except_ws: Optional[WebSocket] = None) -> Set[int]:
    """Набор занятых клеток всеми игроками; можно исключить одного."""
    occ = set()
    for ws, p in players_by_ws.items():
        if except_ws is not None and ws is except_ws:
            continue
        occ.add(p.cell)
    return occ

def first_free_start_cell(occupied_override: Optional[Set[int]] = None) -> int:
    """Ищем свободную стартовую клетку (центр, затем по спирали)."""
    occ = set(occupied_override) if occupied_override is not None else occupied_cells()

    # Начинаем с центра; если занят — ищем ближайшую свободную.
    start = center_cell()
    if start not in occ:
        return start

    # Простейший поиск по слоям вокруг центра
    r0, c0 = to_rc(start)
    for radius in range(1, GRID_SIZE):
        for dr in range(-radius, radius + 1):
            for dc in range(-radius, radius + 1):
                r, c = r0 + dr, c0 + dc
                if r < 0 or r >= GRID_SIZE or c < 0 or c >= GRID_SIZE:
                    continue
                cand = from_rc(r, c)
                if cand not in occ:
                    return cand

    # На крайний случай
    for i in range(1, GRID_SIZE * GRID_SIZE + 1):
        if i not in occ:
            return i

    # Если всё занято (не должно случиться при MAX_CLIENTS << N^2)
    return center_cell()

# ===================== WebSocket =====================

@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    global game_active
    await websocket.accept()
    if len(active_connections) >= MAX_CLIENTS:
        await websocket.send_text("Комната переполнена, соединение отклонено.")
        await websocket.close()
        return

    # Регистрируем игрока
    active_connections.append(websocket)
    pid = uuid.uuid4().hex[:8]
    start_cell = first_free_start_cell()
    player = Player(id=pid, ws=websocket, cell=start_cell, lives=3, inventory=[])
    players_by_ws[websocket] = player
    players_by_id[player.id] = player

    # Открываем стартовую клетку
    if start_cell not in revealed:
        revealed.add(start_cell)

    # Отправляем подключившемуся полное состояние
    await send_full_state(player)

    # Сообщаем всем о новом игроке
    await broadcast_player_snapshot(player)

    if game_active and player.alive:
        await resolve_cell_item(player)

    try:
        while True:
            raw = await websocket.receive_text()

            # Пинги/строки игнорируем — ожидаем JSON
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            mtype = msg.get("t")

            # --------- Ход игрока ---------
            if mtype == "move":
                if not game_active:
                    await notify_game_inactive(websocket)
                    continue
                dx = int(msg.get("dx", 0))
                dy = int(msg.get("dy", 0))

                occ = occupied_cells(except_ws=websocket)
                ok, reason = player.try_move(dx, dy, occ)

                if not ok:
                    await send_json(websocket, {"t": "error", "code": reason, "reason": reason})
                    continue

                newly = []
                if player.cell not in revealed:
                    revealed.add(player.cell)
                    newly.append(player.cell)

                # Сначала всем сообщим новую позицию (даже если сейчас умрёт — будет видно, куда шагнул)
                await broadcast_player_snapshot(player)

                # Открытие клетки — всем
                if newly:
                    await broadcast_json({"t": "reveal", "cells": newly})

                    # --- Новое: автосмерть/опасность на новой клетке ---
                    if HAZARD_ON_ENTER and random.random() < HAZARD_PROB and player.alive:
                        died = await apply_damage(player, HAZARD_DAMAGE)
                        # Если умер — дальше ничего делать не нужно (ход уже завершён)
                        # Если выжил — тоже всё ок, состояние уже разослано.

                if player.alive:
                    await resolve_cell_item(player)


            # --------- (Опционально) урон/хил ---------
            elif mtype == "damage":
                if not game_active:
                    await notify_game_inactive(websocket)
                    continue
                amount = int(msg.get("amount", 0))
                await apply_damage(player, amount)


            # --------- (Опционально) инвентарь ---------
            elif mtype == "pickup":
                if not game_active:
                    await notify_game_inactive(websocket)
                    continue
                # пример: {"t":"pickup","item":"key"}
                item = str(msg.get("item", "")).strip()
                if item:
                    player.inventory.append(item)
                    await send_json(websocket, {"t": "inventory", "items": player.inventory})

            elif mtype == "drop":
                if not game_active:
                    await notify_game_inactive(websocket)
                    continue
                item = str(msg.get("item", "")).strip()
                if item in player.inventory:
                    player.inventory.remove(item)
                    await send_json(websocket, {"t": "inventory", "items": player.inventory})

            elif mtype == "start":
                if game_active:
                    await send_json(websocket, {"t": "error", "code": "already_started", "reason": "game_already_active"})
                    continue
                game_active = True
                await broadcast_game_status("started", by=player.id)
                for pl in list(players_by_id.values()):
                    await broadcast_player_snapshot(pl)
                for pl in list(players_by_id.values()):
                    if pl.alive:
                        await resolve_cell_item(pl)

            elif mtype == "restart":
                await restart_game(player)

            # можно расширять другими типами сообщений…

    except WebSocketDisconnect:
        # Удаляем игрока
        active_connections.remove(websocket)
        players_by_id.pop(players_by_ws[websocket].id, None)
        players_by_ws.pop(websocket, None)
