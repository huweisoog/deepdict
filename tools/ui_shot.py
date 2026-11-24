"""界面验证脚本：真实热键触发 → 取词（打桩）→ 流式回答 → 截图。"""

import ctypes
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["DEEPDICT_CONFIG_DIR"] = os.path.join(ROOT, ".testcfg")
os.environ["DEEPDICT_MOCK"] = "1"
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

from deepdict import app as appmod  # noqa: E402
from deepdict import capture, config, ui  # noqa: E402

cfg = config.load_config()
cfg["api_key"] = "sk-test"
cfg["model"] = "deepseek-chat"
config.save_config(cfg)

SAMPLE = (
    "The quick brown fox jumps over the lazy dog. It is a pangram used for testing "
    "fonts and keyboards; a good sentence for a translation demo."
)
SELECTION = capture.Selection(text=SAMPLE, source="UIA", title="记事本")
appmod.cap.capture_selection = lambda **kwargs: SELECTION  # 取词单独验证，这里只测热键→UI

from PyQt5.QtCore import QTimer, Qt  # noqa: E402
from PyQt5.QtWidgets import QApplication, QLabel  # noqa: E402

os.environ.setdefault("QT_QPA_PLATFORM", "windows")

app = QApplication([])
controller = appmod.DeepDictApp(app)

shots = os.path.join(ROOT, ".shots")
os.makedirs(shots, exist_ok=True)
results = {}

# 深色背景板，避免截图里出现乱七八糟的桌面
backdrop = QLabel("DeepDict · 全局划词 + DeepSeek")
backdrop.setStyleSheet(
    "background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #0d1017, stop:1 #1b2233);"
    "color: #2a3450; font-size: 44px; font-weight: 700; padding: 40px;"
)
backdrop.setWindowFlags(Qt.FramelessWindowHint)
backdrop.resize(1000, 620)
backdrop.move(80, 80)
backdrop.show()


def press_hotkey():
    # SendInput 的合成按键不会触发 RegisterHotKey，这里直接投递热键消息，
    # 走的是和真实按键完全相同的处理链路（WM_HOTKEY → nativeEventFilter）。
    from ctypes import wintypes

    from deepdict import win32util as w32

    w32.user32.PostMessageW(wintypes.HWND(controller._hwnd), 0x0312, 1, 0)
    results["sent"] = True
    results["hotkey"] = controller.cfg["hotkey"]


def check_popup():
    results["visible"] = controller.popup.isVisible()
    results["answer_len"] = len(controller.popup._answer)
    results["status"] = controller.popup.status.text()
    doc = controller.popup.answer.document()
    results["doc_h"] = round(doc.documentLayout().documentSize().height(), 1)
    results["view_h"] = controller.popup.answer.height()
    results["win_h"] = controller.popup.height()
    controller.popup.move(150, 120)
    controller.popup.raise_()
    app.processEvents()
    time.sleep(0.3)
    app.processEvents()
    controller.popup.grab().save(os.path.join(shots, "popup.png"))
    controller.popup.raise_()
    controller.popup.grab().save(os.path.join(shots, "popup.png"))
    screen = app.primaryScreen()
    geo = controller.popup.frameGeometry()
    screen.grabWindow(0, 100, 70, 760, 620).save(os.path.join(shots, "context.png"))


def shot_settings():
    dialog = ui.SettingsDialog(controller.cfg)
    dialog.resize(560, 560)
    dialog.show()
    app.processEvents()
    time.sleep(0.4)
    app.processEvents()
    dialog.grab().save(os.path.join(shots, "settings.png"))
    dialog.close()


def shot_bubble():
    bubble = ui.Bubble()
    bubble.show_for("hello", 700, 300, 5000)
    app.processEvents()
    time.sleep(0.2)
    app.processEvents()
    bubble.grab().save(os.path.join(shots, "bubble.png"))
    bubble.hide()


QTimer.singleShot(1000, press_hotkey)
QTimer.singleShot(4200, check_popup)
QTimer.singleShot(4600, shot_settings)
QTimer.singleShot(5200, shot_bubble)
QTimer.singleShot(5800, controller.quit)

app.exec_()
print("RESULTS", results)
for name in ("popup.png", "settings.png", "bubble.png", "context.png"):
    path = os.path.join(shots, name)
    print(name, os.path.getsize(path) if os.path.exists(path) else "MISSING")
