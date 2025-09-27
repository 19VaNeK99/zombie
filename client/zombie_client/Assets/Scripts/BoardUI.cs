using System.Collections.Generic;
using UnityEngine;

public class BoardUI : MonoBehaviour
{
    [Tooltip("Фишка, которую будем перемещать между ячейками")]
    [SerializeField] private RectTransform token;

    // Ячейки будут автоматически собраны из детей Board (Cell1..Cell9) в порядке иерархии
    private readonly List<RectTransform> _cells = new();

    private void Awake()
    {
        // Собираем всех непосредственных детей Board, кроме Token
        _cells.Clear();
        for (int i = 0; i < transform.childCount; i++)
        {
            var child = transform.GetChild(i) as RectTransform;
            if (child == null) continue;
            if (child == token) continue;     // пропускаем Token
            _cells.Add(child);
        }

        // На всякий случай убедимся, что 9 клеток
        if (_cells.Count != 9)
            Debug.LogWarning($"BoardUI: найдено {_cells.Count} клеток, ожидается 9.");
    }

    /// <summary>
    /// Перемещает фишку в клетку по номеру 1..9.
    /// 1 — верхний левый угол, 3 — верхний правый, 9 — нижний правый (row-major).
    /// </summary>
    public void MoveTokenToCell(int cellNumber)
    {
        if (token == null) { Debug.LogWarning("BoardUI: Token не назначен"); return; }
        if (cellNumber < 1 || cellNumber > _cells.Count) { Debug.LogWarning($"Неверный номер клетки: {cellNumber}"); return; }

        var targetCell = _cells[cellNumber - 1];

        // Делает Token дочерним объектом целевой ячейки и ставит по центру
        token.SetParent(targetCell, worldPositionStays: false);
        token.anchoredPosition = Vector2.zero;
    }
}
