"""Tests for src/texture_generator.py and the preview helpers."""

import base64
import tempfile
import unittest
from pathlib import Path

from src.utils import CropConfig
from src.texture_generator import (
    generate_all_textures,
    generate_diffuse_preview_b64,
    generate_icon_preview_b64,
)


def _make_crop(name="testcrop", preset="grain") -> CropConfig:
    # Use a smaller texture so tests run fast
    c = CropConfig(name=name, title=name.capitalize(), preset=preset, textureSize=256)
    c.apply_preset()
    c.textureSize = 256  # override after preset
    return c


class TestTextureGenerator(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_all_textures_created(self):
        crop = _make_crop()
        paths = generate_all_textures(crop, self.out)
        for role, p in paths.items():
            with self.subTest(role=role):
                self.assertTrue(p.exists(), f"{role} missing: {p}")

    def test_diffuse_is_png(self):
        from PIL import Image
        crop = _make_crop()
        paths = generate_all_textures(crop, self.out)
        with Image.open(paths["diffuse"]) as img:
            self.assertEqual(img.format, "PNG")

    def test_diffuse_correct_size(self):
        from PIL import Image
        crop = _make_crop()
        paths = generate_all_textures(crop, self.out)
        with Image.open(paths["diffuse"]) as img:
            self.assertEqual(img.size, (256, 256))

    def test_normal_rgb(self):
        from PIL import Image
        crop = _make_crop()
        paths = generate_all_textures(crop, self.out)
        with Image.open(paths["normal"]) as img:
            self.assertEqual(img.mode, "RGB")

    def test_roughness_grayscale(self):
        from PIL import Image
        crop = _make_crop()
        paths = generate_all_textures(crop, self.out)
        with Image.open(paths["roughness"]) as img:
            self.assertEqual(img.mode, "L")

    def test_icon_rgba_128(self):
        from PIL import Image
        crop = _make_crop()
        paths = generate_all_textures(crop, self.out)
        with Image.open(paths["icon"]) as img:
            self.assertEqual(img.mode, "RGBA")
            self.assertEqual(img.size, (128, 128))

    def test_all_presets_generate(self):
        from src.utils import CROP_PRESETS
        for preset in CROP_PRESETS:
            with self.subTest(preset=preset):
                crop = _make_crop(f"crop_{preset}", preset)
                paths = generate_all_textures(crop, self.out)
                self.assertGreater(len(paths), 0)

    # ── Preview helpers ────────────────────────────────────────────────
    def test_preview_b64_is_valid_png(self):
        from PIL import Image
        import io
        crop = _make_crop()
        b64 = generate_diffuse_preview_b64(crop, 128)
        raw = base64.b64decode(b64)
        img = Image.open(io.BytesIO(raw))
        self.assertEqual(img.format, "PNG")
        self.assertEqual(img.size, (128, 128))

    def test_preview_b64_does_not_alter_texture_size(self):
        crop = _make_crop()
        original = crop.textureSize
        generate_diffuse_preview_b64(crop, 128)
        self.assertEqual(crop.textureSize, original)

    def test_icon_b64_is_valid_png(self):
        from PIL import Image
        import io
        crop = _make_crop()
        b64 = generate_icon_preview_b64(crop)
        raw = base64.b64decode(b64)
        img = Image.open(io.BytesIO(raw))
        self.assertEqual(img.format, "PNG")
        self.assertEqual(img.size, (128, 128))


if __name__ == "__main__":
    unittest.main()
