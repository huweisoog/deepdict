"""应用控制器：托盘、全局热键、鼠标钩子、取词与流式请求的编排。"""

from __future__ import annotations

import ctypes
import os
import sys
import threading
import time

if sys.platform == "win32":
    from ctypes import wintypes
else:
    wintypes = None  # type: ignore[assignment]

from PyQt5.QtCore import QAbstractNativeEventFilter, QEvent, QObject, QPoint, QTimer, Qt, pyqtSignal
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from . import APP_NAME, APP_TITLE, __version__, ai
from . import capture as cap
from . import config as cfgmod
from . import platform_util as plat
from . import ui

if plat.IS_WINDOWS:
    from . import win32util as w32
    macutil = None
else:
    from . import macutil
    w32 = None  # type: ignore[assignment]

HOTKEY_TRANSLATE = 1
HOTKEY_INPUT = 2

WM_HOTKEY = 0x0312
WM_DEEPDICT_OPEN = 0x8000 + 41
CONTROL_TITLE = "DeepDict.Control.Window.v1"


def find_control_window(user32):
    """Find the hidden Qt window, including Qt's optional title suffix."""
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = (enum_proc, wintypes.LPARAM)
    user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    found = []

    @enum_proc
    def visit(hwnd, _):
        title = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, title, len(title))
        if title.value.startswith(CONTROL_TITLE):
            found.append(hwnd)
            return False
        return True

    user32.EnumWindows(visit, 0)
    return found[0] if found else None


def set_autostart(enabled: bool) -> bool:
    if not plat.IS_WINDOWS:
        return macutil.set_autostart(enabled, APP_NAME) if macutil is not None else False

    import winreg

    run_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_key, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                if getattr(sys, "frozen", False):
                    command = f'"{sys.executable}"'
                else:
                    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
                    if not os.path.exists(pythonw):
                        pythonw = sys.executable
                    command = f'"{pythonw}" "{os.path.join(base, "run.pyw")}"'
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, command)
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False


class Bridge(QObject):
    selection_ready = pyqtSignal(object, str, int)   # Selection, 用途, token
    bubble_text = pyqtSignal(str, int, int, int)     # text, x, y, token
    delta = pyqtSignal(str, int)
    reasoning = pyqtSignal(int)
    done = pyqtSignal(int, float)
    failed = pyqtSignal(str, int)
    hotkey_triggered = pyqtSignal(int)               # hotkey_id
    mouse_release = pyqtSignal(int, int, int)        # x, y, kind
    dismiss_popup = pyqtSignal(int, int)             # x, y
    mac_mouse = pyqtSignal(bool, int, int)           # down, x, y


class HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, on_hotkey, on_control, on_raw_mouse) -> None:
        super().__init__()
        self._on_hotkey = on_hotkey
        self._on_control = on_control
        self._on_raw_mouse = on_raw_mouse

    def nativeEventFilter(self, event_type, message):  # noqa: N802
        if event_type == b"windows_generic_MSG":
            try:
                msg = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
                if msg.message == WM_HOTKEY:
                    self._on_hotkey(int(msg.wParam))
                    return True, 0
                elif msg.message == WM_DEEPDICT_OPEN:
                    self._on_control(int(msg.wParam))
                    return True, 0
                elif msg.message == w32.WM_INPUT:
                    self._on_raw_mouse(w32.raw_mouse_buttons(int(msg.lParam)))
                    if int(msg.wParam) == 0:  # RIM_INPUT must be cleaned up
                        w32.user32.DefWindowProcW(msg.hWnd, msg.message, msg.wParam, msg.lParam)
                    return True, 0
            except Exception:
                pass
        return False, 0


class _AppLifecycleFilter(QObject):
    """处理 macOS 生命周期事件：程序坞右键 Quit / Cmd+Q 真正退出；点程序坞图标恢复状态窗。"""

    def __init__(self, controller) -> None:
        super().__init__(controller)
        self._controller = controller

    def eventFilter(self, obj, event):  # noqa: N802
        etype = event.type()
        if etype == QEvent.Quit:
            if not self._controller._quitting:
                self._controller.quit()
        elif etype == QEvent.ApplicationActivate:
            c = self._controller
            if (
                not c._quitting
                and hasattr(c, "status_window")
                and not c.status_window.isVisible()
                and not c.popup.isVisible()
                and not c.bubble.isVisible()
                and not c._settings_open
                and not c._input_open
            ):
                c.show_status()
        return False


class StatusWindow(QWidget):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller

    def closeEvent(self, event):  # noqa: N802
        if plat.IS_MACOS and not self.controller._quitting:
            # macOS 习惯：点红叉仅隐藏到后台，不退出应用；菜单栏或程序坞右键 Quit 才是退出
            event.ignore()
            self.hide()
            return
        event.accept()
        self.controller.quit()


class DeepDictApp(QObject):
    def __init__(self, app: QApplication, demo: bool = False) -> None:
        super().__init__()
        self.app = app
        self.demo = demo
        self._quitting = False
        self._last_source_pid = 0
        self._prompted_accessibility = False
        self.cfg = cfgmod.load_config()
        self.bridge = Bridge()
        self._sel = 0      # 选区捕获请求序号
        self._bubble_seq = 0
        self._gen = 0      # 翻译请求序号（两者分开，避免划词打断正在流式输出的结果）
        self._stop_event: threading.Event | None = None
        self._messages: list[dict[str, str]] = []
        self._current_reply = ""
        self._last_popup_pos = QPoint(0, 0)
        self._settings_open = False
        self._input_open = False
        self._hook = None
        self._mac_monitor = None
        self._down_point: tuple[int, int] | None = None
        self._down_own = False
        self._down_time = 0.0
        self._mouse_down = False
        self._last_click = (0.0, 0, 0)
        self._hwnd = 0

        self._hidden = QWidget()
        self._hidden.setWindowTitle(CONTROL_TITLE)
        self._hidden.resize(1, 1)
        if plat.IS_WINDOWS:
            self._hidden.show()
            self._hidden.hide()
            self._hwnd = int(self._hidden.winId())

        self.popup = ui.PopupWindow(self.cfg)
        self.popup.regenerate_requested.connect(self._on_regenerate)
        self.popup.followup_requested.connect(self._on_followup)
        self.popup.settings_requested.connect(self.open_settings)

        self.bubble = ui.Bubble()
        self.bubble.clicked.connect(self._on_bubble_clicked)

        self._build_tray()

        self.bridge.selection_ready.connect(self._on_selection_ready)
        self.bridge.bubble_text.connect(self._on_bubble_text)
        self.bridge.delta.connect(self._on_delta)
        self.bridge.reasoning.connect(self._on_reasoning)
        self.bridge.done.connect(self._on_done)
        self.bridge.failed.connect(self._on_failed)
        self.bridge.hotkey_triggered.connect(self._on_hotkey)
        self.bridge.mouse_release.connect(self._on_mouse_release)
        self.bridge.dismiss_popup.connect(self._on_dismiss_popup)
        self.bridge.mac_mouse.connect(self._on_mac_mouse)

        if plat.IS_WINDOWS and w32 is not None:
            self._hotkey_filter = HotkeyFilter(self._on_hotkey, self._on_control, self._on_raw_mouse)
            self.app.installNativeEventFilter(self._hotkey_filter)
            self._register_hotkeys()
            self._raw_mouse_registered = w32.register_raw_mouse(self._hwnd)
        else:
            self._hotkey_filter = None
            self._mac_monitor = (
                macutil.MacInputMonitor(
                    on_hotkey=lambda hid: self.bridge.hotkey_triggered.emit(hid),
                    on_mouse_down=self._on_mac_mouse_down,
                    on_mouse_up=self._on_mac_mouse_up,
                )
                if macutil is not None
                else None
            )
            self._register_hotkeys()
            self._raw_mouse_registered = self._mac_monitor.start_mouse() if self._mac_monitor else False
            self._lifecycle_filter = _AppLifecycleFilter(self)
            self.app.installEventFilter(self._lifecycle_filter)

        self._build_status_window()
        if not demo:
            self.show_status()

        QTimer.singleShot(400, self._first_run if not demo else lambda: None)

    # ------------------------------------------------------------------ 托盘
    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(ui.app_icon(), self)
        self.tray.setToolTip(f"{APP_TITLE} · {self.cfg.get('hotkey')}")
        menu = QMenu()
        translate_clip = QAction("翻译剪贴板", menu)
        translate_clip.triggered.connect(self.translate_clipboard)
        input_action = QAction(f"输入翻译（{self.cfg.get('input_hotkey')}）", menu)
        input_action.triggered.connect(self.show_input)
        settings_action = QAction("设置…", menu)
        settings_action.triggered.connect(self.open_settings)
        self.autostart_action = QAction("开机自启", menu)
        self.autostart_action.setCheckable(True)
        self.autostart_action.setChecked(bool(self.cfg.get("autostart")))
        self.autostart_action.triggered.connect(self._toggle_autostart)
        about_action = QAction("关于", menu)
        about_action.triggered.connect(self._about)
        quit_action = QAction("退出", menu)
        quit_action.triggered.connect(self.quit)
        menu.addAction(translate_clip)
        menu.addAction(input_action)
        menu.addSeparator()
        menu.addAction(settings_action)
        menu.addAction(self.autostart_action)
        menu.addAction(about_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self._tray_menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            self.show_status()

    def _build_status_window(self) -> None:
        self.status_window = StatusWindow(self)
        self.status_window.setWindowTitle("DeepDict")
        self.status_window.setObjectName("statusWindow")
        self.status_window.setWindowIcon(ui.dock_icon())
        self.status_window.setStyleSheet(ui.STYLE_SHEET + "QWidget#statusWindow { background: #f8fafc; }")
        self.status_window.setMinimumWidth(420)
        layout = QVBoxLayout(self.status_window)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)
        label = QLabel("DeepDict 正在运行")
        label.setObjectName("title")
        layout.addWidget(label)
        self.status_hotkeys = QLabel()
        layout.addWidget(self.status_hotkeys)
        self.mouse_status = QLabel()
        layout.addWidget(self.mouse_status)
        hint_text = (
            "选中文字后点击蓝色「译 翻译」气泡（可拖动移位），或使用快捷键。\n"
            "点窗口红叉会隐藏到后台继续运行，右键程序坞图标或顶部菜单栏可退出。"
            if plat.IS_MACOS
            else "选中文字后点击蓝色「译 翻译」气泡（可拖动移位），或使用快捷键。"
        )
        hint = QLabel(hint_text)
        hint.setObjectName("hint")
        layout.addWidget(hint)
        row = QHBoxLayout()
        buttons = [("输入翻译", self.show_input), ("设置", self.open_settings)]
        if plat.IS_MACOS and macutil is not None and not macutil.is_accessibility_trusted():
            buttons.append(("授权辅助功能", self._request_accessibility))
        buttons.append(("退出 DeepDict", self.quit))
        for idx, (title, handler) in enumerate(buttons):
            button = QPushButton(title)
            if idx == 0:
                button.setObjectName("primary")
            button.clicked.connect(handler)
            row.addWidget(button)
        layout.addLayout(row)
        self._update_status()

    def _request_accessibility(self) -> None:
        if macutil is not None:
            macutil.open_accessibility_settings()

    def _update_status(self) -> None:
        self.status_hotkeys.setText(f"划词：{self.cfg.get('hotkey')}    输入：{self.cfg.get('input_hotkey')}")
        integrity = plat.process_integrity_level()
        if plat.IS_MACOS:
            trusted = macutil.is_accessibility_trusted() if macutil is not None else False
            if not self._raw_mouse_registered:
                mouse_text = "划词气泡：未启动（请在系统设置授予辅助功能 / 输入监控权限后重启）"
            elif not trusted:
                mouse_text = "划词气泡：已启动（未获「辅助功能」权限，点「授权辅助功能」后重启即可取词）"
            else:
                mouse_text = "划词气泡：已启动（辅助功能权限已就绪）"
        elif not self._raw_mouse_registered:
            mouse_text = "划词气泡：鼠标监听启动失败"
        elif integrity in ("Low", "Untrusted"):
            mouse_text = f"划词气泡：已启动（警告：当前进程权限为 {integrity}，后台划词会被系统拦截）"
        elif integrity:
            mouse_text = f"划词气泡：已启动（进程权限：{integrity}）"
        else:
            mouse_text = "划词气泡：已启动"
        self.mouse_status.setText(mouse_text)

    def show_status(self) -> None:
        self._update_status()
        self.status_window.showNormal()
        self.status_window.raise_()
        self.status_window.activateWindow()

    def _on_control(self, action: int) -> None:
        if action == 1:
            self.show_input()
        elif action == 2:
            self.open_settings()
        elif action == 3:
            self.quit()
        elif action == 4:
            self.show_status()

    def _about(self) -> None:
        QMessageBox.information(
            None,
            "关于 DeepDict",
            f"DeepDict {__version__}\n\n"
            "全局划词 → DeepSeek 译释。\n"
            "取词：UI Automation 优先，Ctrl+C 兜底；控制台自动跳过。\n\n"
            f"划词：{self.cfg.get('hotkey')}    输入翻译：{self.cfg.get('input_hotkey')}\n"
            f"配置：{cfgmod.config_path()}",
        )

    def _toggle_autostart(self, checked: bool) -> None:
        ok = set_autostart(checked)
        self.cfg["autostart"] = checked and ok
        cfgmod.save_config(self.cfg)
        if not ok:
            self.tray.showMessage(APP_TITLE, "写入开机启动项失败", QSystemTrayIcon.Warning)

    # ------------------------------------------------------------------ 热键
    def _register_hotkeys(self) -> None:
        if not plat.IS_WINDOWS:
            if self._mac_monitor is not None:
                self._mac_monitor.register_hotkeys(
                    {
                        HOTKEY_TRANSLATE: str(self.cfg.get("hotkey", "")),
                        HOTKEY_INPUT: str(self.cfg.get("input_hotkey", "")),
                    }
                )
            return
        assert w32 is not None
        w32.unregister_hotkey(self._hwnd, HOTKEY_TRANSLATE)
        w32.unregister_hotkey(self._hwnd, HOTKEY_INPUT)
        self._register_one(
            HOTKEY_TRANSLATE,
            "hotkey",
            ["Ctrl+Alt+Q", "Ctrl+Alt+Z", "Ctrl+Shift+Q", "Alt+Q", "Ctrl+Alt+W"],
            "划词",
        )
        self._register_one(
            HOTKEY_INPUT,
            "input_hotkey",
            ["Ctrl+Alt+S", "Ctrl+Alt+E", "Ctrl+Shift+S", "Alt+S"],
            "输入翻译",
        )

    def _register_one(self, hotkey_id: int, key: str, alternates: list[str], label: str) -> None:
        wanted = str(self.cfg.get(key, ""))
        if w32.register_hotkey(self._hwnd, hotkey_id, wanted):
            return
        for alt in alternates:
            if alt == wanted:
                continue
            if w32.register_hotkey(self._hwnd, hotkey_id, alt):
                self.cfg[key] = alt
                cfgmod.save_config(self.cfg)
                self.tray.showMessage(
                    APP_TITLE,
                    f"{label}快捷键 {wanted} 被其他软件占用，已自动改用 {alt}（可在设置里修改）。",
                    QSystemTrayIcon.Warning,
                    4000,
                )
                return
        self.tray.showMessage(
            APP_TITLE,
            f"{label}快捷键 {wanted} 注册失败，请到设置里换一个组合键。",
            QSystemTrayIcon.Warning,
            4000,
        )

    def _on_hotkey(self, hotkey_id: int) -> None:
        if hotkey_id == HOTKEY_TRANSLATE:
            self.translate_selection()
        elif hotkey_id == HOTKEY_INPUT:
            self.show_input()

    # ------------------------------------------------------------------ 取词
    def translate_selection(self, purpose: str = "hotkey", source_pid: int = 0) -> None:
        self._sel += 1
        token = self._sel
        if plat.IS_MACOS and not source_pid:
            cur = plat.foreground_window()
            if cur and not plat.is_own_pid(cur):
                source_pid = cur
            else:
                source_pid = self._last_source_pid
        threading.Thread(
            target=self._capture_worker, args=(token, purpose, source_pid), daemon=True
        ).start()

    def _capture_worker(self, token: int, purpose: str = "hotkey", source_pid: int = 0) -> None:
        text = ""
        try:
            if plat.IS_WINDOWS:
                import comtypes

                comtypes.CoInitialize()
            try:
                sel = cap.capture_selection(
                    limit=int(self.cfg.get("max_selection_chars", 4000)),
                    restore_clipboard=bool(self.cfg.get("restore_clipboard", True)),
                    source_pid=source_pid,
                )
                text = sel.text
                self.bridge.selection_ready.emit(sel, purpose, token)
            finally:
                if plat.IS_WINDOWS:
                    comtypes.CoUninitialize()
        except Exception:
            if not text:
                self.bridge.selection_ready.emit(cap.Selection(text=""), purpose, token)

    def _on_selection_ready(self, sel, purpose: str, token: int) -> None:
        if token != self._sel:
            return
        if not sel.text:
            if plat.IS_MACOS and macutil is not None and not macutil.is_accessibility_trusted():
                box = QMessageBox(self.status_window)
                box.setIcon(QMessageBox.Warning)
                box.setWindowTitle("需要 macOS 辅助功能权限")
                box.setText("未能读取选中文字：当前尚未授予 DeepDict「辅助功能」权限。")
                box.setInformativeText(
                    "点击「打开系统设置」后，系统会把对应进程加入「隐私与安全性 → 辅助功能」列表，"
                    "勾选开启并重启 DeepDict 即可正常划词翻译。"
                )
                open_btn = box.addButton("打开系统设置", QMessageBox.AcceptRole)
                box.addButton("稍后再说", QMessageBox.RejectRole)
                box.exec_()
                if box.clickedButton() == open_btn:
                    macutil.open_accessibility_settings()
                return
            self.tray.showMessage(
                APP_TITLE,
                "没有取到选中文字。请先在任意应用里选中文本；或使用「输入翻译」。",
                QSystemTrayIcon.Information,
                2500,
            )
            if purpose == "hotkey":
                self.show_input()
            else:
                pos = QCursor.pos()
                self.popup.begin("（未检测到选中的文字）", "提示", "")
                self.popup.fail("当前应用未返回选中内容，请确认已选中文字或先按 Cmd+C 后点菜单栏「翻译剪贴板」。")
                self.popup.show_near(pos.x(), pos.y())
            return
        # 弹窗定位用 Qt 的逻辑坐标（已经过 DPI 换算），避免高缩放下偏移
        pos = QCursor.pos()
        self._start_translation(sel.text, sel.source, sel.title, pos.x(), pos.y())

    # ------------------------------------------------------------------ 气泡
    def _on_mac_mouse_down(self, x: int, y: int) -> None:
        self.bridge.mac_mouse.emit(True, x, y)

    def _on_mac_mouse_up(self, x: int, y: int) -> None:
        self.bridge.mac_mouse.emit(False, x, y)

    def _on_mac_mouse(self, down: bool, x: int, y: int) -> None:
        self._mouse_transition(down, pos=(x, y))

    def _on_raw_mouse(self, flags: int) -> None:
        assert w32 is not None
        if flags & w32.RI_MOUSE_LEFT_BUTTON_DOWN:
            self._mouse_transition(True)
        if flags & w32.RI_MOUSE_LEFT_BUTTON_UP:
            self._mouse_transition(False)

    def _mouse_transition(self, down: bool, pos: tuple[int, int] | None = None) -> None:
        if down == self._mouse_down:
            return
        self._mouse_down = down
        x, y = pos if pos is not None else plat.cursor_pos()
        now = time.monotonic()
        if down:
            self._hook_callback("down", x, y)
            return
        start = self._down_point
        previous_time, previous_x, previous_y = self._last_click
        is_double = now - previous_time <= 0.5 and abs(x - previous_x) <= 6 and abs(y - previous_y) <= 6
        self._hook_callback("up", x, y)
        if start and is_double and (x - start[0]) ** 2 + (y - start[1]) ** 2 < 36:
            self._hook_callback("dblclick", x, y)
            self._last_click = (0.0, 0, 0)
        else:
            self._last_click = (now, x, y)

    def _is_point_in_own_window(self, x: int, y: int) -> bool:
        if plat.IS_WINDOWS:
            hwnd = plat.window_from_point(x, y)
            return bool(hwnd and plat.is_own_pid(plat.window_pid(plat.root_window(hwnd))))
        pt = QPoint(x, y)
        for widget in (self.bubble, self.popup, getattr(self, "status_window", None)):
            if widget is not None and widget.isVisible() and widget.frameGeometry().contains(pt):
                return True
        return False

    def _hook_callback(self, event: str, x: int, y: int) -> None:
        if event == "down":
            self._down_own = self._is_point_in_own_window(x, y)
            self._down_point = (x, y)
            self._down_time = time.time()
            self.bridge.dismiss_popup.emit(x, y)
        elif event == "up":
            down = self._down_point
            down_own = self._down_own
            self._down_point = None
            self._down_own = False
            if down_own or not down or not self.cfg.get("auto_bubble", True):
                return
            dx, dy = x - down[0], y - down[1]
            if dx * dx + dy * dy >= 36:
                self.bridge.mouse_release.emit(x, y, 0)
        elif event == "dblclick":
            if not self._down_own and self.cfg.get("auto_bubble", True):
                self.bridge.mouse_release.emit(x, y, 1)

    def _on_mouse_release(self, x: int, y: int, kind: int) -> None:
        if not self.cfg.get("auto_bubble", True):
            return
        if kind == 0:
            QTimer.singleShot(170, lambda: self._try_bubble(x, y))
        else:
            QTimer.singleShot(210, lambda: self._try_bubble(x, y))

    def _on_dismiss_popup(self, x: int, y: int) -> None:
        pos = QCursor.pos()
        if self.bubble.isVisible() and not self.bubble.frameGeometry().contains(pos):
            self.bubble.hide()
        if not self.popup.isVisible() or self.popup.is_pinned():
            return
        if self.popup.frameGeometry().contains(pos):
            return
        self.popup.hide()

    def _try_bubble(self, x: int, y: int) -> None:
        if self._is_point_in_own_window(x, y):
            return
        hwnd = plat.window_from_point(x, y) if plat.IS_WINDOWS else 0
        if plat.IS_MACOS:
            src_pid = plat.foreground_window()
            if src_pid and not plat.is_own_pid(src_pid):
                self._last_source_pid = src_pid
        pos = QCursor.pos()
        if self.popup.isVisible() and self.popup.frameGeometry().contains(pos):
            return
        self._bubble_seq += 1
        token = self._bubble_seq
        # Show an actionable bubble immediately, even when the application
        # does not expose its selection through UI Automation / Accessibility.
        # A click can then use the existing explicit copy fallback if necessary.
        self.bubble.show_for("", pos.x(), pos.y(), 6000)
        if plat.IS_WINDOWS and not cap.should_skip_uia(plat.root_window(hwnd) if hwnd else 0):
            threading.Thread(target=self._bubble_worker, args=(pos.x(), pos.y(), token, x, y), daemon=True).start()
        elif plat.IS_MACOS:
            threading.Thread(
                target=self._bubble_worker_mac,
                args=(pos.x(), pos.y(), token, self._last_source_pid),
                daemon=True,
            ).start()

    def _bubble_worker(self, x: int, y: int, token: int, physical_x: int, physical_y: int) -> None:
        try:
            import comtypes

            comtypes.CoInitialize()
            try:
                text = cap.read_selection_uia(limit=2000, point=(physical_x, physical_y))
            finally:
                comtypes.CoUninitialize()
            if text:
                self.bridge.bubble_text.emit(text, x, y, token)
        except Exception:
            pass

    def _bubble_worker_mac(self, x: int, y: int, token: int, source_pid: int) -> None:
        try:
            text = cap.clean_text(plat.read_selection_ax(source_pid), 2000)
            if text:
                self.bridge.bubble_text.emit(text, x, y, token)
        except Exception:
            pass

    def _on_bubble_text(self, text: str, x: int, y: int, token: int) -> None:
        if token != self._bubble_seq:
            return
        if not text.strip():
            return
        if self.bubble.isVisible():
            self.bubble._text = text

    def _on_bubble_clicked(self, text: str) -> None:
        self._bubble_seq += 1
        if not text:
            self.translate_selection(purpose="bubble", source_pid=self._last_source_pid)
            return
        pos = self.bubble.pos()
        x = pos.x() + self.bubble.width() + 2
        y = pos.y() - 6
        self._start_translation(text, "划词", "", x, y)

    # ------------------------------------------------------------------ 翻译
    def _stream_current_messages(self, token: int) -> None:
        started = time.time()
        client = ai.DeepSeekClient(self.cfg)
        client.stream_messages(
            self._messages,
            on_delta=lambda delta: self.bridge.delta.emit(delta, token),
            on_reasoning=lambda _reason: self.bridge.reasoning.emit(token),
            on_done=lambda: self.bridge.done.emit(token, time.time() - started),
            on_error=lambda message: self.bridge.failed.emit(message, token),
            stop_event=self._stop_event,
        )

    def _start_translation(self, text: str, source: str, title: str, x: int, y: int) -> None:
        self._gen += 1
        token = self._gen
        if self._stop_event is not None:
            self._stop_event.set()
        self._stop_event = threading.Event()
        self._messages = ai.build_messages(text, self.cfg, title)
        self._current_reply = ""
        self._last_popup_pos = QPoint(x, y)
        self.popup.begin(text, source, title)
        self.popup.show_near(x, y)
        self._stream_current_messages(token)

    def _on_followup(self, question: str) -> None:
        question = question.strip()
        if not question or not self._messages:
            return
        self._gen += 1
        token = self._gen
        if self._stop_event is not None:
            self._stop_event.set()
        self._stop_event = threading.Event()
        if self._current_reply and self._messages[-1].get("role") != "assistant":
            self._messages.append({"role": "assistant", "content": self._current_reply})
        self._messages.append({"role": "user", "content": question})
        self._current_reply = ""
        self.popup.begin_followup(question)
        self._stream_current_messages(token)

    def _on_regenerate(self, text: str) -> None:
        pos = self.popup.pos()
        self._start_translation(text, "重试", "", pos.x() + 60, pos.y() + 40)

    def translate_clipboard(self) -> None:
        text = plat.get_clipboard_text()
        text = cap.clean_text(text, int(self.cfg.get("max_selection_chars", 4000)))
        if not text:
            self.tray.showMessage(APP_TITLE, "剪贴板里没有文本", QSystemTrayIcon.Information, 2000)
            return
        pos = QCursor.pos()
        self._start_translation(text, "剪贴板", "", pos.x(), pos.y())

    def _on_delta(self, delta: str, token: int) -> None:
        if token != self._gen:
            return
        self._current_reply += delta
        self.popup.append(delta)

    def _on_reasoning(self, token: int) -> None:
        if token != self._gen:
            return
        self.popup.note_reasoning()

    def _on_done(self, token: int, elapsed: float) -> None:
        if token != self._gen:
            return
        if self._current_reply:
            self._messages.append({"role": "assistant", "content": self._current_reply})
        self.popup.finish()

    def _on_failed(self, message: str, token: int) -> None:
        if token != self._gen:
            return
        if len(self._messages) > 2 and self._messages[-1].get("role") == "user":
            self._messages.pop()
        self.popup.fail(message)

    # ------------------------------------------------------------------ 输入框 / 设置
    def show_input(self) -> None:
        if self._input_open:
            return
        self._input_open = True
        dialog = ui.InputDialog()
        dialog.submitted.connect(self._on_input_submitted)
        dialog.exec_()
        self._input_open = False

    def _on_input_submitted(self, text: str) -> None:
        pos = QCursor.pos()
        self._start_translation(text, "输入", "", pos.x(), pos.y())

    def open_settings(self) -> None:
        if self._settings_open:
            return
        self._settings_open = True
        dialog = ui.SettingsDialog(self.cfg)
        if dialog.exec_() == QDialog.Accepted:
            self.cfg = dialog.cfg
            cfgmod.save_config(self.cfg)
            self._register_hotkeys()
            self.popup.cfg = dict(self.cfg)
            self.popup.set_model(str(self.cfg.get("model")))
            set_autostart(bool(self.cfg.get("autostart")))
            self.autostart_action.setChecked(bool(self.cfg.get("autostart")))
            self.tray.setToolTip(f"{APP_TITLE} · {self.cfg.get('hotkey')}")
            self._update_status()
        self._settings_open = False

    def _first_run(self) -> None:
        if not cfgmod.is_configured(self.cfg):
            self.tray.showMessage(
                APP_TITLE,
                "先填一个 DeepSeek API Key 即可开始使用。",
                QSystemTrayIcon.Information,
                3000,
            )
            self.open_settings()

    def show_demo(self) -> None:
        """不调用真实接口，演示一次结果卡片（--demo 启动时用）。"""
        pos = QCursor.pos()
        self._start_translation(
            "Serendipity is the occurrence of events by chance in a happy or beneficial way. "
            "It explains why so many discoveries were accidental.",
            "示例",
            "",
            pos.x() + 40,
            pos.y() + 40,
        )

    # ------------------------------------------------------------------ 退出
    def quit(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        try:
            if plat.IS_WINDOWS and w32 is not None:
                if self._raw_mouse_registered:
                    w32.unregister_raw_mouse()
                if self._hook:
                    self._hook.stop()
                w32.unregister_hotkey(self._hwnd, HOTKEY_TRANSLATE)
                w32.unregister_hotkey(self._hwnd, HOTKEY_INPUT)
            elif self._mac_monitor is not None:
                self._mac_monitor.stop()
            self.tray.hide()
            self.status_window.hide()
        finally:
            self.app.quit()


def _log_exception(exc_type, exc_value, exc_tb) -> None:
    """pythonw 下没有控制台，把未捕获异常写到配置目录，便于排查。"""
    import traceback

    try:
        path = cfgmod.config_dir() / "error.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(time.strftime("[%Y-%m-%d %H:%M:%S]\n"))
            handle.write("".join(traceback.format_exception(exc_type, exc_value, exc_tb)))
            handle.write("\n")
    except Exception:
        pass


def _print_help() -> None:
    print(
        f"{APP_NAME} {__version__} — 全局划词 + DeepSeek 桌面翻译与多轮追问助手\n\n"
        "用法:\n"
        "  deepdict [选项]\n\n"
        "选项:\n"
        "  -h, --help             显示此帮助信息\n"
        "  -V, --version          显示版本号\n"
        "  --selftest             运行环境自检（不打开窗口）\n"
        "  --demo                 演示模式（不调用真实接口）\n"
        "  --install-app          创建/更新 macOS 应用程序图标（DeepDict.app）\n"
        "  --config-dir=<路径>    指定配置文件目录\n"
    )


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    if "-h" in argv or "--help" in argv:
        _print_help()
        return 0
    if "-V" in argv or "--version" in argv:
        print(f"{APP_NAME} {__version__}")
        return 0
    for arg in argv:
        if arg.startswith("--config-dir="):
            os.environ["DEEPDICT_CONFIG_DIR"] = arg.split("=", 1)[1]
    if "--install-app" in argv:
        if not plat.IS_MACOS or macutil is None:
            print("--install-app 仅用于 macOS。")
            return 1
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        app_path = macutil.install_app_bundle(version=__version__)
        print(f"已创建 macOS 应用图标：{app_path}")
        return 0
    if "--selftest" in argv:
        from .selftest import run_selftest

        return run_selftest()

    if "--mock" in argv:
        os.environ["DEEPDICT_MOCK"] = "1"
    if "--demo" in argv:
        os.environ["DEEPDICT_MOCK"] = "1"

    plat.enable_dpi_awareness()
    sys.excepthook = _log_exception
    threading.excepthook = lambda args: _log_exception(args.exc_type, args.exc_value, args.exc_traceback)
    if hasattr(Qt, "HighDpiScaleFactorRoundingPolicy"):
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    # 自定义参数不要传给 Qt，避免解析告警
    qt_argv = [item for item in argv if not item.startswith("--")] or [argv[0]]
    app = QApplication(qt_argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_TITLE)
    app.setWindowIcon(ui.dock_icon())
    app.setFont(ui.default_font())

    mutex = plat.acquire_single_instance("DeepDict.SingleInstance.v1")
    if mutex is None:
        if plat.IS_WINDOWS and wintypes is not None:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
            user32.PostMessageW.restype = wintypes.BOOL
            hwnd = find_control_window(user32)
            if not hwnd or not user32.PostMessageW(hwnd, WM_DEEPDICT_OPEN, 4, 0):
                QMessageBox.warning(None, APP_TITLE, "无法联系已运行的 DeepDict，请通过任务栏托盘退出后重试。")
        else:
            QMessageBox.information(None, APP_TITLE, "DeepDict 已在运行中，请查看顶部菜单栏图标。")
        return 0

    controller = DeepDictApp(app, demo="--demo" in argv)
    app._controller = controller  # type: ignore[attr-defined]
    app._instance_lock = mutex    # type: ignore[attr-defined]
    if "--demo" in argv:
        QTimer.singleShot(1200, controller.show_demo)
    return app.exec_()
