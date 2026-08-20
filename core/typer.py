"""Inject text into the active window via Win32 clipboard + keybd_event."""

import ctypes
import ctypes.wintypes as w

# ── Win32 constants ──────────────────────────────────────────────────────────

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
KEYEVENTF_KEYUP = 0x0002
VK_CONTROL = 0x11
VK_V = 0x56
VK_RETURN = 0x0D

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# ── Explicit Win32 Signatures (Prevents 64-bit pointer truncation) ────────────

user32.OpenClipboard.argtypes = [w.HWND]
user32.OpenClipboard.restype = w.BOOL
user32.CloseClipboard.argtypes = []
user32.CloseClipboard.restype = w.BOOL
user32.EmptyClipboard.argtypes = []
user32.EmptyClipboard.restype = w.BOOL
user32.GetClipboardData.argtypes = [w.UINT]
user32.GetClipboardData.restype = w.HANDLE
user32.SetClipboardData.argtypes = [w.UINT, w.HANDLE]
user32.SetClipboardData.restype = w.HANDLE
user32.keybd_event.argtypes = [w.BYTE, w.BYTE, w.DWORD, ctypes.c_size_t]
user32.keybd_event.restype = None

kernel32.GlobalAlloc.argtypes = [w.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = w.HGLOBAL
kernel32.GlobalLock.argtypes = [w.HGLOBAL]
kernel32.GlobalLock.restype = w.LPVOID
kernel32.GlobalUnlock.argtypes = [w.HGLOBAL]
kernel32.GlobalUnlock.restype = w.BOOL


# ── Clipboard ────────────────────────────────────────────────────────────────

def _get_clipboard() -> str | None:
    """Read current clipboard text (to restore later)."""
    if not user32.OpenClipboard(0):
        return None
    try:
        h = user32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return None
        ptr = kernel32.GlobalLock(h)
        if not ptr:
            return None
        try:
            return ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(h)
    finally:
        user32.CloseClipboard()


def _set_clipboard(text: str) -> bool:
    """Copy *text* to the Windows clipboard using Win32 API."""
    for _ in range(5):
        if user32.OpenClipboard(0):
            break
        import time; time.sleep(0.02)
    else:
        return False
    try:
        user32.EmptyClipboard()
        data = text.encode("utf-16-le") + b"\x00\x00"
        h = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not h:
            return False
        ptr = kernel32.GlobalLock(h)
        ctypes.memmove(ptr, data, len(data))
        kernel32.GlobalUnlock(h)
        user32.SetClipboardData(CF_UNICODETEXT, h)
        return True
    finally:
        user32.CloseClipboard()


# ── Public API ───────────────────────────────────────────────────────────────

def type_text(text: str) -> None:
    """Paste *text* into the currently focused window.

    Saves and restores the previous clipboard content.
    """
    if not text:
        return

    # Save current clipboard
    prev = _get_clipboard()

    # Put our text on the clipboard
    if not _set_clipboard(text):
        return

    # Simulate Ctrl+V
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    user32.keybd_event(VK_V, 0, 0, 0)
    user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)

    # Restore previous clipboard after a short delay
    if prev is not None:
        import threading
        def _restore():
            import time; time.sleep(0.3)
            _set_clipboard(prev)
        threading.Thread(target=_restore, daemon=True).start()


def send_enter() -> None:
    """Simulate pressing Enter."""
    user32.keybd_event(VK_RETURN, 0, 0, 0)
    user32.keybd_event(VK_RETURN, 0, KEYEVENTF_KEYUP, 0)
