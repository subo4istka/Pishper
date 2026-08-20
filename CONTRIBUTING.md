# Contributing to Pishper

Спасибо за интерес к проекту! / Thanks for your interest!

Issues и pull request'ы принимаются на русском и на английском — пишите на том
языке, который вам удобнее. Issues and pull requests are accepted in Russian or
English, whichever you prefer.

## Getting set up

```bash
git clone https://github.com/subo4istka/Pishper.git
cd Pishper
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
python main.py
```

Sanity-check the environment before you start digging:

```bash
python tools/diagnostics/check_imports.py
```

There is no automated test suite. `tools/diagnostics/` holds small scripts that
each verify one moving part (imports, PyQt startup, clipboard round-trip, sound
playback) — useful when a PyInstaller build misbehaves.

## What helps most

- **macOS / Linux support.** The audio, HTTP and UI layers are portable; hotkeys
  (`main.py`), text insertion (`core/typer.py`) and autostart
  (`core/autostart.py`) are Win32-specific and need platform backends.
- **UI localisation.** All strings are currently inline Russian literals. Extracting
  them and adding a language switch is a self-contained, high-value change.
- **New recognition providers.** Add an entry to `PROVIDERS` in `core/config.py`
  and a `_transcribe_*` function in `core/transcriber.py` — the existing four are
  the pattern to follow.

## Screenshots

`docs/screenshots/` is generated, not hand-captured:

```bash
python tools/make_screenshots.py
```

The script grabs the widgets with a synthetic config, so the images stay in sync
with the UI and never carry anyone's API key or proxy credentials. Re-run it when
you change the settings window, and commit the result.

## Releasing

The `.exe` attached to a release is built locally and launched at least once
before it is uploaded. CI builds the same thing on every tag, but its artifact is
never published: a green build only proves PyInstaller finished, not that the
binary starts. A bundle whose DLLs were mangled by `strip` builds without a
complaint and then dies on `LoadLibrary` — and the runner *has* `strip` (Git for
Windows ships one) while a typical dev box does not, so the difference only shows
up in what you publish. Hence `strip=False` and `upx=False` in `Pishper.spec`;
leave them off.

```bash
pyinstaller Pishper.spec --noconfirm
dist\Pishper.exe                        # it must actually come up in the tray
gh release create v2 dist\Pishper.exe --notes-file notes.md
```

## Code style

Match the surrounding code rather than a linter:

- 4 spaces, ~100 column soft limit, type hints on function signatures.
- Docstrings on modules, classes and non-obvious functions.
- Comments explain *why*, not *what* — especially where a workaround exists.
  If you remove one of those workarounds, check the comment first: several of
  them document real bugs that took a while to find.
- Section dividers (`# ── name ──`) are used to group related code; keep them
  consistent within a file.

## Pull requests

1. One logical change per PR — keep unrelated refactors out.
2. Describe what you changed and how you verified it manually (this is a GUI app,
   so "clicked X, saw Y" is a legitimate test report).
3. Never commit secrets. API keys belong in `%USERPROFILE%\.pishper\config.json`,
   never in the repository — not even in a throwaway script.
4. Don't commit build output (`build/`, `dist/`) or local backups; `.gitignore`
   already covers them.

## Reporting bugs

Include: Windows version, how you run Pishper (`.exe` or from source), the
provider and model, what you expected, and what happened. If the app was started
from source, the console output is usually the fastest way to a diagnosis — it
logs hotkey registration, API timings and full tracebacks.

Please don't paste your API key into an issue. Redact it.
