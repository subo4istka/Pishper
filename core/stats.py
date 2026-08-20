"""Usage statistics — tracks session count and total transcribed minutes.

Stats are stored in ~/.pishper/stats.txt as a simple human-readable file.
"""

import threading
from pathlib import Path
from datetime import datetime

STATS_FILE = Path.home() / ".pishper" / "stats.txt"
_lock = threading.Lock()


def _read() -> tuple[int, float]:
    """Return (session_count, total_minutes) from the stats file."""
    if not STATS_FILE.exists():
        return 0, 0.0
    try:
        data = {}
        for line in STATS_FILE.read_text(encoding="utf-8").splitlines():
            if ":" in line:
                key, _, val = line.partition(":")
                data[key.strip()] = val.strip()
        count = int(data.get("Сессий", 0))
        minutes = float(data.get("Минут записи", 0.0))
        return count, minutes
    except Exception:
        return 0, 0.0


def _write(count: int, minutes: float) -> None:
    """Write stats to the text file."""
    STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    STATS_FILE.write_text(
        f"Pishper — Статистика использования\n"
        f"{'=' * 38}\n"
        f"Сессий: {count}\n"
        f"Минут записи: {minutes:.2f}\n"
        f"Обновлено: {now}\n",
        encoding="utf-8",
    )


def log_session(duration_seconds: float) -> None:
    """Increment the session counter and add duration (in seconds) to total minutes."""
    with _lock:
        count, minutes = _read()
        count += 1
        minutes += duration_seconds / 60.0
        _write(count, minutes)


def get_stats() -> tuple[int, float]:
    """Return (session_count, total_minutes)."""
    with _lock:
        return _read()
