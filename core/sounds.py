"""Audio feedback — multiple sound themes to choose from.

Uses a single persistent sounddevice OutputStream that doubles as both
a keepalive (prevents Windows 11 audio sleep) and the playback engine.
Sound data is injected directly into the stream callback — zero overhead.
"""

import sys
import threading
import numpy as np
import sounddevice as sd
import datetime


def _log(msg: str):
    now = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
    line = f"[{now}] {msg}"
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        # A legacy console code page (cp1251/cp866/cp1252) cannot encode the
        # emoji in these lines.  This matters more than it looks: _log is
        # called from the except branch of _init_stream(), so a raise here
        # turns "no audio device" into a failed import of the whole module.
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        print(line.encode(enc, "replace").decode(enc), flush=True)
    except (AttributeError, ValueError):
        pass  # frozen windowed build: stdout may be absent or already closed


# ═════════════════════════════════════════════════════════════════════
#  Tone generation (numpy-based)
# ═════════════════════════════════════════════════════════════════════

SAMPLE_RATE = 44100


def _tone(freq: float, ms: int, vol: float = 0.25, fade: int = 10) -> np.ndarray:
    n = int(SAMPLE_RATE * ms / 1000)
    fd = int(SAMPLE_RATE * fade / 1000)
    t = np.arange(n, dtype=np.float32)
    samples = np.sin(2 * np.pi * freq * t / SAMPLE_RATE).astype(np.float32) * vol
    if fd > 0:
        samples[:fd] *= np.minimum(t[:fd] / fd, 1.0).astype(np.float32)
    if fd > 0 and n > fd:
        samples[-fd:] *= np.minimum((n - t[-fd:]) / fd, 1.0).astype(np.float32)
    return samples


def _concat(*arrays) -> np.ndarray:
    return np.concatenate(arrays).astype(np.float32)


# ═════════════════════════════════════════════════════════════════════
#  Sound themes
# ═════════════════════════════════════════════════════════════════════

THEMES: dict[str, tuple[str, tuple[np.ndarray, np.ndarray, np.ndarray]]] = {}


def _register(key: str, label: str, start, stop, cancel):
    THEMES[key] = (label, (start, stop, cancel))


_register("spring", "🌸 Весна",
    start  = _concat(_tone(1047, 70, 0.2), _tone(1319, 90, 0.25)),
    stop   = _concat(_tone(659, 70, 0.2), _tone(523, 90, 0.2)),
    cancel = _tone(392, 150, 0.15),
)
_register("minimal", "◻️ Минимал",
    start  = _tone(1200, 80, 0.2),
    stop   = _tone(800, 80, 0.18),
    cancel = _tone(400, 120, 0.12),
)
_register("bubbles", "🫧 Пузыри",
    start  = _concat(_tone(784, 50, 0.18), _tone(988, 50, 0.2), _tone(1175, 60, 0.22)),
    stop   = _concat(_tone(988, 50, 0.18), _tone(784, 60, 0.15)),
    cancel = _tone(523, 100, 0.12),
)
_register("space", "🚀 Космос",
    start  = _concat(_tone(440, 60, 0.15), _tone(880, 80, 0.2)),
    stop   = _concat(_tone(880, 60, 0.18), _tone(440, 80, 0.12)),
    cancel = _tone(330, 160, 0.1),
)
_register("soft", "🕊️ Нежный",
    start  = _concat(_tone(698, 90, 0.15), _tone(880, 100, 0.18)),
    stop   = _concat(_tone(587, 90, 0.15), _tone(440, 100, 0.12)),
    cancel = _tone(349, 180, 0.1),
)
_register("tick", "🔘 Тик",
    start  = _tone(1400, 30, 0.12),
    stop   = _tone(1000, 30, 0.1),
    cancel = _tone(600, 40, 0.08),
)


# ═════════════════════════════════════════════════════════════════════
#  Single persistent output stream — acts as both keepalive and player.
#  The callback feeds silence unless sound data has been injected.
# ═════════════════════════════════════════════════════════════════════

_lock = threading.Lock()
_play_buffer: np.ndarray | None = None   # sound data to play
_play_pos: int = 0                        # current read position
_stream: sd.OutputStream | None = None


def _audio_callback(outdata: np.ndarray, frames: int, time_info, status):
    """Called by PortAudio from a real-time C thread — no Python GIL delays."""
    global _play_buffer, _play_pos

    with _lock:
        if _play_buffer is not None:
            remaining = len(_play_buffer) - _play_pos
            to_copy = min(frames, remaining)
            outdata[:to_copy, 0] = _play_buffer[_play_pos : _play_pos + to_copy]
            _play_pos += to_copy

            # Zero-fill rest if sound is shorter than buffer
            if to_copy < frames:
                outdata[to_copy:] = 0.0
                _play_buffer = None
                _play_pos = 0
        else:
            # Silence — keeps the audio device awake on Windows 11
            outdata.fill(0)


def _init_stream():
    global _stream
    try:
        _stream = sd.OutputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype='float32',
            blocksize=256,       # small block = low latency (~6ms)
            latency='low',
            callback=_audio_callback,
        )
        _stream.start()
        _log("🔇 [Sounds] Audio stream ready (keepalive + instant playback)")
    except Exception as e:
        _log(f"⚠️ [Sounds] Could not start audio stream: {e}")


# Initialize at import time
_init_stream()


# ═════════════════════════════════════════════════════════════════════
#  Public API
# ═════════════════════════════════════════════════════════════════════

_current_theme = "spring"


def set_theme(key: str) -> None:
    global _current_theme
    if key in THEMES:
        _current_theme = key


def _play(idx: int) -> None:
    global _play_buffer, _play_pos
    _, sounds = THEMES.get(_current_theme, THEMES["spring"])
    with _lock:
        _play_buffer = sounds[idx]
        _play_pos = 0


def play_start() -> None:
    _play(0)

def play_stop() -> None:
    _play(1)

def play_cancel() -> None:
    _play(2)
