"""On-screen recording indicator — a small always-on-top pill.

Shows a pulsing status dot and live microphone level bars while
recording (or while continuous mode is listening).  The window is
frameless, click-through and never steals focus.
"""

import math
from collections import deque

from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import QPainter, QColor


class RecordingOverlay(QWidget):
    """Floating pill at the bottom-center of the primary screen."""

    WIDTH = 168
    HEIGHT = 44
    BARS = 14              # number of level-history bars
    MARGIN_BOTTOM = 24     # px above the taskbar (availableGeometry)
    FPS_MS = 50            # UI refresh interval

    COLOR_REC = QColor("#ff453a")    # red — actively capturing speech
    COLOR_IDLE = QColor("#0a84ff")   # blue — continuous mode, waiting for voice

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(self.WIDTH, self.HEIGHT)

        self._levels: deque[float] = deque([0.0] * self.BARS, maxlen=self.BARS)
        self._level_provider = None    # () -> float 0..1
        self._speech_provider = None   # () -> bool (continuous mode only)
        self._continuous = False
        self._phase = 0.0              # pulse animation phase

        self._timer = QTimer(self)
        self._timer.setInterval(self.FPS_MS)
        self._timer.timeout.connect(self._tick)

    # ---- public API ----

    def show_for(self, level_provider, continuous: bool = False,
                 speech_provider=None) -> None:
        """Show the overlay; *level_provider* is polled ~20 times/sec."""
        self._level_provider = level_provider
        self._speech_provider = speech_provider
        self._continuous = continuous
        self._levels.extend([0.0] * self.BARS)
        self._phase = 0.0
        self._reposition()
        self._timer.start()
        self.show()

    def hide_overlay(self) -> None:
        self._timer.stop()
        self._level_provider = None
        self._speech_provider = None
        self.hide()

    # ---- internals ----

    def _reposition(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = geo.x() + (geo.width() - self.WIDTH) // 2
        y = geo.y() + geo.height() - self.HEIGHT - self.MARGIN_BOTTOM
        self.move(x, y)

    def _tick(self) -> None:
        level = 0.0
        if self._level_provider is not None:
            try:
                level = float(self._level_provider())
            except Exception:
                level = 0.0
        self._levels.append(max(0.0, min(1.0, level)))
        self._phase = (self._phase + 0.35) % (2 * math.pi)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)

        # Pill background
        p.setBrush(QColor(28, 28, 30, 235))
        p.drawRoundedRect(QRectF(0, 0, self.WIDTH, self.HEIGHT),
                          self.HEIGHT / 2, self.HEIGHT / 2)

        # Status dot: red = capturing, blue = continuous mode waiting
        speech = True
        if self._continuous and self._speech_provider is not None:
            try:
                speech = bool(self._speech_provider())
            except Exception:
                speech = False
        color = QColor(self.COLOR_REC if (not self._continuous or speech)
                       else self.COLOR_IDLE)
        # Pulse only while capturing; steady dot while waiting
        if not self._continuous or speech:
            color.setAlphaF(0.55 + 0.45 * (0.5 + 0.5 * math.sin(self._phase)))
        dot = 10.0
        p.setBrush(color)
        p.drawEllipse(QRectF(16, (self.HEIGHT - dot) / 2, dot, dot))

        # Level-history bars
        x0, bar_w, gap = 38.0, 5.0, 3.0
        max_h = self.HEIGHT - 16.0
        for i, lvl in enumerate(self._levels):
            h = max(3.0, lvl * max_h)
            x = x0 + i * (bar_w + gap)
            y = (self.HEIGHT - h) / 2
            p.setBrush(QColor(255, 255, 255, 90 + int(150 * lvl)))
            p.drawRoundedRect(QRectF(x, y, bar_w, h), 2.5, 2.5)
