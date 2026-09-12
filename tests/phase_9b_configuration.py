import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def env_names(path):
    names = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=", line)
        if match:
            names.add(match.group(1))
    return names


class ConfigurationTests(unittest.TestCase):
    def test_env_example_uses_only_official_runtime_names(self):
        names = env_names(ROOT / ".env.example")
        expected = {
            "APP_ENV",
            "PORT",
            "DATABASE_URL",
            "FLASK_SECRET_KEY",
            "JWT_SECRET_KEY",
            "JWT_ACCESS_TOKEN_MINUTES",
            "JWT_REFRESH_TOKEN_DAYS",
            "PASSWORD_RESET_TOKEN_MINUTES",
            "PASSWORD_RESET_TEST_KEY",
            "CORS_ALLOWED_ORIGINS",
            "FACE_VERIFICATION_MAX_COSINE_DISTANCE",
            "FACIAL_ATTEMPT_MAX_AGE_SECONDS",
            "CLOUDINARY_CLOUD_NAME",
            "CLOUDINARY_API_KEY",
            "CLOUDINARY_API_SECRET",
        }
        self.assertEqual(names, expected)

    def test_backend_does_not_use_obsolete_runtime_aliases(self):
        sources = "\n".join(
            (ROOT / relative).read_text(encoding="utf-8")
            for relative in ("app.py", "db.py", "routes/face.py", "services/face_service.py")
        )
        for obsolete in (
            "DB_HOST",
            "DB_PASSWORD",
            "NEW_DB_HOST",
            "NEW_DB_URL",
            'os.getenv("CLOUD_NAME")',
            'os.getenv("CLOUD_KEY")',
            'os.getenv("CLOUD_SECRET")',
        ):
            self.assertNotIn(obsolete, sources)

    def test_local_env_files_are_ignored_but_example_is_tracked(self):
        ignored_results = [
            subprocess.run(
                ["git", "check-ignore", "--quiet", path],
                cwd=ROOT,
                check=False,
            )
            for path in (".env", ".env.frequenia.local")
        ]
        example = subprocess.run(
            ["git", "ls-files", "--error-unmatch", ".env.example"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertTrue(all(result.returncode == 0 for result in ignored_results))
        self.assertEqual(example.returncode, 0)

    def test_dockerfile_contains_no_secret_arguments_or_values(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertNotRegex(dockerfile, r"(?im)^\s*ARG\s+")
        for secret_name in (
            "DATABASE_URL",
            "FLASK_SECRET_KEY",
            "JWT_SECRET_KEY",
            "CLOUDINARY_API_SECRET",
        ):
            self.assertNotIn(secret_name, dockerfile)

    def test_docker_context_excludes_local_credentials(self):
        dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        rules = {line.strip() for line in dockerignore if line.strip()}
        for expected in (".env", ".env.*", ".secrets", "*.pem", "*.key"):
            self.assertIn(expected, rules)


if __name__ == "__main__":
    unittest.main(verbosity=2)
