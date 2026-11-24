"""环境自检：deepdict --selftest（不需要打开界面，支持 Windows 与 macOS）。"""

from __future__ import annotations

import os
import sys
import time


def _line(ok: bool, label: str, detail: str = "") -> bool:
    mark = "OK  " if ok else "FAIL"
    print(f"[{mark}] {label}" + (f"  — {detail}" if detail else ""))
    return ok


def run_selftest() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    results: list[bool] = []

    print("DeepDict 自检")
    print("-" * 56)
    print(f"Platform : {sys.platform}")
    print(f"Python   : {sys.version.split()[0]} ({sys.executable})")

    deps = (
        ("PyQt5.QtWidgets", "win32clipboard", "requests", "comtypes", "uiautomation")
        if sys.platform == "win32"
        else ("PyQt5.QtWidgets", "requests", "pynput")
    )
    for module in deps:
        try:
            __import__(module)
            results.append(_line(True, f"依赖 {module}"))
        except Exception as exc:  # noqa: BLE001
            results.append(_line(False, f"依赖 {module}", str(exc)))

    try:
        from . import config as cfgmod

        cfg = cfgmod.load_config()
        results.append(_line(True, "读取配置", str(cfgmod.config_path())))
        results.append(_line(cfgmod.is_configured(cfg), "已配置 API Key", "未配置时只能界面演示"))
    except Exception as exc:  # noqa: BLE001
        results.append(_line(False, "读取配置", str(exc)))

    try:
        from . import platform_util as plat

        text = f"deepdict-selftest-{int(time.time())}"
        plat.set_clipboard_text(text)
        got = plat.get_clipboard_text()
        results.append(_line(got == text, "剪贴板读写", got or "(空)"))

        sample_key = "Cmd+Alt+Q" if plat.IS_MACOS else "Ctrl+Alt+D"
        parsed = plat.parse_hotkey(sample_key)
        results.append(_line(parsed is not None, f"解析快捷键 {sample_key}", str(parsed)))

        if plat.IS_WINDOWS:
            from . import win32util as w32

            ok = w32.register_hotkey(0, 999, "Ctrl+Alt+Shift+F12")
            w32.unregister_hotkey(0, 999)
            results.append(_line(ok, "注册全局热键（临时 id）", "若失败通常是安全软件拦截"))
            level = w32.process_integrity_level()
            results.append(_line(level not in ("Low", "Untrusted"), "进程完整性级别", level or "未知"))
    except Exception as exc:  # noqa: BLE001
        results.append(_line(False, "系统基础能力", str(exc)))

    if sys.platform == "win32":
        try:
            from . import capture as cap

            root_ok = cap.probe_uia_available()
            results.append(_line(root_ok, "UI Automation 可访问"))
        except Exception as exc:  # noqa: BLE001
            results.append(_line(False, "UI Automation", str(exc)))

    try:
        from .markdown_view import render_markdown

        html = render_markdown("**译文**：你好\n- 一条\n- 两条")
        results.append(_line("<b>" in html and "<li>" in html, "Markdown 渲染"))
    except Exception as exc:  # noqa: BLE001
        results.append(_line(False, "Markdown 渲染", str(exc)))

    print("-" * 56)
    failed = sum(1 for ok in results if not ok)
    print(f"共 {len(results)} 项，失败 {failed} 项。")
    if failed:
        print("提示：失败项若与 API Key 有关，可忽略；macOS 首次使用请授予辅助功能权限。")
    return 1 if failed else 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    raise SystemExit(run_selftest())
