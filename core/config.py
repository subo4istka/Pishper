"""Application configuration management — load/save from JSON."""

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path

CONFIG_DIR = Path.home() / ".pishper"
CONFIG_FILE = CONFIG_DIR / "config.json"

# Supported languages for the Whisper API (subset of most useful ones)
LANGUAGES = {
    "ru": "Русский",
    # Deepgram Nova-3 code-switching: распознаёт русский и английский
    # вперемешку (термины, названия). Для Whisper = автоопределение языка.
    "multi": "Русский + English",
    "en": "English",
    "de": "Deutsch",
    "fr": "Français",
    "es": "Español",
    "it": "Italiano",
    "pt": "Português",
    "ja": "日本語",
    "zh": "中文",
    "ko": "한국어",
    "uk": "Українська",
    "pl": "Polski",
    "tr": "Türkçe",
    "ar": "العربية",
}

# Provider definitions
PROVIDERS = {
    "openai": {
        "name": "OpenAI",
        "base_url": None,
        "models": [
            ("whisper-1", "Whisper v1"),
        ],
        "key_hint": "sk-proj-...",
        "key_url": "platform.openai.com/api-keys",
        "key_desc": "Секретный ключ создаётся в панели OpenAI — нужен аккаунт с оплаченным балансом.",
    },
    "groq": {
        "name": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "models": [
            ("whisper-large-v3-turbo", "Whisper Large V3 Turbo (быстрая)"),
            ("whisper-large-v3", "Whisper Large V3 (качественная)"),
            ("distil-whisper-large-v3-en", "Distil Whisper EN (только English)"),
        ],
        "key_hint": "gsk_...",
        "key_url": "console.groq.com/keys",
        "key_desc": "Ключ бесплатный, создаётся в консоли Groq за пару кликов.",
    },
    "deepgram": {
        "name": "Deepgram",
        "base_url": "https://api.deepgram.com/v1",
        "models": [
            ("nova-3", "Nova 3 (новейшая)"),
            ("nova-2", "Nova 2"),
        ],
        "key_hint": "dg_...",
        "key_url": "console.deepgram.com",
        "key_desc": "Ключ выдаётся в консоли Deepgram, при регистрации даётся бесплатный лимит.",
    },
    "gigachat": {
        "name": "GigaChat",
        "base_url": "https://gigachat.devices.sberbank.ru/api/v1",
        "models": [
            ("GigaChat-2-Pro", "GigaChat-2 Pro (быстрая и точная)"),
            ("GigaChat-2-Max", "GigaChat-2 Max (флагманская)"),
            ("GigaChat-Pro", "GigaChat Pro"),
            ("GigaChat-Max", "GigaChat Max"),
        ],
        "key_hint": "MDFhM... (Authorization Data)",
        "key_url": "developers.sber.ru/studio",
        "key_desc": "Нужны Authorization Data из проекта GigaChat API в личном кабинете Sber Studio.",
    },
}


@dataclass
class AppConfig:
    """Stores all user-facing settings."""

    provider: str = "groq"             # "openai" | "groq" | "deepgram" | "gigachat"
    model: str = "whisper-large-v3-turbo"  # Whisper model ID
    api_key: str = ""                  # legacy single key (migrated to api_keys)
    api_keys: dict = None              # {"groq": "gsk_...", "deepgram": "dg_..."}
    language: str = "ru"               # ISO 639-1 code forced into Whisper
    proxy: str = ""                    # e.g. "http://127.0.0.1:8080"
    proxy_enabled: bool = False        # toggle proxy on/off without losing the URL
    mode: str = "transcribe"           # "transcribe" | "translate"
    prompt: str = "Используй правильную пунктуацию, заглавные буквы и знаки препинания."
    sound_enabled: bool = True         # play feedback sounds
    sound_theme: str = "spring"        # sound theme key
    show_overlay: bool = True          # on-screen recording indicator
    autostart: bool = True             # start with Windows
    silence_timeout_ms: int = 2000     # ms of silence to end continuous segment
    mp3_bitrate: int = 32              # MP3 encoding: 16, 32, or 64 kbps
    replacements: dict = None          # word replacements {"from": "to"}
    hotkey: str = "<ctrl>+<shift>+<space>"  # pynput-style combination
    hotkey_display: str = "Ctrl + Shift + Space"  # human-readable
    hotkey_vk: int = 0  # raw Win32 VK code (for single-key suppress)
    hotkey2: str = ""              # second hotkey (e.g. mouse button)
    hotkey2_display: str = ""
    hotkey2_vk: int = 0
    first_run_seen: bool = False   # has the user seen the welcome guide?

    def __post_init__(self):
        if self.replacements is None:
            self.replacements = {}
        if self.api_keys is None:
            self.api_keys = {}
        # Migrate legacy single api_key into api_keys dict
        if self.api_key and self.provider and self.provider not in self.api_keys:
            self.api_keys[self.provider] = self.api_key

    @property
    def active_api_key(self) -> str:
        """Return the API key for the currently selected provider."""
        return self.api_keys.get(self.provider, self.api_key or "")

    # ---- persistence ----

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls) -> "AppConfig":
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
            except Exception:
                pass
        return cls()
