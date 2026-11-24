"""跨平台系统适配层：Windows 路由到 win32util，macOS 路由到 macutil。"""

from __future__ import annotations

import sys

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"

if IS_WINDOWS:
    from . import win32util as _backend
else:
    from . import macutil as _backend


def enable_dpi_awareness() -> None:
    _backend.enable_dpi_awareness()


def foreground_window() -> int:
    return _backend.foreground_window()


def window_pid(hwnd: int) -> int:
    return _backend.window_pid(hwnd)


def window_title(hwnd: int) -> str:
    return _backend.window_title(hwnd)


def window_class(hwnd: int) -> str:
    return _backend.window_class(hwnd)


def cursor_pos() -> tuple[int, int]:
    return _backend.cursor_pos()


def window_from_point(x: int, y: int) -> int:
    return _backend.window_from_point(x, y)


def root_window(hwnd: int) -> int:
    return _backend.root_window(hwnd)


def is_own_pid(pid: int) -> bool:
    return _backend.is_own_pid(pid)


def get_clipboard_text(retries: int = 6, delay: float = 0.02) -> str | None:
    return _backend.get_clipboard_text(retries=retries, delay=delay)


def set_clipboard_text(text: str, retries: int = 6, delay: float = 0.02) -> bool:
    return _backend.set_clipboard_text(text, retries=retries, delay=delay)


def clipboard_sequence() -> int:
    return _backend.clipboard_sequence()


def send_copy_shortcut() -> bool:
    if IS_WINDOWS:
        return _backend.send_ctrl_c()
    return _backend.send_copy_shortcut()


def wait_modifiers_released(timeout: float = 0.5) -> bool:
    return _backend.wait_modifiers_released(timeout)


def parse_hotkey(spec: str):
    return _backend.parse_hotkey(spec)


def set_window_noactivate(hwnd: int) -> bool:
    return _backend.set_window_noactivate(hwnd)


def configure_popup_window(hwnd: int) -> bool:
    if IS_MACOS and hasattr(_backend, "configure_popup_window"):
        return _backend.configure_popup_window(hwnd)
    return False


def activate_app_pid(pid: int) -> bool:
    if IS_MACOS and hasattr(_backend, "activate_app_pid"):
        return _backend.activate_app_pid(pid)
    return False


def read_selection_ax(pid: int = 0) -> str:
    if IS_MACOS and hasattr(_backend, "read_selection_ax"):
        return _backend.read_selection_ax(pid)
    return ""


def process_integrity_level() -> str:
    return _backend.process_integrity_level()


def acquire_single_instance(name: str):
    return _backend.acquire_single_instance(name)
