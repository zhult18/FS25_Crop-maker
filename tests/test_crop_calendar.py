"""Tests for the crop calendar web server (crop_calendar.py) API."""

import json
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

from src.crop_calendar import make_server, generate_calendar_html
from src.utils import CalendarEntry, CropConfig


def _find_free_port() -> int:
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestCalendarServer(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp    = tempfile.TemporaryDirectory()
        cls.port   = _find_free_port()
        cls.server = make_server(cls.port, cls.tmp.name)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.tmp.cleanup()

    def _post(self, path: str, body: dict):
        data = json.dumps(body).encode()
        req  = urllib.request.Request(
            self.base + path, data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())

    # ── GET / ──────────────────────────────────────────────────────────
    def test_root_returns_html(self):
        req = urllib.request.Request(self.base + "/")
        with urllib.request.urlopen(req) as r:
            self.assertEqual(r.status, 200)
            body = r.read().decode()
            self.assertIn("FS25 Crop Calendar", body)

    # ── POST /api/save ─────────────────────────────────────────────────
    def test_save_config(self):
        status, data = self._post("/api/save", {
            "name": "testwheat",
            "title": "Test Wheat",
            "preset": "grain",
            "calendar": [{"zone": "temperate", "planting_months": [3, 4],
                           "growing_months": [4, 5, 6], "harvesting_months": [7, 8]}],
        })
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertIn("path", data)
        self.assertTrue(Path(data["path"]).exists())

    # ── POST /api/export-html ──────────────────────────────────────────
    def test_export_html(self):
        status, data = self._post("/api/export-html", {
            "name": "testcorn",
            "title": "Test Corn",
            "preset": "row_crop",
            "calendar": [{"zone": "tropical", "planting_months": [1, 2],
                           "growing_months": [2, 3, 4], "harvesting_months": [5]}],
        })
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertIn("html", data)
        self.assertIn("FS25 Crop Calendar", data["html"])
        self.assertIn("testcorn", data["html"])


class TestGenerateCalendarHtml(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _make_crop(self) -> CropConfig:
        c = CropConfig(name="wheat", title="Wheat", preset="grain")
        c.apply_preset()
        c.calendar = [
            CalendarEntry(
                zone="temperate",
                planting_months=[3, 4],
                growing_months=[4, 5, 6, 7],
                harvesting_months=[7, 8],
            )
        ]
        return c

    def test_html_file_created(self):
        crop = self._make_crop()
        p = generate_calendar_html(crop, self.out)
        self.assertTrue(p.exists())
        self.assertEqual(p.suffix, ".html")

    def test_html_contains_crop_name(self):
        crop = self._make_crop()
        p = generate_calendar_html(crop, self.out)
        self.assertIn("wheat", p.read_text())

    def test_html_contains_zone(self):
        crop = self._make_crop()
        p = generate_calendar_html(crop, self.out)
        self.assertIn("temperate", p.read_text().lower())

    def test_html_colour_classes_present(self):
        crop = self._make_crop()
        p = generate_calendar_html(crop, self.out)
        content = p.read_text()
        for cls in ("plant", "grow", "harvest"):
            self.assertIn(cls, content)

    def test_no_calendar_graceful(self):
        crop = CropConfig(name="empty", title="Empty", preset="grain")
        crop.apply_preset()
        p = generate_calendar_html(crop, self.out)
        self.assertIn("No calendar data", p.read_text())


if __name__ == "__main__":
    unittest.main()
