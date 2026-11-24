"""界面：划词气泡、结果弹窗、设置、输入翻译。"""

from __future__ import annotations

import ctypes
import html
import sys
import time

if sys.platform == "win32":
    from ctypes import wintypes
else:
    wintypes = None  # type: ignore[assignment]

from PyQt5.QtCore import QPoint, QSize, Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QIcon,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPixmap,
)
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import ai
from . import config as cfgmod
from . import platform_util as plat
from .markdown_view import document_html, render_markdown

if plat.IS_WINDOWS:
    from . import win32util as w32
else:
    w32 = None  # type: ignore[assignment]

CARD_BG = "#ffffff"
CARD_BORDER = "#dbe4f0"
HEADER_BG = "#f8fafc"
TEXT = "#1e293b"
TITLE_TEXT = "#0f172a"
MUTED = "#64748b"
ACCENT = "#2563eb"
ACCENT_HI = "#3b82f6"
ACCENT_SOFT = "#eff6ff"
DANGER = "#dc2626"

STYLE_SHEET = f"""
QWidget {{ color: {TEXT}; font-family: "PingFang SC", "Microsoft YaHei UI", "Segoe UI", sans-serif; }}
QFrame#card {{ background: {CARD_BG}; border: 1px solid {CARD_BORDER}; border-radius: 14px; }}
QFrame#headerBar {{
    background: {HEADER_BG};
    border-top-left-radius: 13px;
    border-top-right-radius: 13px;
    border-bottom: 1px solid #eef2f7;
}}
QLabel#logoBadge {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #3b82f6, stop:1 #2563eb);
    color: #ffffff;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 700;
}}
QLabel#title {{ font-size: 13px; font-weight: 600; color: {TITLE_TEXT}; }}
QLabel#badge {{ color: {ACCENT}; background: {ACCENT_SOFT}; border: 1px solid #dbeafe; border-radius: 8px; padding: 1px 8px; font-size: 10px; font-weight: 600; }}
QLabel#orig {{
    color: #475569;
    background: #f8fafc;
    border: 1px solid #eef2f7;
    border-left: 3px solid {ACCENT_HI};
    border-radius: 8px;
    padding: 7px 10px;
    font-size: 12px;
}}
QLabel#status {{ color: {MUTED}; font-size: 11px; }}
QTextBrowser#answer {{ background: transparent; border: none; selection-background-color: #bfdbfe; selection-color: #0f172a; }}
QScrollBar:vertical {{ background: transparent; width: 6px; margin: 2px 0; }}
QScrollBar::handle:vertical {{ background: #cbd5e1; border-radius: 3px; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: #94a3b8; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
QToolButton {{ background: transparent; border: none; color: {MUTED}; padding: 3px 7px; border-radius: 6px; font-size: 12px; }}
QToolButton:hover {{ background: #eef2f7; color: {TITLE_TEXT}; }}
QToolButton:checked {{ color: {ACCENT}; background: {ACCENT_SOFT}; font-weight: 600; }}
QPushButton {{ background: #ffffff; border: 1px solid #cbd5e1; border-radius: 8px; padding: 5px 14px; font-size: 12px; color: {TEXT}; }}
QPushButton:hover {{ background: #f1f5f9; border-color: #94a3b8; }}
QPushButton#primary {{ background: {ACCENT}; border: none; color: white; font-weight: 600; }}
QPushButton#primary:hover {{ background: {ACCENT_HI}; }}
QProgressBar {{ background: #eff6ff; border: none; max-height: 3px; border-radius: 1px; }}
QProgressBar::chunk {{ background: {ACCENT_HI}; border-radius: 1px; }}
QLineEdit, QPlainTextEdit, QComboBox, QKeySequenceEdit {{
    background: #ffffff; border: 1px solid #cbd5e1; border-radius: 7px; padding: 5px 8px; font-size: 12px;
    color: {TEXT}; selection-background-color: #bfdbfe; selection-color: #0f172a;
}}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QKeySequenceEdit:focus {{ border-color: {ACCENT_HI}; }}
QComboBox QAbstractItemView {{ background: #ffffff; color: {TEXT}; selection-background-color: {ACCENT_SOFT}; selection-color: {ACCENT}; border: 1px solid #cbd5e1; }}
QCheckBox {{ font-size: 12px; spacing: 6px; color: {TEXT}; }}
QDialog {{ background: #f8fafc; }}
QLabel#section {{ color: {ACCENT}; font-size: 11px; font-weight: 700; padding-top: 6px; }}
QLabel#hint {{ color: {MUTED}; font-size: 11px; }}
"""


def app_icon(size: int = 64) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0.5, 0.5, size - 1, size - 1, size * 0.26, size * 0.26)
    gradient = QLinearGradient(0, 0, size, size)
    gradient.setColorAt(0.0, QColor("#6b86ff"))
    gradient.setColorAt(1.0, QColor("#3a54d6"))
    painter.fillPath(path, gradient)
    painter.setPen(QColor(255, 255, 255, 235))
    font = QFont("Microsoft YaHei UI")
    font.setPixelSize(int(size * 0.52))
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "译")
    painter.end()
    return QIcon(pixmap)


class Bubble(QWidget):
    """选中文字后出现在光标旁的蓝色悬浮胶囊按钮（支持点击翻译与直接拖动移位）。"""

    clicked = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.NoFocus)
        # 四周预留 8px 透明阴影边距，胶囊本体 96×34
        self.setFixedSize(112, 50)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("点击翻译选中内容（可按住拖动位置）")
        self._text = ""
        self._hover = False
        self._pressed = False
        self._press_global: QPoint | None = None
        self._drag_origin: QPoint | None = None
        self._dragging = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        if plat.IS_WINDOWS:
            plat.set_window_noactivate(int(self.winId()))

    def nativeEvent(self, event_type, message):  # noqa: N802
        if plat.IS_WINDOWS and w32 is not None and wintypes is not None and event_type == b"windows_generic_MSG":
            try:
                msg = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
                if msg.message == w32.WM_MOUSEACTIVATE:
                    return True, w32.MA_NOACTIVATE
            except Exception:
                pass
        return super().nativeEvent(event_type, message)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 柔和多层外阴影，避免生硬边缘
        for dy, spread, alpha in ((4, 3, 22), (2, 1, 34)):
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(37, 99, 235, alpha))
            painter.drawRoundedRect(8 - spread, 6 + dy - spread, 96 + spread * 2, 34 + spread * 2, 17 + spread, 17 + spread)

        # 宝石蓝渐变胶囊本体
        pill = (8, 6, 96, 34)
        gradient = QLinearGradient(8, 6, 104, 40)
        if self._pressed:
            gradient.setColorAt(0.0, QColor("#2563eb"))
            gradient.setColorAt(1.0, QColor("#1d4ed8"))
        elif self._hover:
            gradient.setColorAt(0.0, QColor("#4f8ff9"))
            gradient.setColorAt(1.0, QColor("#2563eb"))
        else:
            gradient.setColorAt(0.0, QColor("#3b82f6"))
            gradient.setColorAt(1.0, QColor("#2563eb"))

        painter.setBrush(gradient)
        painter.setPen(QColor(255, 255, 255, 90))
        painter.drawRoundedRect(*pill, 17, 17)

        # 左侧白色圆形徽章「译」
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 240))
        painter.drawEllipse(14, 12, 22, 22)

        badge_font = QFont("Microsoft YaHei UI")
        badge_font.setPixelSize(12)
        badge_font.setBold(True)
        painter.setFont(badge_font)
        painter.setPen(QColor("#2563eb"))
        painter.drawText(14, 12, 22, 22, Qt.AlignCenter, "译")

        # 右侧「翻译」文案
        label_font = QFont("Microsoft YaHei UI")
        label_font.setPixelSize(13)
        label_font.setBold(True)
        painter.setFont(label_font)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(40, 6, 48, 34, Qt.AlignCenter, "翻译")

        # 最右侧极细拖拽圆点提示（方便直观知道可拖）
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 130))
        for dx in (89, 93):
            for dy in (18, 22, 26):
                painter.drawEllipse(dx, dy, 2, 2)

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._pressed = True
            self._dragging = False
            self._press_global = event.globalPos()
            self._drag_origin = self.pos()
            self._timer.stop()
            self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._press_global is not None and self._drag_origin is not None and (event.buttons() & Qt.LeftButton):
            delta = event.globalPos() - self._press_global
            if not self._dragging and (abs(delta.x()) + abs(delta.y())) >= 5:
                self._dragging = True
                self.setCursor(Qt.ClosedHandCursor)
            if self._dragging:
                self.move(self._drag_origin + delta)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            was_dragging = self._dragging
            self._pressed = False
            self._dragging = False
            self._press_global = None
            self._drag_origin = None
            self.setCursor(Qt.PointingHandCursor)
            self.update()
            if was_dragging:
                self._timer.start(6000)
                return
            text = self._text
            self.hide()
            self.clicked.emit(text)

    def show_for(self, text: str, x: int, y: int, duration_ms: int = 3500) -> None:
        self._text = text
        self._pressed = False
        self._dragging = False
        screen = QGuiApplication.screenAt(QPoint(x, y)) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        # 避开 Adobe / Edge / 其他划词工具默认紧贴光标的工具栏位置，往右下方多错开一点
        pos_x = x + 26
        if pos_x + self.width() > area.right():
            pos_x = x - self.width() - 18
        pos_y = y + 32
        if pos_y + self.height() > area.bottom():
            pos_y = y - self.height() - 26
        pos_x = min(max(pos_x, area.left()), area.right() - self.width())
        pos_y = min(max(pos_y, area.top()), area.bottom() - self.height())
        self.move(pos_x, pos_y)
        if plat.IS_WINDOWS:
            plat.set_window_noactivate(int(self.winId()))
        self.show()
        if plat.IS_MACOS:
            plat.set_window_noactivate(int(self.winId()))
        self.raise_()
        self._timer.start(duration_ms)


class PopupWindow(QWidget):
    """结果卡片：原文 + 流式回答 + 多轮追问。"""

    regenerate_requested = pyqtSignal(str)
    followup_requested = pyqtSignal(str)
    settings_requested = pyqtSignal()

    def __init__(self, cfg: dict) -> None:
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.cfg = dict(cfg)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setStyleSheet(STYLE_SHEET)

        self._answer = ""
        self._turns: list[tuple[str | None, str]] = []  # (追问文本或None, 回答Markdown)
        self._active_question: str | None = None
        self._render_pending = False
        self._started_at = 0.0
        self._pinned = False
        self._drag_offset: QPoint | None = None
        self._user_moved = False
        self._model = str(cfg.get("model") or "deepseek-chat")
        self._stopped = False
        self._anchor: tuple[int, int] | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 16)
        card = QFrame(self)
        card.setObjectName("card")
        self._card = card
        outer.addWidget(card)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(15, 23, 42, 48))
        card.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        self.header_bar = QFrame(card)
        self.header_bar.setObjectName("headerBar")
        self.header_bar.setCursor(Qt.OpenHandCursor)
        self.header_bar.setFixedHeight(40)
        self.header_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        header = QHBoxLayout(self.header_bar)
        header.setContentsMargins(14, 9, 10, 9)
        header.setSpacing(7)
        logo = QLabel("译")
        logo.setObjectName("logoBadge")
        logo.setAlignment(Qt.AlignCenter)
        logo.setFixedSize(20, 20)
        title = QLabel("DeepSeek 翻译")
        title.setObjectName("title")
        self.badge = QLabel("UIA")
        self.badge.setObjectName("badge")
        self.pin_btn = QToolButton()
        self.pin_btn.setText("钉住")
        self.pin_btn.setCheckable(True)
        self.pin_btn.setCursor(Qt.PointingHandCursor)
        self.pin_btn.setToolTip("钉住后切换窗口也不自动关闭")
        self.pin_btn.toggled.connect(self._toggle_pin)
        close_btn = QToolButton()
        close_btn.setText("✕")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setToolTip("关闭 (Esc)")
        close_btn.clicked.connect(self._close)
        header.addWidget(logo)
        header.addWidget(title)
        header.addSpacing(2)
        header.addWidget(self.badge)
        header.addStretch(1)
        header.addWidget(self.pin_btn)
        header.addWidget(close_btn)
        card_layout.addWidget(self.header_bar)

        inner = QVBoxLayout()
        inner.setContentsMargins(14, 10, 14, 10)
        inner.setSpacing(8)
        card_layout.addLayout(inner, 1)

        self.original = QLabel()
        self.original.setObjectName("orig")
        self.original.setWordWrap(True)
        self.original.setMaximumHeight(64)
        self.original.setTextInteractionFlags(Qt.TextSelectableByMouse)
        inner.addWidget(self.original)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(3)
        inner.addWidget(self.progress)

        self.answer = QTextBrowser()
        self.answer.setObjectName("answer")
        self.answer.setOpenExternalLinks(True)
        self.answer.setFrameShape(QFrame.NoFrame)
        self.answer.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.answer.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.answer.setMinimumHeight(64)
        self.answer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        inner.addWidget(self.answer, 1)

        followup_row = QHBoxLayout()
        followup_row.setSpacing(6)
        self.followup_edit = QLineEdit()
        self.followup_edit.setPlaceholderText("继续追问…（如：拆解语法 / 换种说法，回车发送）")
        self.followup_edit.returnPressed.connect(self._submit_followup)
        self.followup_btn = QPushButton("追问")
        self.followup_btn.setObjectName("primary")
        self.followup_btn.setCursor(Qt.PointingHandCursor)
        self.followup_btn.setFixedWidth(56)
        self.followup_btn.clicked.connect(self._submit_followup)
        followup_row.addWidget(self.followup_edit, 1)
        followup_row.addWidget(self.followup_btn)
        inner.addLayout(followup_row)

        footer = QHBoxLayout()
        footer.setSpacing(2)
        self.status = QLabel("")
        self.status.setObjectName("status")
        self.copy_btn = QToolButton()
        self.copy_btn.setText("复制")
        self.copy_btn.clicked.connect(self._copy_answer)
        self.retry_btn = QToolButton()
        self.retry_btn.setText("重试")
        self.retry_btn.clicked.connect(self._retry)
        self.settings_btn = QToolButton()
        self.settings_btn.setText("设置")
        self.settings_btn.clicked.connect(self.settings_requested.emit)
        footer.addWidget(self.status)
        footer.addStretch(1)
        footer.addWidget(self.copy_btn)
        footer.addWidget(self.retry_btn)
        footer.addWidget(self.settings_btn)
        inner.addLayout(footer)

        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._fit_height)

        self.setFixedWidth(int(cfg.get("popup_width", 470)))
        self._font_size = 14

    # ------------------------------------------------------------------ 生命周期
    def begin(self, text: str, source: str, title: str, font_size: int = 14) -> None:
        self._answer = ""
        self._turns = []
        self._active_question = None
        self._stopped = False
        self._started_at = time.time()
        self._font_size = font_size
        self.badge.setText(source or "手动")
        shown = text if len(text) <= 220 else text[:220] + "…"
        self.original.setText(shown)
        self.original.setToolTip(text)
        self.status.setText(f"{self._model} · 请求中…")
        self.progress.show()
        self.copy_btn.setText("复制")
        self.followup_edit.clear()
        self.followup_btn.setEnabled(False)
        self._render("<p style='color:#64748b'>正在请求 DeepSeek…</p>")
        self._fit_height(force=True)

    def begin_followup(self, question: str) -> None:
        if self._answer or self._active_question is not None:
            self._turns.append((self._active_question, self._answer))
        self._active_question = question
        self._answer = ""
        self._stopped = False
        self._started_at = time.time()
        self.status.setText(f"{self._model} · 回答追问中…")
        self.progress.show()
        self.followup_edit.clear()
        self.followup_btn.setEnabled(False)
        self._render(self._compose_html("<p style='color:#64748b'>正在思考回答…</p>"), force_bottom=True)
        self._fit_height()

    def append(self, delta: str) -> None:
        if self._stopped:
            return
        self._answer += delta
        if not self._render_pending:
            self._render_pending = True
            QTimer.singleShot(40, self._flush)

    def note_reasoning(self) -> None:
        if self._answer:
            return
        self.status.setText(f"{self._model} · 深度思考中…")

    def finish(self) -> None:
        self.progress.hide()
        self.followup_btn.setEnabled(True)
        elapsed = time.time() - self._started_at
        self.status.setText(f"{self._model} · {elapsed:.1f}s")
        self._flush()

    def fail(self, message: str) -> None:
        self.progress.hide()
        self.followup_btn.setEnabled(True)
        self.status.setText("出错了")
        err_html = (
            f"<p style='color:{DANGER}'><b>请求失败</b></p>"
            f"<p style='color:#334155'>{html.escape(message)}</p>"
            "<p style='color:#64748b'>点右下角「设置」检查 API Key 和接口地址。</p>"
        )
        if self._turns or self._active_question is not None:
            self._render(self._compose_html(err_html), force_bottom=True)
        else:
            self._render(err_html)

    def stop(self) -> None:
        self._stopped = True
        self.progress.hide()
        self.followup_btn.setEnabled(True)
        self.status.setText(f"{self._model} · 已停止")

    def show_near(self, x: int, y: int) -> None:
        self._anchor = (x, y)
        self._user_moved = False
        self._fit_height(force=True)
        self._place()
        self.show()
        if plat.IS_MACOS:
            plat.configure_popup_window(int(self.winId()))
        self.raise_()

    def _place(self) -> None:
        """把窗口摆在锚点旁，并保证完整落在当前屏幕可见区域内。"""
        if self._anchor is None:
            return
        if self._user_moved:
            pos = self.pos()
            screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
            area = screen.availableGeometry()
            width = max(self.width(), self.sizeHint().width())
            height = max(self.height(), self.sizeHint().height())
            pos_x = max(area.left() + 8, min(pos.x(), area.right() - width - 8))
            pos_y = max(area.top() + 8, min(pos.y(), area.bottom() - height - 8))
            self.move(pos_x, pos_y)
            return
        x, y = self._anchor
        screen = QGuiApplication.screenAt(QPoint(x, y)) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        width = max(self.width(), self.sizeHint().width())
        height = max(self.height(), self.sizeHint().height())
        pos_x = x + 18
        if pos_x + width > area.right():
            pos_x = x - width - 18
        pos_y = y + 20
        if pos_y + height > area.bottom():
            pos_y = y - height - 20
        pos_x = max(area.left() + 8, min(pos_x, area.right() - width - 8))
        pos_y = max(area.top() + 8, min(pos_y, area.bottom() - height - 8))
        self.move(pos_x, pos_y)

    # ------------------------------------------------------------------ 内部
    def _question_block_html(self, question: str) -> str:
        safe = html.escape(question).replace("\n", "<br>")
        return (
            "<hr>"
            "<p style='background-color:#eff6ff; color:#1d4ed8; padding:6px 9px; margin:8px 0 6px 0;'>"
            f"<b>追问：</b>{safe}</p>"
        )

    def _compose_html(self, current_html: str | None = None) -> str:
        parts: list[str] = []
        for q, ans in self._turns:
            if q:
                parts.append(self._question_block_html(q))
            if ans:
                parts.append(render_markdown(ans))
        if self._active_question:
            parts.append(self._question_block_html(self._active_question))
        if current_html is not None:
            parts.append(current_html)
        elif self._answer:
            parts.append(render_markdown(self._answer))
        return "".join(parts)

    def _render(self, body_html: str | None = None, force_bottom: bool = False) -> None:
        if body_html is None:
            body_html = self._compose_html()
        scrollbar = self.answer.verticalScrollBar()
        at_bottom = force_bottom or scrollbar.value() >= scrollbar.maximum() - 24
        self.answer.setHtml(document_html(body_html, self._font_size))
        if at_bottom:
            scrollbar.setValue(scrollbar.maximum())
        self._resize_timer.start(60)

    def _submit_followup(self) -> None:
        question = self.followup_edit.text().strip()
        if not question or not self.followup_btn.isEnabled():
            return
        self.followup_requested.emit(question)

    def _flush(self) -> None:
        self._render_pending = False
        if not self._answer:
            return
        self._render()

    def _fit_height(self, force: bool = False) -> None:
        document = self.answer.document()
        viewport_width = self.answer.viewport().width()
        if not self.isVisible() or viewport_width < 200:
            # 还没显示时 viewport 宽度不可信，按窗口宽度推算最终可用宽度
            viewport_width = max(200, self.width() - 56)
        document.setTextWidth(viewport_width)
        doc_height = int(document.documentLayout().documentSize().height())
        view_height = max(64, min(doc_height + 14, 420))
        if force or abs(self.answer.height() - view_height) > 6:
            self.answer.setFixedHeight(view_height)
            self.answer.updateGeometry()
            self._card.updateGeometry()
            if self._card.layout() is not None:
                self._card.layout().invalidate()
                self._card.layout().activate()
            if self.layout() is not None:
                self.layout().invalidate()
                self.layout().activate()
            target_h = self.layout().sizeHint().height() if self.layout() is not None else self.sizeHint().height()
            if target_h > 0:
                self.setFixedHeight(target_h)
            if self.isVisible():
                self._place()

    def is_pinned(self) -> bool:
        return self._pinned

    def set_model(self, model: str) -> None:
        self._model = str(model or "deepseek-chat")

    def _toggle_pin(self, checked: bool) -> None:
        self._pinned = checked
        self.pin_btn.setText("已钉住" if checked else "钉住")

    def _close(self) -> None:
        self.hide()

    def _copy_answer(self) -> None:
        text = self._answer or self.original.toolTip()
        QApplication.clipboard().setText(text)
        self.copy_btn.setText("已复制")
        QTimer.singleShot(1200, lambda: self.copy_btn.setText("复制"))

    def _retry(self) -> None:
        text = self.original.toolTip()
        if text:
            self.regenerate_requested.emit(text)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key_Escape:
            if not self._pinned:
                self.hide()
        elif event.key() == Qt.Key_C and event.modifiers() & Qt.ControlModifier:
            self._copy_answer()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPos() - self.frameGeometry().topLeft()
            self.header_bar.setCursor(Qt.ClosedHandCursor)
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self._user_moved = True
            self.move(event.globalPos() - self._drag_offset)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_offset = None
        self.header_bar.setCursor(Qt.OpenHandCursor)
        self.unsetCursor()


class _ConnectionTest(QThread):
    finished_ok = pyqtSignal(bool, str)

    def __init__(self, cfg: dict) -> None:
        super().__init__()
        self._cfg = dict(cfg)

    def run(self) -> None:
        ok, message = ai.test_connection(self._cfg)
        self.finished_ok.emit(ok, message)


class SettingsDialog(QDialog):
    def __init__(self, cfg: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("DeepDict 设置")
        self.setWindowIcon(app_icon())
        self.setStyleSheet(STYLE_SHEET)
        self.setMinimumWidth(520)
        self.cfg = dict(cfg)
        self._worker: _ConnectionTest | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(8)

        layout.addWidget(self._section("接口"))
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setSpacing(8)

        self.key_edit = QLineEdit(str(cfg.get("api_key", "")))
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.setPlaceholderText("sk-…（在 platform.deepseek.com 创建）")
        key_row = QHBoxLayout()
        key_row.addWidget(self.key_edit, 1)
        show_key = QCheckBox("显示")
        show_key.toggled.connect(
            lambda on: self.key_edit.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password)
        )
        key_row.addWidget(show_key)
        form.addRow("API Key", self._wrap(key_row))

        self.base_edit = QLineEdit(str(cfg.get("base_url", "")))
        self.base_edit.setPlaceholderText("https://api.deepseek.com/v1")
        form.addRow("接口地址", self.base_edit)

        self.model_box = QComboBox()
        self.model_box.setEditable(True)
        for model_id, label in cfgmod.MODEL_PRESETS:
            self.model_box.addItem(f"{model_id} — {label}", model_id)
        current_model = str(cfg.get("model", "deepseek-chat"))
        index = self.model_box.findData(current_model)
        if index >= 0:
            self.model_box.setCurrentIndex(index)
        else:
            self.model_box.setEditText(current_model)
        form.addRow("模型", self.model_box)
        layout.addLayout(form)

        layout.addWidget(self._section("行为"))
        form2 = QFormLayout()
        form2.setLabelAlignment(Qt.AlignRight)
        form2.setSpacing(8)

        self.lang_box = QComboBox()
        self.lang_box.setEditable(True)
        self.lang_box.addItems(cfgmod.LANGUAGE_PRESETS)
        self.lang_box.setCurrentText(str(cfg.get("target_language", "简体中文")))
        form2.addRow("译文语言", self.lang_box)

        self.hotkey_edit = QKeySequenceEdit(QKeySequence(str(cfg.get("hotkey", "Ctrl+Alt+D"))))
        form2.addRow("划词快捷键", self.hotkey_edit)

        self.input_hotkey_edit = QKeySequenceEdit(QKeySequence(str(cfg.get("input_hotkey", "Ctrl+Alt+S"))))
        form2.addRow("输入翻译快捷键", self.input_hotkey_edit)

        self.bubble_check = QCheckBox("选中文字后，在光标旁显示「译」按钮")
        self.bubble_check.setChecked(bool(cfg.get("auto_bubble", True)))
        form2.addRow("", self.bubble_check)

        copy_key = "Cmd+C" if plat.IS_MACOS else "Ctrl+C"
        self.restore_check = QCheckBox(f"用 {copy_key} 兜底取词后恢复原剪贴板内容")
        self.restore_check.setChecked(bool(cfg.get("restore_clipboard", True)))
        form2.addRow("", self.restore_check)

        self.autostart_check = QCheckBox("开机自动启动")
        self.autostart_check.setChecked(bool(cfg.get("autostart", False)))
        form2.addRow("", self.autostart_check)
        layout.addLayout(form2)

        hint_text = (
            "取词方式：模拟 Cmd+C 读选区，并自动还原剪贴板。\n"
            "首次使用请在「系统设置 → 隐私与安全性 → 辅助功能」中授权终端/Python。"
            if plat.IS_MACOS
            else "取词顺序：UI Automation（不动剪贴板）→ 模拟 Ctrl+C（会临时占用剪贴板）。\n"
            "控制台窗口会自动跳过，避免把 Ctrl+C 变成中断信号。"
        )
        self.hint = QLabel(hint_text)
        self.hint.setObjectName("hint")
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)

        row = QHBoxLayout()
        self.test_btn = QPushButton("测试连接")
        self.test_btn.clicked.connect(self._test)
        self.test_label = QLabel("")
        self.test_label.setObjectName("hint")
        self.test_label.setWordWrap(True)
        row.addWidget(self.test_btn)
        row.addWidget(self.test_label, 1)
        layout.addLayout(row)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("保存")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _section(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("section")
        return label

    @staticmethod
    def _wrap(layout) -> QWidget:
        holder = QWidget()
        layout.setContentsMargins(0, 0, 0, 0)
        holder.setLayout(layout)
        return holder

    def _current(self) -> dict:
        data = dict(self.cfg)
        data["api_key"] = self.key_edit.text().strip()
        data["base_url"] = self.base_edit.text().strip()
        model = self.model_box.currentData()
        data["model"] = str(model or self.model_box.currentText().split(" — ")[0]).strip()
        data["target_language"] = self.lang_box.currentText().strip() or "简体中文"
        hotkey = self.hotkey_edit.keySequence().toString()
        if hotkey:
            data["hotkey"] = hotkey
        input_hotkey = self.input_hotkey_edit.keySequence().toString()
        if input_hotkey:
            data["input_hotkey"] = input_hotkey
        data["auto_bubble"] = self.bubble_check.isChecked()
        data["restore_clipboard"] = self.restore_check.isChecked()
        data["autostart"] = self.autostart_check.isChecked()
        return data

    def _test(self) -> None:
        self.test_btn.setEnabled(False)
        self.test_label.setText("正在连接…")
        self._worker = _ConnectionTest(self._current())
        self._worker.finished_ok.connect(self._test_done)
        self._worker.start()

    def _test_done(self, ok: bool, message: str) -> None:
        self.test_btn.setEnabled(True)
        color = "#16a34a" if ok else DANGER
        self.test_label.setText(f"<span style='color:{color}'>{message}</span>")

    def _save(self) -> None:
        data = self._current()
        for key in ("hotkey", "input_hotkey"):
            if plat.parse_hotkey(data[key]) is None:
                self.test_label.setText(f"<span style='color:{DANGER}'>快捷键格式不对：{data[key]}</span>")
                return
        self.cfg = data
        cfgmod.save_config(data)
        self.accept()


class InputDialog(QDialog):
    """热键呼出的输入翻译窗口。"""

    submitted = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.Dialog | Qt.WindowStaysOnTopHint)
        self.setWindowTitle("输入翻译")
        self.setWindowIcon(app_icon())
        self.setStyleSheet(STYLE_SHEET)
        self.setMinimumSize(520, 220)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        title = QLabel("输入或粘贴要翻译的内容")
        title.setObjectName("title")
        layout.addWidget(title)
        self.edit = QPlainTextEdit()
        self.edit.setPlaceholderText("Ctrl+Enter 翻译")
        layout.addWidget(self.edit, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        submit = QPushButton("翻译")
        submit.setObjectName("primary")
        submit.clicked.connect(self._submit)
        row.addWidget(cancel)
        row.addWidget(submit)
        layout.addLayout(row)

    def _submit(self) -> None:
        text = self.edit.toPlainText().strip()
        if text:
            self.submitted.emit(text)
            self.accept()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and event.modifiers() & Qt.ControlModifier:
            self._submit()
            return
        if event.key() == Qt.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)


def default_font() -> QFont:
    font = QFont("PingFang SC" if plat.IS_MACOS else "Microsoft YaHei UI")
    font.setPointSize(11 if plat.IS_MACOS else 9)
    return font
