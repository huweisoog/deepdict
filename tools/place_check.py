"""校验弹窗在多屏 / 屏幕边缘的落位：必须完整落在所在屏幕的可用区域内。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("DEEPDICT_CONFIG_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".testcfg"))

from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QGuiApplication
from PyQt5.QtWidgets import QApplication

from deepdict import ui

app = QApplication([])
popup = ui.PopupWindow({"popup_width": 470, "model": "deepseek-chat"})
popup.begin("Serendipity is the occurrence of events by chance in a happy way.", "示例", "")

failures = []
for screen in QGuiApplication.screens():
    area = screen.availableGeometry()
    probes = [
        ("左下", area.left() + 4, area.bottom() - 4),
        ("右下", area.right() - 4, area.bottom() - 4),
        ("右上", area.right() - 4, area.top() + 4),
        ("中间", area.center().x(), area.center().y()),
    ]
    for name, x, y in probes:
        popup.show_near(x, y)
        popup.adjustSize()
        app.processEvents()
        frame = popup.frameGeometry()
        inside = area.contains(frame)
        print(f"{screen.name()} {name}: popup={frame.x()},{frame.y()} {frame.width()}x{frame.height()} "
              f"screen={area.x()},{area.y()} {area.width()}x{area.height()} inside={inside}", flush=True)
        if not inside:
            failures.append((screen.name(), name))
        popup.hide()

print("FAILURES:", failures, flush=True)
QTimer.singleShot(10, app.quit)
app.exec_()
