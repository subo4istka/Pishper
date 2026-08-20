"""Settings window — clean light design (pre-Fluent version, custom CSS)."""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QFrame, QCheckBox, QWidget,
    QStackedWidget, QListWidget, QListWidgetItem, QTextEdit, QSpinBox,
    QSlider, QButtonGroup,
)
from PyQt6.QtCore import Qt, QSize, QObject, pyqtSignal
from PyQt6.QtGui import QFont

from core.config import AppConfig, PROVIDERS, LANGUAGES

import os
import tempfile
import threading
from pathlib import Path

# Битрейт MP3: значение → подпись кнопки и пояснение под переключателем.
_BITRATES = [
    (16, "Минимум трафика: на тихой речи слышны артефакты."),
    (32, "Точность почти как у 64, трафика вдвое меньше — по умолчанию."),
    (64, "Максимальное качество записи, больше трафика."),
]

_PROMPT_MAX = 400   # символов: длинный prompt только сбивает модель


def _generate_ui_images():
    """Create toggle switch + dropdown chevron + spinbox arrow PNGs using QPainter (2x for HiDPI)."""
    from PyQt6.QtGui import QImage, QPainter, QColor, QPen, QBrush, QPainterPath
    from PyQt6.QtCore import Qt, QRectF, QPointF

    ui_dir = Path(tempfile.gettempdir()) / "pishper_ui"
    ui_dir.mkdir(exist_ok=True)

    # ── Toggle switches (2x: 88×48 pixels, displayed as 44×24) ──
    toggle_off = ui_dir / "toggle_off.png"
    toggle_on = ui_dir / "toggle_on.png"
    S = 2  # scale factor
    W, H = 44 * S, 24 * S
    KNOB = 18 * S
    PAD = 3 * S

    for path, track_color, knob_x in [
        (toggle_off, QColor("#b0b0b0"), PAD),
        (toggle_on, QColor("#1a73e8"), W - KNOB - PAD),
    ]:
        img = QImage(W, H, QImage.Format.Format_ARGB32)
        img.fill(QColor(0, 0, 0, 0))
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Track
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(track_color))
        p.drawRoundedRect(QRectF(0, 0, W, H), H / 2, H / 2)
        # Knob shadow
        p.setBrush(QBrush(QColor(0, 0, 0, 40)))
        p.drawEllipse(QRectF(knob_x + 1, PAD + 1.5, KNOB, KNOB))
        # Knob
        p.setBrush(QBrush(QColor("#ffffff")))
        p.setPen(QPen(QColor(0, 0, 0, 20), 1))
        p.drawEllipse(QRectF(knob_x, PAD, KNOB, KNOB))
        p.end()
        img.save(str(path))

    # ── Chevron for combo box (2x: 24×24) ──
    chevron_path = ui_dir / "chevron_down.png"
    img = QImage(24, 24, QImage.Format.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor("#666"))
    pen.setWidthF(2.0)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.drawLine(QPointF(6, 9), QPointF(12, 15))
    p.drawLine(QPointF(12, 15), QPointF(18, 9))
    p.end()
    img.save(str(chevron_path))

    # ── SpinBox arrows (2x: 16×16) ──
    for name, y1, y2 in [("spin_up", 11, 5), ("spin_down", 5, 11)]:
        arrow_path = ui_dir / f"{name}.png"
        img = QImage(16, 16, QImage.Format.Format_ARGB32)
        img.fill(QColor(0, 0, 0, 0))
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#666"))
        pen.setWidthF(2.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawLine(QPointF(4, y1), QPointF(8, y2))
        p.drawLine(QPointF(8, y2), QPointF(12, y1))
        p.end()
        img.save(str(arrow_path))

    spin_up_path = str(ui_dir / "spin_up.png").replace("\\", "/")
    spin_down_path = str(ui_dir / "spin_down.png").replace("\\", "/")

    return (
        str(toggle_off).replace("\\", "/"),
        str(toggle_on).replace("\\", "/"),
        str(chevron_path).replace("\\", "/"),
        spin_up_path,
        spin_down_path,
    )

_TOGGLE_OFF, _TOGGLE_ON, _CHEVRON_DOWN, _SPIN_UP, _SPIN_DOWN = _generate_ui_images()

_STYLE = f"""
QDialog {{ background: #ffffff; }}

/* ── Sidebar ── */
QWidget#sidebarWrap {{ background: #f2f3f5; }}
QLabel#appName {{
    font-size: 18px; font-weight: 700; color: #1a1a1a;
    padding: 18px 16px 10px 16px; background: transparent;
}}
QListWidget#sidebar {{
    background: transparent; border: none; outline: none;
    padding: 4px 8px; font-size: 14px;
}}
QListWidget#sidebar::item {{
    color: #333; padding: 8px 12px; border-radius: 6px; margin: 1px 0;
}}
QListWidget#sidebar::item:selected {{
    color: #1a73e8; background: #d2e3fc; font-weight: 700;
}}
QListWidget#sidebar::item:hover:!selected {{
    background: #e8e9eb;
}}

/* ── Page title ── */
QLabel#pageTitle {{
    font-size: 18px; font-weight: 700; color: #1a1a1a;
    background: transparent; padding: 0 0 6px 0;
}}
QLabel#sectionHead {{
    font-size: 14px; font-weight: 600; color: #1a1a1a;
    background: transparent; padding: 4px 0 2px 0;
}}
QLabel#fieldLabel {{
    font-size: 14px; font-weight: 500; color: #1a1a1a;
    background: transparent;
}}
QLabel#hint {{
    font-size: 14px; font-weight: 500; color: #2b2f33;
    background: transparent;
}}

/* ── Inputs ── */
QLineEdit, QComboBox {{
    background: #ffffff; color: #1a1a1a;
    border: 1px solid #ccc; border-radius: 6px;
    padding: 6px 10px; font-size: 14px; min-height: 16px;
}}
QLineEdit:focus, QComboBox:focus {{ border-color: #1a73e8; }}

/* ── ComboBox dropdown ── */
QComboBox::drop-down {{
    border: none; width: 28px;
}}
QComboBox::down-arrow {{
    image: url({_CHEVRON_DOWN}); width: 12px; height: 12px;
}}

/* ── SpinBox ── */
QSpinBox {{
    background: #ffffff; color: #1a1a1a;
    border: 1px solid #ccc; border-radius: 6px;
    padding: 6px 8px; font-size: 14px; min-height: 14px;
}}
QSpinBox:focus {{ border-color: #1a73e8; }}
QSpinBox::up-button, QSpinBox::down-button {{
    background: transparent; border: none;
    width: 20px; height: 12px;
    subcontrol-origin: border;
}}
QSpinBox::up-button {{ subcontrol-position: top right; padding-top: 2px; }}
QSpinBox::down-button {{ subcontrol-position: bottom right; padding-bottom: 2px; }}
QSpinBox::up-arrow {{
    image: url({_SPIN_UP}); width: 8px; height: 8px;
}}
QSpinBox::down-arrow {{
    image: url({_SPIN_DOWN}); width: 8px; height: 8px;
}}

/* ── Toggle switch ── */
QCheckBox {{ color: #1a1a1a; font-size: 14px; spacing: 10px; background: transparent; }}
QCheckBox::indicator {{
    width: 44px; height: 24px; border: none; background: transparent;
}}
QCheckBox::indicator:unchecked {{
    image: url({_TOGGLE_OFF});
}}
QCheckBox::indicator:checked {{
    image: url({_TOGGLE_ON});
}}

/* ── Buttons ── */
QPushButton#primary {{
    background: #1a73e8; color: #ffffff; border: none; border-radius: 6px;
    padding: 8px 18px; font-size: 14px; font-weight: 500;
}}
QPushButton#primary:hover {{ background: #1765cc; }}
QPushButton#secondary {{
    background: #ffffff; color: #333; border: 1px solid #ccc;
    border-radius: 6px; padding: 8px 18px; font-size: 14px;
}}
QPushButton#secondary:hover {{ background: #f2f3f5; border-color: #aaa; }}

/* ── Счётчик символов ── */
QLabel#counter {{
    font-size: 13px; color: #70757d; background: transparent;
}}
QLabel#counterOver {{
    font-size: 13px; color: #d93025; background: transparent;
}}

/* ── Слайдер ── */
QSlider::groove:horizontal {{
    height: 6px; background: #e6e7e9; border-radius: 3px;
}}
QSlider::sub-page:horizontal {{
    height: 6px; background: #1a73e8; border-radius: 3px;
}}
QSlider::handle:horizontal {{
    width: 16px; height: 16px; margin: -6px 0;
    background: #1a73e8; border: 2px solid #ffffff; border-radius: 9px;
}}
QSlider::handle:horizontal:hover {{ background: #1765cc; }}
QLabel#sliderValue {{
    font-size: 14px; font-weight: 600; color: #333; background: transparent;
}}

/* ── Сегментированный переключатель ── */
QFrame#segmented {{
    background: #f2f3f5; border: 1px solid #e0e1e3; border-radius: 8px;
}}
QPushButton#segBtn {{
    background: transparent; border: 1px solid transparent; border-radius: 6px;
    color: #777; font-size: 13px; padding: 6px 14px;
}}
QPushButton#segBtn:hover:!checked {{ color: #333; }}
QPushButton#segBtn:checked {{
    background: #ffffff; border: 1px solid #d4d5d7;
    color: #1a1a1a; font-weight: 600;
}}

/* ── Ссылка-кнопка ("Показать" / "Скрыть") ── */
QPushButton#linkBtn {{
    background: transparent; border: none; color: #1a73e8;
    font-size: 13px; font-weight: 500; padding: 0 2px;
}}
QPushButton#linkBtn:hover {{ color: #1765cc; text-decoration: underline; }}

/* ── Hotkey button ── */
QPushButton#hotkeyBtn {{
    background: #ffffff; color: #333;
    border: 1px solid #ccc;
    border-radius: 6px; padding: 8px 12px; font-size: 14px; min-height: 16px;
    text-align: left; font-weight: 600;
}}
QPushButton#hotkeyBtn:hover {{ border-color: #1a73e8; }}
QPushButton#hotkeyBtnRecording {{
    background: #fff8f8; color: #ea4335; border: 2px solid #ea4335;
    border-radius: 6px; padding: 8px 12px; font-size: 14px; min-height: 16px;
    text-align: left; font-weight: 600;
}}

/* ── TextEdit ── */
QTextEdit {{
    background: #ffffff; color: #1a1a1a;
    border: 1px solid #ccc; border-radius: 6px;
    padding: 6px 10px; font-size: 13px;
}}
QTextEdit:focus {{ border-color: #1a73e8; }}

/* ── Separator ── */
QFrame#sep {{ background: #ddd; max-height: 1px; }}

/* ── Результат проверки подключения ── */
QLabel#checkOk {{ font-size: 14px; color: #1e8e3e; background: transparent; }}
QLabel#checkWarn {{ font-size: 14px; color: #b06000; background: transparent; }}
QLabel#checkFail {{ font-size: 14px; color: #d93025; background: transparent; }}
"""


class _ConnectionCheckWorker(QObject):
    """Гоняет проверку подключения в фоне, чтобы диалог не подвисал."""

    done = pyqtSignal(str, str)   # status: ok | warn | fail, message

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self._config = config

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        from core.transcriber import check_connection
        from core.errors import ApiError
        try:
            dt = check_connection(self._config)
            self.done.emit("ok", f"Подключение работает — ответ за {dt:.1f} с")
        except ApiError as err:
            print(f"[Pishper] Проверка подключения: {err.title}: {err.detail}")
            if err.kind == "request":
                # Сервис ответил и отклонил именно тестовое аудио (полсекунды
                # тишины): значит сеть и ключ в порядке, а вот про сам запрос
                # судить нельзя — не выдаём это ни за успех, ни за обрыв связи.
                self.done.emit(
                    "warn",
                    "Связь и ключ работают, но сервис отклонил тестовое аудио. "
                    "Проверьте модель — подробности в логе.",
                )
            else:
                self.done.emit("fail", err.user_text)
        except Exception as exc:  # noqa: BLE001 — диалог не должен падать
            print(f"[Pishper] Проверка подключения: {type(exc).__name__}: {exc}")
            self.done.emit("fail", f"Не удалось выполнить проверку: {exc}")


class SettingsWindow(QDialog):
    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Pishper — Настройки")
        self.setFixedSize(660, 520)
        self.setStyleSheet(_STYLE)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint)
        # Window icon
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "icon.png")
        if os.path.exists(icon_path):
            from PyQt6.QtGui import QIcon
            self.setWindowIcon(QIcon(icon_path))
        self._build_ui()
        self._load_from_config()

    @classmethod
    def _field(cls, label: str, widget, hint: str = "") -> QVBoxLayout:
        col = QVBoxLayout(); col.setSpacing(4)
        lbl = QLabel(label); lbl.setObjectName("fieldLabel")
        col.addWidget(lbl); col.addWidget(widget)
        if hint:
            col.addWidget(cls._hint(hint))
        return col

    @staticmethod
    def _hint(text: str) -> QLabel:
        h = QLabel(text); h.setObjectName("hint"); h.setWordWrap(True)
        return h

    def _sep(self) -> QFrame:
        f = QFrame(); f.setObjectName("sep"); f.setFixedHeight(1)
        return f

    # ── Pages ──

    def _page_connection(self) -> QWidget:
        p = QWidget(); lay = QVBoxLayout(p)
        lay.setContentsMargins(24, 20, 24, 12); lay.setSpacing(10)

        t = QLabel("Подключение"); t.setObjectName("pageTitle"); lay.addWidget(t)

        self.provider_combo = QComboBox()
        for k, v in PROVIDERS.items():
            self.provider_combo.addItem(v["name"], k)
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        lay.addLayout(self._field("Провайдер", self.provider_combo))

        self.model_combo = QComboBox()
        lay.addLayout(self._field("Модель", self.model_combo))

        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)

        # Подпись слева, ссылка "Показать" справа — как в примере.
        key_head = QHBoxLayout(); key_head.setSpacing(8)
        kl = QLabel("API-ключ"); kl.setObjectName("fieldLabel")
        key_head.addWidget(kl); key_head.addStretch()
        self.key_reveal_btn = QPushButton("Показать")
        self.key_reveal_btn.setObjectName("linkBtn")
        self.key_reveal_btn.setFlat(True)
        self.key_reveal_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.key_reveal_btn.clicked.connect(self._toggle_key_visibility)
        key_head.addWidget(self.key_reveal_btn)

        # Описание + кликабельная ссылка на личный кабинет провайдера.
        self.api_key_hint = QLabel("")
        self.api_key_hint.setObjectName("hint")
        self.api_key_hint.setWordWrap(True)
        self.api_key_hint.setTextFormat(Qt.TextFormat.RichText)
        self.api_key_hint.setOpenExternalLinks(True)
        self.api_key_hint.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
        )

        kc = QVBoxLayout(); kc.setSpacing(4)
        kc.addLayout(key_head); kc.addWidget(self.api_key_edit)
        kc.addWidget(self.api_key_hint)
        lay.addLayout(kc)

        self.proxy_check = QCheckBox("Использовать прокси")
        lay.addWidget(self.proxy_check)
        self.proxy_edit = QLineEdit()
        self.proxy_edit.setPlaceholderText("socks5://host:port  или http://host:port")
        lay.addLayout(self._field("Прокси", self.proxy_edit))
        self.proxy_check.toggled.connect(self.proxy_edit.setEnabled)

        # ── Проверка подключения ──
        check_row = QHBoxLayout(); check_row.setSpacing(10)
        self.check_btn = QPushButton("🔌  Проверить подключение")
        self.check_btn.setObjectName("secondary")
        self.check_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.check_btn.clicked.connect(self._on_check_connection)
        check_row.addWidget(self.check_btn)
        check_row.addStretch()
        lay.addLayout(check_row)

        self.check_result = QLabel("")
        self.check_result.setObjectName("hint")
        self.check_result.setWordWrap(True)
        lay.addWidget(self.check_result)

        lay.addStretch(); return p

    def _page_speech(self) -> QWidget:
        p = QWidget(); lay = QVBoxLayout(p)
        lay.setContentsMargins(24, 20, 24, 12); lay.setSpacing(14)

        t = QLabel("Распознавание"); t.setObjectName("pageTitle"); lay.addWidget(t)

        # ── Язык и режим — в одну строку ──
        self.language_combo = QComboBox()
        for code, name in LANGUAGES.items():
            self.language_combo.addItem(f"{name} ({code})", code)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Транскрипция", "transcribe")
        self.mode_combo.addItem("Перевод → English", "translate")

        top = QHBoxLayout(); top.setSpacing(16)
        top.addLayout(self._field("Язык", self.language_combo), 1)
        top.addLayout(self._field("Режим", self.mode_combo), 1)
        lay.addLayout(top)

        # ── Подсказка модели + счётчик символов ──
        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlaceholderText("Контекст для модели…")
        self.prompt_edit.setFixedHeight(76)
        self.prompt_edit.textChanged.connect(self._on_prompt_changed)

        self.prompt_counter = QLabel(); self.prompt_counter.setObjectName("counter")
        prompt_head = QHBoxLayout(); prompt_head.setSpacing(8)
        pl = QLabel("Подсказка модели"); pl.setObjectName("fieldLabel")
        prompt_head.addWidget(pl); prompt_head.addStretch()
        prompt_head.addWidget(self.prompt_counter)

        prompt_col = QVBoxLayout(); prompt_col.setSpacing(4)
        prompt_col.addLayout(prompt_head); prompt_col.addWidget(self.prompt_edit)
        lay.addLayout(prompt_col)

        # ── Пауза для отсечки фразы — слайдер вместо счётчика ──
        self.silence_slider = QSlider(Qt.Orientation.Horizontal)
        self.silence_slider.setRange(500, 5000)
        self.silence_slider.setSingleStep(100)
        self.silence_slider.setPageStep(500)
        self.silence_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.silence_slider.valueChanged.connect(self._on_silence_changed)

        self.silence_value = QLabel(); self.silence_value.setObjectName("sliderValue")
        self.silence_value.setFixedWidth(52)
        self.silence_value.setAlignment(Qt.AlignmentFlag.AlignRight
                                        | Qt.AlignmentFlag.AlignVCenter)

        silence_row = QHBoxLayout(); silence_row.setSpacing(12)
        silence_row.addWidget(self.silence_slider, 1)
        silence_row.addWidget(self.silence_value)

        silence_col = QVBoxLayout(); silence_col.setSpacing(4)
        sl = QLabel("Пауза для отсечки фразы"); sl.setObjectName("fieldLabel")
        silence_col.addWidget(sl); silence_col.addLayout(silence_row)
        silence_col.addWidget(self._hint(
            "Сколько тишины считать концом фразы. "
            "Только для непрерывного режима — он включается из трея."))
        lay.addLayout(silence_col)

        # ── Качество записи — сегментированный переключатель ──
        seg = QFrame(); seg.setObjectName("segmented")
        seg_lay = QHBoxLayout(seg)
        seg_lay.setContentsMargins(3, 3, 3, 3); seg_lay.setSpacing(2)
        self.bitrate_group = QButtonGroup(self)
        self.bitrate_group.setExclusive(True)
        for br, _desc in _BITRATES:
            b = QPushButton(f"{br} кб/с"); b.setObjectName("segBtn")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            self.bitrate_group.addButton(b, br)
            seg_lay.addWidget(b)
        self.bitrate_group.idToggled.connect(self._on_bitrate_changed)

        seg_row = QHBoxLayout(); seg_row.addWidget(seg); seg_row.addStretch()

        self.bitrate_hint = self._hint("")
        quality_col = QVBoxLayout(); quality_col.setSpacing(4)
        ql = QLabel("Качество записи"); ql.setObjectName("fieldLabel")
        quality_col.addWidget(ql); quality_col.addLayout(seg_row)
        quality_col.addWidget(self.bitrate_hint)
        lay.addLayout(quality_col)

        lay.addStretch(); return p

    # ── Реакции полей страницы «Распознавание» ──

    def _on_prompt_changed(self) -> None:
        text = self.prompt_edit.toPlainText()
        if len(text) > _PROMPT_MAX:
            # Обрезаем молча, курсор возвращаем в конец — иначе он прыгает в начало.
            self.prompt_edit.blockSignals(True)
            self.prompt_edit.setPlainText(text[:_PROMPT_MAX])
            self.prompt_edit.blockSignals(False)
            cursor = self.prompt_edit.textCursor()
            cursor.setPosition(_PROMPT_MAX)
            self.prompt_edit.setTextCursor(cursor)
            text = text[:_PROMPT_MAX]
        self.prompt_counter.setText(f"{len(text)}  /  {_PROMPT_MAX}")

    def _on_silence_changed(self, value: int) -> None:
        snapped = round(value / 100) * 100
        if snapped != value:
            self.silence_slider.setValue(snapped)   # рекурсия обрывается: значения совпадут
            return
        self.silence_value.setText(f"{snapped / 1000:.1f}".replace(".", ",") + " с")

    def _on_bitrate_changed(self, br: int, checked: bool) -> None:
        if checked:
            self.bitrate_hint.setText(dict(_BITRATES).get(br, ""))

    def _bitrate(self) -> int:
        br = self.bitrate_group.checkedId()
        return br if br > 0 else 32

    def _page_controls(self) -> QWidget:
        p = QWidget(); lay = QVBoxLayout(p)
        lay.setContentsMargins(24, 20, 24, 12); lay.setSpacing(10)

        t = QLabel("Управление"); t.setObjectName("pageTitle"); lay.addWidget(t)

        from ui.hotkey_recorder import HotkeyRecorderButton
        self.hotkey_btn = HotkeyRecorderButton()
        self.hotkey_btn.hotkey_recorded.connect(self._on_hotkey_recorded)
        lay.addLayout(self._field("Горячая клавиша 1", self.hotkey_btn,
                                  "Основной хоткей (клавиатура или мышь)."))

        self.hotkey2_btn = HotkeyRecorderButton()
        self.hotkey2_btn.hotkey_recorded.connect(self._on_hotkey2_recorded)
        lay.addLayout(self._field("Горячая клавиша 2", self.hotkey2_btn,
                                  "Дополнительный хоткей (необязательно)."))

        lay.addWidget(self._sep())

        sh = QLabel("Звук и уведомления"); sh.setObjectName("sectionHead"); lay.addWidget(sh)
        self.sound_check = QCheckBox("Звуковой сигнал при записи")
        lay.addWidget(self.sound_check)

        self.overlay_check = QCheckBox("Индикатор записи на экране")
        lay.addWidget(self.overlay_check)

        from core.sounds import THEMES
        self.theme_combo = QComboBox()
        for key, (label, _) in THEMES.items():
            self.theme_combo.addItem(label, key)
        lay.addLayout(self._field("Тема звуков", self.theme_combo))

        lay.addWidget(self._sep())

        sh2 = QLabel("Система"); sh2.setObjectName("sectionHead"); lay.addWidget(sh2)
        self.autostart_check = QCheckBox("Запускать при старте Windows")
        lay.addWidget(self.autostart_check)

        lay.addStretch(); return p

    # ── Main layout ──

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        # Sidebar
        sb_wrap = QWidget(); sb_wrap.setObjectName("sidebarWrap")
        sb_wrap.setFixedWidth(180)
        sb_lay = QVBoxLayout(sb_wrap)
        sb_lay.setContentsMargins(0, 0, 0, 0); sb_lay.setSpacing(0)

        name = QLabel("Pishper"); name.setObjectName("appName"); sb_lay.addWidget(name)

        self.sidebar = QListWidget(); self.sidebar.setObjectName("sidebar")
        for icon, text in [("🔌", "Подключение"), ("🎙️", "Распознавание"), ("⌨️", "Управление")]:
            it = QListWidgetItem(f"{icon}  {text}")
            it.setSizeHint(QSize(0, 36))
            self.sidebar.addItem(it)
        sb_lay.addWidget(self.sidebar)

        sb_lay.addStretch()

        # Buttons in sidebar bottom
        bb = QVBoxLayout(); bb.setContentsMargins(12, 0, 12, 12); bb.setSpacing(6)
        help_btn = QPushButton("❓ Инструкция"); help_btn.setObjectName("secondary")
        help_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        help_btn.clicked.connect(self._show_help)
        bb.addWidget(help_btn)
        save = QPushButton("Сохранить"); save.setObjectName("primary")
        save.setCursor(Qt.CursorShape.PointingHandCursor); save.clicked.connect(self._on_save)
        cancel = QPushButton("Отмена"); cancel.setObjectName("secondary")
        cancel.setCursor(Qt.CursorShape.PointingHandCursor); cancel.clicked.connect(self.reject)
        bb.addWidget(save); bb.addWidget(cancel)
        sb_lay.addLayout(bb)

        root.addWidget(sb_wrap)

        # Content
        self.stack = QStackedWidget()
        self.stack.addWidget(self._page_connection())
        self.stack.addWidget(self._page_speech())
        self.stack.addWidget(self._page_controls())
        root.addWidget(self.stack)

        self.sidebar.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.sidebar.setCurrentRow(0)

    # ── Data ↔ UI ──

    def _on_provider_changed(self, _i: int) -> None:
        key = self.provider_combo.currentData()
        prov = PROVIDERS.get(key, PROVIDERS["groq"])
        self.api_key_edit.setPlaceholderText(prov["key_hint"])
        self.api_key_hint.setText(self._key_hint_html(prov))
        self.model_combo.clear()
        for mid, mname in prov["models"]:
            self.model_combo.addItem(mname, mid)
        # Save current key to dict before switching
        if hasattr(self, '_current_provider') and self._current_provider:
            self.config.api_keys[self._current_provider] = self.api_key_edit.text().strip()
        self._current_provider = key
        # Load key for new provider
        self.api_key_edit.setText(self.config.api_keys.get(key, ""))

    @staticmethod
    def _key_hint_html(prov: dict) -> str:
        """Описание ключа + ссылка на личный кабинете провайдера."""
        url = prov.get("key_url", "")
        desc = prov.get("key_desc", "")
        if not url:
            return desc
        href = url if url.startswith(("http://", "https://")) else f"https://{url}"
        link = (
            f'<a href="{href}" style="color:#1a73e8; text-decoration:none;">'
            f'{url} ↗</a>'
        )
        return f"{desc} {link}" if desc else link

    def _toggle_key_visibility(self) -> None:
        hidden = self.api_key_edit.echoMode() == QLineEdit.EchoMode.Password
        self.api_key_edit.setEchoMode(
            QLineEdit.EchoMode.Normal if hidden else QLineEdit.EchoMode.Password
        )
        self.key_reveal_btn.setText("Скрыть" if hidden else "Показать")

    def _load_from_config(self) -> None:
        self._current_provider = None  # prevent saving during load
        idx = self.provider_combo.findData(self.config.provider)
        if idx >= 0: self.provider_combo.setCurrentIndex(idx)
        self._on_provider_changed(0)
        idx = self.model_combo.findData(self.config.model)
        if idx >= 0: self.model_combo.setCurrentIndex(idx)
        self.api_key_edit.setText(self.config.active_api_key)
        self._current_provider = self.config.provider
        self.proxy_edit.setText(self.config.proxy)
        self.proxy_check.setChecked(self.config.proxy_enabled)
        self.proxy_edit.setEnabled(self.config.proxy_enabled)
        idx = self.language_combo.findData(self.config.language)
        if idx >= 0: self.language_combo.setCurrentIndex(idx)
        idx = self.mode_combo.findData(self.config.mode)
        if idx >= 0: self.mode_combo.setCurrentIndex(idx)
        self.prompt_edit.setPlainText(self.config.prompt)
        self.silence_slider.setValue(self.config.silence_timeout_ms)
        self._on_silence_changed(self.silence_slider.value())
        btn = self.bitrate_group.button(self.config.mp3_bitrate)
        (btn or self.bitrate_group.button(32)).setChecked(True)
        self._on_bitrate_changed(self._bitrate(), True)
        self.hotkey_btn.set_hotkey_text(self.config.hotkey_display or self.config.hotkey)
        self._pending_hotkey = self.config.hotkey
        self._pending_hotkey_display = self.config.hotkey_display
        self._pending_hotkey_vk = self.config.hotkey_vk
        self.hotkey2_btn.set_hotkey_text(self.config.hotkey2_display or self.config.hotkey2 or "")
        self._pending_hotkey2 = self.config.hotkey2
        self._pending_hotkey2_display = self.config.hotkey2_display
        self._pending_hotkey2_vk = self.config.hotkey2_vk
        self.sound_check.setChecked(self.config.sound_enabled)
        self.overlay_check.setChecked(self.config.show_overlay)
        idx = self.theme_combo.findData(self.config.sound_theme)
        if idx >= 0: self.theme_combo.setCurrentIndex(idx)
        self.autostart_check.setChecked(self.config.autostart)

    # ── Проверка подключения ──

    def _form_config(self) -> AppConfig:
        """Конфиг из текущих полей формы — проверяем то, что видит пользователь,
        а не то, что сохранено на диске."""
        provider = self.provider_combo.currentData()
        return AppConfig(
            provider=provider,
            model=self.model_combo.currentData() or self.config.model,
            api_keys={provider: self.api_key_edit.text().strip()},
            language=self.language_combo.currentData(),
            mode="transcribe",     # проверке хватает транскрипции
            prompt="",
            proxy=self.proxy_edit.text().strip(),
            proxy_enabled=self.proxy_check.isChecked(),
            mp3_bitrate=self._bitrate(),
        )

    def _on_check_connection(self) -> None:
        self.check_btn.setEnabled(False)
        self.check_btn.setText("⏳  Проверяю…")
        self.check_result.setObjectName("hint")
        self.check_result.setStyleSheet("")
        self.check_result.setText("Отправляю короткий тестовый запрос…")

        # Ссылка на воркер живёт в диалоге: иначе его соберёт GC до ответа.
        self._check_worker = _ConnectionCheckWorker(self._form_config())
        self._check_worker.done.connect(self._on_check_done)
        self._check_worker.start()

    _CHECK_STYLES = {
        "ok":   ("checkOk", "✓  "),
        "warn": ("checkWarn", "⚠  "),
        "fail": ("checkFail", "✗  "),
    }

    def _on_check_done(self, status: str, message: str) -> None:
        self.check_btn.setEnabled(True)
        self.check_btn.setText("🔌  Проверить подключение")
        obj_name, prefix = self._CHECK_STYLES.get(status, self._CHECK_STYLES["fail"])
        self.check_result.setObjectName(obj_name)
        self.check_result.setText(prefix + message)
        # Пересобрать стиль после смены objectName
        self.check_result.style().unpolish(self.check_result)
        self.check_result.style().polish(self.check_result)

    def _on_hotkey_recorded(self, display: str, pynput_str: str, vk_code: int) -> None:
        self._pending_hotkey = pynput_str
        self._pending_hotkey_display = display
        self._pending_hotkey_vk = vk_code

    def _on_hotkey2_recorded(self, display: str, pynput_str: str, vk_code: int) -> None:
        self._pending_hotkey2 = pynput_str
        self._pending_hotkey2_display = display
        self._pending_hotkey2_vk = vk_code

    def _on_save(self) -> None:
        self.config.provider = self.provider_combo.currentData()
        self.config.model = self.model_combo.currentData() or self.config.model
        # Save current key into per-provider dict
        current_key = self.api_key_edit.text().strip()
        self.config.api_keys[self.config.provider] = current_key
        self.config.api_key = current_key  # legacy compat
        self.config.language = self.language_combo.currentData()
        self.config.mode = self.mode_combo.currentData()
        self.config.prompt = self.prompt_edit.toPlainText().strip()
        self.config.silence_timeout_ms = self.silence_slider.value()
        self.config.mp3_bitrate = self._bitrate()
        self.config.proxy = self.proxy_edit.text().strip()
        self.config.proxy_enabled = self.proxy_check.isChecked()
        self.config.sound_enabled = self.sound_check.isChecked()
        self.config.show_overlay = self.overlay_check.isChecked()
        self.config.sound_theme = self.theme_combo.currentData() or "spring"
        self.config.autostart = self.autostart_check.isChecked()
        if hasattr(self, "_pending_hotkey") and self._pending_hotkey:
            self.config.hotkey = self._pending_hotkey
            self.config.hotkey_display = self._pending_hotkey_display
            self.config.hotkey_vk = getattr(self, "_pending_hotkey_vk", 0)
        if hasattr(self, "_pending_hotkey2"):
            self.config.hotkey2 = self._pending_hotkey2 or ""
            self.config.hotkey2_display = self._pending_hotkey2_display or ""
            self.config.hotkey2_vk = getattr(self, "_pending_hotkey2_vk", 0)
        self.config.save()
        # Apply theme immediately
        from core.sounds import set_theme
        set_theme(self.config.sound_theme)
        # Update Windows autostart
        from core.autostart import set_autostart
        set_autostart(self.config.autostart)
        self.accept()

    def _show_help(self) -> None:
        from ui.welcome import WelcomeDialog
        WelcomeDialog(self, first_run=False).exec()
