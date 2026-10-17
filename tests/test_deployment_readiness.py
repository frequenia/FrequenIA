import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[1]


class DeploymentReadinessTests(unittest.TestCase):
    def test_admin_assets_do_not_call_a_loopback_backend(self):
        loopback_url = re.compile(r"https?://(?:127\.0\.0\.1|localhost)(?::\d+)?")
        offenders = []
        for directory in (PROJECT_ROOT / "static", PROJECT_ROOT / "templates"):
            for path in directory.rglob("*"):
                if path.is_file() and path.suffix.lower() in {".js", ".html"}:
                    if loopback_url.search(path.read_text(encoding="utf-8")):
                        offenders.append(str(path.relative_to(PROJECT_ROOT)))

        self.assertEqual(offenders, [])

    def test_docker_image_preloads_both_facial_models(self):
        dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn("model_name='Fasnet'", dockerfile)
        self.assertIn("model_name='ArcFace'", dockerfile)
        self.assertIn("--retry-all-errors", dockerfile)
        self.assertIn("--continue-at -", dockerfile)
        self.assertIn("FROM python:3.10-slim AS builder", dockerfile)
        self.assertIn("COPY --from=builder /root/.deepface", dockerfile)
        self.assertIn("libpq5", dockerfile)
        self.assertIn("0.0.0.0:${PORT:-5000}", dockerfile)

    def test_compose_exposes_the_documented_local_port_and_healthcheck(self):
        compose = (PROJECT_ROOT / "compose.yaml").read_text(encoding="utf-8")

        self.assertIn('"5013:5000"', compose)
        self.assertIn("/health", compose)
        self.assertIn(".env", compose)

    def test_docker_context_excludes_local_artifacts(self):
        ignore = (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8")

        self.assertIn("mobile\n", ignore)
        self.assertIn("tools/*\n", ignore)
        self.assertIn("!tools/dispatch_attachment_scan_jobs.py\n", ignore)
        self.assertIn("!tools/run_attachment_scan_worker.py\n", ignore)
        self.assertIn("tests\n", ignore)
        self.assertIn("output\n", ignore)
        self.assertIn("document-assets\n", ignore)


if __name__ == "__main__":
    unittest.main()
