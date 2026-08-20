import sys
from PyQt6.QtWidgets import QApplication, QWidget

try:
    app = QApplication(sys.argv)
    w = QWidget()
    print("PyQt6 initialized successfully")
    sys.exit(0)
except Exception as e:
    print(f"PyQt6 initialization failed: {e}")
    sys.exit(1)
