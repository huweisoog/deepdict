"""选中文本的获取：Windows 优先 UI Automation 失败退回 Ctrl+C；macOS 使用安全 Cmd+C。"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass

from . import platform_util as plat

# 在这些窗口里 Ctrl+C 可能是中断信号，绝不能盲发
_CONSOLE_CLASSES = {
    "consolewindowclass",
    "cascadia_hosting_window_class",
    "windowsterminal",
    "mintty",
    "puTTY",
}

# 这些应用的多格式剪贴板/COM 树较重，UIA 取选区容易慢或返回空，直接走安全 Ctrl+C 更稳
_SKIP_UIA_CLASSES = {
    "acrobatsdiwindow",
}


@dataclass
class Selection:
    text: str
    source: str = "UIA"  # UIA / 剪贴板 / 手动
    hwnd: int = 0
    title: str = ""

    def __bool__(self) -> bool:
        return bool(self.text)


def clean_text(text: str | None, limit: int = 4000) -> str:
    if not text:
        return ""
    text = text.replace("\u200b", "").replace("\ufeff", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in text.split("\n")]
    # 去掉首尾空行，连续空行压成一行
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    out: list[str] = []
    for line in lines:
        if line or (out and out[-1]):
            out.append(line)
    cleaned = "\n".join(out).strip()
    if limit and len(cleaned) > limit:
        cleaned = cleaned[:limit].rstrip() + "…"
    return cleaned


def is_console_window(hwnd: int) -> bool:
    if not plat.IS_WINDOWS:
        return False
    return plat.window_class(hwnd).lower() in {c.lower() for c in _CONSOLE_CLASSES}


def should_skip_uia(hwnd: int) -> bool:
    if not plat.IS_WINDOWS:
        return True
    return bool(hwnd) and plat.window_class(hwnd).lower() in _SKIP_UIA_CLASSES


def _uia_text_pattern(control):
    try:
        import uiautomation as auto

        return control.GetPattern(auto.PatternId.TextPattern)
    except Exception:
        return None


def _selection_text(control) -> str:
    pattern = _uia_text_pattern(control)
    if pattern is None:
        return ""
    try:
        ranges = pattern.GetSelection()
    except Exception:
        return ""
    parts: list[str] = []
    for rng in ranges or []:
        try:
            chunk = rng.GetText(-1)
        except Exception:
            chunk = ""
        if chunk:
            parts.append(chunk)
    return "".join(parts)


def read_selection_uia(limit: int = 4000, own_pid: int | None = None, point: tuple[int, int] | None = None) -> str:
    """从当前焦点元素读取选区文本；读不到返回空串（仅 Windows）。"""
    if not plat.IS_WINDOWS:
        return ""
    try:
        import uiautomation as auto
    except Exception:
        return ""

    own_pid = own_pid if own_pid is not None else os.getpid()
    roots = []
    if point is not None:
        try:
            roots.append(auto.ControlFromPoint(*point))
        except Exception:
            pass
    try:
        roots.append(auto.GetFocusedControl())
    except Exception:
        pass

    for root in roots:
        if root is None:
            continue
        try:
            if root.ProcessId == own_pid:
                continue
        except Exception:
            pass
        candidates = [root]
        node = root
        for _ in range(4):
            try:
                node = node.GetParentControl()
            except Exception:
                break
            if node is None:
                break
            candidates.append(node)
        try:
            candidates.extend((root.GetChildren() or [])[:12])
        except Exception:
            pass
        for control in candidates:
            text = clean_text(_selection_text(control), limit)
            if text:
                return text
    return ""


def _wait_clipboard_settled(initial_seq: int, wait_timeout: float = 0.9, settle_ms: float = 0.09) -> bool:
    """等待剪贴板序号发生变化，并稳定一小段时间，避免与 Adobe/Office 多格式写入冲突。"""
    deadline = time.time() + wait_timeout
    last_seq = initial_seq
    changed_at = 0.0
    while time.time() < deadline:
        current = plat.clipboard_sequence()
        if current != last_seq:
            last_seq = current
            changed_at = time.time()
        elif changed_at and (time.time() - changed_at) >= settle_ms:
            return True
        time.sleep(0.015)
    return changed_at > 0.0


def capture_by_copy(limit: int = 4000, restore: bool = True, source_pid: int = 0) -> tuple[str, bool]:
    """模拟复制快捷键（Windows Ctrl+C / macOS Cmd+C）读选区。返回 (文本, 是否动过剪贴板)。"""
    hwnd = plat.foreground_window()
    if plat.IS_MACOS and source_pid and not plat.is_own_pid(source_pid):
        if not hwnd or plat.is_own_pid(plat.window_pid(hwnd)):
            if plat.activate_app_pid(source_pid):
                time.sleep(0.08)
                hwnd = plat.foreground_window()
    if not hwnd:
        return "", False
    if plat.is_own_pid(plat.window_pid(hwnd)):
        return "", False
    if is_console_window(hwnd):
        return "", False

    previous = plat.get_clipboard_text()
    sequence = plat.clipboard_sequence()

    # 用户可能还按着 Ctrl/Alt/Cmd（热键触发时），等松开再发复制快捷键，避免组合成别的命令
    plat.wait_modifiers_released(0.45)
    # 留出短暂间隙，确保前一步读取剪贴板已完全释放，不与目标程序抢占剪贴板
    time.sleep(0.03)
    if not plat.send_copy_shortcut():
        return "", False

    if not _wait_clipboard_settled(sequence, wait_timeout=1.0, settle_ms=0.14):
        # 剪贴板没变化 = 对方没有可复制的选区，别把旧内容当成选区返回
        return "", True

    text = clean_text(plat.get_clipboard_text(retries=10, delay=0.03), limit)
    if not text:
        # 某些程序（如 Adobe Acrobat）会先 EmptyClipboard 再异步写入文本，稍后再读一次
        time.sleep(0.15)
        text = clean_text(plat.get_clipboard_text(retries=10, delay=0.03), limit)

    if restore and text and previous is not None and text != previous:
        # 延迟在后台还原剪贴板，既不拖慢翻译启动，又避免与 Adobe Acrobat 的后续剪贴板操作冲突
        copied_seq = plat.clipboard_sequence()

        def _restore_later() -> None:
            time.sleep(0.3)
            if plat.clipboard_sequence() == copied_seq:
                plat.set_clipboard_text(previous, retries=10, delay=0.03)

        threading.Thread(target=_restore_later, daemon=True).start()
    return text, True


def capture_selection(limit: int = 4000, restore_clipboard: bool = True, source_pid: int = 0) -> Selection:
    hwnd = plat.foreground_window()
    effective_pid = source_pid if (plat.IS_MACOS and source_pid and not plat.is_own_pid(source_pid)) else hwnd
    title = plat.window_title(effective_pid)
    if plat.IS_MACOS:
        ax_text = clean_text(plat.read_selection_ax(effective_pid if effective_pid else 0), limit)
        if ax_text:
            return Selection(text=ax_text, source="划词", hwnd=effective_pid, title=title)
    elif not should_skip_uia(hwnd):
        text = read_selection_uia(limit)
        if text:
            return Selection(text=text, source="UIA", hwnd=hwnd, title=title)
    text, _ = capture_by_copy(limit, restore_clipboard, source_pid=source_pid)
    if text:
        return Selection(text=text, source="剪贴板", hwnd=effective_pid, title=title)
    return Selection(text="", source="", hwnd=effective_pid, title=title)


def probe_uia_available() -> bool:
    if not plat.IS_WINDOWS:
        return False
    try:
        import uiautomation as auto

        return auto.GetRootControl() is not None
    except Exception:
        return False
