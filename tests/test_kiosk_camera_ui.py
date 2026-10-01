"""Regressões da inicialização e dos diagnósticos da câmera do quiosque."""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class KioskCameraUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = (ROOT / "static" / "js" / "reconhecimento.js").read_text(
            encoding="utf-8"
        )
        cls.template = (
            ROOT / "templates" / "reconhecimentoFacial.html"
        ).read_text(encoding="utf-8")

    def test_camera_is_opened_when_page_loads(self):
        self.assertIn("openCamera();", self.script)
        self.assertIn("navigator.mediaDevices.getUserMedia", self.script)
        self.assertIn('facingMode: { ideal: "user" }', self.script)

    def test_camera_errors_are_actionable(self):
        for browser_error in (
            "NotAllowedError",
            "NotFoundError",
            "NotReadableError",
            "SecurityError",
        ):
            self.assertIn(browser_error, self.script)
        self.assertIn("window.isSecureContext", self.script)
        self.assertIn("HTTPS", self.script)

    def test_retry_and_accessible_status_are_present(self):
        self.assertIn('id="btnTentarCamera"', self.template)
        self.assertIn('id="kiosk-status" role="status"', self.template)
        self.assertIn('retryButton.addEventListener("click", openCamera)', self.script)

    def test_stream_is_closed_when_page_is_left(self):
        self.assertIn('window.addEventListener("pagehide", stopCamera)', self.script)
        self.assertIn("track.stop()", self.script)


if __name__ == "__main__":
    unittest.main()
