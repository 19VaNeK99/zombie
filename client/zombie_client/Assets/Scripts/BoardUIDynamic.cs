// Assets/Scripts/BoardUIDynamic.cs
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

public class BoardUIDynamic : MonoBehaviour
{
    [Header("Board")]
    [SerializeField] private int gridSize = 5;
    [SerializeField] private Vector2 spacing = new(6,6);
    [SerializeField] private Vector2 padding = new(8,8);
    [SerializeField] private Color cellColor = new(0.85f,0.85f,0.85f,1f);
    [SerializeField] private Color coverColor = new(0f,0f,0f,0.55f); // цвет «крышки»

    [Header("Tokens")]
    [SerializeField] private RectTransform botToken;
    [SerializeField] private RectTransform playerToken;
    [SerializeField] private Vector2 tokenSize = new(80,80);

    private readonly List<RectTransform> _cells = new();      // сами клетки
    private readonly List<Image> _covers = new();              // полупрозрачные крышки над клетками
    private GridLayoutGroup _grid;
    private RectTransform _rt;
    private int _playerCell=1, _botCell=1;

    private void Awake()
    {
        _rt = GetComponent<RectTransform>();
        _grid = GetComponent<GridLayoutGroup>() ?? gameObject.AddComponent<GridLayoutGroup>();
        _grid.constraint = GridLayoutGroup.Constraint.FixedColumnCount;
        _grid.spacing = spacing;
        _grid.padding = new RectOffset((int)padding.x,(int)padding.x,(int)padding.y,(int)padding.y);

        BuildGrid(gridSize);

        _playerCell = Mathf.Clamp((gridSize*gridSize+1)/2,1,gridSize*gridSize);
        _botCell = 1;
        MoveTokenToCell(playerToken, _playerCell);
        MoveTokenToCell(botToken, _botCell);
    }

    // -------- API --------
    public void SetSize(int n)
    {
        n = Mathf.Clamp(n,1,50);
        if (n==gridSize) return;
        gridSize = n;
        BuildGrid(n);
        _playerCell = Mathf.Clamp(_playerCell,1,n*n);
        _botCell = Mathf.Clamp(_botCell,1,n*n);
        MoveTokenToCell(playerToken,_playerCell);
        MoveTokenToCell(botToken,_botCell);
    }

    public void MoveBotToCell(int idx1)    { _botCell    = ClampIndex(idx1);    MoveTokenToCell(botToken,_botCell); }
    public void MovePlayerToCell(int idx1) { _playerCell = ClampIndex(idx1);    MoveTokenToCell(playerToken,_playerCell); }

    public void RevealCell(int idx1)
    {
        int i = ClampIndex(idx1)-1;
        if (i >= 0 && i < _covers.Count && _covers[i] != null)
            _covers[i].enabled = false; // сняли крышку
    }
    public void RevealCells(IList<int> idxs)
    {
        foreach (var idx1 in idxs) RevealCell(idx1);
    }
    public void HideAllCovers()  // если вдруг надо снова закрыть
    {
        foreach (var c in _covers) if (c) c.enabled = true;
    }

    // -------- internals --------
    private void BuildGrid(int n)
    {
        // удалить старые
        foreach (var rt in _cells) if (rt) Destroy(rt.gameObject);
        _cells.Clear();
        _covers.Clear();

        LayoutRebuilder.ForceRebuildLayoutImmediate(_rt);

        var innerW = _rt.rect.width  - _grid.padding.left - _grid.padding.right  - spacing.x*(n-1);
        var innerH = _rt.rect.height - _grid.padding.top  - _grid.padding.bottom - spacing.y*(n-1);
        var cellSize = new Vector2(Mathf.Floor(innerW/n), Mathf.Floor(innerH/n));
        _grid.cellSize = cellSize; _grid.constraintCount = n;

        for (int i=0;i<n*n;i++)
        {
            var cellGO = new GameObject($"Cell{i+1}", typeof(RectTransform), typeof(Image));
            var cellRT = cellGO.GetComponent<RectTransform>();
            var bg = cellGO.GetComponent<Image>();
            bg.color = cellColor;
            cellGO.transform.SetParent(transform, false);
            cellRT.SetSiblingIndex(i);
            _cells.Add(cellRT);

            // крышка (как ребёнок клетки)
            var coverGO = new GameObject($"Cover{i+1}", typeof(RectTransform), typeof(Image));
            var coverRT = coverGO.GetComponent<RectTransform>();
            var coverImg = coverGO.GetComponent<Image>();
            coverGO.transform.SetParent(cellRT, false);
            coverRT.anchorMin = coverRT.anchorMax = new Vector2(0.5f,0.5f);
            coverRT.pivot = new Vector2(0.5f,0.5f);
            coverRT.sizeDelta = cellSize;
            coverRT.anchoredPosition = Vector2.zero;
            coverImg.color = coverColor;
            coverImg.raycastTarget = false; // чтобы клики шли в клетку (если будут)
            _covers.Add(coverImg);
        }

        botToken?.SetAsLastSibling();
        playerToken?.SetAsLastSibling();
    }

    private void MoveTokenToCell(RectTransform token, int idx1)
    {
        if (!token || _cells.Count==0) return;
        int i = Mathf.Clamp(idx1-1, 0, _cells.Count-1);
        var target = _cells[i];
        token.SetParent(target, worldPositionStays:false);
        token.anchorMin = token.anchorMax = new Vector2(0.5f,0.5f);
        token.pivot = new Vector2(0.5f,0.5f);
        token.anchoredPosition = Vector2.zero;
        token.sizeDelta = tokenSize;
        token.SetAsLastSibling();
    }

    private int ClampIndex(int idx1) => Mathf.Clamp(idx1, 1, gridSize*gridSize);
}
