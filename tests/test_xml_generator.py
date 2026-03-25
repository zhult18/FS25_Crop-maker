"""Tests for src/xml_generator.py."""

import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

from src.utils import CropConfig
from src.xml_generator import generate_fruit_type_xml, generate_mod_desc_entry


def _make_crop(name="testcrop", preset="grain") -> CropConfig:
    c = CropConfig(name=name, title=name.capitalize(), preset=preset)
    c.apply_preset()
    return c


class TestXmlGenerator(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    # ── fruit_type XML ─────────────────────────────────────────────────
    def test_fruit_type_xml_created(self):
        crop = _make_crop()
        p = generate_fruit_type_xml(crop, self.out)
        self.assertTrue(p.exists())
        self.assertEqual(p.name, "testcrop.xml")

    def test_fruit_type_xml_is_valid(self):
        crop = _make_crop()
        p = generate_fruit_type_xml(crop, self.out)
        tree = ET.parse(str(p))
        root = tree.getroot()
        self.assertEqual(root.tag, "fruitType")

    def test_fruit_type_xml_name_attr(self):
        crop = _make_crop("mybeancrop", "legume")
        p = generate_fruit_type_xml(crop, self.out)
        root = ET.parse(str(p)).getroot()
        self.assertEqual(root.get("name"), "mybeancrop")

    def test_growth_states_reflected(self):
        crop = _make_crop()
        p = generate_fruit_type_xml(crop, self.out)
        content = p.read_text()
        self.assertIn(str(crop.numGrowthStates), content)

    def test_texture_filename_in_xml(self):
        crop = _make_crop("sunflower")
        p = generate_fruit_type_xml(crop, self.out)
        content = p.read_text()
        self.assertIn("sunflower_DIFFUSE.png", content)

    # ── modDesc entry ──────────────────────────────────────────────────
    def test_mod_desc_entry_created(self):
        crop = _make_crop()
        p = generate_mod_desc_entry(crop, self.out)
        self.assertTrue(p.exists())
        self.assertIn("modDesc_entry", p.name)

    def test_mod_desc_entry_references_crop(self):
        crop = _make_crop("barleycrop")
        p = generate_mod_desc_entry(crop, self.out)
        content = p.read_text()
        self.assertIn("barleycrop", content)

    # ── Presets round-trip ─────────────────────────────────────────────
    def test_all_presets_produce_valid_xml(self):
        from src.utils import CROP_PRESETS
        for preset in CROP_PRESETS:
            with self.subTest(preset=preset):
                crop = _make_crop(f"crop_{preset}", preset)
                p = generate_fruit_type_xml(crop, self.out)
                root = ET.parse(str(p)).getroot()
                self.assertEqual(root.tag, "fruitType")


if __name__ == "__main__":
    unittest.main()
