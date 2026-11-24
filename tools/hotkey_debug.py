import ctypes
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ctypes import wintypes

from PyQt5.QtCore import QAbstractNativeEventFilter, QTimer
from PyQt5.QtWidgets import QApplication, QWidget

from deepdict import win32util as w32

hits = []


class Filter(QAbstractNativeEventFilter):
    def nativeEventFilter(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            msg = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
            if msg.message == 0x0312:
                hits.append(int(msg.wParam))
                print("WM_HOTKEY", int(msg.wParam), flush=True)
        return False, 0


app = QApplication([])
w = QWidget()
w.resize(1, 1)
w.show()
w.hide()
hwnd = int(w.winId())

filt = Filter()
app.installNativeEventFilter(filt)
print("hwnd", hwnd, flush=True)

candidates = [
    "Ctrl+Alt+D", "Ctrl+Alt+Q", "Ctrl+Alt+Z", "Ctrl+Alt+X", "Ctrl+Alt+F10",
    "Ctrl+Shift+D", "Ctrl+Shift+Q", "Alt+Q", "Alt+Z", "Ctrl+Alt+Space",
]
free = []
for i, spec in enumerate(candidates, start=10):
    ok = w32.register_hotkey(hwnd, i, spec)
    print(f"{spec:16s} {'FREE' if ok else 'TAKEN'}", flush=True)
    if ok:
        free.append((i, spec))
    else:
        w32.unregister_hotkey(hwnd, i)

# 1) 直接投递 WM_HOTKEY，验证 Qt 原生事件过滤器
if free:
    hid, spec = free[0]
    w32.user32.PostMessageW(wintypes.HWND(hwnd), 0x0312, hid, 0)
    print("posted WM_HOTKEY for", spec, flush=True)


def send(vk, mods):
    events = [w32._key_event(m) for m in mods] + [w32._key_event(vk), w32._key_event(vk, True)]
    events += [w32._key_event(m, True) for m in reversed(mods)]
    return w32._send(events)


def synth():
    if free:
        hid, spec = free[0]
        print("SendInput", spec, send(0x71, [0x11, 0x12]), flush=True)  # Ctrl+Alt+F2


def done():
    print("HITS", hits, flush=True)
    for hid, _ in free:
        w32.unregister_hotkey(hwnd, hid)
    app.quit()


QTimer.singleShot(500, synth)
QTimer.singleShot(1500, done)
app.exec_()
