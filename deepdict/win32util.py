"""Win32 底座：DPI、剪贴板、模拟按键、全局热键、低级鼠标钩子、单实例。"""

from __future__ import annotations

import ctypes
import threading
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# Win32 window handles and pointer-sized arguments must not be truncated on
# 64-bit Windows; ctypes otherwise assumes a 32-bit integer return value.
user32.SetProcessDpiAwarenessContext.argtypes = (ctypes.c_void_p,)
user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
user32.GetForegroundWindow.argtypes = ()
user32.GetForegroundWindow.restype = wintypes.HWND
user32.WindowFromPoint.argtypes = (wintypes.POINT,)
user32.WindowFromPoint.restype = wintypes.HWND
user32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
user32.GetAncestor.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
user32.GetClassNameW.restype = ctypes.c_int
user32.GetCursorPos.argtypes = (ctypes.POINTER(wintypes.POINT),)
user32.GetCursorPos.restype = wintypes.BOOL
user32.GetClipboardSequenceNumber.argtypes = ()
user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
user32.MapVirtualKeyW.argtypes = (wintypes.UINT, wintypes.UINT)
user32.MapVirtualKeyW.restype = wintypes.UINT
user32.SendInput.argtypes = (wintypes.UINT, ctypes.c_void_p, ctypes.c_int)
user32.SendInput.restype = wintypes.UINT
user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.RegisterHotKey.argtypes = (wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT)
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = (wintypes.HWND, ctypes.c_int)
user32.UnregisterHotKey.restype = wintypes.BOOL
kernel32.GetCurrentProcessId.argtypes = ()
kernel32.GetCurrentProcessId.restype = wintypes.DWORD
kernel32.GetCurrentThreadId.argtypes = ()
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
kernel32.GetCurrentProcess.argtypes = ()
kernel32.GetCurrentProcess.restype = wintypes.HANDLE
kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
kernel32.CloseHandle.restype = wintypes.BOOL

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WM_MOUSEACTIVATE = 0x0021
MA_NOACTIVATE = 3

_get_window_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
_set_window_long = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
_get_window_long.argtypes = (wintypes.HWND, ctypes.c_int)
_get_window_long.restype = ctypes.c_ssize_t
_set_window_long.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t)
_set_window_long.restype = ctypes.c_ssize_t


def set_window_noactivate(hwnd: int) -> bool:
    """为窗口设置 WS_EX_NOACTIVATE，避免点击气泡时抢占目标程序焦点。"""
    if not hwnd:
        return False
    style = _get_window_long(wintypes.HWND(hwnd), GWL_EXSTYLE)
    if not (style & WS_EX_NOACTIVATE):
        _set_window_long(wintypes.HWND(hwnd), GWL_EXSTYLE, style | WS_EX_NOACTIVATE)
    return True


def process_integrity_level() -> str:
    """返回当前进程的完整性级别（Untrusted/Low/Medium/High/System），失败返回空串。"""
    try:
        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        advapi32.OpenProcessToken.argtypes = (wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE))
        advapi32.OpenProcessToken.restype = wintypes.BOOL
        advapi32.GetTokenInformation.argtypes = (
            wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
        )
        advapi32.GetTokenInformation.restype = wintypes.BOOL
        advapi32.GetSidSubAuthorityCount.argtypes = (ctypes.c_void_p,)
        advapi32.GetSidSubAuthorityCount.restype = ctypes.POINTER(ctypes.c_ubyte)
        advapi32.GetSidSubAuthority.argtypes = (ctypes.c_void_p, wintypes.DWORD)
        advapi32.GetSidSubAuthority.restype = ctypes.POINTER(wintypes.DWORD)

        token = wintypes.HANDLE()
        if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
            return ""
        try:
            needed = wintypes.DWORD(0)
            advapi32.GetTokenInformation(token, 25, None, 0, ctypes.byref(needed))
            if needed.value <= 0 or needed.value > 4096:
                return ""
            buf = ctypes.create_string_buffer(needed.value)
            if not advapi32.GetTokenInformation(token, 25, buf, needed.value, ctypes.byref(needed)):
                return ""
            sid_ptr = ctypes.c_void_p.from_buffer(buf).value
            if not sid_ptr:
                return ""
            count_ptr = advapi32.GetSidSubAuthorityCount(sid_ptr)
            if not count_ptr or count_ptr.contents.value == 0:
                return ""
            rid = int(advapi32.GetSidSubAuthority(sid_ptr, count_ptr.contents.value - 1).contents.value)
            if rid < 0x1000:
                return "Untrusted"
            if rid < 0x2000:
                return "Low"
            if rid < 0x3000:
                return "Medium"
            if rid < 0x4000:
                return "High"
            return "System"
        finally:
            kernel32.CloseHandle(token)
    except Exception:
        return ""

# ---------------------------------------------------------------- DPI

def enable_dpi_awareness() -> None:
    """必须在创建 QApplication 之前调用，否则 UIA / 鼠标坐标会错位。"""
    try:
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 == -4
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


# ---------------------------------------------------------------- 基础查询

def foreground_window() -> int:
    return int(user32.GetForegroundWindow() or 0)


def window_pid(hwnd: int) -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
    return int(pid.value)


def window_title(hwnd: int) -> str:
    length = int(user32.GetWindowTextLengthW(wintypes.HWND(hwnd)) or 0)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(wintypes.HWND(hwnd), buf, length + 1)
    return buf.value


def window_class(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(wintypes.HWND(hwnd), buf, 256)
    return buf.value


def cursor_pos() -> tuple[int, int]:
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return int(pt.x), int(pt.y)


def window_from_point(x: int, y: int) -> int:
    return int(user32.WindowFromPoint(wintypes.POINT(int(x), int(y))) or 0)


def root_window(hwnd: int) -> int:
    return int(user32.GetAncestor(wintypes.HWND(hwnd), 2) or hwnd)  # GA_ROOT


def is_own_pid(pid: int) -> bool:
    return pid == kernel32.GetCurrentProcessId()


# ---------------------------------------------------------------- 剪贴板

CF_UNICODETEXT = 13
CF_TEXT = 1


def get_clipboard_text(retries: int = 6, delay: float = 0.02) -> str | None:
    import win32clipboard  # pywin32

    for _ in range(retries):
        try:
            win32clipboard.OpenClipboard()
        except Exception:
            time.sleep(delay)
            continue
        try:
            if win32clipboard.IsClipboardFormatAvailable(CF_UNICODETEXT):
                value = win32clipboard.GetClipboardData(CF_UNICODETEXT)
                return str(value) if value is not None else None
            return None
        except Exception:
            return None
        finally:
            try:
                win32clipboard.CloseClipboard()
            except Exception:
                pass
    return None


def set_clipboard_text(text: str, retries: int = 6, delay: float = 0.02) -> bool:
    import win32clipboard

    for _ in range(retries):
        try:
            win32clipboard.OpenClipboard()
        except Exception:
            time.sleep(delay)
            continue
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(CF_UNICODETEXT, text)
            return True
        except Exception:
            return False
        finally:
            try:
                win32clipboard.CloseClipboard()
            except Exception:
                pass
    return False


def clipboard_sequence() -> int:
    return int(user32.GetClipboardSequenceNumber())


# ---------------------------------------------------------------- 模拟按键

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
VK_CONTROL = 0x11
VK_V = 0x56
VK_C = 0x43


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


def _key_event(vk: int, up: bool = False) -> INPUT:
    event = INPUT()
    event.type = INPUT_KEYBOARD
    event.u.ki.wVk = vk
    event.u.ki.wScan = int(user32.MapVirtualKeyW(vk, 0))
    event.u.ki.dwFlags = KEYEVENTF_KEYUP if up else 0
    event.u.ki.time = 0
    event.u.ki.dwExtraInfo = 0
    return event


def _send(events: list[INPUT]) -> bool:
    array = (INPUT * len(events))(*events)
    sent = user32.SendInput(len(events), array, ctypes.sizeof(INPUT))
    return sent == len(events)


def send_ctrl_c() -> bool:
    """分段发送 Ctrl+C，避免 Adobe Acrobat 等应用漏接 0ms 连续按键。"""
    if not _send([_key_event(VK_CONTROL)]):
        return False
    time.sleep(0.015)
    ok_down = _send([_key_event(VK_C)])
    time.sleep(0.025)
    ok_up = _send([_key_event(VK_C, True)])
    time.sleep(0.015)
    ok_ctrl = _send([_key_event(VK_CONTROL, True)])
    return ok_down and ok_up and ok_ctrl


def send_ctrl_v() -> bool:
    return _send([
        _key_event(VK_CONTROL),
        _key_event(VK_V),
        _key_event(VK_V, True),
        _key_event(VK_CONTROL, True),
    ])


def modifiers_held() -> bool:
    for vk in (0x10, 0x11, 0x12, 0x5B, 0x5C):  # Shift Ctrl Alt LWin RWin
        if user32.GetAsyncKeyState(vk) & 0x8000:
            return True
    return False


def wait_modifiers_released(timeout: float = 0.5) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not modifiers_held():
            return True
        time.sleep(0.01)
    return False


# ---------------------------------------------------------------- 全局热键

WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

_VK_NAMES = {
    "SPACE": 0x20, "ENTER": 0x0D, "RETURN": 0x0D, "TAB": 0x09,
    "ESC": 0x1B, "ESCAPE": 0x1B, "BACKSPACE": 0x08, "DELETE": 0x2E,
    "INSERT": 0x2D, "HOME": 0x24, "END": 0x23, "PAGEUP": 0x21,
    "PAGEDOWN": 0x22, "LEFT": 0x25, "UP": 0x26, "RIGHT": 0x27, "DOWN": 0x28,
    "`": 0xC0, "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD, "\\": 0xDC,
    ";": 0xBA, "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF,
}


def parse_hotkey(spec: str) -> tuple[int, int] | None:
    """'Ctrl+Alt+D' -> (modifiers, vk)。无法解析时返回 None。"""
    if not spec:
        return None
    mods = 0
    vk = 0
    for raw in str(spec).split("+"):
        token = raw.strip().upper()
        if not token:
            continue
        if token in ("CTRL", "CONTROL"):
            mods |= MOD_CONTROL
        elif token == "ALT":
            mods |= MOD_ALT
        elif token == "SHIFT":
            mods |= MOD_SHIFT
        elif token in ("WIN", "META", "SUPER"):
            mods |= MOD_WIN
        elif token in _VK_NAMES:
            vk = _VK_NAMES[token]
        elif len(token) == 1 and (token.isalnum() or token in "`-=[]\\;',./"):
            vk = ord(token)
        elif token.startswith("F") and token[1:].isdigit() and 1 <= int(token[1:]) <= 24:
            vk = 0x70 + int(token[1:]) - 1
        else:
            return None
    if vk == 0:
        return None
    return mods | MOD_NOREPEAT, vk


def register_hotkey(hwnd: int, hotkey_id: int, spec: str) -> bool:
    parsed = parse_hotkey(spec)
    if parsed is None:
        return False
    mods, vk = parsed
    user32.UnregisterHotKey(wintypes.HWND(hwnd), hotkey_id)
    return bool(user32.RegisterHotKey(wintypes.HWND(hwnd), hotkey_id, mods, vk))


def unregister_hotkey(hwnd: int, hotkey_id: int) -> None:
    try:
        user32.UnregisterHotKey(wintypes.HWND(hwnd), hotkey_id)
    except Exception:
        pass


# ---------------------------------------------------------------- 后台鼠标原始输入

WM_INPUT = 0x00FF
RIDEV_INPUTSINK = 0x00000100
RIDEV_REMOVE = 0x00000001
RID_INPUT = 0x10000003
RI_MOUSE_LEFT_BUTTON_DOWN = 0x0001
RI_MOUSE_LEFT_BUTTON_UP = 0x0002


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [("usage_page", wintypes.USHORT), ("usage", wintypes.USHORT),
                ("flags", wintypes.DWORD), ("hwnd", wintypes.HWND)]


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("size", wintypes.DWORD),
                ("device", wintypes.HANDLE), ("wparam", wintypes.WPARAM)]


class RAWMOUSE(ctypes.Structure):
    _fields_ = [("flags", wintypes.USHORT), ("buttons", wintypes.DWORD),
                ("raw_buttons", wintypes.DWORD), ("last_x", wintypes.LONG),
                ("last_y", wintypes.LONG), ("extra", wintypes.DWORD)]


class RAWMOUSEINPUT(ctypes.Structure):
    _fields_ = [("header", RAWINPUTHEADER), ("mouse", RAWMOUSE)]


user32.RegisterRawInputDevices.argtypes = (ctypes.POINTER(RAWINPUTDEVICE), wintypes.UINT, wintypes.UINT)
user32.RegisterRawInputDevices.restype = wintypes.BOOL
user32.GetRawInputData.argtypes = (wintypes.HANDLE, wintypes.UINT, ctypes.c_void_p,
                                   ctypes.POINTER(wintypes.UINT), wintypes.UINT)
user32.GetRawInputData.restype = wintypes.UINT
user32.DefWindowProcW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.DefWindowProcW.restype = ctypes.c_ssize_t


def register_raw_mouse(hwnd: int) -> bool:
    device = RAWINPUTDEVICE(1, 2, RIDEV_INPUTSINK, wintypes.HWND(hwnd))
    return bool(user32.RegisterRawInputDevices(ctypes.byref(device), 1, ctypes.sizeof(device)))


def unregister_raw_mouse() -> bool:
    device = RAWINPUTDEVICE(1, 2, RIDEV_REMOVE, None)
    return bool(user32.RegisterRawInputDevices(ctypes.byref(device), 1, ctypes.sizeof(device)))


def raw_mouse_buttons(handle: int) -> int:
    size = wintypes.UINT(0)
    header_size = ctypes.sizeof(RAWINPUTHEADER)
    if user32.GetRawInputData(wintypes.HANDLE(handle), RID_INPUT, None, ctypes.byref(size), header_size) != 0:
        return 0
    if size.value < ctypes.sizeof(RAWMOUSEINPUT) or size.value > 65536:
        return 0
    data = ctypes.create_string_buffer(size.value)
    read = user32.GetRawInputData(wintypes.HANDLE(handle), RID_INPUT, data, ctypes.byref(size), header_size)
    if read == 0xFFFFFFFF or read < ctypes.sizeof(RAWMOUSEINPUT):
        return 0
    raw = ctypes.cast(data, ctypes.POINTER(RAWMOUSEINPUT)).contents
    return (raw.mouse.buttons & 0xFFFF) if raw.header.type == 0 else 0


# ---------------------------------------------------------------- 鼠标钩子

WH_MOUSE_LL = 14
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_MOUSEMOVE = 0x0200
WM_QUIT = 0x0012


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", wintypes.POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

user32.SetWindowsHookExW.argtypes = (ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD)
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = (wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.UnhookWindowsHookEx.argtypes = (wintypes.HHOOK,)
user32.UnhookWindowsHookEx.restype = wintypes.BOOL
user32.GetMessageW.argtypes = (ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT)
user32.GetMessageW.restype = wintypes.BOOL
user32.TranslateMessage.argtypes = (ctypes.POINTER(wintypes.MSG),)
user32.TranslateMessage.restype = wintypes.BOOL
user32.DispatchMessageW.argtypes = (ctypes.POINTER(wintypes.MSG),)
user32.DispatchMessageW.restype = ctypes.c_ssize_t
user32.PostThreadMessageW.argtypes = (wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.PostThreadMessageW.restype = wintypes.BOOL


class MouseHook:
    """低级鼠标钩子。回调在钩子线程中执行，必须尽快返回。

    callback(event, x, y)：event 为 'down' | 'up' | 'dblclick' | 'move'。
    """

    def __init__(self, callback):
        self._callback = callback
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._hook = None
        self._proc = HOOKPROC(self._on_event)
        self._running = False

    def start(self) -> bool:
        if self._running:
            return True
        self._running = True
        self._thread = threading.Thread(target=self._run, name="mouse-hook", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._running = False
        if self._thread_id:
            try:
                user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            except Exception:
                pass
        self._thread = None

    def _run(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()
        self._hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._proc, None, 0)
        if not self._hook:
            self._running = False
            return
        msg = wintypes.MSG()
        try:
            while self._running and user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            try:
                user32.UnhookWindowsHookEx(self._hook)
            except Exception:
                pass
            self._hook = None

    def _on_event(self, code, wparam, lparam):
        if code >= 0 and self._running:
            try:
                info = ctypes.cast(lparam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                event = None
                if wparam == WM_LBUTTONDOWN:
                    event = "down"
                elif wparam == WM_LBUTTONUP:
                    event = "up"
                elif wparam == WM_LBUTTONDBLCLK:
                    event = "dblclick"
                elif wparam == WM_MOUSEMOVE:
                    event = "move"
                if event:
                    self._callback(event, int(info.pt.x), int(info.pt.y))
            except Exception:
                pass
        return user32.CallNextHookEx(None, code, wparam, lparam)


# ---------------------------------------------------------------- 单实例

def acquire_single_instance(name: str) -> int | None:
    """返回互斥量句柄；已有实例时返回 None。"""
    handle = kernel32.CreateMutexW(None, True, name)
    if not handle:
        return None
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        kernel32.CloseHandle(handle)
        return None
    return handle
