// PlayerInput.cs (под новый Input System)
using UnityEngine;
using UnityEngine.InputSystem;

public class PlayerInput : MonoBehaviour
{
    [SerializeField] private NetClient net;  // ← ссылка на NetClient

    [SerializeField] private Rect startButtonRect = new Rect(16f, 16f, 160f, 36f);
    [SerializeField] private Rect restartButtonRect = new Rect(16f, 60f, 160f, 36f);

    private void Update()
    {
        if (net == null) return;

        var kb = Keyboard.current;
        if (kb == null) return;

        if (kb.leftArrowKey.wasPressedThisFrame  || kb.aKey.wasPressedThisFrame) net.SendPlayerDelta(-1, 0);
        if (kb.rightArrowKey.wasPressedThisFrame || kb.dKey.wasPressedThisFrame) net.SendPlayerDelta(+1, 0);
        if (kb.upArrowKey.wasPressedThisFrame    || kb.wKey.wasPressedThisFrame) net.SendPlayerDelta( 0,-1);
        if (kb.downArrowKey.wasPressedThisFrame  || kb.sKey.wasPressedThisFrame) net.SendPlayerDelta( 0,+1);

        if (kb.gKey.wasPressedThisFrame) net.SendStartCommand();
        if (kb.pKey.wasPressedThisFrame) net.SendRestartCommand();
    }

    private void OnGUI()
    {
        if (net == null) return;

        if (GUI.Button(startButtonRect, "Start (G)"))
            net.SendStartCommand();

        if (GUI.Button(restartButtonRect, "Restart (P)"))
            net.SendRestartCommand();
    }
}
