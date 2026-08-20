"""Pishper — WhisperTyping clone.  Main entry point."""

import sys
import ctypes
import ctypes.wintypes as wt
import queue
import threading
import time
import traceback
import datetime


# Windows consoles run a legacy code page (cp1251/cp866/cp1252) that cannot
# encode the emoji used in the log lines below.  Replacing unencodable
# characters keeps a stray log line from raising UnicodeEncodeError.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass  # frozen windowed build: no real stdout to reconfigure


def _log(msg: str):
    now = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{now}] {msg}", flush=True)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QObject, pyqtSignal, QTimer

from pynput.keyboard import Listener as KBListener, Key, KeyCode, HotKey
from pynput.mouse import Listener as MouseListener, Button

from core.config import AppConfig
from core.recorder import AudioRecorder
from core.continuous import ContinuousRecorder
from core.transcriber import transcribe
from core.errors import ApiError
from core.typer import type_text, send_enter
from core.sounds import play_start, play_stop, play_cancel, set_theme
from core.stats import log_session
from ui.tray import PishperTray
from ui.settings_window import SettingsWindow
from ui.overlay import RecordingOverlay

user32 = ctypes.windll.user32

# Mouse button name → pynput.mouse.Button
_MOUSE_BUTTONS = {
    "mouse:x1": Button.x1,
    "mouse:x2": Button.x2,
    "mouse:middle": Button.middle,
}


# ═══════════════════════════════════════════════════════════════════════
#  Low-level Windows keyboard hook (ctypes) — suppresses a single key
#  and calls a Python callback.  Runs on a dedicated thread with its
#  own message pump so the hook receives events.
# ═══════════════════════════════════════════════════════════════════════

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
WM_QUIT = 0x0012
HC_ACTION = 0

# Low-level hook callback type (stdcall)
HOOKPROC = ctypes.WINFUNCTYPE(
    wt.LPARAM,       # return (LRESULT)
    ctypes.c_int,    # nCode
    wt.WPARAM,       # wParam
    wt.LPARAM,       # lParam
)

# Use a fresh WinDLL with use_last_error to get real error codes
_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wt.HMODULE, wt.DWORD]
_user32.SetWindowsHookExW.restype = wt.HHOOK

_user32.CallNextHookEx.argtypes = [wt.HHOOK, ctypes.c_int, wt.WPARAM, wt.LPARAM]
_user32.CallNextHookEx.restype = wt.LPARAM

_user32.UnhookWindowsHookEx.argtypes = [wt.HHOOK]
_user32.UnhookWindowsHookEx.restype = wt.BOOL

_kernel32.GetModuleHandleW.argtypes = [wt.LPCWSTR]
_kernel32.GetModuleHandleW.restype = wt.HMODULE

_kernel32.GetCurrentThreadId.argtypes = []
_kernel32.GetCurrentThreadId.restype = wt.DWORD


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode",      wt.DWORD),
        ("scanCode",    wt.DWORD),
        ("flags",       wt.DWORD),
        ("time",        wt.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


# ── Mouse LL hook constants ──
WH_MOUSE_LL = 14
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP   = 0x0208
WM_XBUTTONDOWN = 0x020B
WM_XBUTTONUP   = 0x020C
XBUTTON1 = 0x0001
XBUTTON2 = 0x0002


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt",          wt.POINT),
        ("mouseData",   wt.DWORD),
        ("flags",       wt.DWORD),
        ("time",        wt.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class LowLevelKeyHook:
    """Installs a WH_KEYBOARD_LL hook that suppresses one VK code
    and calls *callback* every time it is pressed.

    Runs its own message-pump thread so the hook stays alive.
    The hook_proc is kept ultra-fast (just sets an Event flag)
    to avoid Windows removing the hook due to timeout.
    """

    def __init__(self, vk_code: int, callback):
        self._vk = vk_code
        self._callback = callback
        self._hook = None
        self._thread_id = None
        self._alive = True
        self._event = threading.Event()  # bridge: hook_proc → watcher
        # prevent the C function from being garbage-collected
        self._c_proc = HOOKPROC(self._hook_proc)
        self._ready = threading.Event()

        # Start the watcher thread (picks up events, calls callback)
        threading.Thread(target=self._watcher, daemon=True).start()
        # Start the hook thread (message pump)
        threading.Thread(target=self._run, daemon=True).start()
        self._ready.wait()

    def _run(self):
        self._thread_id = _kernel32.GetCurrentThreadId()
        hmod = _kernel32.GetModuleHandleW(None)
        self._hook = _user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._c_proc, hmod, 0,
        )
        if not self._hook:
            err = ctypes.get_last_error()
            print(f"[LowLevelKeyHook] ❌ FAILED! err={err}")
        else:
            print(f"[LowLevelKeyHook] ✅ VK=0x{self._vk:02X}")
        self._ready.set()
        msg = wt.MSG()
        while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            _user32.TranslateMessage(ctypes.byref(msg))
            _user32.DispatchMessageW(ctypes.byref(msg))

    def _hook_proc(self, nCode, wParam, lParam):
        # ⚡ MUST return ASAP — Windows kills slow LL hooks
        if nCode == HC_ACTION and wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
            kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            if kb.vkCode == self._vk:
                # Ignore if any modifier is held (Ctrl+ё, Alt+ё, etc.)
                gaks = _user32.GetAsyncKeyState
                if not (gaks(0x10) & 0x8000    # Shift
                        or gaks(0x11) & 0x8000  # Ctrl
                        or gaks(0x12) & 0x8000  # Alt
                        or gaks(0x5B) & 0x8000  # LWin
                        or gaks(0x5C) & 0x8000):  # RWin
                    self._event.set()
                    return 1  # suppress
        return _user32.CallNextHookEx(self._hook, nCode, wParam, lParam)

    def _watcher(self):
        """Separate thread: waits for the event flag, then calls callback."""
        while self._alive:
            self._event.wait()
            self._event.clear()
            if self._alive:  # stop() sets event to unblock — don't fire callback
                _log(f"⌨️  [LowLevelKeyHook] Event detected (VK=0x{self._vk:02X})")
                self._callback()

    def stop(self):
        self._alive = False
        self._event.set()  # unblock watcher so it can exit
        if self._hook:
            _user32.UnhookWindowsHookEx(self._hook)
            self._hook = None
        if self._thread_id:
            _user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)


class LowLevelMouseHook:
    """WH_MOUSE_LL hook that suppresses a specific mouse button
    and fires *callback* on press (ignoring modified clicks)."""

    # Map config strings to (down_msg, up_msg, xbutton_id_or_0)
    BUTTON_MAP = {
        "mouse:middle": (WM_MBUTTONDOWN, WM_MBUTTONUP, 0),
        "mouse:x1":     (WM_XBUTTONDOWN, WM_XBUTTONUP, XBUTTON1),
        "mouse:x2":     (WM_XBUTTONDOWN, WM_XBUTTONUP, XBUTTON2),
    }

    def __init__(self, button_key: str, callback) -> None:
        target = self.BUTTON_MAP.get(button_key)
        if not target:
            raise ValueError(f"Unknown mouse button: {button_key}")
        self._down_msg, self._up_msg, self._target_xbutton = target
        self._callback = callback
        self._alive = True
        self._event = threading.Event()
        self._hook = None
        self._thread_id = None
        self._hook_ref = HOOKPROC(self._hook_proc)

        threading.Thread(target=self._watcher, daemon=True).start()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        hmod = _kernel32.GetModuleHandleW(None)
        self._hook = _user32.SetWindowsHookExW(
            WH_MOUSE_LL, self._hook_ref, hmod, 0,
        )
        self._thread_id = _kernel32.GetCurrentThreadId()
        msg = wt.MSG()
        while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            _user32.TranslateMessage(ctypes.byref(msg))
            _user32.DispatchMessageW(ctypes.byref(msg))

    def _matches_button(self, wParam, lParam) -> bool:
        """Check if this mouse event matches our target button."""
        if wParam not in (self._down_msg, self._up_msg):
            return False
        if self._target_xbutton:
            info = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            hi_word = (info.mouseData >> 16) & 0xFFFF
            if hi_word != self._target_xbutton:
                return False
        return True

    def _hook_proc(self, nCode, wParam, lParam) -> int:
        if nCode == HC_ACTION and self._matches_button(wParam, lParam):
            # Always suppress UP to prevent partial click
            if wParam == self._up_msg:
                return 1

            # DOWN: check modifiers — pass through if any held
            VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN = 0x10, 0x11, 0x12, 0x5B, 0x5C
            for vk in (VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN):
                if _user32.GetAsyncKeyState(vk) & 0x8000:
                    return _user32.CallNextHookEx(self._hook, nCode, wParam, lParam)

            self._event.set()
            return 1  # suppress DOWN

        return _user32.CallNextHookEx(self._hook, nCode, wParam, lParam)

    def _watcher(self) -> None:
        while self._alive:
            self._event.wait()
            self._event.clear()
            if self._alive:
                _log(f"🖱️  [LowLevelMouseHook] Event detected")
                self._callback()

    def stop(self) -> None:
        self._alive = False
        self._event.set()
        if self._hook:
            _user32.UnhookWindowsHookEx(self._hook)
            self._hook = None
        if self._thread_id:
            _user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)


# ═══════════════════════════════════════════════════════════════════════


def _canonical_key(key):
    """Normalize a key for comparison (merge left/right modifiers, lowercase chars)."""
    if isinstance(key, Key):
        if key in (Key.ctrl_l, Key.ctrl_r):
            return Key.ctrl_l
        if key in (Key.shift_l, Key.shift_r):
            return Key.shift_l
        if key in (Key.alt_l, Key.alt_r):
            return Key.alt_l
        return key
    if isinstance(key, KeyCode) and key.char:
        return KeyCode.from_char(key.char.lower())
    return key


def _parse_hotkey(hotkey_str: str) -> frozenset:
    """Parse a pynput hotkey string into a frozenset of canonical keys."""
    try:
        parsed = HotKey.parse(hotkey_str)
    except ValueError:
        parsed = [KeyCode.from_char(hotkey_str)]
    return frozenset(_canonical_key(k) for k in parsed)


class Orchestrator(QObject):
    """Bridges the global hotkey thread, recorder, and GUI."""

    sig_hotkey_pressed = pyqtSignal()
    sig_cancel_recording = pyqtSignal()
    sig_transcription_done = pyqtSignal(str)
    sig_continuous_chunk = pyqtSignal(bytes)
    sig_error = pyqtSignal(str, str, str)   # title, message, kind

    def __init__(self) -> None:
        super().__init__()
        self.config = AppConfig.load()
        self.recorder = AudioRecorder(bitrate=self.config.mp3_bitrate)

        # ---- UI ----
        self.tray = PishperTray()
        self.tray.sync_mode(self.config.mode)
        self.tray.setVisible(True)
        self.overlay = RecordingOverlay()

        # ---- tray actions ----
        self.tray.action_toggle.triggered.connect(self._toggle_recording)
        self.tray.action_settings.triggered.connect(self._open_settings)
        self.tray.action_quit.triggered.connect(self._quit)
        self.tray.action_mode_transcribe.triggered.connect(
            lambda: self._set_mode("transcribe")
        )
        self.tray.action_mode_translate.triggered.connect(
            lambda: self._set_mode("translate")
        )
        self.tray.action_copy_last.triggered.connect(self._copy_last)
        self.tray.action_continuous.triggered.connect(self._toggle_continuous)

        self._last_text = ""  # stores last transcription
        self._last_error = ("", 0.0)  # (kind, monotonic ts) — anti-spam

        # Single transcription worker: jobs are processed strictly in
        # order, so continuous-mode chunks are always typed in the order
        # they were spoken (parallel threads could finish out of order).
        self._jobs: queue.Queue = queue.Queue()
        threading.Thread(target=self._transcribe_loop, daemon=True).start()

        self._continuous = ContinuousRecorder(
            on_speech_chunk=self._on_speech_chunk,
            silence_timeout_ms=self.config.silence_timeout_ms,
            bitrate=self.config.mp3_bitrate,
        )

        # ---- signals ----
        self.sig_hotkey_pressed.connect(self._toggle_recording)
        self.sig_cancel_recording.connect(self._cancel_recording)
        self.sig_transcription_done.connect(self._on_transcription)
        self.sig_continuous_chunk.connect(self._on_continuous_chunk)
        self.sig_error.connect(self._on_error)

        # ---- hotkey state ----
        self._hotkey_listener = None   # pynput listener (keyboard)
        self._single_key_hook = None   # LowLevelKeyHook for single keys
        self._mouse_hook = None        # LowLevelMouseHook for mouse buttons
        self._esc_listener = None      # pynput listener for Escape
        set_theme(self.config.sound_theme)
        self._start_hotkey_listener()

        if not self.config.active_api_key:
            QTimer.singleShot(
                500,
                lambda: self.tray.show_message(
                    "Pishper",
                    "API Key не указан. Откройте настройки (правый клик → Настройки).",
                ),
            )

    # ---- hotkey ----

    def _stop_listeners(self):
        if self._hotkey_listener is not None:
            self._hotkey_listener.stop()
            self._hotkey_listener = None
        if self._single_key_hook is not None:
            self._single_key_hook.stop()
            self._single_key_hook = None
        if self._mouse_hook is not None:
            self._mouse_hook.stop()
            self._mouse_hook = None
        if self._esc_listener is not None:
            self._esc_listener.stop()
            self._esc_listener = None

    def _start_hotkey_listener(self) -> None:
        self._stop_listeners()

        # Activate primary hotkey
        self._activate_one_hotkey(self.config.hotkey, self.config.hotkey_vk,
                                  self.config.hotkey_display)

        # Activate secondary hotkey (if set)
        if self.config.hotkey2:
            self._activate_one_hotkey(self.config.hotkey2, self.config.hotkey2_vk,
                                      self.config.hotkey2_display)

        # One Escape listener for cancellation (if any non-combo hotkey is active)
        if (self._single_key_hook or self._mouse_hook) and not self._esc_listener:
            self._esc_listener = KBListener(on_press=self._on_esc_only)
            self._esc_listener.daemon = True
            self._esc_listener.start()

    def _activate_one_hotkey(self, hotkey: str, vk: int, display: str) -> None:
        """Start a listener for a single hotkey string."""
        if not hotkey:
            return

        if hotkey in _MOUSE_BUTTONS:
            def on_mouse():
                self.sig_hotkey_pressed.emit()
            self._mouse_hook = LowLevelMouseHook(hotkey, on_mouse)
            print(f"[Pishper] 🖱️  Хоткей: {display or hotkey} (Win32 мышь-хук)")

        elif vk:
            def on_key():
                self.sig_hotkey_pressed.emit()
            self._single_key_hook = LowLevelKeyHook(vk, on_key)
            print(f"[Pishper] ⌨️  Хоткей: {display or hotkey}"
                  f"  (VK=0x{vk:02X}, прямой Win32-хук)")

        else:
            try:
                self._hk_keys = _parse_hotkey(hotkey)
            except Exception as exc:
                QTimer.singleShot(
                    500,
                    lambda: self.tray.show_message(
                        "Pishper — ошибка хоткея",
                        f"Невалидный хоткей '{hotkey}'.\n{exc}",
                        self.tray.MessageIcon.Warning,
                    ),
                )
                return

            self._hk_pressed = set()
            self._hotkey_listener = KBListener(
                on_press=self._on_kb_press,
                on_release=self._on_kb_release,
            )
            self._hotkey_listener.daemon = True
            self._hotkey_listener.start()
            print(f"[Pishper] ⌨️  Хоткей: {display or hotkey}")

    # ── keyboard callbacks ───────────────────────────────────────────────

    def _on_esc_only(self, key) -> None:
        """Escape listener for single-key mode."""
        if key == Key.esc and self.recorder.is_recording:
            print("[Pishper] ⎋  Escape — отмена записи")
            self.sig_cancel_recording.emit()

    def _on_kb_press(self, key) -> None:
        if key == Key.esc and self.recorder.is_recording:
            print("[Pishper] ⎋  Escape — отмена записи")
            self.sig_cancel_recording.emit()
            return

        canon = _canonical_key(key)
        self._hk_pressed.add(canon)

        if self._hk_keys and self._hk_keys.issubset(self._hk_pressed):
            self._hk_pressed.clear()
            _log(f"⌨️  [Orchestrator] Combo hotkey detected")
            self.sig_hotkey_pressed.emit()

    def _on_kb_release(self, key) -> None:
        canon = _canonical_key(key)
        self._hk_pressed.discard(canon)

    # ---- recording toggle ----

    def _toggle_recording(self) -> None:
        state = "STOP" if self.recorder.is_recording else "START"
        _log(f"⚡ [Orchestrator] Toggle recording -> {state}")
        if self.recorder.is_recording:
            self._stop_and_transcribe()
        else:
            self._start_recording()

    def _cancel_recording(self) -> None:
        if self.recorder.is_recording:
            self.recorder.stop()
            self.tray.set_recording(False)
            self.overlay.hide_overlay()
            if self.config.sound_enabled:
                play_cancel()

    def _start_recording(self) -> None:
        if not self.config.active_api_key:
            self.tray.show_message("Pishper", "Сначала укажите API Key в настройках.")
            return
        # Stop continuous mode if active
        if self._continuous.is_active:
            self._continuous.stop()
            self.tray.action_continuous.setChecked(False)
        try:
            self.recorder.start()
            self.tray.set_recording(True)
            if self.config.show_overlay:
                self.overlay.show_for(lambda: self.recorder.level)
            if self.config.sound_enabled:
                play_start()
        except Exception as exc:
            self.sig_error.emit("Pishper — ошибка записи", str(exc), "audio")

    def _stop_and_transcribe(self) -> None:
        self.tray.set_recording(False)
        self.overlay.hide_overlay()
        if self.config.sound_enabled:
            play_stop()
        duration = time.perf_counter() - self.recorder._start_time
        audio = self.recorder.stop()
        if not audio:
            return
        self._jobs.put((audio, duration))

    def _transcribe_loop(self) -> None:
        """Worker thread: transcribes queued audio strictly in order."""
        while True:
            audio, duration_sec = self._jobs.get()
            try:
                t0 = time.perf_counter()
                text = transcribe(audio, self.config)
                dt = time.perf_counter() - t0
                print(f"[Pishper] API: {dt:.2f}с  ({len(audio)}б) → '{text}'")
                if text:
                    log_session(duration_sec)
                self.sig_transcription_done.emit(text)
            except ApiError as err:
                # Повторы уже исчерпаны внутри transcribe() —
                # остаётся показать понятное уведомление.
                print(f"[Pishper] {err.title}: {err.detail}")
                self.sig_error.emit(f"Pishper — {err.title}",
                                    err.user_text, err.kind)
            except Exception:
                tb = traceback.format_exc()
                print(f"[Pishper] ОШИБКА:\n{tb}")
                self.sig_error.emit("Pishper — ошибка",
                                    tb.strip().splitlines()[-1], "unknown")

    # ---- callbacks on main thread ----

    def _on_transcription(self, text: str) -> None:
        if text:
            self._last_text = text
            self.tray.action_copy_last.setEnabled(True)
            self.tray.action_copy_last.setText(f"📋  {text[:40]}{'…' if len(text) > 40 else ''}")
            type_text(text)
            if self.tray.action_auto_enter.isChecked():
                import time; time.sleep(0.05)
                send_enter()

    def _copy_last(self) -> None:
        """Copy last transcription to clipboard."""
        if self._last_text:
            from core.typer import _set_clipboard
            _set_clipboard(self._last_text)
            self.tray.show_message("Pishper", f"Скопировано: {self._last_text[:60]}")

    # ---- continuous mode ----

    def _on_speech_chunk(self, mp3_bytes: bytes) -> None:
        """Called from ContinuousRecorder bg thread — emit signal to main thread."""
        self.sig_continuous_chunk.emit(mp3_bytes)

    def _on_continuous_chunk(self, mp3_bytes: bytes) -> None:
        """Main-thread handler: queue speech chunk for ordered transcription."""
        # Estimate duration from MP3 size: bitrate in kbps → bytes/sec
        est_duration = len(mp3_bytes) / (self.config.mp3_bitrate * 125)
        self._jobs.put((mp3_bytes, est_duration))

    def _toggle_continuous(self) -> None:
        if self._continuous.is_active:
            self._continuous.stop()
            self.tray.action_continuous.setChecked(False)
            self.tray.setToolTip("Pishper — голосовой ввод (idle)")
            self.overlay.hide_overlay()
            if self.config.sound_enabled:
                play_stop()
        else:
            # Stop regular recording if active
            if self.recorder.is_recording:
                self._cancel_recording()
            self._continuous.start()
            self.tray.action_continuous.setChecked(True)
            self.tray.setToolTip("Pishper — 🔄 непрерывный режим")
            if self.config.show_overlay:
                self.overlay.show_for(
                    lambda: self._continuous.level,
                    continuous=True,
                    speech_provider=lambda: self._continuous.in_speech,
                )
            if self.config.sound_enabled:
                play_start()

    # ---- errors ----

    # Не показывать один и тот же тип ошибки чаще, чем раз в N секунд:
    # в непрерывном режиме при выключенном VPN каждая фраза даёт ошибку,
    # и без этого пользователя завалило бы всплывашками.
    ERROR_REPEAT_SEC = 20.0

    _WARNING_KINDS = ("network", "timeout", "rate_limit", "server")

    def _restore_tooltip(self) -> None:
        if self.recorder.is_recording:
            self.tray.setToolTip("Pishper — 🔴 ЗАПИСЬ...")
        elif self._continuous.is_active:
            self.tray.setToolTip("Pishper — 🔄 непрерывный режим")
        else:
            self.tray.setToolTip("Pishper — голосовой ввод (idle)")

    def _on_error(self, title: str, message: str, kind: str) -> None:
        now = time.monotonic()
        last_kind, last_ts = self._last_error
        self._last_error = (kind, now)

        # Подсказка в трее обновляется всегда, даже если всплывашку подавили —
        # так видно, что последняя фраза не дошла до сервиса.
        self.tray.setToolTip(f"Pishper — ⚠ {title}")
        QTimer.singleShot(8000, self._restore_tooltip)

        if kind == last_kind and (now - last_ts) < self.ERROR_REPEAT_SEC:
            print(f"[Pishper] Уведомление подавлено (повтор {kind}): {message}")
            return

        icon = (self.tray.MessageIcon.Warning if kind in self._WARNING_KINDS
                else self.tray.MessageIcon.Critical)
        self.tray.show_message(title, message[:300], icon)

    # ---- settings ----

    def _open_settings(self) -> None:
        self._stop_listeners()  # pause hotkey while dialog is open
        dlg = SettingsWindow(self.config)
        if dlg.exec():
            self.tray.sync_mode(self.config.mode)
            set_theme(self.config.sound_theme)
            # Apply overlay setting to an already-visible indicator
            if not self.config.show_overlay:
                self.overlay.hide_overlay()
            elif self._continuous.is_active and not self.overlay.isVisible():
                self.overlay.show_for(
                    lambda: self._continuous.level,
                    continuous=True,
                    speech_provider=lambda: self._continuous.in_speech,
                )
        # Restart listener after a short delay to avoid catching stray key events
        QTimer.singleShot(200, self._start_hotkey_listener)

    def _set_mode(self, mode: str) -> None:
        self.config.mode = mode
        self.config.save()
        self.tray.sync_mode(mode)

    # ---- quit ----

    def _quit(self) -> None:
        self._stop_listeners()
        if self._continuous.is_active:
            self._continuous.stop()
        QApplication.instance().quit()


def main() -> None:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    orchestrator = Orchestrator()  # noqa: F841  prevent GC

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
