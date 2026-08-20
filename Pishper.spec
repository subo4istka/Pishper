# -*- mode: python ; coding: utf-8 -*-
"""Optimised one-file build for Pishper."""
from PyInstaller.utils.hooks import collect_data_files

datas = [('assets', 'assets')]
datas += collect_data_files('certifi')          # TLS root certs for httpx/openai

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'lameenc',
        # pynput platform backends
        'pynput', 'pynput.keyboard', 'pynput.keyboard._win32',
        'pynput.mouse', 'pynput.mouse._win32',
        # socksio (SOCKS proxy support for httpx)
        'socksio',
        # h11 — HTTP/1.1 layer under httpx
        'h11',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # ── Heavy science/data libs (not used) ──
        'pandas', 'matplotlib', 'scipy', 'PIL', 'Pillow',
        'sklearn', 'skimage', 'sympy', 'statsmodels',
        'pyarrow', 'openpyxl', 'xlrd', 'xlsxwriter',
        # ── GUI toolkits we don't use ──
        'tkinter', '_tkinter', 'PySide6', 'wx',
        # ── Testing / dev ──
        'pytest', 'unittest', 'doctest', 'IPython', 'notebook',
        'setuptools', 'pip',
        # ── PyQt6 heavyweight modules we don't use ──
        'PyQt6.QtWebEngine', 'PyQt6.QtWebEngineCore',
        'PyQt6.QtWebEngineWidgets', 'PyQt6.QtWebChannel',
        'PyQt6.QtDesigner', 'PyQt6.QtHelp',
        'PyQt6.QtMultimedia', 'PyQt6.QtMultimediaWidgets',
        'PyQt6.QtOpenGL', 'PyQt6.QtOpenGLWidgets',
        'PyQt6.QtPositioning', 'PyQt6.QtBluetooth',
        'PyQt6.QtNfc', 'PyQt6.QtSensors', 'PyQt6.QtSerialPort',
        'PyQt6.QtSql', 'PyQt6.QtTest', 'PyQt6.QtPdf',
        'PyQt6.QtPdfWidgets', 'PyQt6.QtSvgWidgets',
        'PyQt6.QtRemoteObjects', 'PyQt6.QtDBus',
        'PyQt6.Qt3DCore', 'PyQt6.Qt3DRender', 'PyQt6.Qt3DInput',
        'PyQt6.Qt3DLogic', 'PyQt6.Qt3DExtras', 'PyQt6.Qt3DAnimation',
        'PyQt6.QtQuick', 'PyQt6.QtQuickWidgets', 'PyQt6.QtQml',
        'PyQt6.QtCharts', 'PyQt6.QtDataVisualization',
        'PyQt6.QtNetworkAuth', 'PyQt6.QtSpatialAudio',
        'PyQt6.QtTextToSpeech',
        # ── Fluent Widgets (not used in old UI) ──
        'qfluentwidgets', 'PyQt6_Fluent_Widgets',
        # ── Other unused ──
        'sqlalchemy', 'jinja2', 'markupsafe', 'lark',
        'xml.etree', 'xmlrpc', 'multiprocessing',
        # asyncio & concurrent kept — openai SDK imports them internally
        'lib2to3', 'ensurepip',
    ],
    noarchive=False,
    optimize=2,       # strip docstrings + asserts
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Pishper',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,       # strip debug symbols from binaries
    upx=True,         # compress with UPX if available
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,    # no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico',
)
