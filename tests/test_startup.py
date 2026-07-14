from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from PyQt5.QtWidgets import QApplication

from app import StartupWindow, start_renderer_with_feedback


class FakeController:
    def __init__(self) -> None:
        self.progress = None
        self.feedback_was_visible = False

    def start(self) -> str:
        app = QApplication.instance()
        self.feedback_was_visible = any(
            isinstance(widget, StartupWindow) and widget.isVisible()
            for widget in app.topLevelWidgets()
        )
        if self.progress:
            self.progress("正在载入角色模型…")
        return "ready"


class StartupFeedbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_feedback_is_visible_before_renderer_initialization(self) -> None:
        controller = FakeController()

        result = start_renderer_with_feedback(self.app, controller)

        self.assertEqual(result, "ready")
        self.assertTrue(controller.feedback_was_visible)
        self.assertFalse(
            any(
                isinstance(widget, StartupWindow) and widget.isVisible()
                for widget in self.app.topLevelWidgets()
            )
        )


if __name__ == "__main__":
    unittest.main()

