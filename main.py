# main.py:
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import asyncio

# Описание проекта:
# Минимальный сервер WebSocket на FastAPI для одной игровой комнаты без авторизации и сохранения.
# - Максимум 5 одновременных клиентов.
# - Сервер ведет общий счетчик (таймер), увеличивающийся каждые N секунд.
# - Текущее значение таймера рассылается всем подключенным клиентам.
# - При подключении нового клиента он сразу получает актуальное значение таймера.
# - Используется асинхронный подход (async/await) и Uvicorn для запуска ASGI-сервера.

app = FastAPI()

# Глобальные переменные для состояния игры:
timer_value = 0            # текущее значение таймера (счетчика)
MAX_CLIENTS = 5            # максимальное число одновременно подключенных клиентов
BROADCAST_INTERVAL = 1     # интервал (в секундах) для обновления таймера и рассылки

# Список активных подключений WebSocket:
active_connections: list[WebSocket] = []

# Фоновая асинхронная задача, увеличивающая таймер и рассылающая его значение всем клиентам
async def broadcast_timer():
    cells = [str(i) for i in range(1, 10)]
    idx = 0
    while True:
        await asyncio.sleep(1)
        msg = cells[idx]
        idx = (idx + 1) % 9
        for ws in list(active_connections):
            await ws.send_text(msg)

# Запускаем фоновую задачу при старте приложения
@app.on_event("startup")
async def on_startup():
    # Создаем задачу для таймера (работает параллельно, пока приложение запущено)
    asyncio.create_task(broadcast_timer())

# Обработчик WebSocket-соединений для общей игровой комнаты
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # Ограничение на число подключений
    if len(active_connections) >= MAX_CLIENTS:
        # Отклоняем подключение, если уже достигнуто 5 клиентов
        await websocket.accept()
        await websocket.send_text("Комната переполнена, соединение отклонено.")
        await websocket.close()
        return

    # Принимаем новое WebSocket-соединение
    await websocket.accept()
    # Добавляем нового клиента в список активных подключений
    active_connections.append(websocket)

    # Отправляем новому клиенту текущее значение таймера сразу после подключения
    await websocket.send_text(str(timer_value))

    try:
        # Держим соединение открытым, ожидая сообщений от клиента
        # (Если клиент ничего не отправляет, этот вызов будет блокировать до отключения)
        while True:
            _ = await websocket.receive_text()
            # Сервер не обрабатывает входящие сообщения (игра односторонняя: только рассылка таймера),
            # поэтому просто игнорируем любые полученные данные.
    except WebSocketDisconnect:
        # Если клиент отключился, удаляем соединение из списка активных
        active_connections.remove(websocket)
        # (Не рассылаем сообщение об отключении, т.к. этого не требуется по заданию)

# Пример запуска сервера локально:
# uvicorn main:app --reload
# После запуска, клиенты могут подключаться по адресу ws://localhost:8000/ws для получения обновлений таймера.
