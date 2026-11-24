"""极简 Markdown → QTextBrowser 可渲染的 HTML。"""

from __future__ import annotations

import html
import re

_PLACEHOLDER = "\x00CODE{}\x00"

_BLOCK_CODE = re.compile(r"^```(\w*)\s*$")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_HR = re.compile(r"^\s*(-{3,}|\*{3,}|_{3,})\s*$")
_QUOTE = re.compile(r"^\s*>\s?(.*)$")
_BULLET = re.compile(r"^\s*[-*•]\s+(.*)$")
_ORDERED = re.compile(r"^\s*(\d+)[.)]\s+(.*)$")
_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_CODE_SPAN = re.compile(r"`([^`\n]+)`")
_BOLD = re.compile(r"\*\*(?!\s)(.+?)(?<!\s)\*\*")
_ITALIC = re.compile(r"(?<![*\w])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![*\w])")


def _inline(text: str) -> str:
    escaped = html.escape(text, quote=False)
    codes: list[str] = []

    def stash(match: re.Match) -> str:
        codes.append(match.group(1))
        return _PLACEHOLDER.format(len(codes) - 1)

    escaped = _CODE_SPAN.sub(stash, escaped)
    escaped = _LINK.sub(lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', escaped)
    escaped = _BOLD.sub(r"<b>\1</b>", escaped)
    escaped = _ITALIC.sub(r"<i>\1</i>", escaped)
    for index, code in enumerate(codes):
        escaped = escaped.replace(_PLACEHOLDER.format(index), f"<code>{code}</code>")
    return escaped


def render_markdown(text: str) -> str:
    """把模型输出的 Markdown 片段转成 HTML 片段。"""
    lines = (text or "").replace("\r\n", "\n").split("\n")
    out: list[str] = []
    paragraph: list[str] = []
    list_kind: str | None = None
    in_code = False
    code_buffer: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            out.append("<p>" + "<br>".join(_inline(line) for line in paragraph) + "</p>")
            paragraph = []

    def flush_list() -> None:
        nonlocal list_kind
        if list_kind:
            out.append(f"</{list_kind}>")
            list_kind = None

    for line in lines:
        fence = _BLOCK_CODE.match(line)
        if in_code:
            if fence:
                out.append("<pre><code>" + html.escape("\n".join(code_buffer)) + "</code></pre>")
                code_buffer = []
                in_code = False
            else:
                code_buffer.append(line)
            continue
        if fence:
            flush_paragraph()
            flush_list()
            in_code = True
            continue

        if not line.strip():
            flush_paragraph()
            flush_list()
            continue

        heading = _HEADING.match(line)
        if heading:
            flush_paragraph()
            flush_list()
            level = min(len(heading.group(1)) + 2, 6)
            out.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
            continue

        if _HR.match(line):
            flush_paragraph()
            flush_list()
            out.append("<hr>")
            continue

        quote = _QUOTE.match(line)
        if quote:
            flush_paragraph()
            flush_list()
            out.append(f"<blockquote>{_inline(quote.group(1))}</blockquote>")
            continue

        bullet = _BULLET.match(line)
        if bullet:
            flush_paragraph()
            if list_kind != "ul":
                flush_list()
                out.append("<ul>")
                list_kind = "ul"
            out.append(f"<li>{_inline(bullet.group(1))}</li>")
            continue

        ordered = _ORDERED.match(line)
        if ordered:
            flush_paragraph()
            if list_kind != "ol":
                flush_list()
                out.append("<ol>")
                list_kind = "ol"
            out.append(f"<li>{_inline(ordered.group(2))}</li>")
            continue

        flush_list()
        paragraph.append(line.strip())

    if in_code and code_buffer:
        out.append("<pre><code>" + html.escape("\n".join(code_buffer)) + "</code></pre>")
    flush_paragraph()
    flush_list()
    return "\n".join(out)


def document_html(body: str, font_size: int = 13, color: str = "#1e293b", muted: str = "#64748b") -> str:
    return f"""<html><head><style>
    body {{ color: {color}; font-size: {font_size}px; line-height: 158%; }}
    p {{ margin: 0 0 8px 0; }}
    h1, h2, h3, h4 {{ color: #0f172a; margin: 9px 0 4px 0; }}
    h3 {{ font-size: {font_size + 2}px; }}
    ul, ol {{ margin: 2px 0 8px 18px; }}
    li {{ margin: 2px 0; }}
    code {{ background-color: #eff6ff; color: #1d4ed8; padding: 1px 5px; border-radius: 4px; }}
    pre {{ background-color: #f8fafc; color: #0f172a; padding: 8px 10px; border: 1px solid #e2e8f0; }}
    blockquote {{ color: {muted}; border-left: 3px solid #3b82f6; padding-left: 9px; margin: 6px 0; }}
    a {{ color: #2563eb; text-decoration: none; }}
    hr {{ color: #e2e8f0; }}
    </style></head><body>{body}</body></html>"""
