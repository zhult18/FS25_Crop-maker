"""Tests for the crop-maker web server (crop_maker.py) API handlers."""

import json
import tempfile
import threading
import unittest
import urllib.request
import zipfile

from src.crop_maker import make_server


def _find_free_port() -> int:
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestCropMakerServer(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp   = tempfile.TemporaryDirectory()
        cls.port  = _find_free_port()
        cls.server = make_server(cls.port, cls.tmp.name)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.tmp.cleanup()

    def _get(self, path: str):
        with urllib.request.urlopen(self.base + path) as r:
            return r.status, json.loads(r.read())

    def _post(self, path: str, body: dict):
        data = json.dumps(body).encode()
        req  = urllib.request.Request(
            self.base + path, data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())

    # ── GET / ──────────────────────────────────────────────────────────
    def test_spa_root_returns_html(self):
        req = urllib.request.Request(self.base + "/")
        with urllib.request.urlopen(req) as r:
            self.assertEqual(r.status, 200)
            ct = r.headers.get("Content-Type", "")
            self.assertIn("text/html", ct)
            body = r.read().decode()
            self.assertIn("FS25 Crop Maker", body)

    # ── GET /api/crops ─────────────────────────────────────────────────
    def test_crops_endpoint(self):
        status, data = self._get("/api/crops")
        self.assertEqual(status, 200)
        self.assertIn("crops", data)
        self.assertGreater(len(data["crops"]), 10)

    # ── POST /api/detect ───────────────────────────────────────────────
    def test_detect_wheat(self):
        status, data = self._post("/api/detect", {"prompt": "wheat"})
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["crop"]["crop_name"], "wheat")

    def test_detect_returns_preview_b64(self):
        _, data = self._post("/api/detect", {"prompt": "sunflower"})
        self.assertIn("preview_diffuse_b64", data)
        self.assertIn("preview_icon_b64", data)
        # Should be valid base64
        import base64
        base64.b64decode(data["preview_diffuse_b64"])

    def test_detect_missing_prompt(self):
        req = urllib.request.Request(
            self.base + "/api/detect",
            data=json.dumps({}).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req) as r:
                data = json.loads(r.read())
                self.assertFalse(data.get("ok", True))
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)

    # ── POST /api/generate ─────────────────────────────────────────────
    def test_generate_creates_files(self):
        status, data = self._post("/api/generate", {
            "prompt": "wheat",
            "name": "testwheatsrv",
            "title": "Test Wheat",
            "preset": "grain",
        })
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertIn("session_id", data)
        self.assertGreater(len(data["files"]), 0)

    def test_generate_returns_previews(self):
        _, data = self._post("/api/generate", {
            "prompt": "corn",
            "name": "testcornsrv",
            "title": "Test Corn",
            "preset": "row_crop",
        })
        self.assertIn("preview_diffuse_b64", data)
        self.assertIn("preview_icon_b64", data)

    # ── GET /api/download ──────────────────────────────────────────────
    def test_download_zip(self):
        # First generate
        _, gen = self._post("/api/generate", {
            "prompt": "barley",
            "name": "testbarleysrv",
            "title": "Test Barley",
            "preset": "grain",
        })
        sid = gen["session_id"]

        # Then download
        req = urllib.request.Request(f"{self.base}/api/download?session={sid}")
        with urllib.request.urlopen(req) as r:
            self.assertEqual(r.status, 200)
            ct = r.headers.get("Content-Type", "")
            self.assertIn("zip", ct)
            zdata = r.read()

        # Should be a valid ZIP containing at least one XML file
        import io
        with zipfile.ZipFile(io.BytesIO(zdata)) as zf:
            names = zf.namelist()
            self.assertTrue(any(".xml" in n for n in names))

    def test_download_invalid_session(self):
        req = urllib.request.Request(f"{self.base}/api/download?session=invalid_xyz")
        try:
            with urllib.request.urlopen(req) as r:
                data = json.loads(r.read())
                self.assertIn("error", data)
        except urllib.error.HTTPError as e:
            self.assertIn(e.code, (404, 500))


if __name__ == "__main__":
    unittest.main()
