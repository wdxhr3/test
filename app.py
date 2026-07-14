from __future__ import annotations

import ctypes
import json
import logging
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

import win32api
import win32con
import win32gui
import win32process
from PyQt5.QtCore import QPoint, QRectF, QTimer, Qt
from PyQt5.QtGui import QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt5.QtNetwork import QHostAddress, QTcpServer, QUdpSocket
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QStyle,
    QSystemTrayIcon,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)


APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "pet_config.json"
LOG_PATH = APP_DIR / "pet.log"
USER32 = ctypes.windll.user32
ERROR_ALREADY_EXISTS = 183
MUTEX_NAME = "Local\\CodexDesktopPet"

logging.basicConfig(
    filename=str(LOG_PATH),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    encoding="utf-8",
)
LOG = logging.getLogger("codex_desktop_pet")


def load_config() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def enum_top_windows(predicate: Callable[[int], bool]) -> List[int]:
    result: List[int] = []

    def callback(hwnd: int, _: object) -> None:
        try:
            if predicate(hwnd):
                result.append(hwnd)
        except Exception:
            return

    win32gui.EnumWindows(callback, None)
    return result


def pid_for_window(hwnd: int) -> int:
    return win32process.GetWindowThreadProcessId(hwnd)[1]


def find_child(parent: int, class_name: str, control_id: int) -> Optional[int]:
    found: List[int] = []

    def callback(hwnd: int, _: object) -> None:
        if (
            win32gui.GetClassName(hwnd) == class_name
            and win32gui.GetDlgCtrlID(hwnd) == control_id
        ):
            found.append(hwnd)

    win32gui.EnumChildWindows(parent, callback, None)
    return found[0] if found else None


def force_focus(hwnd: int) -> None:
    if not hwnd or not win32gui.IsWindow(hwnd):
        return
    foreground = win32gui.GetForegroundWindow()
    foreground_thread = win32process.GetWindowThreadProcessId(foreground)[0]
    target_thread = win32process.GetWindowThreadProcessId(hwnd)[0]
    attached = False
    try:
        if foreground_thread != target_thread:
            USER32.AttachThreadInput(foreground_thread, target_thread, True)
            attached = True
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.BringWindowToTop(hwnd)
        win32gui.SetForegroundWindow(hwnd)
        USER32.SetFocus(hwnd)
    finally:
        if attached:
            USER32.AttachThreadInput(foreground_thread, target_thread, False)


def click_client(hwnd: int, point: Iterable[int]) -> None:
    x, y = [int(value) for value in point]
    old_cursor = win32api.GetCursorPos()
    force_focus(hwnd)
    screen_point = win32gui.ClientToScreen(hwnd, (x, y))
    win32api.SetCursorPos(screen_point)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0)
    win32api.SetCursorPos(old_cursor)


def unsigned_window_style(hwnd: int) -> int:
    return USER32.GetWindowLongW(hwnd, win32con.GWL_STYLE) & 0xFFFFFFFF


@dataclass
class RendererHandles:
    pid: int
    main: int
    pet: int
    started_by_us: bool


class PngTuberController:
    def __init__(self, config: dict):
        self.config = config
        self.handles: Optional[RendererHandles] = None
        self.process: Optional[subprocess.Popen] = None
        self.last_expression: Optional[str] = None

    @property
    def main_hwnd(self) -> int:
        return self.handles.main if self.handles else 0

    @property
    def pet_hwnd(self) -> int:
        return self.handles.pet if self.handles else 0

    def _find_main(self) -> Optional[int]:
        title_prefix = self.config["renderer"]["main_window_title"]
        windows = enum_top_windows(
            lambda hwnd: win32gui.IsWindowVisible(hwnd)
            and win32gui.GetWindowText(hwnd).startswith(title_prefix)
        )
        return windows[0] if windows else None

    def _find_pet_window(self, pid: int) -> Optional[int]:
        pattern = re.compile(self.config["renderer"]["pet_window_title_pattern"])
        windows = enum_top_windows(
            lambda hwnd: pid_for_window(hwnd) == pid
            and win32gui.IsWindowVisible(hwnd)
            and bool(pattern.fullmatch(win32gui.GetWindowText(hwnd)))
        )
        return windows[0] if windows else None

    def _wait_for(
        self, finder: Callable[[], Optional[int]], timeout: float, label: str
    ) -> int:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            hwnd = finder()
            if hwnd:
                return hwnd
            time.sleep(0.1)
        raise TimeoutError(f"等待 {label} 超时")

    def _start_process(self) -> Tuple[int, bool]:
        existing = self._find_main()
        if existing:
            return existing, False

        renderer = self.config["renderer"]
        executable = Path(renderer["executable"])
        if not executable.exists():
            raise FileNotFoundError(f"找不到 PNGTuber Remix：{executable}")
        self.process = subprocess.Popen(
            [str(executable)],
            cwd=str(executable.parent),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        main = self._wait_for(
            self._find_main,
            renderer.get("startup_timeout", 20),
            "PNGTuber Remix 主窗口",
        )
        time.sleep(renderer.get("startup_ready_delay", 3))
        return main, True

    def _dialog_for_pid(self, pid: int) -> Optional[int]:
        dialogs = enum_top_windows(
            lambda hwnd: pid_for_window(hwnd) == pid
            and win32gui.IsWindowVisible(hwnd)
            and win32gui.GetClassName(hwnd) == "#32770"
        )
        return dialogs[0] if dialogs else None

    def _load_model(self, main: int, pid: int) -> None:
        renderer = self.config["renderer"]
        model = Path(renderer["model_file"])
        if not model.exists():
            raise FileNotFoundError(f"找不到角色模型：{model}")

        points = renderer["automation_points"]
        LOG.info("Opening PNGTuber model dialog")
        click_client(main, points["file_menu"])
        time.sleep(0.2)
        click_client(main, points["file_open"])
        dialog = self._wait_for(
            lambda: self._dialog_for_pid(pid),
            renderer.get("dialog_timeout", 8),
            "模型文件选择框",
        )
        edit = find_child(dialog, "Edit", 1148)
        if not edit:
            raise RuntimeError("无法定位 PNGTuber 文件选择框")
        win32gui.SendMessage(edit, win32con.WM_SETTEXT, 0, str(model))
        open_button = win32gui.GetDlgItem(dialog, win32con.IDOK)
        win32gui.SendMessage(open_button, win32con.BM_CLICK, 0, 0)
        self._wait_for(
            lambda: main if not win32gui.IsWindow(dialog) else None,
            renderer.get("model_load_timeout", 20),
            "模型加载完成",
        )
        time.sleep(renderer.get("post_load_delay", 2))
        LOG.info("PNGTuber model loaded")

    def _create_pet_window(self, main: int, pid: int) -> int:
        renderer = self.config["renderer"]
        points = renderer["automation_points"]
        click_client(main, points["window_menu"])
        time.sleep(0.2)
        click_client(main, points["add_window"])
        return self._wait_for(
            lambda: self._find_pet_window(pid),
            renderer.get("window_timeout", 8),
            "透明角色窗口",
        )

    def _lock_pet_window(self, pet: int) -> None:
        if not (unsigned_window_style(pet) & win32con.WS_CAPTION):
            return
        left, top, right, bottom = win32gui.GetClientRect(pet)
        click_client(pet, (max(10, right - 63), max(10, bottom - 40)))
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if not (unsigned_window_style(pet) & win32con.WS_CAPTION):
                return
            time.sleep(0.1)
        raise RuntimeError("无法锁定 PNGTuber 透明窗口")

    def _apply_view_transform(self, pet: int) -> None:
        steps = int(self.config["renderer"].get("zoom_steps", 0))
        if not steps:
            return
        old_cursor = win32api.GetCursorPos()
        force_focus(pet)
        left, top, right, bottom = win32gui.GetWindowRect(pet)
        win32api.SetCursorPos(((left + right) // 2, (top + bottom) // 2))
        wheel_delta = 120 if steps > 0 else -120
        for _ in range(abs(steps)):
            win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, 0, 0, wheel_delta)
            time.sleep(0.05)
        win32api.SetCursorPos(old_cursor)
        time.sleep(0.5)

    def start(self) -> RendererHandles:
        main, started_by_us = self._start_process()
        pid = pid_for_window(main)
        pet = self._find_pet_window(pid)
        if not pet:
            self._load_model(main, pid)
            pet = self._create_pet_window(main, pid)
        self._lock_pet_window(pet)
        self._apply_view_transform(pet)
        win32gui.ShowWindow(main, win32con.SW_HIDE)
        self.handles = RendererHandles(pid, main, pet, started_by_us)
        LOG.info("Renderer ready pid=%s main=%s pet=%s", pid, main, pet)
        return self.handles

    def move_pet(self, x: int, y: int, width: int, height: int, overlay: int = 0) -> None:
        if not self.pet_hwnd or not win32gui.IsWindow(self.pet_hwnd):
            return
        flags = win32con.SWP_NOACTIVATE | win32con.SWP_SHOWWINDOW
        win32gui.SetWindowPos(
            self.pet_hwnd, win32con.HWND_TOPMOST, x, y, width, height, flags
        )
        if overlay and win32gui.IsWindow(overlay):
            win32gui.SetWindowPos(
                overlay,
                win32con.HWND_TOPMOST,
                x,
                y,
                width,
                height,
                flags,
            )

    def _send_expression_hotkey(self, key: str) -> None:
        if not self.pet_hwnd or not win32gui.IsWindow(self.pet_hwnd):
            return
        previous = win32gui.GetForegroundWindow()
        force_focus(self.pet_hwnd)
        virtual_key = 0xBD if key == "-" else ord(key)
        win32api.keybd_event(win32con.VK_SHIFT, 0, 0, 0)
        win32api.keybd_event(virtual_key, 0, 0, 0)
        win32api.keybd_event(virtual_key, 0, win32con.KEYEVENTF_KEYUP, 0)
        win32api.keybd_event(
            win32con.VK_SHIFT, 0, win32con.KEYEVENTF_KEYUP, 0
        )
        time.sleep(0.03)
        if previous and previous != self.pet_hwnd and win32gui.IsWindow(previous):
            try:
                force_focus(previous)
            except Exception:
                pass

    def set_expression(self, key: str) -> None:
        if key not in {"1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-"}:
            raise ValueError(f"不支持的表情键：{key}")
        if self.last_expression and self.last_expression != key:
            self._send_expression_hotkey(self.last_expression)
        self._send_expression_hotkey(key)
        self.last_expression = None if self.last_expression == key else key
        LOG.info("Expression changed to %s", self.last_expression or "default")

    def show_settings(self) -> None:
        if self.main_hwnd and win32gui.IsWindow(self.main_hwnd):
            win32gui.ShowWindow(self.main_hwnd, win32con.SW_SHOW)
            force_focus(self.main_hwnd)

    def hide_settings(self) -> None:
        if self.main_hwnd and win32gui.IsWindow(self.main_hwnd):
            win32gui.ShowWindow(self.main_hwnd, win32con.SW_HIDE)

    def cleanup(self) -> None:
        if not self.handles:
            return
        if self.handles.started_by_us and win32gui.IsWindow(self.main_hwnd):
            win32gui.PostMessage(self.main_hwnd, win32con.WM_CLOSE, 0, 0)
            time.sleep(0.4)
            if self.process and self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
        elif win32gui.IsWindow(self.main_hwnd):
            win32gui.ShowWindow(self.main_hwnd, win32con.SW_SHOW)


class BubbleWindow(QWidget):
    """Independent, interactive conversation card anchored above the character."""

    STATUS = {
        "running": ("正在回答", "#69B2C6", "#E3F4F8", "#3F7887"),
        "needs_input": ("需要输入", "#E3A15B", "#FFF0DA", "#8C5A1E"),
        "ready": ("已完成", "#72B99F", "#E2F5EE", "#3E7866"),
        "blocked": ("遇到问题", "#D77B86", "#FCE8EB", "#934955"),
        "idle": ("空闲", "#A899C6", "#F0EBF8", "#665979"),
    }

    def __init__(self, owner: "PetOverlay"):
        super().__init__(None)
        self.owner = owner
        self.expanded = False
        self.full_text = ""
        self.prompt = ""
        self.state = "idle"
        self.body_height = 176
        self.message_time = time.time()
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFixedWidth(424)

        root = QVBoxLayout(self)
        root.setContentsMargins(30, 22, 30, 42)
        root.setSpacing(7)

        header = QHBoxLayout()
        header.setSpacing(7)
        mark = QLabel("▦")
        mark.setFixedSize(20, 20)
        mark.setAlignment(Qt.AlignCenter)
        mark.setStyleSheet(
            "color:#657CB8;background:#EEF7FA;border:1px solid #D2EAF2;"
            "border-radius:5px;font:600 13px 'Microsoft YaHei UI';"
        )
        title = QLabel("Codex")
        title.setStyleSheet("color:#59445E;font:600 13px 'Microsoft YaHei UI';")
        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignCenter)
        self.time_label = QLabel("刚刚")
        self.time_label.setMinimumWidth(58)
        self.time_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.time_label.setStyleSheet("color:#827887;font:11px 'Microsoft YaHei UI';")
        self.close_button = QPushButton("×")
        self.close_button.setFixedSize(22, 22)
        self.close_button.setCursor(Qt.PointingHandCursor)
        self.close_button.setStyleSheet(
            "QPushButton{color:#786F7D;background:transparent;border:0;font:17px 'Segoe UI';}"
            "QPushButton:hover{background:#F0EBF8;border-radius:11px;color:#4C3458;}"
        )
        self.close_button.clicked.connect(self.hide)
        header.addWidget(mark)
        header.addWidget(title)
        header.addWidget(self.status_label)
        header.addStretch()
        header.addWidget(self.time_label)
        header.addWidget(self.close_button)
        root.addLayout(header)

        self.prompt_label = QLabel()
        self.prompt_label.setWordWrap(True)
        self.prompt_label.setStyleSheet(
            "color:#66717A;background:#EEF7FA;border:1px solid #D2EAF2;"
            "border-radius:9px;padding:5px 8px;font:12px 'Microsoft YaHei UI';"
        )
        self.prompt_label.hide()
        root.addWidget(self.prompt_label)

        self.answer = QTextBrowser()
        self.answer.setReadOnly(True)
        self.answer.setOpenExternalLinks(True)
        self.answer.setFrameShape(QFrame.NoFrame)
        self.answer.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.answer.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.answer.setStyleSheet(
            "QTextBrowser{color:#403646;background:transparent;border:0;"
            "font:14px 'Microsoft YaHei UI';selection-background-color:#B7A5D4;}"
            "QScrollBar:vertical{width:8px;background:transparent;margin:2px;}"
            "QScrollBar::handle:vertical{background:#D8CCE2;border-radius:4px;min-height:24px;}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}"
        )
        root.addWidget(self.answer, 1)

        footer = QHBoxLayout()
        self.meta_label = QLabel("自动同步当前 Codex 任务")
        self.meta_label.setStyleSheet("color:#827887;font:11px 'Microsoft YaHei UI';")
        self.expand_button = QPushButton("展开全文  ⌄")
        self.expand_button.setCursor(Qt.PointingHandCursor)
        self.expand_button.setStyleSheet(
            "QPushButton{color:#665979;background:#F0EBF8;border:1px solid #DED4E8;"
            "border-radius:10px;padding:3px 9px;font:11px 'Microsoft YaHei UI';}"
            "QPushButton:hover{background:#E8E0F2;}"
        )
        self.expand_button.clicked.connect(self.toggle_expanded)
        footer.addWidget(self.meta_label)
        footer.addStretch()
        footer.addWidget(self.expand_button)
        root.addLayout(footer)
        self._apply_state("idle")
        self._apply_size()

        self.time_timer = QTimer(self)
        self.time_timer.timeout.connect(self._update_time_label)
        self.time_timer.start(15000)

    def _apply_state(self, state: str) -> None:
        self.state = state if state in self.STATUS else "idle"
        label, dot, background, text = self.STATUS[self.state]
        self.status_label.setText(f"  ●  {label}  ")
        self.status_label.setStyleSheet(
            f"color:{text};background:{background};border-radius:10px;"
            f"font:500 11px 'Microsoft YaHei UI';"
        )
        self.status_label.setProperty("dotColor", dot)

    def _preview(self, text: str, limit: int = 280) -> str:
        clean = text.strip()
        if len(clean) <= limit:
            return clean
        return clean[:limit].rstrip() + "…"

    def present(self, text: str, state: str = "idle", prompt: str = "", meta: str = "") -> None:
        self.full_text = text.strip()
        self.prompt = prompt.strip()
        self._apply_state(state)
        self.prompt_label.setText("你 · " + self._preview(self.prompt, 100))
        self.prompt_label.setVisible(bool(self.prompt))
        self.meta_label.setText(meta or "自动同步当前 Codex 任务")
        self.message_time = time.time()
        self._update_time_label()
        self.expanded = False
        self._render_text()
        self._apply_size()
        self.reposition()
        self.update()
        self.show()
        self.ensure_topmost()

    def _update_time_label(self) -> None:
        elapsed = max(0, int(time.time() - self.message_time))
        if elapsed < 60:
            label = "刚刚"
        elif elapsed < 3600:
            label = f"{elapsed // 60} 分钟前"
        elif elapsed < 86400:
            label = f"{elapsed // 3600} 小时前"
        else:
            label = time.strftime("%m-%d %H:%M", time.localtime(self.message_time))
        self.time_label.setText(label)

    def ensure_topmost(self) -> None:
        if not self.isVisible():
            return
        self.raise_()
        try:
            flags = win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE
            win32gui.SetWindowPos(
                int(self.winId()), win32con.HWND_TOPMOST, 0, 0, 0, 0, flags
            )
        except Exception:
            LOG.exception("Failed to keep conversation bubble above pet overlay")

    def _render_text(self) -> None:
        text = self.full_text or self.STATUS[self.state][0]
        shown = text if self.expanded else self._preview(text)
        if hasattr(self.answer, "setMarkdown"):
            self.answer.setMarkdown(shown)
        else:
            self.answer.setPlainText(shown)
        is_long = len(text) > 280 or text.count("\n") > 5
        self.expand_button.setVisible(is_long)
        self.expand_button.setText("收起  ⌃" if self.expanded else "展开全文  ⌄")

    def toggle_expanded(self) -> None:
        self.expanded = not self.expanded
        self._render_text()
        self._apply_size()
        self.reposition()
        self.update()
        self.ensure_topmost()

    def _apply_size(self) -> None:
        if self.expanded:
            self.setFixedWidth(480)
            screen = QApplication.screenAt(self.owner.geometry().center()) or QApplication.primaryScreen()
            maximum = min(500, screen.availableGeometry().height() - 32)
            self.body_height = max(280, maximum - 46)
            self.answer.setMinimumHeight(max(150, self.body_height - 116))
            self.answer.setMaximumHeight(max(150, self.body_height - 116))
        else:
            self.setFixedWidth(424)
            # The previous 168/138px body was smaller than the layout's
            # 242px size hint for a long answer with a prompt, leaving the
            # expand button visually present but with a clipped hit area.
            self.body_height = 210 if self.prompt else 176
            self.answer.setMinimumHeight(62)
            self.answer.setMaximumHeight(92 if self.prompt else 82)
        self.setFixedHeight(self.body_height + 46)

    def reposition(self) -> None:
        pet = self.owner.geometry()
        screen = QApplication.screenAt(pet.center()) or QApplication.primaryScreen()
        available = screen.availableGeometry()
        anchor_x = pet.left() + round(pet.width() * 0.485)
        anchor_y = pet.top() + round(pet.height() * 0.14)
        body_width = self.width() - 28
        tail_x = 14 + round(body_width * 0.63)
        x = anchor_x - tail_x
        y = anchor_y - (10 + self.body_height + 22)
        x = max(available.left() + 12, min(x, available.right() - self.width() - 11))
        y = max(available.top() + 12, min(y, available.bottom() - self.height() - 11))
        self.move(x, y)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        body = QRectF(14, 10, self.width() - 28, self.body_height)
        path = QPainterPath()
        path.addRoundedRect(body, 22, 22)
        pet = self.owner.geometry()
        anchor_x = pet.left() + round(pet.width() * 0.485) - self.x()
        anchor_y = pet.top() + round(pet.height() * 0.14) - self.y()
        root_x = max(68.0, min(float(self.width() - 68), float(anchor_x)))
        tail = QPainterPath()
        tail.moveTo(root_x - 15, body.bottom() - 2)
        tail.cubicTo(root_x - 7, body.bottom() + 8, anchor_x - 5, anchor_y - 5, anchor_x, anchor_y)
        tail.cubicTo(anchor_x + 5, anchor_y - 3, root_x + 9, body.bottom() + 8, root_x + 13, body.bottom() - 2)
        tail.closeSubpath()
        path = path.united(tail)
        # A top-level QGraphicsDropShadowEffect caches the whole translucent
        # window on Windows and can leave old conversation text visible when
        # the bubble geometry does not change. Paint the shadow into the
        # window instead so every event refreshes deterministically.
        painter.save()
        painter.translate(0, 7)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(47, 31, 58, 42))
        painter.drawPath(path)
        painter.restore()
        gradient = QLinearGradient(0, body.top(), 0, body.bottom())
        gradient.setColorAt(0, QColor(255, 253, 247, 252))
        gradient.setColorAt(1, QColor(255, 248, 237, 250))
        painter.setBrush(gradient)
        painter.setPen(QPen(QColor(76, 52, 88, 205), 2))
        painter.drawPath(path)
        accent = QLinearGradient(body.left(), 0, body.left() + 52, 0)
        accent.setColorAt(0, QColor("#B7A5D4"))
        accent.setColorAt(.5, QColor("#9FD2EA"))
        accent.setColorAt(1, QColor("#8DCEB6"))
        painter.setPen(QPen(accent, 3, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(int(body.left() + 20), 18, int(body.left() + 72), 18)

    def mouseDoubleClickEvent(self, event) -> None:
        self.owner.open_codex()
        event.accept()


class PetOverlay(QWidget):
    def __init__(self, controller: PngTuberController, config: dict):
        super().__init__()
        self.controller = controller
        self.config = config
        self.drag_origin: Optional[QPoint] = None
        self.window_origin: Optional[QPoint] = None
        self.bubble_generation = 0

        flags = Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
        if hasattr(Qt, "WindowDoesNotAcceptFocus"):
            flags |= Qt.WindowDoesNotAcceptFocus
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setWindowTitle("Codex Desktop Pet")

        self.bubble = BubbleWindow(self)

        self.health_timer = QTimer(self)
        self.health_timer.timeout.connect(self.ensure_alignment)
        self.health_timer.start(1000)

    def paintEvent(self, event) -> None:
        # Alpha 1 keeps the transparent overlay mouse-active without changing the art.
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(255, 255, 255, 1))

    def resizeEvent(self, event) -> None:
        self.bubble.reposition()
        super().resizeEvent(event)

    def moveEvent(self, event) -> None:
        self.bubble.reposition()
        QTimer.singleShot(0, self.ensure_alignment)
        super().moveEvent(event)

    def ensure_alignment(self) -> None:
        if not self.controller.pet_hwnd or not win32gui.IsWindow(self.controller.pet_hwnd):
            self.say("角色渲染窗口已关闭，请重新启动桌宠。", 0)
            return
        geometry = self.geometry()
        self.controller.move_pet(
            geometry.x(),
            geometry.y(),
            geometry.width(),
            geometry.height(),
            int(self.winId()),
        )
        self.bubble.ensure_topmost()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.drag_origin = event.globalPos()
            self.window_origin = self.pos()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self.drag_origin and self.window_origin and event.buttons() & Qt.LeftButton:
            self.move(self.window_origin + event.globalPos() - self.drag_origin)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.drag_origin = None
            self.window_origin = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.open_codex()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event) -> None:
        menu = self.build_menu()
        menu.exec_(event.globalPos())

    def build_menu(self) -> QMenu:
        menu = QMenu()
        expression_menu = menu.addMenu("切换表情")
        for key in ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-"]:
            action = expression_menu.addAction(f"表情 Shift + {key}")
            action.triggered.connect(
                lambda checked=False, selected=key: self.change_expression(selected)
            )
        menu.addSeparator()
        menu.addAction("显示示例气泡", lambda: self.say("我在这里，双击可以打开 Codex。"))
        menu.addAction("隐藏气泡", self.hide_bubble)
        menu.addAction("打开 Codex", self.open_codex)
        menu.addSeparator()
        menu.addAction("显示 PNGTuber 设置", self.controller.show_settings)
        menu.addAction("隐藏 PNGTuber 设置", self.controller.hide_settings)
        menu.addSeparator()
        menu.addAction("退出桌宠", QApplication.instance().quit)
        return menu

    def change_expression(self, key: str) -> None:
        try:
            self.controller.set_expression(key)
            QTimer.singleShot(60, self.raise_)
        except Exception as exc:
            LOG.exception("Failed to change expression")
            self.say(f"表情切换失败：{exc}", 0)

    def say(self, text: str, duration: Optional[int] = None, state: str = "idle", prompt: str = "", meta: str = "") -> None:
        if not text:
            self.hide_bubble()
            return
        self.bubble_generation += 1
        generation = self.bubble_generation
        self.bubble.present(text, state=state, prompt=prompt, meta=meta)
        seconds = self.config["ui"].get("bubble_seconds", 10) if duration is None else duration
        if seconds and seconds > 0:
            QTimer.singleShot(
                int(seconds * 1000),
                lambda: self.hide_bubble() if generation == self.bubble_generation else None,
            )

    def hide_bubble(self) -> None:
        self.bubble_generation += 1
        self.bubble.hide()

    def set_state(self, state: str, text: str = "") -> None:
        state_config = self.config.get("states", {}).get(state, {})
        expression = state_config.get("expression")
        if expression:
            self.change_expression(str(expression))
        message = text or state_config.get("message", "")
        if message:
            duration = 0 if state in {"ready", "needs_input", "blocked"} else None
            self.say(message, duration, state=state)

    def open_codex(self) -> None:
        app_id = self.config["codex"]["windows_app_id"]
        try:
            subprocess.Popen(
                ["explorer.exe", f"shell:AppsFolder\\{app_id}"],
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except Exception as exc:
            LOG.exception("Failed to open Codex")
            self.say(f"无法打开 Codex：{exc}", 0)


class LocalCommandServer:
    def __init__(self, overlay: PetOverlay, port: int):
        self.overlay = overlay
        self.socket = QUdpSocket(overlay)
        if not self.socket.bind(QHostAddress.LocalHost, port):
            raise RuntimeError(f"无法监听本地控制端口 {port}")
        self.socket.readyRead.connect(self.read_pending)
        LOG.info("Local control server listening on 127.0.0.1:%s", port)

    def read_pending(self) -> None:
        while self.socket.hasPendingDatagrams():
            data, _, _ = self.socket.readDatagram(self.socket.pendingDatagramSize())
            try:
                message = json.loads(bytes(data).decode("utf-8"))
                self.dispatch(message)
            except Exception:
                LOG.exception("Invalid local command")

    def dispatch(self, message: Dict[str, object]) -> None:
        action = str(message.get("action", ""))
        if action == "say":
            duration = message.get("duration")
            self.overlay.say(
                str(message.get("text", "")),
                int(duration) if duration is not None else None,
            )
        elif action == "expression":
            self.overlay.change_expression(str(message.get("key", "")))
        elif action == "state":
            self.overlay.set_state(
                str(message.get("state", "idle")), str(message.get("text", ""))
            )
        elif action == "codex_event":
            state = str(message.get("state", "idle"))
            text = str(message.get("text", ""))
            prompt = str(message.get("prompt", ""))
            event = str(message.get("event", "Codex"))
            session_id = str(message.get("session_id", ""))
            meta = event + (f" · {session_id[:8]}" if session_id else "")
            state_config = self.overlay.config.get("states", {}).get(state, {})
            expression = state_config.get("expression")
            if expression:
                self.overlay.change_expression(str(expression))
            self.overlay.say(text or state_config.get("message", ""), 0, state, prompt, meta)
        elif action == "open_codex":
            self.overlay.open_codex()
        elif action == "show":
            self.overlay.show()
            self.overlay.raise_()
        elif action == "quit":
            QApplication.instance().quit()


class CodexEventServer(QTcpServer):
    """Newline-delimited JSON transport for complete, potentially long answers."""

    def __init__(self, dispatcher: LocalCommandServer, port: int):
        super().__init__(dispatcher.overlay)
        self.dispatcher = dispatcher
        self.buffers: Dict[object, bytearray] = {}
        self.newConnection.connect(self.accept_connections)
        if not self.listen(QHostAddress.LocalHost, port):
            raise RuntimeError(f"无法监听 Codex 事件端口 {port}")
        LOG.info("Codex event server listening on 127.0.0.1:%s", port)

    def accept_connections(self) -> None:
        while self.hasPendingConnections():
            socket = self.nextPendingConnection()
            self.buffers[socket] = bytearray()
            socket.readyRead.connect(lambda s=socket: self.read_socket(s))
            socket.disconnected.connect(lambda s=socket: self.drop_socket(s))

    def read_socket(self, socket) -> None:
        buffer = self.buffers.setdefault(socket, bytearray())
        buffer.extend(bytes(socket.readAll()))
        while b"\n" in buffer:
            raw, _, rest = buffer.partition(b"\n")
            buffer[:] = rest
            if not raw.strip():
                continue
            try:
                self.dispatcher.dispatch(json.loads(raw.decode("utf-8")))
            except Exception:
                LOG.exception("Invalid Codex event")

    def drop_socket(self, socket) -> None:
        self.buffers.pop(socket, None)
        socket.deleteLater()


def create_tray(overlay: PetOverlay) -> QSystemTrayIcon:
    icon: QIcon = QApplication.style().standardIcon(QStyle.SP_ComputerIcon)
    tray = QSystemTrayIcon(icon, overlay)
    tray.setToolTip("Codex Desktop Pet")
    tray.setContextMenu(overlay.build_menu())
    tray.activated.connect(
        lambda reason: overlay.open_codex()
        if reason == QSystemTrayIcon.DoubleClick
        else None
    )
    tray.show()
    return tray


def acquire_mutex() -> Tuple[int, bool]:
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    return handle, ctypes.windll.kernel32.GetLastError() != ERROR_ALREADY_EXISTS


def send_existing(port: int, command: dict) -> None:
    import socket

    payload = json.dumps(command, ensure_ascii=False).encode("utf-8")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(payload, ("127.0.0.1", port))


def drain_pending_events(server: LocalCommandServer) -> bool:
    pending = APP_DIR / "runtime" / "pending_events.jsonl"
    if not pending.exists():
        return False
    try:
        lines = pending.read_text(encoding="utf-8").splitlines()
        pending.unlink(missing_ok=True)
        for line in lines[-20:]:
            if line.strip():
                server.dispatch(json.loads(line))
        return bool(lines)
    except Exception:
        LOG.exception("Failed to replay pending Codex events")
        return False


def main() -> int:
    config = load_config()
    mutex, is_first = acquire_mutex()
    if not is_first:
        send_existing(config["control_port"], {"action": "show"})
        return 0

    app = QApplication(sys.argv)
    app.setApplicationName("Codex Desktop Pet")
    app.setQuitOnLastWindowClosed(False)
    controller = PngTuberController(config)
    try:
        controller.start()
        overlay = PetOverlay(controller, config)
        width = int(config["ui"].get("width", 420))
        height = int(config["ui"].get("height", 438))
        screen = QApplication.primaryScreen().availableGeometry()
        margin = int(config["ui"].get("screen_margin", 24))
        overlay.setGeometry(
            screen.right() - width - margin + 1,
            screen.bottom() - height - margin + 1,
            width,
            height,
        )
        overlay.show()
        overlay.ensure_alignment()
        server = LocalCommandServer(overlay, int(config["control_port"]))
        event_server = CodexEventServer(server, int(config.get("event_port", 19289)))
        tray = create_tray(overlay)
        overlay._server = server
        overlay._event_server = event_server
        overlay._tray = tray
        if not drain_pending_events(server):
            overlay.say("桌宠已就绪。右键可切换表情，双击打开 Codex。", 7)
        app.aboutToQuit.connect(controller.cleanup)
        return app.exec_()
    except Exception as exc:
        LOG.exception("Startup failed")
        controller.cleanup()
        QMessageBox.critical(None, "Codex Desktop Pet", f"桌宠启动失败：\n{exc}")
        return 1
    finally:
        if mutex:
            ctypes.windll.kernel32.CloseHandle(mutex)


if __name__ == "__main__":
    raise SystemExit(main())

