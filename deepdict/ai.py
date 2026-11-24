"""DeepSeek（任意 OpenAI 兼容接口）流式客户端与提示词。"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Callable

SYSTEM_PROMPT = """你是 DeepSeek 驱动的桌面划词助手，悬浮在用户所有 Windows 应用之上。
用户从任意软件中选中一段文字，你要用尽量短的篇幅给出最有用的结果。

输出格式（Markdown，不要开场白，不要复述原文，不要写"好的"）：

**译文**：{target}译文（忠实、通顺、一句话；若原文已是{target}，则给英文译文）

如果原文是单词或短语，再补充：
- 音标 / 词性（若适用）
- 2~3 个常用义项，用「·」分隔
- 一个地道例句，后接中文解释

如果原文是句子或段落，再补充：
- 一句话说明它在当前语境里的意思或语气
- 挑 1~2 个关键表达解释（若有值得讲的）
- 若有语法、搭配或文化背景值得注意，补一句提示

规则：面向中文读者；专业术语保留英文并在括号内给中文；不确定就说不确定，不要编造；
除原文很长外，首次翻译总长度控制在 150 字以内。
若用户针对原文或译文继续追问，则直接结合上下文清晰、准确地回答追问，不受上述固定格式和 150 字限制。"""


class AIError(Exception):
    pass


def is_mock() -> bool:
    return os.environ.get("DEEPDICT_MOCK") == "1"


def build_messages(text: str, cfg: dict[str, Any], title: str = "") -> list[dict[str, str]]:
    target = str(cfg.get("target_language") or "简体中文")
    system = str(cfg.get("custom_system_prompt") or "").strip() or SYSTEM_PROMPT.replace("{target}", target)
    context = f"（来源窗口：{title}）\n\n" if title else ""
    user = f"{context}选中的文本：\n\n{text}"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _friendly_http_error(status: int, body: str, url: str) -> str:
    detail = ""
    try:
        payload = json.loads(body)
        detail = str(payload.get("error", {}).get("message") or payload.get("message") or "")
    except Exception:
        detail = (body or "").strip()[:200]
    mapping = {
        400: "请求格式不对",
        401: "API Key 无效或已过期",
        402: "账户余额不足",
        403: "没有权限访问该模型",
        404: "接口地址不存在，Base URL 应形如 https://api.deepseek.com/v1",
        422: "参数不合法",
        429: "请求太频繁，请稍后再试",
    }
    base = mapping.get(status, f"服务返回 HTTP {status}" if status < 500 else f"服务端错误 HTTP {status}")
    return f"{base}。{detail}" if detail else base


class DeepSeekClient:
    def __init__(self, cfg: dict[str, Any]):
        self.cfg = dict(cfg)

    # ------------------------------------------------------------------ 公共
    def stream(
        self,
        text: str,
        title: str = "",
        on_delta: Callable[[str], None] | None = None,
        on_reasoning: Callable[[str], None] | None = None,
        on_done: Callable[[], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        stop_event: threading.Event | None = None,
    ) -> threading.Thread:
        messages = build_messages(text, self.cfg, title)
        return self.stream_messages(
            messages,
            on_delta=on_delta,
            on_reasoning=on_reasoning,
            on_done=on_done,
            on_error=on_error,
            stop_event=stop_event,
        )

    def stream_messages(
        self,
        messages: list[dict[str, str]],
        on_delta: Callable[[str], None] | None = None,
        on_reasoning: Callable[[str], None] | None = None,
        on_done: Callable[[], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        stop_event: threading.Event | None = None,
    ) -> threading.Thread:
        snapshot = [dict(item) for item in messages]
        thread = threading.Thread(
            target=self._run_messages,
            args=(snapshot, on_delta, on_reasoning, on_done, on_error, stop_event),
            name="deepseek-stream",
            daemon=True,
        )
        thread.start()
        return thread

    def _run_messages(self, messages, on_delta, on_reasoning, on_done, on_error, stop_event):
        try:
            if is_mock():
                last_user = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")
                self._mock_stream(last_user, on_delta, on_done, stop_event, is_followup=len(messages) > 2)
            else:
                self._http_stream(messages, on_delta, on_reasoning, stop_event)
            if on_done:
                on_done()
        except AIError as exc:
            if on_error:
                on_error(str(exc))
        except Exception as exc:  # noqa: BLE001 - 任何异常都要落到 UI
            if on_error:
                on_error(f"请求失败：{exc}")

    # ------------------------------------------------------------------ 实现
    def _http_stream(self, messages, on_delta, on_reasoning, stop_event):
        import requests

        cfg = self.cfg
        base = str(cfg.get("base_url") or "").strip().rstrip("/")
        if not base:
            raise AIError("还没有配置接口地址")
        if not str(cfg.get("api_key") or "").strip():
            raise AIError("还没有配置 DeepSeek API Key，点「设置」填一个即可")
        url = f"{base}/chat/completions"
        payload = {
            "model": cfg.get("model") or "deepseek-chat",
            "messages": messages,
            "stream": True,
            "temperature": float(cfg.get("temperature", 0.2)),
            "max_tokens": int(cfg.get("max_tokens", 900)),
        }
        headers = {
            "Authorization": f"Bearer {cfg.get('api_key')}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        try:
            response = requests.post(url, headers=headers, json=payload, stream=True, timeout=(8, 120))
        except requests.exceptions.ConnectTimeout:
            raise AIError(f"连接 {base} 超时，检查网络或代理")
        except requests.exceptions.RequestException as exc:
            raise AIError(f"无法连接 {base}：{exc}")

        with response:
            if response.status_code != 200:
                raise AIError(_friendly_http_error(response.status_code, response.text, url))
            response.encoding = "utf-8"
            produced = False
            for line in response.iter_lines(decode_unicode=True):
                if stop_event is not None and stop_event.is_set():
                    return
                if not line:
                    continue
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except ValueError:
                    continue
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                reasoning = delta.get("reasoning_content")
                if reasoning and on_reasoning:
                    on_reasoning(reasoning)
                piece = delta.get("content")
                if piece:
                    produced = True
                    if on_delta:
                        on_delta(piece)
            if not produced and (stop_event is None or not stop_event.is_set()):
                raise AIError("模型没有返回内容，可能是提示词被拦截或模型名不对")

    def _mock_stream(self, text, on_delta, on_done, stop_event, is_followup: bool = False):
        if is_followup:
            demo = f"这是针对「{text[:40]}」的模拟追问回答：\n\n- 上下文已自动保留，你可以继续连续提问。"
        else:
            demo = (
                "**译文**：这是一段用于演示界面的模拟回答，没有调用真实接口。\n\n"
                "- **音标**：/ˈmɒk/ · **词性**：adj.\n"
                "- **义项**：模拟的 · 假的 · 测试用的\n"
                "- **例句**：*This is a mock response.*（这是一段模拟回答。）\n\n"
                "> 设置里填入 DeepSeek API Key 后，这里会是真实结果。"
            )
        for index in range(0, len(demo), 3):
            if stop_event is not None and stop_event.is_set():
                return
            if on_delta:
                on_delta(demo[index:index + 3])
            time.sleep(0.012)


def test_connection(cfg: dict[str, Any], timeout: float = 10.0) -> tuple[bool, str]:
    import requests

    base = str(cfg.get("base_url") or "").strip().rstrip("/")
    key = str(cfg.get("api_key") or "").strip()
    if not key:
        return False, "请先填入 API Key"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    try:
        response = requests.get(f"{base}/models", headers=headers, timeout=timeout)
        if response.status_code == 200:
            try:
                models = [m.get("id") for m in response.json().get("data", [])]
            except Exception:
                models = []
            hint = f"（可用模型：{', '.join(m for m in models[:4] if m)}）" if models else ""
            return True, f"连接成功{hint}"
        if response.status_code == 404:
            # 有些兼容服务没有 /models，用一次最小请求验证
            probe = requests.post(
                f"{base}/chat/completions",
                headers=headers,
                json={
                    "model": cfg.get("model") or "deepseek-chat",
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 1,
                    "stream": False,
                },
                timeout=timeout,
            )
            if probe.status_code == 200:
                return True, "连接成功"
            return False, _friendly_http_error(probe.status_code, probe.text, base)
        return False, _friendly_http_error(response.status_code, response.text, base)
    except requests.exceptions.RequestException as exc:
        return False, f"无法连接 {base}：{exc}"
