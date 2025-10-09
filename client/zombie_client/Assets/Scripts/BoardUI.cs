using System.Collections.Generic;
using UnityEngine;

public class BoardUI : MonoBehaviour
{
    [Header("Tokens")]
    [SerializeField] private RectTransform playerToken;  // фишка игрока (локально)

    private readonly List<RectTransform> _cells = new(); // Cell1..Cell9 (по порядку)
    private int _playerCell = 5;   // текущее положение игрока (1..9)

    private void Awake()
    {
        _cells.Clear();
        for (int i = 0; i < transform.childCount; i++)
        {
            var child = transform.GetChild(i) as RectTransform;
            if (child == null) continue;

            // собираем только клетки (исключаем токены, если они уже лежат внутри Board)
            if (child == playerToken) continue;
            _cells.Add(child);
        }

        if (_cells.Count != 9)
            Debug.LogWarning($"BoardUI: найдено {_cells.Count} клеток, ожидается 9.");

        // стартовые позиции по центру (клетка 5)
        MoveTokenToCell(playerToken, _playerCell);
    }

    // ========== Публичные методы ==========
    /// <summary>Переместить игрока в конкретную клетку 1..9 (если захочешь клики).</summary>
    public void MovePlayerToCell(int cellNumber)
    {
        _playerCell = ClampCell(cellNumber);
        MoveTokenToCell(playerToken, _playerCell);
    }

    /// <summary>Сдвинуть игрока на dx,dy по сетке (dx: -1..1 колонка, dy: -1..1 строка).</summary>
    public void MovePlayerByDelta(int dx, int dy)
    {
        var (r, c) = ToRC(_playerCell);
        r += dy; c += dx;
        r = Mathf.Clamp(r, 0, 2);
        c = Mathf.Clamp(c, 0, 2);
        _playerCell = FromRC(r, c);
        MoveTokenToCell(playerToken, _playerCell);
    }

    // ========== Вспомогательные ==========

    private void MoveTokenToCell(RectTransform token, int cellNumber)
    {
        if (token == null) return;
        int idx = cellNumber - 1;
        if (idx < 0 || idx >= _cells.Count) return;

        var target = _cells[idx];
        token.SetParent(target, worldPositionStays: false);
        token.anchoredPosition = Vector2.zero; // по центру клетки
    }

    private static (int r, int c) ToRC(int cell)   // 1..9 -> (row, col)
    {
        int i = Mathf.Clamp(cell, 1, 9) - 1;
        return (i / 3, i % 3);
    }

    private static int FromRC(int r, int c)        // (row, col) -> 1..9
    {
        r = Mathf.Clamp(r, 0, 2);
        c = Mathf.Clamp(c, 0, 2);
        return r * 3 + c + 1;
    }

    private static int ClampCell(int cell) => Mathf.Clamp(cell, 1, 9);
}
