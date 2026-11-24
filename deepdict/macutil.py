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


def frontmost_app_pid() -> int:
    try:
        from AppKit import NSWorkspace  # type: ignore[import-not-found]

        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is not None:
            return int(app.processIdentifier())
    except Exception:
        pass
    return 0


def activate_app_pid(pid: int) -> bool:
    if not pid or pid == os.getpid():
        return False
    try:
        from AppKit import (  # type: ignore[import-not-found]
            NSApplicationActivateIgnoringOtherApps,
            NSRunningApplication,
        )

        app = NSRunningApplication.runningApplicationWithProcessIdentifier_(int(pid))
        if app is not None:
            return bool(app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps))
    except Exception:
        pass
    return False


def foreground_window() -> int:
    return frontmost_app_pid()


def window_pid(hwnd: int) -> int:
    return int(hwnd) if hwnd else 0


def window_title(hwnd: int) -> str:
    try:
        from AppKit import NSRunningApplication, NSWorkspace  # type: ignore[import-not-found]

        app = (
            NSRunningApplication.runningApplicationWithProcessIdentifier_(int(hwnd))
            if hwnd
            else NSWorkspace.sharedWorkspace().frontmostApplication()
        )
        if app is not None:
            name = app.localizedName()
            if name:
                return str(name)
    except Exception:
        pass
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


def is_accessibility_trusted(prompt: bool = False) -> bool:
    try:
        import ApplicationServices  # type: ignore[import-not-found]

        if prompt and hasattr(ApplicationServices, "AXIsProcessTrustedWithOptions"):
            key = getattr(ApplicationServices, "kAXTrustedCheckOptionPrompt", "AXTrustedCheckOptionPrompt")
            return bool(ApplicationServices.AXIsProcessTrustedWithOptions({key: True}))
        return bool(ApplicationServices.AXIsProcessTrusted())
    except Exception:
        return False


def open_accessibility_settings() -> bool:
    is_accessibility_trusted(prompt=True)
    try:
        subprocess.Popen(
            ["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:
        return False


def read_selection_ax(pid: int = 0) -> str:
    """尝试通过 macOS Accessibility API 直接读取当前选中文本（不触碰剪贴板）。"""
    try:
        import ApplicationServices  # type: ignore[import-not-found]

        targets = []
        if pid and pid != os.getpid():
            targets.append(ApplicationServices.AXUIElementCreateApplication(int(pid)))
        targets.append(ApplicationServices.AXUIElementCreateSystemWide())

        for root in targets:
            err, focused = ApplicationServices.AXUIElementCopyAttributeValue(
                root, "AXFocusedUIElement", None
            )
            if err != 0 or focused is None:
                continue
            err2, selected = ApplicationServices.AXUIElementCopyAttributeValue(
                focused, "AXSelectedText", None
            )
            if err2 == 0 and isinstance(selected, str) and selected.strip():
                return selected
    except Exception:
        pass
    return ""


def _configure_cocoa_window(hwnd: int, nonactivating: bool) -> bool:
    """配置 macOS 悬浮窗口：失焦不自动隐藏、跨桌面/全屏悬浮；气泡模式启用 NonactivatingPanel 防止抢占焦点。"""
    if not hwnd:
        return False
    try:
        import AppKit  # type: ignore[import-not-found]
        import objc  # type: ignore[import-not-found]

        ns_view = objc.objc_object(c_void_p=int(hwnd))
        ns_win = ns_view.window() if ns_view is not None else None
        if ns_win is None:
            return False
        if nonactivating and isinstance(ns_win, AppKit.NSPanel):
            ns_win.setStyleMask_(ns_win.styleMask() | AppKit.NSWindowStyleMaskNonactivatingPanel)
            ns_win.setBecomesKeyOnlyIfNeeded_(True)
        ns_win.setHidesOnDeactivate_(False)
        ns_win.setLevel_(AppKit.NSFloatingWindowLevel)
        behavior = (
            AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
            | AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary
        )
        ns_win.setCollectionBehavior_(behavior)
        return True
    except Exception:
        return False


def set_window_noactivate(hwnd: int) -> bool:
    return _configure_cocoa_window(hwnd, nonactivating=True)


def configure_popup_window(hwnd: int) -> bool:
    return _configure_cocoa_window(hwnd, nonactivating=False)


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
    """发送 Cmd+C 到当前前台应用（使用纯 Quartz CGEvent，避免后台线程调用 HIToolbox 触发主线程断言崩溃）。"""
    try:
        import Quartz  # type: ignore[import-not-found]

        # kVK_ANSI_C = 8（静态虚拟键码，不调用 HIToolbox/TSMGetInputSourceProperty，后台线程安全）
        src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStatePrivate)
        down = Quartz.CGEventCreateKeyboardEvent(src, 8, True)
        up = Quartz.CGEventCreateKeyboardEvent(src, 8, False)
        if down is not None and up is not None:
            Quartz.CGEventSetFlags(down, Quartz.kCGEventFlagMaskCommand)
            Quartz.CGEventSetFlags(up, Quartz.kCGEventFlagMaskCommand)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
            time.sleep(0.02)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
            return True
    except Exception:
        pass
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
    return False


def wait_modifiers_released(timeout: float = 0.35) -> bool:
    time.sleep(min(timeout, 0.12))
    return True


# ---------------------------------------------------------------- 热键解析

# macOS Carbon/Quartz 静态虚拟键码表（避免调用 HIToolbox/TSM，后台线程安全）
_QUARTZ_MOD_BITS: dict[str, int] = {
    "SHIFT": 1 << 17,     # kCGEventFlagMaskShift
    "CTRL": 1 << 18,      # kCGEventFlagMaskControl
    "CONTROL": 1 << 18,
    "ALT": 1 << 19,       # kCGEventFlagMaskAlternate
    "OPTION": 1 << 19,
    "OPT": 1 << 19,
    "CMD": 1 << 20,       # kCGEventFlagMaskCommand
    "COMMAND": 1 << 20,
    "META": 1 << 20,
    "SUPER": 1 << 20,
    "WIN": 1 << 20,
}
_QUARTZ_RELEVANT_MODS = (1 << 17) | (1 << 18) | (1 << 19) | (1 << 20)

_MAC_KEYCODES: dict[str, int] = {
    "A": 0, "S": 1, "D": 2, "F": 3, "H": 4, "G": 5, "Z": 6, "X": 7, "C": 8, "V": 9,
    "B": 11, "Q": 12, "W": 13, "E": 14, "R": 15, "Y": 16, "T": 17,
    "1": 18, "2": 19, "3": 20, "4": 21, "6": 22, "5": 23, "=": 24, "9": 25, "7": 26,
    "-": 27, "8": 28, "0": 29, "]": 30, "O": 31, "U": 32, "[": 33, "I": 34, "P": 35,
    "ENTER": 36, "RETURN": 36, "L": 37, "J": 38, "'": 39, "K": 40, ";": 41, "\\": 42,
    ",": 43, "/": 44, "N": 45, "M": 46, ".": 47, "TAB": 48, "SPACE": 49, "`": 50,
    "BACKSPACE": 51, "ESC": 53, "ESCAPE": 53,
    "F17": 64, "F18": 79, "F19": 80, "F20": 90,
    "F5": 96, "F6": 97, "F7": 98, "F3": 99, "F8": 100, "F9": 101,
    "F11": 103, "F13": 105, "F16": 106, "F14": 107, "F10": 109, "F12": 111, "F15": 113,
    "HOME": 115, "PAGEUP": 116, "DELETE": 117, "F4": 118, "END": 119, "F2": 120,
    "PAGEDOWN": 121, "F1": 122, "LEFT": 123, "RIGHT": 124, "DOWN": 125, "UP": 126,
}


def parse_hotkey(spec: str) -> str | None:
    """'Cmd+Alt+Q' / 'Ctrl+Alt+Q' -> 规范格式 '<cmd>+<alt>+q'。"""
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


def parse_hotkey_quartz(spec: str) -> tuple[int, int] | None:
    """'Cmd+Alt+Q' -> (Quartz modifier_mask, macOS virtual_keycode)。"""
    if not spec:
        return None
    mod_mask = 0
    keycode: int | None = None
    for raw in str(spec).split("+"):
        token = raw.strip().upper()
        if not token:
            continue
        if token in _QUARTZ_MOD_BITS:
            mod_mask |= _QUARTZ_MOD_BITS[token]
        elif token in _MAC_KEYCODES:
            keycode = _MAC_KEYCODES[token]
        else:
            return None
    if keycode is None:
        return None
    return mod_mask, keycode


# ---------------------------------------------------------------- 后台监听（纯 Quartz CGEventTap）

class _QuartzTapThread:
    """使用纯 Quartz CGEventTap 在后台线程监听事件（不调用 HIToolbox，杜绝主线程断言崩溃）。"""

    def __init__(self, event_mask: int, handler) -> None:
        self._event_mask = event_mask
        self._handler = handler
        self._ready = threading.Event()
        self._started_ok = False
        self._stop_requested = False
        self._tap = None
        self._run_loop = None
        self._thread: threading.Thread | None = None

    def start(self, timeout: float = 1.5) -> bool:
        self._thread = threading.Thread(target=self._run, name="DeepDict-QuartzTap", daemon=True)
        self._thread.start()
        self._ready.wait(timeout)
        return self._started_ok

    def _run(self) -> None:
        try:
            import Quartz  # type: ignore[import-not-found]
        except Exception:
            self._ready.set()
            return

        tap_ref: list[object] = []

        def _callback(_proxy, event_type, event, _refcon):
            if event_type in (
                Quartz.kCGEventTapDisabledByTimeout,
                Quartz.kCGEventTapDisabledByUserInput,
            ):
                if tap_ref and not self._stop_requested:
                    try:
                        Quartz.CGEventTapEnable(tap_ref[0], True)
                    except Exception:
                        pass
                return event
            try:
                self._handler(event_type, event)
            except Exception:
                pass
            return event

        tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionListenOnly,
            self._event_mask,
            _callback,
            None,
        )
        if tap is None:
            self._ready.set()
            return

        tap_ref.append(tap)
        self._tap = tap
        source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
        run_loop = Quartz.CFRunLoopGetCurrent()
        self._run_loop = run_loop
        Quartz.CFRunLoopAddSource(run_loop, source, Quartz.kCFRunLoopCommonModes)
        Quartz.CGEventTapEnable(tap, True)
        self._started_ok = True
        self._ready.set()
        try:
            Quartz.CFRunLoopRun()
        finally:
            try:
                Quartz.CGEventTapEnable(tap, False)
            except Exception:
                pass

    def stop(self) -> None:
        self._stop_requested = True
        try:
            import Quartz  # type: ignore[import-not-found]

            if self._tap is not None:
                Quartz.CGEventTapEnable(self._tap, False)
            if self._run_loop is not None:
                Quartz.CFRunLoopStop(self._run_loop)
        except Exception:
            pass
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=0.5)
        self._tap = None
        self._run_loop = None
        self._thread = None


class MacInputMonitor:
    """macOS 全局热键 + 鼠标左键拖选/双击监听器（基于纯 Quartz CGEventTap，无 HIToolbox 崩溃）。"""

    def __init__(self, on_hotkey, on_mouse_down, on_mouse_up) -> None:
        self._on_hotkey = on_hotkey
        self._on_mouse_down = on_mouse_down
        self._on_mouse_up = on_mouse_up
        self._mouse_tap: _QuartzTapThread | None = None
        self._hotkey_tap: _QuartzTapThread | None = None
        self._hotkeys: dict[tuple[int, int], int] = {}
        self._lock = threading.Lock()
        self.mouse_ok = False
        self.hotkey_ok = False

    def start_mouse(self) -> bool:
        try:
            import Quartz  # type: ignore[import-not-found]
        except Exception:
            self.mouse_ok = False
            return False

        down_type = Quartz.kCGEventLeftMouseDown
        up_type = Quartz.kCGEventLeftMouseUp
        mask = (1 << down_type) | (1 << up_type)

        def _handle(event_type, event) -> None:
            loc = Quartz.CGEventGetLocation(event)
            x, y = int(loc.x), int(loc.y)
            if event_type == down_type:
                self._on_mouse_down(x, y)
            elif event_type == up_type:
                self._on_mouse_up(x, y)

        with self._lock:
            self.stop_mouse()
            tap = _QuartzTapThread(mask, _handle)
            ok = tap.start()
            if ok:
                self._mouse_tap = tap
            self.mouse_ok = ok
            return ok

    def register_hotkeys(self, mapping: dict[int, str]) -> dict[int, bool]:
        results: dict[int, bool] = {}
        try:
            import Quartz  # type: ignore[import-not-found]
        except Exception:
            self.hotkey_ok = False
            return {hid: False for hid in mapping}

        parsed_map: dict[tuple[int, int], int] = {}
        for hid, spec in mapping.items():
            parsed = parse_hotkey_quartz(spec)
            if parsed is None:
                results[hid] = False
                continue
            parsed_map[parsed] = hid
            results[hid] = True

        key_down_type = Quartz.kCGEventKeyDown
        mask = 1 << key_down_type

        def _handle(event_type, event) -> None:
            if event_type != key_down_type:
                return
            keycode = int(Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode))
            flags = int(Quartz.CGEventGetFlags(event)) & _QUARTZ_RELEVANT_MODS
            hid = self._hotkeys.get((flags, keycode))
            if hid is not None:
                self._on_hotkey(hid)

        with self._lock:
            self._hotkeys = parsed_map
            if not parsed_map:
                self.stop_hotkeys()
                self.hotkey_ok = False
                return results
            if self._hotkey_tap is not None and self.hotkey_ok:
                return results
            self.stop_hotkeys()
            tap = _QuartzTapThread(mask, _handle)
            ok = tap.start()
            if ok:
                self._hotkey_tap = tap
                self.hotkey_ok = True
            else:
                self.hotkey_ok = False
                return {hid: False for hid in mapping}
        return results

    def stop_mouse(self) -> None:
        if self._mouse_tap is not None:
            self._mouse_tap.stop()
            self._mouse_tap = None

    def stop_hotkeys(self) -> None:
        if self._hotkey_tap is not None:
            self._hotkey_tap.stop()
            self._hotkey_tap = None

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


# ---------------------------------------------------------------- macOS .app 应用包

def build_icns_bytes() -> bytes:
    """使用 PyQt5 离屏渲染生成多尺寸 macOS .icns 图标字节（遵循 Apple HIG 留白比例）。"""
    import struct

    if "QT_QPA_PLATFORM" not in os.environ:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    from PyQt5.QtCore import QBuffer, QIODevice
    from PyQt5.QtGui import QGuiApplication

    from .ui import render_macos_icon_image

    app = QGuiApplication.instance()
    created_app = None
    if app is None:
        created_app = QGuiApplication(["deepdict-icon"])

    def _render_png(size: int) -> bytes:
        img = render_macos_icon_image(size)
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        if not img.save(buf, "PNG"):
            raise RuntimeError(f"Failed to encode {size}px PNG icon")
        return bytes(buf.data())

    entries = (
        (b"icp4", 16),
        (b"icp5", 32),
        (b"icp6", 64),
        (b"ic07", 128),
        (b"ic08", 256),
        (b"ic09", 512),
        (b"ic10", 1024),
        (b"ic11", 32),
        (b"ic12", 64),
        (b"ic13", 256),
        (b"ic14", 512),
    )
    cache: dict[int, bytes] = {}
    chunks: list[bytes] = []
    for tag, size in entries:
        if size not in cache:
            cache[size] = _render_png(size)
        data = cache[size]
        chunks.append(tag + struct.pack(">I", len(data) + 8) + data)
    del created_app
    body = b"".join(chunks)
    return b"icns" + struct.pack(">I", len(body) + 8) + body


def install_app_bundle(
    python_executable: str | None = None,
    app_dir: Path | None = None,
    version: str = "0.2.0",
    icns_bytes: bytes | None = None,
) -> Path:
    """创建或更新 macOS DeepDict.app（优先写入 /Applications，无权限时回退 ~/Applications）。"""
    import shlex

    if app_dir is not None:
        target_parent = Path(app_dir)
    else:
        system_apps = Path("/Applications")
        if system_apps.is_dir() and os.access(system_apps, os.W_OK):
            target_parent = system_apps
        else:
            target_parent = Path.home() / "Applications"

    app_path = target_parent / "DeepDict.app"
    contents = app_path / "Contents"
    macos_dir = contents / "MacOS"
    resources_dir = contents / "Resources"
    macos_dir.mkdir(parents=True, exist_ok=True)
    resources_dir.mkdir(parents=True, exist_ok=True)

    info = {
        "CFBundleDevelopmentRegion": "zh_CN",
        "CFBundleDisplayName": "DeepDict",
        "CFBundleExecutable": "DeepDict",
        "CFBundleIconFile": "AppIcon",
        "CFBundleIdentifier": "com.deepdict.app",
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleName": "DeepDict",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": version,
        "CFBundleVersion": version,
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
    }
    with (contents / "Info.plist").open("wb") as handle:
        plistlib.dump(info, handle)

    py_exe = python_executable or sys.executable
    launcher = macos_dir / "DeepDict"
    launcher.write_text(
        "#!/bin/zsh\n"
        'export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"\n'
        'if [ -f "$HOME/.zprofile" ]; then\n'
        '  source "$HOME/.zprofile" >/dev/null 2>&1 || true\n'
        "fi\n"
        'if [ -f "$HOME/.zshrc" ]; then\n'
        '  source "$HOME/.zshrc" >/dev/null 2>&1 || true\n'
        "fi\n"
        f'exec {shlex.quote(py_exe)} -m deepdict "$@"\n',
        encoding="utf-8",
    )
    os.chmod(launcher, 0o755)

    icon_data = icns_bytes if icns_bytes is not None else build_icns_bytes()
    (resources_dir / "AppIcon.icns").write_bytes(icon_data)

    try:
        os.utime(app_path, None)
    except OSError:
        pass

    lsregister = Path(
        "/System/Library/Frameworks/CoreServices.framework/Frameworks/"
        "LaunchServices.framework/Support/lsregister"
    )
    if sys.platform == "darwin" and lsregister.exists():
        try:
            subprocess.run(
                [str(lsregister), "-f", str(app_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3.0,
                check=False,
            )
        except Exception:
            pass

    return app_path
