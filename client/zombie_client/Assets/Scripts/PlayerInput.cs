// PlayerInput.cs (под новый Input System)
using UnityEngine;
using UnityEngine.InputSystem;

public class PlayerInput : MonoBehaviour
{
    [SerializeField] private NetClient net;  // ← ссылка на NetClient

    private void Update()
    {
        if (net == null) return;

        var kb = Keyboard.current;
        if (kb == null) return;

        if (kb.leftArrowKey.wasPressedThisFrame  || kb.aKey.wasPressedThisFrame) net.SendPlayerDelta(-1, 0);
        if (kb.rightArrowKey.wasPressedThisFrame || kb.dKey.wasPressedThisFrame) net.SendPlayerDelta(+1, 0);
        if (kb.upArrowKey.wasPressedThisFrame    || kb.wKey.wasPressedThisFrame) net.SendPlayerDelta( 0,-1);
        if (kb.downArrowKey.wasPressedThisFrame  || kb.sKey.wasPressedThisFrame) net.SendPlayerDelta( 0,+1);
    }
}
