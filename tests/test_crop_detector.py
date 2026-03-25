"""Tests for src/crop_detector.py."""

import unittest

from src.crop_detector import detect_crop, list_known_crops, CropMatch


class TestDetectCrop(unittest.TestCase):

    # ── Exact / high-confidence matches ───────────────────────────────
    def test_exact_name_wheat(self):
        m = detect_crop("wheat")
        self.assertEqual(m.crop_name, "wheat")
        self.assertGreaterEqual(m.confidence, 0.7)

    def test_sentence_sunflower(self):
        m = detect_crop("I want to create a sunflower crop")
        self.assertEqual(m.crop_name, "sunflower")
        self.assertEqual(m.preset, "oilseed")

    def test_sentence_corn(self):
        m = detect_crop("make me a corn / maize row crop")
        self.assertEqual(m.crop_name, "corn")
        self.assertEqual(m.preset, "row_crop")

    def test_alias_rapeseed(self):
        m = detect_crop("rapeseed")
        self.assertEqual(m.crop_name, "canola")

    def test_alias_soybeans(self):
        m = detect_crop("soybeans")
        self.assertEqual(m.crop_name, "soybean")

    def test_potato(self):
        m = detect_crop("I would like a potato root crop")
        self.assertEqual(m.crop_name, "potato")
        self.assertEqual(m.preset, "root_crop")

    def test_barley(self):
        m = detect_crop("winter barley")
        self.assertEqual(m.crop_name, "barley")

    def test_alfalfa(self):
        m = detect_crop("alfalfa / lucerne forage")
        self.assertEqual(m.crop_name, "alfalfa")
        self.assertEqual(m.preset, "grass")

    # ── Category fallbacks ─────────────────────────────────────────────
    def test_category_grain_fallback(self):
        m = detect_crop("some grain crop called quinoa")
        self.assertEqual(m.preset, "grain")

    def test_category_legume_fallback(self):
        m = detect_crop("a pod-bearing legume called vetch")
        self.assertEqual(m.preset, "legume")

    def test_category_root_fallback(self):
        m = detect_crop("an underground root vegetable tuber")
        self.assertEqual(m.preset, "root_crop")

    # ── Unknown crop ───────────────────────────────────────────────────
    def test_unknown_prompt_returns_crop_match(self):
        m = detect_crop("xyzzy foobar")
        self.assertIsInstance(m, CropMatch)
        self.assertIn(m.preset, ("grain", "row_crop", "root_crop", "oilseed", "legume", "grass"))

    # ── CropMatch properties ───────────────────────────────────────────
    def test_confidence_label_high(self):
        m = detect_crop("wheat")
        self.assertEqual(m.confidence_label, "High")

    def test_config_is_populated(self):
        m = detect_crop("sunflower")
        self.assertIsNotNone(m.config)
        self.assertEqual(m.config.name, "sunflower")
        self.assertEqual(m.config.preset, "oilseed")

    # ── list_known_crops ───────────────────────────────────────────────
    def test_list_known_crops_non_empty(self):
        crops = list_known_crops()
        self.assertGreater(len(crops), 10)

    def test_list_known_crops_schema(self):
        for c in list_known_crops():
            self.assertIn("name", c)
            self.assertIn("title", c)
            self.assertIn("preset", c)
            self.assertIn("description", c)


if __name__ == "__main__":
    unittest.main()
