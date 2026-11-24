"""Count background mouse button transitions; no text or positions are read."""
import ctypes
import sys
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PyQt5.QtCore import QAbstractNativeEventFilter, QTimer
from PyQt5.QtWidgets import QApplication, QWidget
from deepdict import win32util as w

app = QApplication([])
app.setQuitOnLastWindowClosed(False)
window = QWidget()
window.setWindowTitle("DeepDict raw input diagnostic")
window.show()
window.hide()
hwnd = int(window.winId())
assert w.register_raw_mouse(hwnd), "raw mouse registration failed"
counts = {"down": 0, "up": 0}


class Filter(QAbstractNativeEventFilter):
    def nativeEventFilter(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            msg = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
            if msg.message == w.WM_INPUT:
                flags = w.raw_mouse_buttons(int(msg.lParam))
                if flags & w.RI_MOUSE_LEFT_BUTTON_DOWN:
                    counts["down"] += 1
                if flags & w.RI_MOUSE_LEFT_BUTTON_UP:
                    counts["up"] += 1
                if int(msg.wParam) == 0:
                    w.user32.DefWindowProcW(msg.hWnd, msg.message, msg.wParam, msg.lParam)
                return True, 0
        return False, 0


flt = Filter()
app.installNativeEventFilter(flt)
print("RAW_DIAGNOSTIC_READY", flush=True)
QTimer.singleShot(45000, app.quit)
app.exec_()
w.unregister_raw_mouse()
print("PRESS_COUNT", counts["down"], "RELEASE_COUNT", counts["up"], flush=True)
