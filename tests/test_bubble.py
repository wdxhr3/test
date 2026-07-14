from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QWidget

from app import BubbleWindow


class DummyOwner(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setGeometry(1280, 600, 640, 400)
        self.opened = False

    def open_codex(self) -> None:
        self.opened = True


class BubbleWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.owner = DummyOwner()
        self.bubble = BubbleWindow(self.owner)

    def tearDown(self) -> None:
        self.bubble.close()
        self.owner.close()

    def test_long_answer_button_expands_full_text(self) -> None:
        answer = "\n".join(f"第 {index} 行测试内容" for index in range(20))
        self.bubble.present(answer, state="ready", prompt="测试展开全文")
        self.app.processEvents()

        self.assertTrue(self.bubble.expand_button.isVisible())
        self.assertGreaterEqual(self.bubble.height(), self.bubble.layout().sizeHint().height())
        collapsed_height = self.bubble.height()

        QTest.mouseClick(self.bubble.expand_button, Qt.LeftButton)
        self.app.processEvents()

        self.assertTrue(self.bubble.expanded)
        self.assertGreater(self.bubble.height(), collapsed_height)
        rendered = self.bubble.answer.toPlainText().strip()
        self.assertIn("第 0 行测试内容", rendered)
        self.assertIn("第 19 行测试内容", rendered)
        self.assertNotIn("…", rendered)

    def test_time_label_updates_from_just_now_to_minutes(self) -> None:
        self.bubble.present("时间测试", state="ready")
        self.assertEqual(self.bubble.time_label.text(), "刚刚")

        self.bubble.message_time = time.time() - 125
        self.bubble._update_time_label()
        self.assertEqual(self.bubble.time_label.text(), "2 分钟前")


if __name__ == "__main__":
    unittest.main()

