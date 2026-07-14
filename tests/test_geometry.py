from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from app import calculate_model_zoom_steps, corrected_logical_position


class PetGeometryTests(unittest.TestCase):
    def test_model_zoom_tracks_window_scale(self) -> None:
        config = {
            "renderer": {
                "zoom_steps": -6,
                "reference_width": 640,
                "reference_height": 400,
                "zoom_ratio_per_step": 0.9,
            },
            "ui": {"width": 540, "height": 338},
        }

        self.assertEqual(calculate_model_zoom_steps(config), -8)

    def test_native_frame_offset_is_removed_from_target_position(self) -> None:
        # Qt requested (1376, 682), but the native transparent window appeared
        # at (1393, 664): +17 horizontally and -18 vertically.
        corrected = corrected_logical_position(
            target_x=1376,
            target_y=682,
            logical_x=1376,
            logical_y=682,
            native_x=1393,
            native_y=664,
        )

        self.assertEqual(corrected, (1359, 700))


if __name__ == "__main__":
    unittest.main()

