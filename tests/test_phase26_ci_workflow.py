from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Phase26CiWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = (ROOT / ".github/workflows/phase26-quality.yml").read_text(
            encoding="utf-8"
        )

    def test_postgresql_pgvector_health_and_disposable_credentials_are_explicit(self):
        self.assertIn("pgvector/pgvector:pg16", self.workflow)
        self.assertIn("pg_isready", self.workflow)
        self.assertIn("frequenia_phase25_test", self.workflow)
        self.assertIn("phase26-disposable", self.workflow)
        self.assertNotIn("DATABASE_URL: ${{ secrets.", self.workflow)

    def test_migrations_and_all_postgresql_phases_are_not_silently_skipped(self):
        self.assertIn("python tools/apply_test_migrations.py", self.workflow)
        self.assertIn('python -m unittest discover -s tests -p "test_*.py" -v', self.workflow)
        self.assertRegex(
            self.workflow,
            r"PHASE25_TEST_DATABASE_URL:[^\n]+\n[^\n]*ATTACHMENT_STORAGE_ROOT:[\s\S]+"
            r"test_phase25_postgres_integration\.py",
        )
        self.assertIn("test_phase26_postgres_attachments.py", self.workflow)
        self.assertIn("test_phase27_postgres_integration.py", self.workflow)
        self.assertIn("PHASE27_TEST_DATABASE_URL:", self.workflow)
        self.assertIn("test_phase28_postgres_integration.py", self.workflow)
        self.assertIn("PHASE28_TEST_DATABASE_URL:", self.workflow)
        self.assertIn("PHASE28_SQS_ENDPOINT_URL:", self.workflow)
        self.assertIn("test_phase29_postgres_integration.py", self.workflow)
        self.assertIn("PHASE29_TEST_DATABASE_URL:", self.workflow)
        self.assertIn("test_phase30_postgres_integration.py", self.workflow)
        self.assertIn("PHASE30_TEST_DATABASE_URL:", self.workflow)

    def test_phase27_disposable_dependencies_have_health_checks(self):
        self.assertIn("motoserver/moto:", self.workflow)
        self.assertIn("clamav/clamav:", self.workflow)
        self.assertIn("curl -fsS -o /dev/null http://127.0.0.1:9000/", self.workflow)
        self.assertIn("clamdscan --ping", self.workflow)
        self.assertIn("PHASE27_S3_ENDPOINT_URL:", self.workflow)
        self.assertIn("PHASE27_CLAMAV_HOST:", self.workflow)

    def test_flutter_runs_in_separate_job_and_actions_pin_major_versions(self):
        self.assertRegex(self.workflow, r"(?m)^  flutter:\s*$")
        self.assertIn("flutter analyze", self.workflow)
        self.assertIn("flutter test", self.workflow)
        actions = re.findall(r"uses:\s+([^\s]+)", self.workflow)
        self.assertTrue(actions)
        self.assertTrue(all(re.search(r"@v\d+$", action) for action in actions))

    def test_cleanup_is_unconditional_and_no_production_secret_is_referenced(self):
        self.assertIn("if: always()", self.workflow)
        self.assertIn("runner.temp", self.workflow)
        self.assertNotIn("secrets.", self.workflow)
        self.assertNotIn("SUPABASE_URL", self.workflow)
        self.assertNotIn("SUPABASE_SERVICE", self.workflow)


if __name__ == "__main__":
    unittest.main()
