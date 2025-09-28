using System.Collections.Concurrent;
using System.Text;
using UnityEngine;
using TMPro;
using NativeWebSocket;

// ---- модели сообщений ----
[System.Serializable] public class MoveMsg { public string t = "move"; public int dx; public int dy; }
[System.Serializable] public class PlayerStateMsg { public string t; public int cell; }
[System.Serializable] public class RevealMsg { public string t; public int[] cells; }
[System.Serializable] public class StateMsg
{
    public string t;
    public int n;               // размер поля
    public int[] revealed;      // открытые клетки
    public PlayerStateMsg player;
}

public class NetClient : MonoBehaviour
{
    [SerializeField] private string serverUrl = "ws://127.0.0.1:8000/ws";
    [SerializeField] private TextMeshProUGUI timerText;
    [SerializeField] private BoardUIDynamic board;   // динамическая доска

    private WebSocket ws;
    private readonly ConcurrentQueue<string> _inbox = new();

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
                        board.MovePlayerToCell(st.player.cell);
                    continue;
                }

                // позиция игрока
                var p = JsonUtility.FromJson<PlayerStateMsg>(msg);
                if (p != null && p.t == "player")
                {
                    board.MovePlayerToCell(p.cell);
                    continue;
                }

                // раскрытие клеток
                var rv = JsonUtility.FromJson<RevealMsg>(msg);
                if (rv != null && rv.t == "reveal")
                {
                    board.RevealCells(rv.cells);
                    continue;
                }
            }

            // иначе — число бота
            if (int.TryParse(msg, out var cell))
                board.MoveBotToCell(cell);
        }
    }

    private async void OnApplicationQuit()
    {
        if (ws != null && ws.State == WebSocketState.Open)
            await ws.Close();
    }
}
