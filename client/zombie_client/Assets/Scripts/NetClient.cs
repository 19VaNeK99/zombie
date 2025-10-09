using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Text;
using UnityEngine;
using TMPro;
using NativeWebSocket;

// ---- модели сообщений ----
[System.Serializable] public class MoveMsg { public string t = "move"; public int dx; public int dy; }
[System.Serializable] public class CommandMsg { public string t; }
[System.Serializable] public class PlayerStateMsg
{
    public string t;
    public string id;
    public int cell;
    public int lives;
    public bool alive;
    public bool finished;
}
[System.Serializable] public class RevealMsg { public string t; public int[] cells; }
[System.Serializable] public class InventoryMsg { public string t; public string[] items; }
[System.Serializable] public class PlayerPublicMsg
{
    public string id;
    public int cell;
    public int lives;
    public bool alive;
    public bool finished;
    public string[] inventory;
}
[System.Serializable] public class StateMsg
{
    public string t;
    public int n;               // размер поля
    public int[] revealed;      // открытые клетки
    public PlayerPublicMsg player;
}

public class NetClient : MonoBehaviour
{
    [SerializeField] private string serverUrl = "ws://127.0.0.1:8000/ws";
    [SerializeField] private TextMeshProUGUI timerText;
    [SerializeField] private TextMeshProUGUI inventoryText;
    [SerializeField] private BoardUIDynamic board;   // динамическая доска

    private WebSocket ws;
    private readonly ConcurrentQueue<string> _inbox = new();

    private readonly (string key, string label)[] _knownInventoryItems =
    {
        ("weapon", "Оружие"),
        ("key", "Ключ"),
        ("fuel", "Топливо"),
    };
    private readonly List<string> _latestInventoryItems = new();
    private int? _playerLives;

    // --- подключение ---
    private async void Start()
    {
        ws = new WebSocket(serverUrl);

        ws.OnOpen  += () => Debug.Log("WS Open");
        ws.OnError += e  => Debug.LogError($"WS Error: {e}");
        ws.OnClose += c  => Debug.Log($"WS Close: {c}");
        ws.OnMessage += bytes =>
        {
            var msg = Encoding.UTF8.GetString(bytes);
            _inbox.Enqueue(msg);
            Debug.Log($"WS Message enqueued: {msg}");
        };

        await ws.Connect();
        InvokeRepeating(nameof(SendPing), 5f, 10f);
    }

    private async void SendPing()
    {
        if (ws != null && ws.State == WebSocketState.Open)
            await ws.SendText("ping");
    }

    // --- отправка хода игрока ---
    public async void SendPlayerDelta(int dx, int dy)
    {
        if (ws == null || ws.State != WebSocketState.Open) return;
        var json = JsonUtility.ToJson(new MoveMsg { dx = dx, dy = dy });
        await ws.SendText(json);
        Debug.Log($"Sent move: {json}");
    }

    public void SendStartCommand() => SendCommand("start");

    public void SendRestartCommand() => SendCommand("restart");

    private async void SendCommand(string commandType)
    {
        if (string.IsNullOrEmpty(commandType)) return;
        if (ws == null || ws.State != WebSocketState.Open) return;

        var json = JsonUtility.ToJson(new CommandMsg { t = commandType });
        await ws.SendText(json);
        Debug.Log($"Sent command: {json}");
    }

    // --- обработка входящих ---
    private void Update()
    {
        ws?.DispatchMessageQueue();

        while (_inbox.TryDequeue(out var msg))
        {
            if (timerText) timerText.text = msg;

            // JSON?
            if (!string.IsNullOrEmpty(msg) && msg[0] == '{')
            {
                // полное состояние
                var st = JsonUtility.FromJson<StateMsg>(msg);
                if (st != null && st.t == "state")
                {
                    if (st.n > 0) board.SetSize(st.n);
                    if (st.revealed != null && st.revealed.Length > 0)
                        board.RevealCells(st.revealed);
                    if (st.player != null)
                    {
                        board.MovePlayerToCell(st.player.cell);
                        _playerLives = st.player.lives;
                        UpdateInventoryDisplay(st.player.inventory);
                    }
                    continue;
                }

                // позиция игрока
                var p = JsonUtility.FromJson<PlayerStateMsg>(msg);
                if (p != null && p.t == "player")
                {
                    board.MovePlayerToCell(p.cell);
                    _playerLives = p.lives;
                    UpdateInventoryDisplay();
                    continue;
                }

                // раскрытие клеток
                var rv = JsonUtility.FromJson<RevealMsg>(msg);
                if (rv != null && rv.t == "reveal")
                {
                    board.RevealCells(rv.cells);
                    continue;
                }

                // инвентарь игрока
                var inv = JsonUtility.FromJson<InventoryMsg>(msg);
                if (inv != null && inv.t == "inventory")
                {
                    UpdateInventoryDisplay(inv.items);
                    continue;
                }
            }

            // иначе — число бота
            if (int.TryParse(msg, out var cell))
                board.MoveBotToCell(cell);
        }
    }

    private void UpdateInventoryDisplay(IList<string> items = null)
    {
        if (inventoryText == null) return;

        if (items != null)
        {
            _latestInventoryItems.Clear();
            foreach (var item in items)
            {
                if (string.IsNullOrEmpty(item)) continue;
                _latestInventoryItems.Add(item);
            }
        }

        var counts = new Dictionary<string, int>();
        foreach (var item in _latestInventoryItems)
        {
            if (!counts.ContainsKey(item)) counts[item] = 0;
            counts[item]++;
        }

        var sb = new StringBuilder();
        sb.AppendLine("Инвентарь:");

        if (_playerLives.HasValue)
        {
            sb.Append("• Жизни: ")
              .Append(_playerLives.Value)
              .AppendLine();
        }

        foreach (var (key, label) in _knownInventoryItems)
        {
            counts.TryGetValue(key, out var value);
            counts.Remove(key);
            sb.Append("• ")
              .Append(label)
              .Append(": ")
              .Append(value)
              .AppendLine();
        }

        foreach (var pair in counts)
        {
            sb.Append("• ")
              .Append(pair.Key)
              .Append(": ")
              .Append(pair.Value)
              .AppendLine();
        }

        inventoryText.text = sb.ToString().TrimEnd('\n');
    }

    private async void OnApplicationQuit()
    {
        if (ws != null && ws.State == WebSocketState.Open)
            await ws.Close();
    }
}
