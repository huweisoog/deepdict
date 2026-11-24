from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

_DEFAULT_HOTKEY = "Cmd+Alt+Q" if sys.platform == "darwin" else "Ctrl+Alt+Q"
_DEFAULT_INPUT_HOTKEY = "Cmd+Alt+S" if sys.platform == "darwin" else "Ctrl+Alt+S"

DEFAULTS: dict[str, Any] = {
    "api_key": "",
    "base_url": "https://api.deepseek.com/v1",
    "model": "deepseek-chat",
    "hotkey": _DEFAULT_HOTKEY,
    "input_hotkey": _DEFAULT_INPUT_HOTKEY,
    "target_language": "简体中文",
    "auto_bubble": True,
    "restore_clipboard": True,
    "autostart": False,
    "popup_width": 470,
    "max_selection_chars": 4000,
    "temperature": 0.2,
    "max_tokens": 900,
    "custom_system_prompt": "",
}

MODEL_PRESETS = [
    ("deepseek-chat", "DeepSeek V3（deepseek-chat，快）"),
    ("deepseek-reasoner", "DeepSeek R1（deepseek-reasoner，推理）"),
]

LANGUAGE_PRESETS = ["简体中文", "繁體中文", "English", "日本語", "한국어"]


def config_dir() -> Path:
    override = os.environ.get("DEEPDICT_CONFIG_DIR")
    if override:
        return Path(override)
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "DeepDict"
    if sys.platform != "win32":
        xdg = os.environ.get("XDG_CONFIG_HOME")
        return (Path(xdg) if xdg else Path.home() / ".config") / "deepdict"
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(base) / "DeepDict"


def config_path() -> Path:
    return config_dir() / "config.json"


def _read_key_file() -> str:
    path = config_dir() / ".env"
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            name, sep, value = line.partition("=")
            if sep and name.strip() == "DEEPDICT_API_KEY":
                value = value.strip()
                if value.startswith('"'):
                    return str(json.loads(value))
                return value
    except (OSError, ValueError):
        pass
    return ""


def load_config() -> dict[str, Any]:
    data = dict(DEFAULTS)
    path = config_path()
    legacy_key = ""
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                for key in DEFAULTS:
                    if key in raw and raw[key] is not None:
                        data[key] = raw[key]
                legacy_key = str(raw.get("api_key") or "")
        except (OSError, ValueError):
            # 配置损坏时回退到默认值，不阻塞启动
            pass
    data["api_key"] = _read_key_file() or legacy_key or os.environ.get("DEEPDICT_API_KEY") or os.environ.get("DEEPSEEK_API_KEY") or ""
    if legacy_key:
        try:
            save_config(data)
        except OSError:
            pass  # Keep the existing config and its key if migration fails.
    return data


def save_config(data: dict[str, Any]) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    payload = {k: data.get(k, DEFAULTS[k]) for k in DEFAULTS}
    key = str(payload.pop("api_key") or "")
    key_path = config_dir() / ".env"
    key_tmp = config_dir() / ".env.tmp"
    key_tmp.write_text("DEEPDICT_API_KEY=" + json.dumps(key, ensure_ascii=False) + "\n", encoding="utf-8")
    key_tmp.replace(key_path)
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def is_configured(cfg: dict[str, Any]) -> bool:
    return bool(str(cfg.get("api_key", "")).strip())
