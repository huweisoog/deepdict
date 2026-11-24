import json
import os
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deepdict import ai, capture, config, macutil  # noqa: E402
from deepdict.markdown_view import render_markdown  # noqa: E402

if sys.platform == "win32":
    from deepdict import win32util  # noqa: E402
else:
    win32util = None  # type: ignore[assignment]


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("DEEPDICT_CONFIG_DIR")
        os.environ["DEEPDICT_CONFIG_DIR"] = self._tmp.name

    def tearDown(self):
        if self._old is None:
            os.environ.pop("DEEPDICT_CONFIG_DIR", None)
        else:
            os.environ["DEEPDICT_CONFIG_DIR"] = self._old
        self._tmp.cleanup()

    def test_defaults_without_file(self):
        cfg = config.load_config()
        self.assertEqual(cfg["model"], "deepseek-chat")
        expected_hotkey = "Cmd+Alt+Q" if sys.platform == "darwin" else "Ctrl+Alt+Q"
        self.assertEqual(cfg["hotkey"], expected_hotkey)
        self.assertFalse(config.is_configured(cfg))

    def test_roundtrip(self):
        cfg = config.load_config()
        cfg["api_key"] = "sk-test"
        cfg["target_language"] = "English"
        config.save_config(cfg)
        again = config.load_config()
        self.assertEqual(again["api_key"], "sk-test")
        self.assertEqual(again["target_language"], "English")
        self.assertTrue(config.is_configured(again))
        self.assertNotIn("sk-test", config.config_path().read_text(encoding="utf-8"))
        self.assertIn("sk-test", (config.config_dir() / ".env").read_text(encoding="utf-8"))

    def test_legacy_key_moves_to_env(self):
        config.config_path().write_text(json.dumps({"api_key": "sk-legacy"}), encoding="utf-8")
        self.assertEqual(config.load_config()["api_key"], "sk-legacy")
        self.assertNotIn("sk-legacy", config.config_path().read_text(encoding="utf-8"))
        self.assertIn("sk-legacy", (config.config_dir() / ".env").read_text(encoding="utf-8"))

    def test_broken_file_falls_back(self):
        path = config.config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json", encoding="utf-8")
        self.assertEqual(config.load_config()["model"], "deepseek-chat")


class TextTests(unittest.TestCase):
    def test_clean_text(self):
        raw = "  hello\r\n\r\n\r\nworld  \n\n"
        self.assertEqual(capture.clean_text(raw), "hello\n\nworld")
        self.assertEqual(capture.clean_text(None), "")

    def test_clean_text_truncates(self):
        out = capture.clean_text("x" * 50, limit=10)
        self.assertTrue(out.endswith("…"))
        self.assertEqual(len(out), 11)

    @unittest.skipUnless(sys.platform == "win32", "Windows only")
    def test_parse_hotkey(self):
        self.assertEqual(win32util.parse_hotkey("Ctrl+Alt+D"), (0x4002 | 0x0001, 0x44))
        self.assertIsNotNone(win32util.parse_hotkey("Ctrl+Shift+Space"))
        self.assertIsNotNone(win32util.parse_hotkey("F9"))
        self.assertIsNone(win32util.parse_hotkey(""))
        self.assertIsNone(win32util.parse_hotkey("Hi"))

    def test_mac_parse_hotkey(self):
        self.assertEqual(macutil.parse_hotkey("Cmd+Alt+Q"), "<cmd>+<alt>+q")
        self.assertEqual(macutil.parse_hotkey("Ctrl+Shift+Space"), "<ctrl>+<shift>+<space>")
        self.assertEqual(macutil.parse_hotkey("F9"), "<f9>")
        self.assertIsNone(macutil.parse_hotkey(""))
        self.assertIsNone(macutil.parse_hotkey("InvalidKeyName"))

    @unittest.skipUnless(sys.platform == "win32", "Windows only")
    def test_win32_64bit_signatures_and_integrity(self):
        self.assertIsNotNone(win32util.user32.CallNextHookEx.argtypes)
        self.assertIsNotNone(win32util.user32.SetWindowsHookExW.argtypes)
        self.assertIsNotNone(win32util.kernel32.CreateMutexW.restype)
        self.assertIn(win32util.process_integrity_level(), {"Untrusted", "Low", "Medium", "High", "System"})
        self.assertFalse(win32util.set_window_noactivate(0))

    def test_clipboard_settle_waits_for_multi_format_writes(self):
        seq = iter([10, 11, 12, 12, 12, 12, 12, 12, 12])
        from deepdict import platform_util

        old = platform_util.clipboard_sequence
        platform_util.clipboard_sequence = lambda: next(seq, 12)
        try:
            self.assertTrue(capture._wait_clipboard_settled(10, wait_timeout=0.5, settle_ms=0.04))
        finally:
            platform_util.clipboard_sequence = old


class MarkdownTests(unittest.TestCase):
    def test_bold_and_list(self):
        html = render_markdown("**译文**：你好\n- 第一条\n- 第二条")
        self.assertIn("<b>译文</b>", html)
        self.assertEqual(html.count("<li>"), 2)
        self.assertIn("<ul>", html)

    def test_code_and_escape(self):
        html = render_markdown("用 `<tag>` 测试\n<script>alert(1)</script>")
        self.assertIn("<code>&lt;tag&gt;</code>", html)
        self.assertNotIn("<script>", html)

    def test_heading_and_quote(self):
        html = render_markdown("## 标题\n> 引用")
        self.assertIn("<h4>标题</h4>", html)
        self.assertIn("<blockquote>引用</blockquote>", html)

    def test_link(self):
        html = render_markdown("见 [文档](https://example.com)")
        self.assertIn('href="https://example.com"', html)


class _SSEHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    pieces = ["**译", "文**：", "你好"]
    status = 200
    last_payload = None

    def log_message(self, *args):
        pass

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw_body = self.rfile.read(length)
        try:
            type(self).last_payload = json.loads(raw_body.decode("utf-8"))
        except Exception:
            type(self).last_payload = None
        if self.status != 200:
            body = json.dumps({"error": {"message": "bad key"}}).encode()
            self.send_response(self.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for piece in self.pieces:
            payload = {"choices": [{"delta": {"content": piece}}]}
            self.wfile.write(f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode())
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


class AIClientTests(unittest.TestCase):
    def _serve(self, status=200):
        handler = type("Handler", (_SSEHandler,), {"status": status})
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_address[1]}/v1"

    def _run(self, base_url):
        cfg = {"api_key": "sk-test", "base_url": base_url, "model": "deepseek-chat", "max_tokens": 50}
        chunks, errors, done = [], [], []
        client = ai.DeepSeekClient(cfg)
        client.stream(
            "hello",
            "test",
            on_delta=chunks.append,
            on_done=lambda: done.append(True),
            on_error=errors.append,
        )
        deadline = time.time() + 8
        while time.time() < deadline and not done and not errors:
            time.sleep(0.02)
        return chunks, errors, done

    def test_stream_success(self):
        chunks, errors, done = self._run(self._serve())
        self.assertEqual(errors, [])
        self.assertEqual("".join(chunks), "**译文**：你好")
        self.assertTrue(done)

    def test_stream_bad_key_message(self):
        chunks, errors, done = self._run(self._serve(status=401))
        self.assertTrue(errors)
        self.assertIn("API Key", errors[0])
        self.assertFalse(done)

    def test_build_messages_contains_target_language(self):
        msgs = ai.build_messages("hello", {"target_language": "日本語"})
        self.assertEqual(msgs[0]["role"], "system")
        self.assertIn("日本語", msgs[0]["content"])
        self.assertIn("hello", msgs[1]["content"])

    def test_followup_stream_messages_preserves_history(self):
        handler = type("FollowupHandler", (_SSEHandler,), {"status": 200, "last_payload": None})
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        base_url = f"http://127.0.0.1:{server.server_address[1]}/v1"

        cfg = {"api_key": "sk-test", "base_url": base_url, "model": "deepseek-chat", "max_tokens": 50}
        messages = ai.build_messages("Serendipity", cfg)
        messages.append({"role": "assistant", "content": "**译文**：机缘巧合"})
        messages.append({"role": "user", "content": "请再造两个学术例句"})

        chunks, errors, done = [], [], []
        client = ai.DeepSeekClient(cfg)
        client.stream_messages(
            messages,
            on_delta=chunks.append,
            on_done=lambda: done.append(True),
            on_error=errors.append,
        )
        deadline = time.time() + 8
        while time.time() < deadline and not done and not errors:
            time.sleep(0.02)
        self.assertEqual(errors, [])
        self.assertTrue(done)
        self.assertEqual("".join(chunks), "**译文**：你好")
        self.assertIsNotNone(handler.last_payload)
        self.assertEqual(len(handler.last_payload["messages"]), 4)
        self.assertEqual(handler.last_payload["messages"][-1]["content"], "请再造两个学术例句")


if __name__ == "__main__":
    unittest.main()
