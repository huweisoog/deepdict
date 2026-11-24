"""macOS 平台底座：剪贴板、Cmd+C 模拟、全局热键与鼠标拖选监听（基于 pynput）、单实例、开机自启。"""

from __future__ import annotations

import os
import plistlib
import subprocess
import sys
import threading
import time
from pathlib import Path

_MOD_MAP = {
    "CTRL": "<ctrl>",
    "CONTROL": "<ctrl>",
    "CMD": "<cmd>",
    "COMMAND": "<cmd>",
    "META": "<cmd>",
    "SUPER": "<cmd>",
    "WIN": "<cmd>",
    "ALT": "<alt>",
    "OPTION": "<alt>",
    "OPT": "<alt>",
    "SHIFT": "<shift>",
}

_KEY_MAP = {
    "SPACE": "<space>",
    "ENTER": "<enter>",
    "RETURN": "<enter>",
    "TAB": "<tab>",
    "ESC": "<esc>",
    "ESCAPE": "<esc>",
    "BACKSPACE": "<backspace>",
    "DELETE": "<delete>",
    "UP": "<up>",
    "DOWN": "<down>",
    "LEFT": "<left>",
    "RIGHT": "<right>",
    "HOME": "<home>",
    "END": "<end>",
    "PAGEUP": "<page_up>",
    "PAGEDOWN": "<page_down>",
}


def enable_dpi_awareness() -> None:
    """macOS Retina 由 Qt 原生处理。"""


def foreground_window() -> int:
    return 1


def window_pid(hwnd: int) -> int:
    return 0


def window_title(hwnd: int) -> str:
    try:
        out = subprocess.check_output(
            [
                "osascript",
                "-e",
                'tell application "System Events" to get name of first application process whose frontmost is true',
            ],
            stderr=subprocess.DEVNULL,
            timeout=0.4,
        )
        return out.decode("utf-8", errors="ignore").strip()
    except Exception:
        return ""


def window_class(hwnd: int) -> str:
    return ""


def cursor_pos() -> tuple[int, int]:
    try:
        from PyQt5.QtGui import QCursor

        pos = QCursor.pos()
        return int(pos.x()), int(pos.y())
    except Exception:
        return 0, 0


def window_from_point(x: int, y: int) -> int:
    return 0


def root_window(hwnd: int) -> int:
    return hwnd


def is_own_pid(pid: int) -> bool:
    return pid != 0 and pid == os.getpid()


def set_window_noactivate(hwnd: int) -> bool:
    return False


def process_integrity_level() -> str:
    return ""


# ---------------------------------------------------------------- 剪贴板

def get_clipboard_text(retries: int = 4, delay: float = 0.02) -> str | None:
    for _ in range(retries):
        try:
            proc = subprocess.run(
                ["pbpaste"],
                capture_output=True,
                timeout=1.0,
                check=False,
            )
            if proc.returncode == 0:
                return proc.stdout.decode("utf-8", errors="replace")
        except Exception:
            pass
        time.sleep(delay)
    return None


def set_clipboard_text(text: str, retries: int = 4, delay: float = 0.02) -> bool:
    data = text.encode("utf-8")
    for _ in range(retries):
        try:
            proc = subprocess.run(
                ["pbcopy"],
                input=data,
                timeout=1.0,
                check=False,
            )
            if proc.returncode == 0:
                return True
        except Exception:
            pass
        time.sleep(delay)
    return False


def clipboard_sequence() -> int:
    """优先读取 NSPasteboard changeCount；不可用时退回文本哈希。"""
    try:
        from AppKit import NSPasteboard  # type: ignore[import-not-found]

        return int(NSPasteboard.generalPasteboard().changeCount())
    except Exception:
        text = get_clipboard_text(retries=1)
        return hash(text) & 0x7FFFFFFF


# ---------------------------------------------------------------- 模拟 Cmd+C

def send_copy_shortcut() -> bool:
    """发送 Cmd+C 到当前前台应用（需要 macOS 辅助功能权限）。"""
    try:
        proc = subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "System Events" to keystroke "c" using command down',
            ],
            capture_output=True,
            timeout=1.0,
            check=False,
        )
        if proc.returncode == 0:
            return True
    except Exception:
        pass
    try:
        from pynput.keyboard import Controller, Key  # type: ignore[import-not-found]

        kb = Controller()
        kb.press(Key.cmd)
        time.sleep(0.015)
        kb.press("c")
        time.sleep(0.025)
        kb.release("c")
        time.sleep(0.015)
        kb.release(Key.cmd)
        return True
    except Exception:
        return False


def wait_modifiers_released(timeout: float = 0.35) -> bool:
    time.sleep(min(timeout, 0.12))
    return True


# ---------------------------------------------------------------- 热键解析

def parse_hotkey(spec: str) -> str | None:
    """'Cmd+Alt+Q' / 'Ctrl+Alt+Q' -> pynput 格式 '<cmd>+<alt>+q'。"""
    if not spec:
        return None
    mods: list[str] = []
    key_part: str | None = None
    for raw in str(spec).split("+"):
        token = raw.strip().upper()
        if not token:
            continue
        if token in _MOD_MAP:
            mapped = _MOD_MAP[token]
            if mapped not in mods:
                mods.append(mapped)
        elif token in _KEY_MAP:
            key_part = _KEY_MAP[token]
        elif len(token) == 1 and (token.isalnum() or token in "`-=[]\\;',./"):
            key_part = token.lower()
        elif token.startswith("F") and token[1:].isdigit() and 1 <= int(token[1:]) <= 24:
            key_part = f"<f{int(token[1:])}>"
        else:
            return None
    if not key_part:
        return None
    return "+".join([*mods, key_part])


# ---------------------------------------------------------------- 后台监听（热键 + 鼠标拖选）

class MacInputMonitor:
    """macOS 全局热键 + 鼠标左键拖选/双击监听器（依赖 pynput）。"""

    def __init__(self, on_hotkey, on_mouse_down, on_mouse_up) -> None:
        self._on_hotkey = on_hotkey
        self._on_mouse_down = on_mouse_down
        self._on_mouse_up = on_mouse_up
        self._mouse_listener = None
        self._hotkey_listener = None
        self._lock = threading.Lock()
        self.mouse_ok = False
        self.hotkey_ok = False

    def start_mouse(self) -> bool:
        try:
            from pynput import mouse  # type: ignore[import-not-found]
        except Exception:
            self.mouse_ok = False
            return False

        def on_click(x, y, button, pressed):
            if button != mouse.Button.left:
                return
            if pressed:
                self._on_mouse_down(int(x), int(y))
            else:
                self._on_mouse_up(int(x), int(y))

        with self._lock:
            self.stop_mouse()
            try:
                listener = mouse.Listener(on_click=on_click)
                listener.daemon = True
                listener.start()
                self._mouse_listener = listener
                self.mouse_ok = True
                return True
            except Exception:
                self.mouse_ok = False
                return False

    def register_hotkeys(self, mapping: dict[int, str]) -> dict[int, bool]:
        results: dict[int, bool] = {}
        try:
            from pynput import keyboard  # type: ignore[import-not-found]
        except Exception:
            self.hotkey_ok = False
            return {hid: False for hid in mapping}

        hotkeys: dict[str, object] = {}
        for hid, spec in mapping.items():
            parsed = parse_hotkey(spec)
            if not parsed:
                results[hid] = False
                continue
            hotkeys[parsed] = lambda _id=hid: self._on_hotkey(_id)
            results[hid] = True

        with self._lock:
            self.stop_hotkeys()
            if not hotkeys:
                self.hotkey_ok = False
                return results
            try:
                listener = keyboard.GlobalHotKeys(hotkeys)
                listener.daemon = True
                listener.start()
                self._hotkey_listener = listener
                self.hotkey_ok = True
            except Exception:
                self.hotkey_ok = False
                return {hid: False for hid in mapping}
        return results

    def stop_mouse(self) -> None:
        if self._mouse_listener is not None:
            try:
                self._mouse_listener.stop()
            except Exception:
                pass
            self._mouse_listener = None

    def stop_hotkeys(self) -> None:
        if self._hotkey_listener is not None:
            try:
                self._hotkey_listener.stop()
            except Exception:
                pass
            self._hotkey_listener = None

    def stop(self) -> None:
        with self._lock:
            self.stop_mouse()
            self.stop_hotkeys()


# ---------------------------------------------------------------- 单实例 & 开机自启

def acquire_single_instance(name: str):
    """使用 fcntl 文件锁实现 macOS/POSIX 单实例。"""
    try:
        import fcntl

        lock_path = Path.home() / "Library" / "Application Support" / "DeepDict" / f"{name}.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = lock_path.open("w", encoding="utf-8")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        handle.write(str(os.getpid()))
        handle.flush()
        return handle
    except Exception:
        return None


def set_autostart(enabled: bool, app_name: str = "DeepDict") -> bool:
    """通过 ~/Library/LaunchAgents 写入/删除 macOS 登录自启动项。"""
    plist_path = Path.home() / "Library" / "LaunchAgents" / "com.deepdict.app.plist"
    try:
        if not enabled:
            if plist_path.exists():
                plist_path.unlink()
            return True
        plist_path.parent.mkdir(parents=True, exist_ok=True)
        if getattr(sys, "frozen", False):
            program_args = [sys.executable]
        else:
            program_args = [sys.executable, "-m", "deepdict"]
        payload = {
            "Label": "com.deepdict.app",
            "ProgramArguments": program_args,
            "RunAtLoad": True,
            "KeepAlive": False,
        }
        with plist_path.open("wb") as handle:
            plistlib.dump(payload, handle)
        return True
    except OSError:
        return False
