import sys
from PyQt6.QtWidgets import QApplication, QLabel, QMainWindow

app = QApplication(sys.argv)
window = QMainWindow()
window.setWindowTitle("Pishper Diagnostic")
label = QLabel("If you can see this, PyQt6 is working and visible.")
window.setCentralWidget(label)
window.resize(400, 200)
window.show()
print("Window shown. Check your desktop.")
sys.exit(app.exec())
