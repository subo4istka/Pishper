"""Welcome / help dialog — shown on first launch or via Settings → Help (pre-Fluent version)."""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton, QScrollArea, QWidget,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


_STYLE = """
* { background: #ffffff; color: #1a1a1a; }
QDialog { background: #ffffff; }
QScrollArea { background: #ffffff; border: none; }
QScrollBar:vertical {
    background: #f0f0f0; width: 8px; border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #ccc; border-radius: 4px; min-height: 30px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QLabel {
    background: transparent; color: #1a1a1a;
}
QLabel#title {
    font-size: 22px; font-weight: 700; color: #1a1a1a;
    background: transparent; padding: 0 0 4px 0;
}
QLabel#subtitle {
    font-size: 13px; color: #5f6368;
    background: transparent; padding: 0 0 10px 0;
}
QLabel#section {
    font-size: 15px; font-weight: 600; color: #1a73e8;
    background: transparent; padding: 10px 0 2px 0;
}
QLabel#body {
    font-size: 13px; color: #333333;
    background: transparent; line-height: 1.5;
}
QPushButton#primary {
    background: #1a73e8; color: #ffffff; border: none; border-radius: 6px;
    padding: 10px 28px; font-size: 14px; font-weight: 500;
}
QPushButton#primary:hover { background: #1765cc; color: #ffffff; }
"""


class WelcomeDialog(QDialog):
    """Shows a concise overview of Pishper for new users."""

    def __init__(self, parent=None, first_run: bool = True):
        super().__init__(parent)
        self.setWindowTitle("Pishper — Добро пожаловать")
        self.setFixedSize(480, 520)
        self.setStyleSheet(_STYLE)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint)
        import os
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "icon.png")
        if os.path.exists(icon_path):
            from PyQt6.QtGui import QIcon
            self.setWindowIcon(QIcon(icon_path))
        self._build_ui(first_run)

    def _build_ui(self, first_run: bool) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(0)

        # Title
        title = QLabel("👋 Добро пожаловать в Pishper!")
        title.setObjectName("title")
        root.addWidget(title)

        sub = QLabel("Голосовой ввод текста — говорите, а программа печатает за вас.")
        sub.setObjectName("subtitle")
        sub.setWordWrap(True)
        root.addWidget(sub)

        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")

        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(0, 0, 12, 0)
        lay.setSpacing(0)

        sections = [
            ("🚀 Как начать", (
                "1. Откройте <b>Настройки</b> → <b>Подключение</b>\n"
                "2. Выберите провайдер и вставьте API-ключ\n"
                "3. Перейдите в <b>Управление</b> → назначьте горячую клавишу\n"
                "4. Нажмите «Сохранить»"
            )),
            ("🎤 Как пользоваться", (
                "• Нажмите горячую клавишу — услышите звуковой сигнал\n"
                "• Говорите в микрофон\n"
                "• Нажмите горячую клавишу ещё раз — текст появится\n"
                "  в том месте, где стоит курсор\n"
                "• <b>Escape</b> — отмена записи"
            )),
            ("⌨️ Горячие клавиши", (
                "• По умолчанию: <b>Ctrl + Shift + Пробел</b>\n"
                "• Можно назначить любую клавишу или кнопку мыши\n"
                "• Настраивается в <b>Настройки → Управление</b>"
            )),
            ("🔄 Режимы работы", (
                "• <b>Транскрипция</b> — речь → текст на вашем языке\n"
                "• <b>Перевод</b> — речь → текст на английском\n"
                "• <b>Непрерывный режим</b> — программа сама определяет\n"
                "  паузы и печатает фразы одну за другой\n"
                "• <b>Автоотправка (Enter)</b> — включается в меню трея,\n"
                "  автоматически нажимает Enter после ввода текста.\n"
                "  Удобно для мессенджеров и чатов!"
            )),
            ("💡 Полезные советы", (
                "• Программа живёт в <b>системном трее</b> (▲ внизу справа)\n"
                "• Правый клик по иконке → меню с настройками\n"
                "• Работает с любым приложением, где можно вставить текст"
            )),
        ]

        for header, body in sections:
            h = QLabel(header)
            h.setObjectName("section")
            lay.addWidget(h)

            b = QLabel(body.replace("\n", "<br>"))
            b.setObjectName("body")
            b.setWordWrap(True)
            b.setTextFormat(Qt.TextFormat.RichText)
            lay.addWidget(b)

        lay.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll)

        # Button
        root.addSpacing(12)
        btn_text = "Начать работу" if first_run else "Закрыть"
        btn = QPushButton(btn_text)
        btn.setObjectName("primary")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self.accept)
        root.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)
