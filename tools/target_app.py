"""被取词的目标窗口（模拟 Word / 浏览器 / 记事本这类第三方应用）。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication, QMainWindow, QTextEdit

from deepdict import win32util as w32

TEXT = (
    "Reading is to the mind what exercise is to the body. "
    "A single good book can change the direction of a life.\n\n"
    "Serendipity — 意外发现美好事物的运气。"
)

app = QApplication([])
window = QMainWindow()
window.setWindowTitle("DeepDict 取词测试目标")
edit = QTextEdit()
edit.setPlainText(TEXT)
edit.setStyleSheet("font-size: 15px; padding: 12px;")
window.setCentralWidget(edit)
window.setGeometry(160, 160, 760, 420)
window.show()
edit.setFocus()
edit.selectAll()

print("TARGET_PID", os.getpid(), "HWND", int(window.winId()), flush=True)
print("FG_MATCH", w32.foreground_window() == int(window.winId()), flush=True)

QTimer.singleShot(40000, app.quit)
app.exec_()
