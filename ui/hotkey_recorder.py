"""Interactive hotkey recorder widget — captures keyboard combos and mouse buttons."""

import threading
from PyQt6.QtWidgets import QPushButton
from PyQt6.QtCore import Qt, pyqtSignal

from pynput import keyboard, mouse


# Map pynput Key objects to human-readable + pynput-format strings
_KEY_NAMES = {
    keyboard.Key.ctrl_l: ("Ctrl", "<ctrl>"),
    keyboard.Key.ctrl_r: ("Ctrl", "<ctrl>"),
    keyboard.Key.shift_l: ("Shift", "<shift>"),
    keyboard.Key.shift_r: ("Shift", "<shift>"),
    keyboard.Key.alt_l: ("Alt", "<alt>"),
    keyboard.Key.alt_r: ("Alt", "<alt>"),
    keyboard.Key.cmd: ("Win", "<cmd>"),
    keyboard.Key.space: ("Space", "<space>"),
    keyboard.Key.enter: ("Enter", "<enter>"),
    keyboard.Key.tab: ("Tab", "<tab>"),
    keyboard.Key.esc: ("Esc", None),  # Esc = cancel recording
    keyboard.Key.f1: ("F1", "<f1>"),
    keyboard.Key.f2: ("F2", "<f2>"),
    keyboard.Key.f3: ("F3", "<f3>"),
    keyboard.Key.f4: ("F4", "<f4>"),
    keyboard.Key.f5: ("F5", "<f5>"),
    keyboard.Key.f6: ("F6", "<f6>"),
    keyboard.Key.f7: ("F7", "<f7>"),
    keyboard.Key.f8: ("F8", "<f8>"),
    keyboard.Key.f9: ("F9", "<f9>"),
    keyboard.Key.f10: ("F10", "<f10>"),
    keyboard.Key.f11: ("F11", "<f11>"),
    keyboard.Key.f12: ("F12", "<f12>"),
    keyboard.Key.caps_lock: ("CapsLock", "<caps_lock>"),
    keyboard.Key.insert: ("Insert", "<insert>"),
    keyboard.Key.home: ("Home", "<home>"),
    keyboard.Key.end: ("End", "<end>"),
    keyboard.Key.page_up: ("PgUp", "<page_up>"),
    keyboard.Key.page_down: ("PgDn", "<page_down>"),
    keyboard.Key.delete: ("Del", "<delete>"),
    keyboard.Key.backspace: ("Backspace", "<backspace>"),
    keyboard.Key.up: ("↑", "<up>"),
    keyboard.Key.down: ("↓", "<down>"),
    keyboard.Key.left: ("←", "<left>"),
    keyboard.Key.right: ("→", "<right>"),
    keyboard.Key.pause: ("Pause", "<pause>"),
    keyboard.Key.scroll_lock: ("ScrollLock", "<scroll_lock>"),
    keyboard.Key.print_screen: ("PrintScrn", "<print_screen>"),
    keyboard.Key.num_lock: ("NumLock", "<num_lock>"),
    keyboard.Key.menu: ("Menu", "<menu>"),
}

# Modifier keys — tracked separately, combined into combo
_MODIFIERS = {
    keyboard.Key.ctrl_l, keyboard.Key.ctrl_r,
    keyboard.Key.shift_l, keyboard.Key.shift_r,
    keyboard.Key.alt_l, keyboard.Key.alt_r,
    keyboard.Key.cmd,
}


class HotkeyRecorderButton(QPushButton):
    """A button that listens for a hotkey combo or mouse button when clicked.

    Emits `hotkey_recorded(display_text, pynput_string)` when done.
    """

    hotkey_recorded = pyqtSignal(str, str, int)  # (display, pynput_format, vk_code)

    def __init__(self, parent=None) -> None:
        super().__init__("Нажмите для записи", parent)
        self.setObjectName("hotkeyBtn")
        self._recording = False
        self._kb_listener: keyboard.Listener | None = None
        self._mouse_listener: mouse.Listener | None = None
        self._modifiers: set = set()
        self._current_display = ""
        self._current_pynput = ""
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._toggle_recording)

    # ── display ──────────────────────────────────────────────────────────

    def set_hotkey_text(self, display: str) -> None:
        """Show current hotkey on the button face."""
        self._current_display = display
        self.setText(f"🎯  {display}" if display else "Нажмите для записи")

    # ── recording toggle ─────────────────────────────────────────────────

    def _toggle_recording(self) -> None:
        if self._recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self) -> None:
        self._recording = True
        self._modifiers.clear()
        self._last_vk = 0
        self.setText("⏳  Нажмите клавишу или кнопку мыши...")
        self.setStyleSheet("PushButton { border: 2px solid #ea4335; color: #ea4335; }")

        # Start keyboard listener
        self._kb_listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
            win32_event_filter=self._win32_filter,
        )
        self._kb_listener.daemon = True
        self._kb_listener.start()

        # Start mouse listener (for side buttons)
        self._mouse_listener = mouse.Listener(on_click=self._on_mouse_click)
        self._mouse_listener.daemon = True
        self._mouse_listener.start()

    def _stop_recording(self) -> None:
        self._recording = False
        self.setStyleSheet("")
        if self._kb_listener:
            self._kb_listener.stop()
            self._kb_listener = None
        if self._mouse_listener:
            self._mouse_listener.stop()
            self._mouse_listener = None

    def _finish(self, display: str, pynput_str: str, vk: int = 0) -> None:
        """Called when a valid combo is captured."""
        self._stop_recording()
        self._current_display = display
        self._current_pynput = pynput_str
        self.setText(f"🎯  {display}")
        self.hotkey_recorded.emit(display, pynput_str, vk)

    # ── keyboard callbacks ───────────────────────────────────────────────

    def _win32_filter(self, msg, data):
        # WM_KEYDOWN = 0x0100, WM_SYSKEYDOWN = 0x0104
        if msg in (0x0100, 0x0104):
            self._last_vk = data.vkCode
        return True  # never suppress during recording

    def _on_key_press(self, key) -> None:
        if not self._recording:
            return

        # Esc → cancel
        if key == keyboard.Key.esc:
            self._stop_recording()
            self.setText(f"🎯  {self._current_display}" if self._current_display else "Нажмите для записи")
            return

        # Track modifiers
        if key in _MODIFIERS:
            self._modifiers.add(key)
            return

        # Non-modifier pressed → build combo
        display_parts = []
        pynput_parts = []

        # Deduplicate modifiers (ctrl_l == ctrl_r → one "Ctrl")
        seen_mod_display = set()
        for m in sorted(self._modifiers, key=lambda k: str(k)):
            d, p = _KEY_NAMES.get(m, (str(m), str(m)))
            if d not in seen_mod_display:
                seen_mod_display.add(d)
                display_parts.append(d)
                pynput_parts.append(p)

        # Main key — use the VK code we captured in the low-level hook
        raw_vk = getattr(self, "_last_vk", 0)

        if key in _KEY_NAMES:
            d, p = _KEY_NAMES[key]
            if p is None:  # e.g. Esc
                return
            display_parts.append(d)
            pynput_parts.append(p)
        elif hasattr(key, "char") and key.char:
            ch = key.char.lower()
            display_parts.append(ch.upper())
            pynput_parts.append(ch)
        else:
            if raw_vk:
                display_parts.append(f"Key{raw_vk}")
                pynput_parts.append(f"<{raw_vk}>")
            else:
                return

        display = " + ".join(display_parts)
        pynput_str = "+".join(pynput_parts)
        self._finish(display, pynput_str, raw_vk)

    def _on_key_release(self, key) -> None:
        self._modifiers.discard(key)

    # ── mouse callbacks ──────────────────────────────────────────────────

    def _on_mouse_click(self, x, y, button, pressed) -> None:
        if not self._recording or not pressed:
            return

        # Only capture side buttons (x1, x2) and middle button
        # Ignore left/right click since those are needed for UI interaction
        btn_map = {
            mouse.Button.middle: ("Middle Click", "mouse:middle"),
            mouse.Button.x1: ("Mouse 4 (Назад)", "mouse:x1"),
            mouse.Button.x2: ("Mouse 5 (Вперёд)", "mouse:x2"),
        }

        if button in btn_map:
            display, code = btn_map[button]
            self._finish(display, code)
