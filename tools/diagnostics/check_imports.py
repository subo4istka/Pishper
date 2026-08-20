import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

try:
    print("Testing imports...")
    import PyQt6.QtWidgets
    import pynput.keyboard
    import pynput.mouse
    import httpx
    import openai
    import sounddevice as sd
    import numpy as np
    import lameenc
    print("Core imports passed.")
    
    from core.config import AppConfig
    from core.recorder import AudioRecorder
    from core.continuous import ContinuousRecorder
    from core.transcriber import transcribe
    from core.typer import type_text, send_enter
    from core.sounds import play_start, play_stop, play_cancel, set_theme
    from ui.tray import PishperTray
    from ui.settings_window import SettingsWindow
    print("Local imports passed.")
    
    print("Tests complete.")
except Exception:
    traceback.print_exc()
    sys.exit(1)
