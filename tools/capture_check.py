"""跨进程验证 UIA 取词（不依赖前台激活）：按窗口标题找到目标，读取其选区。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uiautomation as auto  # noqa: E402

from deepdict import capture, win32util as w32  # noqa: E402

TARGET_TITLE = "DeepDict 取词测试目标"

window = auto.WindowControl(searchDepth=1, Name=TARGET_TITLE)
print("FOUND WINDOW:", bool(window.Exists(2)), flush=True)

found = []


def walk(control, depth=0):
    if depth > 4 or len(found) >= 3:
        return
    try:
        pattern = control.GetPattern(auto.PatternId.TextPattern)
    except Exception:
        pattern = None
    if pattern is not None:
        try:
            ranges = pattern.GetSelection()
            text = "".join(r.GetText(-1) or "" for r in ranges)
            if text.strip():
                found.append((control.ControlTypeName, control.Name, text))
        except Exception:
            pass
    try:
        children = control.GetChildren()
    except Exception:
        children = []
    for child in children:
        walk(child, depth + 1)


walk(window)
print("UIA SELECTION COUNT:", len(found), flush=True)
for ctype, name, text in found:
    print("  ", ctype, "|", name[:20], "|", repr(text[:80]), flush=True)

expected = "Reading is to the mind"
ok = any(expected in text for _, _, text in found)
print("UIA_OK:", ok, flush=True)

# Ctrl+C 兜底：向目标窗口发 WM_COPY（不需要前台），验证读剪贴板 + 还原逻辑
hwnd = int(window.NativeWindowHandle)
before = w32.get_clipboard_text()
w32.user32.SendMessageW(w32.wintypes.HWND(hwnd), 0x0301, 0, 0)  # WM_COPY
print("AFTER_WM_COPY_CLIP:", repr((w32.get_clipboard_text() or "")[:40]), flush=True)
if before is not None:
    w32.set_clipboard_text(before)
print("CLIPBOARD_RESTORED:", w32.get_clipboard_text() == before, flush=True)
print("CLEAN_TEXT:", repr(capture.clean_text(w32.get_clipboard_text(), 30)), flush=True)
