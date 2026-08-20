"""Windows autostart management via Registry (works with both .py and .exe)."""

import sys
import winreg

_REG_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
_APP_NAME = "Pishper"


def _get_exe_path() -> str:
    """Return the executable path — works for both python and frozen .exe."""
    if getattr(sys, "frozen", False):
        return sys.executable  # .exe path
    return f'"{sys.executable}" "{sys.argv[0]}"'  # python script.py


def is_autostart_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_KEY, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, _APP_NAME)
            return True
    except FileNotFoundError:
        return False


def set_autostart(enable: bool) -> None:
    """Add or remove Pishper from Windows startup."""
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enable:
            winreg.SetValueEx(key, _APP_NAME, 0, winreg.REG_SZ, _get_exe_path())
        else:
            try:
                winreg.DeleteValue(key, _APP_NAME)
            except FileNotFoundError:
                pass
