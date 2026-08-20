"""System-tray icon with context menu and status management."""

import os
from pathlib import Path

from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QAction

ASSETS = Path(__file__).resolve().parent.parent / "assets"


class PishperTray(QSystemTrayIcon):
    """Manages the system-tray icon, context menu, and visual state."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._icon_normal = QIcon(str(ASSETS / "icon.png"))
        self._icon_recording = QIcon(str(ASSETS / "icon_recording.png"))
        self.setIcon(self._icon_normal)
        self.setToolTip("Pishper — голосовой ввод (idle)")
        self._build_menu()

    # ---- menu ----

    def _build_menu(self) -> None:
        menu = QMenu()

        self.action_toggle = QAction("🎙️  Начать запись")
        menu.addAction(self.action_toggle)

        self.action_continuous = QAction("🔄  Непрерывный режим")
        self.action_continuous.setCheckable(True)
        menu.addAction(self.action_continuous)

        self.action_auto_enter = QAction("⏎  Автоотправка (Enter)")
        self.action_auto_enter.setCheckable(True)
        menu.addAction(self.action_auto_enter)

        menu.addSeparator()

        self.action_mode_transcribe = QAction("  Транскрипция")
        self.action_mode_transcribe.setCheckable(True)
        menu.addAction(self.action_mode_transcribe)

        self.action_mode_translate = QAction("  Перевод → English")
        self.action_mode_translate.setCheckable(True)
        menu.addAction(self.action_mode_translate)

        menu.addSeparator()

        self.action_settings = QAction("⚙️  Настройки")
        menu.addAction(self.action_settings)

        self.action_copy_last = QAction("📋  Последняя фраза")
        self.action_copy_last.setEnabled(False)
        menu.addAction(self.action_copy_last)

        menu.addSeparator()

        self.action_quit = QAction("❌  Выход")
        menu.addAction(self.action_quit)

        self.setContextMenu(menu)

    # ---- public helpers ----

    def set_recording(self, recording: bool) -> None:
        if recording:
            self.setIcon(self._icon_recording)
            self.setToolTip("Pishper — 🔴 ЗАПИСЬ...")
            self.action_toggle.setText("⏹️  Остановить запись")
        else:
            self.setIcon(self._icon_normal)
            self.setToolTip("Pishper — голосовой ввод (idle)")
            self.action_toggle.setText("🎙️  Начать запись")

    def sync_mode(self, mode: str) -> None:
        self.action_mode_transcribe.setChecked(mode == "transcribe")
        self.action_mode_translate.setChecked(mode == "translate")

    def show_message(self, title: str, msg: str, icon=QSystemTrayIcon.MessageIcon.Information) -> None:  # noqa: ANN001
        self.showMessage(title, msg, icon, 3000)
