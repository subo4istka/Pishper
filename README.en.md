<div align="center">

<img src="assets/icon.png" width="128" alt="Pishper">

# Pishper

**Voice typing for Windows. Press a key, speak, and the text appears wherever your cursor is.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-0078D4)](#requirements)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB)](#building-from-source)
[![Release](https://img.shields.io/github/v/release/subo4istka/Pishper?include_prereleases)](https://github.com/subo4istka/Pishper/releases/latest)

[Русский](README.md) · [Download](#installation) · [Settings](#settings) · [Build](#building-from-source)

</div>

> **Note on language:** the application's user interface is currently in Russian
> only. Speech recognition itself works in 16 languages. UI localisation is a
> welcome contribution — see [Contributing](#contributing).

---

## What it is

Pishper lives in the system tray and has no main window. You work in any
application — browser, editor, messenger — press a hotkey, speak, press it
again. The recognised text is inserted straight into the focused input field,
exactly as if you had typed it.

Recognition runs in the cloud (OpenAI Whisper, Groq, Deepgram or GigaChat), so
there is no local model to download: the app is tens of megabytes rather than
gigabytes and runs on any laptop without a GPU.

**Why bother:** dictating is 3–4× faster than typing. Long messages, commit
messages, AI prompts, support replies, document drafts — all faster spoken.

## Features

| | |
|---|---|
| 🎙️ **Push-to-talk** | Press, speak, press again — text is inserted. `Escape` cancels the recording. |
| 🔄 **Continuous mode** | The mic stays open and a built-in VAD finds phrase boundaries, sending each phrase as soon as it ends. Ideal for long dictation. |
| ⌨️ **Any hotkey** | A combination (`Ctrl+Shift+Space`), a single key (e.g. `` ` `` — captured by a low-level Win32 hook so it never leaks into your text), or a side mouse button. **Two** independent hotkeys can be bound. |
| 🌍 **16 languages** | Russian, English, German, French, Spanish, Italian, Portuguese, Japanese, Chinese, Korean, Ukrainian, Polish, Turkish, Arabic, plus a "Russian + English" mode for speech mixing both. |
| 🔁 **Translate to English** | Tray toggle: transcribe as spoken, or translate to English on the fly. |
| 🔌 **4 providers** | OpenAI, Groq, Deepgram, GigaChat — each key is stored separately, switching is instant. |
| 🎚️ **Low bandwidth** | Audio is encoded to MP3 at 16/32/64 kbps on the fly: a minute of speech is ~240 KB instead of 2 MB of WAV. Works on slow mobile connections. |
| 🔊 **Sound themes** | Six sets of start/stop/cancel cues (Spring, Minimal, Bubbles, Space, Soft, Tick) — or complete silence. |
| 📊 **Recording indicator** | A translucent overlay with a live input level, so you can see the mic is hearing you. |
| ✏️ **Text replacements** | Your own substitution dictionary: when the model insists on "Jason" instead of "JSON", fix it once in settings. |
| 🧹 **Hallucination filter** | Whisper likes to invent "Subscribe to the channel" and "Subtitles by…" on silence — those phrases are dropped. |
| 🌐 **Proxy** | HTTP/SOCKS proxy with its own toggle: the URL is kept even while the proxy is off. |
| ⏎ **Auto-send** | Optionally press `Enter` after inserting — dictate a chat message and it sends itself. |
| 🚀 **Autostart** | One switch to register in Windows startup. |

## Installation

### Prebuilt .exe (recommended)

1. Download `Pishper.exe` from the [Releases](https://github.com/subo4istka/Pishper/releases/latest) page.
2. Run it. No installer — it is a single self-contained file, no Python needed.
3. A welcome window with a short guide opens on first launch.
4. Open **Настройки → Подключение** (Settings → Connection), pick a provider and
   paste your API key.

> **SmartScreen.** The binary is not code-signed (a certificate costs $200+/year),
> so Windows will warn you. Click "More info" → "Run anyway". If you would rather
> not trust the build, [compile your own](#building-from-source) from this source.

### Getting an API key

| Provider | Key | Models | Notes |
|---|---|---|---|
| **Groq** | [console.groq.com/keys](https://console.groq.com/keys) | Whisper Large V3 Turbo / V3 / Distil EN | Free tier, sign-up takes a couple of clicks, fastest transcription. **Best starting point.** |
| **Deepgram** | [console.deepgram.com](https://console.deepgram.com) | Nova-3, Nova-2 | Free starting credits. Nova-3 does code-switching — two languages in one phrase. |
| **OpenAI** | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) | Whisper v1 | Requires an account with a funded balance. |
| **GigaChat** | [developers.sber.ru/studio](https://developers.sber.ru/studio) | GigaChat-2 Pro / Max, GigaChat Pro / Max | Russian service, reachable without a VPN. Needs the Authorization Data from a GigaChat API project. |

Keys are stored locally in `%USERPROFILE%\.pishper\config.json` and are never
sent anywhere except the provider you selected.

## Usage

| Action | How |
|---|---|
| Record and insert | Hotkey → speak → hotkey again |
| Cancel recording | `Escape` |
| Continuous mode | Tray menu → **🔄 Непрерывный режим** |
| Translate instead of transcribe | Tray menu → **Перевод → English** |
| Copy the last phrase | Tray menu → **📋 Последняя фраза** |
| Auto-press `Enter` | Tray menu → **⏎ Автоотправка** |

Text is inserted through the clipboard (`Ctrl+V` at the Win32 level), so it works
in every application, including those where per-character key emulation breaks.
The previous clipboard contents are restored afterwards.

## Settings

Settings open from the tray menu and are split into three pages.

**Подключение (Connection)** — provider, API key, model, proxy, and a "test
connection" button that sends a short request and reports the real latency, so
you are not left guessing why nothing works.

**Распознавание (Recognition)** — language, mode (transcribe / translate), model
prompt (up to 400 characters — sets punctuation style and term spelling), silence
timeout for continuous mode (0.5–5 s), recording quality (MP3 bitrate).

**Управление (Controls)** — hotkey binding (click the button, then just press the
key or mouse button you want), sound theme, recording overlay, autostart, and the
replacement dictionary.

Usage statistics (session count and total recorded minutes) are written to
`%USERPROFILE%\.pishper\stats.txt`.

## How it works

```
hotkey (pynput / Win32 LL hook)
        │
        ▼
mic 16 kHz mono int16 ──► lameenc ──► MP3 16/32/64 kbps
        │                                   │
        │  continuous mode: RMS-based VAD,   ▼
        │  400 ms pre-roll, silence cut-off  HTTP (httpx / openai SDK)
        │                                   │
        │                                   ▼
        │                    Whisper / Nova / GigaChat API
        │                                   │
        ▼                                   ▼
  overlay + sounds        hallucination filter → replacements
                                              │
                                              ▼
                          clipboard + Ctrl+V into the active window
```

Design decisions worth knowing if you read the code:

- **Transcription queue.** A dedicated worker thread drains the queue strictly in
  order, so in continuous mode phrases never get shuffled even when the API
  responds out of order.
- **Low-level hook.** A single-key hotkey is captured via `WH_KEYBOARD_LL` on a
  dedicated thread with its own message pump, so the trigger key never leaks into
  the text being typed. The hook callback only sets an event flag — all real work
  happens on another thread, otherwise Windows unhooks a "slow" hook.
- **MP3 instead of WAV.** Encoding happens on the fly, and `lameenc` returns real
  `bytes`, not a `bytearray`: `httpx` classifies a `bytearray` as an iterable and
  switches to chunked transfer with one byte per chunk — that was a 9× upload
  slowdown.
- **Retries and human errors.** `core/errors.py` classifies failures (network,
  timeout, rate limit, bad key, server), honours `Retry-After`, retries twice and
  shows a readable message instead of a traceback. Identical errors are not
  re-notified more than once per 20 seconds.

### Project layout

```
main.py                  orchestrator: hooks, job queue, state
core/config.py           settings (dataclass ↔ JSON), providers, languages
core/recorder.py         push-to-talk recording → MP3
core/continuous.py       continuous mode with VAD
core/transcriber.py      four provider APIs, hallucination filter
core/errors.py           error classification and retries
core/typer.py            text insertion via the Win32 clipboard
core/sounds.py           sound themes (synthesised in code, no audio files)
core/autostart.py        Windows startup via the registry
core/stats.py            usage statistics
ui/tray.py               tray icon and menu
ui/settings_window.py    settings window
ui/hotkey_recorder.py    hotkey capture
ui/overlay.py            recording overlay with input level
ui/welcome.py            welcome window
tools/diagnostics/       environment checks for debugging builds
```

## Building from source

Requires Windows 10/11 and Python 3.10+ (release builds use 3.14).

```bash
git clone https://github.com/subo4istka/Pishper.git
cd Pishper
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Build the standalone `.exe`:

```bash
pip install -r requirements-dev.txt
pyinstaller Pishper.spec --noconfirm
```

The result lands in `dist\Pishper.exe` (~60 MB). The spec file is already tuned: unused
PyQt6 modules and heavy scientific libraries are excluded, `optimize=2` is on,
and `certifi` TLS roots plus `pynput` platform backends are bundled. If
[UPX](https://upx.github.io/) is on your PATH it is picked up automatically to
shrink the binary.

The spec asks for `strip` and `upx`, neither of which ships with Windows:
PyInstaller prints a `FileNotFoundError: [WinError 2]` traceback, carries on and
exits 0. That is expected — the build is valid.

Verify the environment before building:

```bash
python tools/diagnostics/check_imports.py
```

## Requirements

- Windows 10 or 11 (the project leans heavily on Win32 APIs: hooks, clipboard, registry)
- A microphone
- Internet access and an API key from one of the providers
- Python 3.10+ to run from source

## Privacy

- Audio is sent only to the provider you chose and only for the duration of the
  request; nothing is stored locally.
- API keys, settings and statistics live in `%USERPROFILE%\.pishper\` and are
  never transmitted.
- The app contains no telemetry, no analytics and no auto-update.
- For request-retention policies check your provider — OpenAI, Groq, Deepgram
  and GigaChat all differ.

## Troubleshooting

**The hotkey does nothing.** Another app may own it (some IDEs grab
`Ctrl+Shift+Space`). Bind a different one under **Настройки → Управление**. If
the target window runs as administrator, Windows will not deliver input to it
from a normal process — run Pishper as administrator too.

**Text is not inserted.** The receiving app may block clipboard paste. Check the
tray menu → **📋 Последняя фраза**: if the text is there, recognition works and
the problem is the paste.

**"Network error" while the internet works.** The provider may be unreachable
from your region — enable a proxy under **Настройки → Подключение**, or use
GigaChat. The "test connection" button shows whether requests get through.

**The wrong language is recognised.** Under **Настройки → Распознавание** the
default is Russian. For mixed technical speech pick "Русский + English".

**Random text appears on silence.** Whisper hallucinates on noise; the common
phrases are already filtered, and you can add more to
`_HALLUCINATION_PATTERNS` in [core/transcriber.py](core/transcriber.py).

## Contributing

Issues and pull requests are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).
The most valuable contributions right now: macOS/Linux support, UI localisation,
and additional recognition providers.

## License

[MIT](LICENSE) — use, modify and redistribute freely, commercial use included.

Built with [PyQt6](https://www.riverbankcomputing.com/software/pyqt/),
[sounddevice](https://python-sounddevice.readthedocs.io/),
[lameenc](https://github.com/chrisstaite/lameenc),
[pynput](https://github.com/moses-palmer/pynput) and
[httpx](https://www.python-httpx.org/).
