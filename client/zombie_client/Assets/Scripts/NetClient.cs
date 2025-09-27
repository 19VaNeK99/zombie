using System.Collections.Concurrent;
using System.Text;
using UnityEngine;
using TMPro;
using NativeWebSocket;

public class NetClient : MonoBehaviour
{
    [SerializeField] private string serverUrl = "ws://127.0.0.1:8000/ws";
    [SerializeField] private TextMeshProUGUI timerText;
    [SerializeField] private BoardUI board;     // ← добавили ссылку на доску

    private WebSocket ws;
    private readonly ConcurrentQueue<string> _inbox = new();

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

    private void Update()
    {
        ws?.DispatchMessageQueue();

        while (_inbox.TryDequeue(out var msg))
        {
            // Отобразим текстом как раньше (не обязательно)
            if (timerText != null) timerText.text = $"MSG: {msg}";

            // Попробуем трактовать сообщение как номер клетки 1..9
            if (int.TryParse(msg, out var cell))
            {
                board?.MoveTokenToCell(cell);
            }
        }
    }

    private async void OnApplicationQuit()
    {
        if (ws != null && ws.State == WebSocketState.Open)
            await ws.Close();
    }
}
