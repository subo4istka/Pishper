"""Render the documentation screenshots straight from the widgets.

Run from the repo root:  python tools/make_screenshots.py

Grabbing the widgets instead of taking manual screenshots keeps docs/ in sync
with the UI and — more importantly — keeps personal data out of the images: the
dialog is fed a synthetic config, never the real ~/.pishper/config.json.
Nothing here writes to the user's config.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication  # noqa: E402

from core.config import AppConfig  # noqa: E402
from ui.settings_window import SettingsWindow  # noqa: E402
from ui.tray import PishperTray  # noqa: E402

OUT = ROOT / "docs" / "screenshots"

# A neutral configuration for the shots: default provider, a placeholder key
# (the field renders as dots anyway), no proxy, and both hotkey slots filled so
# the screenshot shows what the second binding looks like.
DEMO = AppConfig(
    provider="groq",
    model="whisper-large-v3-turbo",
    api_keys={"groq": "gsk_" + "0" * 48},
    language="ru",
    mode="transcribe",
    proxy="",
    proxy_enabled=False,
    silence_timeout_ms=2000,
    mp3_bitrate=32,
    sound_enabled=True,
    show_overlay=True,
    autostart=True,
    hotkey="<ctrl>+<shift>+<space>",
    hotkey_display="Ctrl + Shift + Space",
    hotkey2="",
    hotkey2_display="Ё",
    hotkey2_vk=0xC0,
)

PAGES = [
    (0, "settings-connection.png"),
    (1, "settings-recognition.png"),
    (2, "settings-controls.png"),
]


def _save(widget, name: str) -> None:
    widget.ensurePolished()
    widget.adjustSize()
    QApplication.processEvents()
    path = OUT / name
    if not widget.grab().save(str(path)):
        raise RuntimeError(f"failed to write {path}")
    print(f"{name}  {widget.width()}x{widget.height()}")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv)

    dlg = SettingsWindow(DEMO)
    for row, name in PAGES:
        dlg.sidebar.setCurrentRow(row)
        _save(dlg, name)

    tray = PishperTray()
    tray.sync_mode(DEMO.mode)
    _save(tray.contextMenu(), "tray-menu.png")

    del app  # keep Qt from complaining about teardown order


if __name__ == "__main__":
    main()
