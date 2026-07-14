from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from app import (
    apply_user_renderer_config,
    discover_renderer_assets,
    ensure_renderer_configuration,
    renderer_paths_are_valid,
    save_user_renderer_config,
)


class PortableRendererPathTests(unittest.TestCase):
    def test_repository_defaults_do_not_contain_personal_absolute_paths(self) -> None:
        config = json.loads(
            (PROJECT_DIR / "pet_config.json").read_text(encoding="utf-8")
        )

        for key in ("executable", "model_file"):
            value = config["renderer"].get(key, "")
            self.assertFalse(Path(value).is_absolute(), value)

    def test_assets_are_discovered_anywhere_below_project_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            executable = root / "vendor" / "PNGTuber-Remix.exe"
            model = root / "models" / "character.pngRemix"
            executable.parent.mkdir()
            model.parent.mkdir()
            executable.touch()
            model.touch()

            discovered = discover_renderer_assets(root)

            self.assertEqual(discovered["executable"], str(executable.resolve()))
            self.assertEqual(discovered["model_file"], str(model.resolve()))

    def test_local_selection_is_saved_and_reloaded_outside_repository_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            executable = root / "PNGTuber-Remix.exe"
            model = root / "pet.pngRemix"
            executable.touch()
            model.touch()
            user_config = root / "runtime" / "user_config.json"
            config = {
                "renderer": {
                    "executable": str(executable),
                    "model_file": str(model),
                }
            }

            save_user_renderer_config(config, user_config)
            loaded = {"renderer": {"executable": "", "model_file": ""}}
            apply_user_renderer_config(loaded, user_config, root)

            self.assertTrue(renderer_paths_are_valid(loaded))
            self.assertEqual(loaded["renderer"]["executable"], str(executable.resolve()))
            self.assertEqual(loaded["renderer"]["model_file"], str(model.resolve()))

    def test_first_start_uses_colocated_assets_without_opening_dialogs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            executable = root / "portable" / "PNGTuber-Remix.exe"
            model = root / "portable" / "character.pngRemix"
            executable.parent.mkdir()
            executable.touch()
            model.touch()
            user_config = root / "runtime" / "user_config.json"
            config = {"renderer": {"executable": "", "model_file": ""}}

            ensure_renderer_configuration(config, root, user_config)

            self.assertTrue(renderer_paths_are_valid(config))
            self.assertTrue(user_config.exists())

    def test_first_start_prompts_for_assets_when_repo_has_none(self) -> None:
        with tempfile.TemporaryDirectory() as project_dir, tempfile.TemporaryDirectory() as asset_dir:
            root = Path(project_dir)
            assets = Path(asset_dir)
            executable = assets / "PNGTuber-Remix.exe"
            model = assets / "character.pngRemix"
            executable.touch()
            model.touch()
            user_config = root / "runtime" / "user_config.json"
            config = {"renderer": {"executable": "", "model_file": ""}}

            with patch("app.QMessageBox.information"), patch(
                "app.QFileDialog.getOpenFileName",
                side_effect=[(str(executable), ""), (str(model), "")],
            ) as picker:
                ensure_renderer_configuration(config, root, user_config)

            self.assertEqual(picker.call_count, 2)
            self.assertTrue(renderer_paths_are_valid(config))
            self.assertTrue(user_config.exists())


if __name__ == "__main__":
    unittest.main()

