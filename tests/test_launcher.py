from __future__ import annotations

import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]


class LauncherTests(unittest.TestCase):
    def test_batch_preflights_python_and_keeps_a_diagnostic_log(self) -> None:
        launcher = (PROJECT_DIR / "run_pet.bat").read_text(encoding="utf-8")

        self.assertIn("where python.exe", launcher)
        self.assertIn("import PyQt5, win32api", launcher)
        self.assertIn("runtime\\launcher.log", launcher)
        self.assertIn("PYTHONW_EXE", launcher)
        self.assertNotIn('start "" /b pythonw.exe', launcher)


if __name__ == "__main__":
    unittest.main()

