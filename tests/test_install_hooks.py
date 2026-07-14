from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

import install_hooks


class InstallHooksTests(unittest.TestCase):
    def test_installer_preserves_unrelated_hooks_and_uses_safe_windows_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            existing = {
                "hooks": {
                    "Stop": [
                        {
                            "hooks": [
                                {"type": "command", "command": "keep-this-handler"}
                            ]
                        }
                    ]
                }
            }
            (home / "hooks.json").write_text(
                json.dumps(existing), encoding="utf-8"
            )

            with patch.dict(os.environ, {"CODEX_HOME": str(home)}):
                self.assertEqual(install_hooks.main(), 0)

            installed = json.loads((home / "hooks.json").read_text(encoding="utf-8"))
            stop_handlers = [
                handler
                for group in installed["hooks"]["Stop"]
                for handler in group["hooks"]
            ]
            self.assertTrue(
                any(handler.get("command") == "keep-this-handler" for handler in stop_handlers)
            )
            desktop_pet = [
                handler
                for handler in stop_handlers
                if "codex_hook.py" in handler.get("commandWindows", "")
            ]
            self.assertEqual(len(desktop_pet), 1)
            self.assertTrue(desktop_pet[0]["commandWindows"].startswith("py -3 "))


if __name__ == "__main__":
    unittest.main()

