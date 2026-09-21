"""Regressões dos cinco achados da auditoria facial legada."""

import io
import os
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("FLASK_SECRET_KEY", "x" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "security-test-jwt-key")

import app


ROOT = Path(__file__).resolve().parents[1]
LEGACY_PATHS = (
    "/iniciar_cadastro",
    "/adicionar_foto",
    "/finalizar_cadastro",
    "/reconhecer",
    "/confirmar_ponto",
)
COMPANY_A = "00000000-0000-0000-0000-000000000011"
COMPANY_B = "00000000-0000-0000-0000-000000000012"
EMPLOYEE_A = "00000000-0000-0000-0000-000000000021"
EMPLOYEE_B = "00000000-0000-0000-0000-000000000022"
USER_A = "00000000-0000-0000-0000-000000000031"
USER_B = "00000000-0000-0000-0000-000000000032"
SESSION_A = "00000000-0000-0000-0000-000000000041"


def auth_context(company=COMPANY_A, employee=EMPLOYEE_A, user=USER_A, role="funcionario"):
    return {
        "session_id": SESSION_A,
        "familia_id": "00000000-0000-0000-0000-000000000042",
        "user_id": user,
        "funcionario_id": employee,
        "empresa_id": company,
        "perfil": role,
    }


class LegacyFaceSecurityTests(unittest.TestCase):
    def test_all_legacy_routes_are_inert_for_anonymous_and_any_role(self):
        for role in (None, "funcionario", "gestor", "rh", "administrador"):
            with self.subTest(role=role):
                client = app.app.test_client()
                if role:
                    with client.session_transaction() as session:
                        session.update({
                            "user_id": USER_A,
                            "funcionario_id": EMPLOYEE_A,
                            "auth_session_id": SESSION_A,
                        })
                with (
                    patch("db.conectar_bd") as database,
                    patch("shutil.rmtree") as recursive_delete,
                    patch("os.makedirs") as mkdir,
                    patch("cloudinary.uploader.upload") as cloud_upload,
                ):
                    for path in LEGACY_PATHS:
                        response = client.post(path, json={"nome": "Pessoa", "imagem": "fake"})
                        self.assertEqual(response.status_code, 410, (role, path))
                        self.assertNotIn("nome", response.get_json())
                    database.assert_not_called()
                    recursive_delete.assert_not_called()
                    mkdir.assert_not_called()
                    cloud_upload.assert_not_called()

    def test_path_traversal_and_absolute_paths_are_inert(self):
        client = app.app.test_client()
        for name in ("../static", "..\\static", "/tmp/outside", "C:\\Windows\\Temp", "Pessoa"):
            for path in ("/iniciar_cadastro", "/adicionar_foto", "/finalizar_cadastro"):
                with self.subTest(name=name, path=path):
                    with patch("shutil.rmtree") as recursive_delete:
                        response = client.post(path, json={"nome": name, "imagem": "fake"})
                    self.assertEqual(response.status_code, 410)
                    recursive_delete.assert_not_called()

    def test_legacy_module_has_no_global_search_or_file_operations(self):
        source = (ROOT / "routes" / "face.py").read_text(encoding="utf-8")
        for forbidden in ("FROM fotos", "JOIN fotos", "INTO fotos", "rmtree", "imwrite", "nome =", "cloudinary"):
            self.assertNotIn(forbidden, source)

    def test_modern_verification_is_one_to_one_even_for_homonyms(self):
        for company, employee, user in (
            (COMPANY_A, EMPLOYEE_A, USER_A),
            (COMPANY_B, EMPLOYEE_B, USER_B),
        ):
            with self.subTest(company=company):
                client = app.app.test_client()
                with client.session_transaction() as session:
                    session.update({"user_id": user, "funcionario_id": employee, "auth_session_id": SESSION_A})
                with (
                    patch("utils.auth_decorator.buscar_sessao_access", return_value=auth_context(company, employee, user)),
                    patch("routes.biometrics._active_biometric", return_value=None) as active,
                    patch("routes.biometrics._record_face_attempt", return_value="attempt"),
                ):
                    response = client.post("/api/biometria/verificar", data={"nome": "Mesmo Nome"})
                self.assertEqual(response.status_code, 409)
                active.assert_called_once_with(employee, company)
                self.assertNotIn("nome", response.get_json())

    def test_foreign_employee_cannot_be_enrolled_and_client_cannot_choose_identity(self):
        client = app.app.test_client()
        with client.session_transaction() as session:
            session.update({"user_id": USER_A, "funcionario_id": EMPLOYEE_A, "auth_session_id": SESSION_A})
        with (
            patch("utils.auth_decorator.buscar_sessao_access", return_value=auth_context(role="administrador")),
            patch("routes.biometrics._employee_exists", return_value=False) as exists,
        ):
            response = client.post(f"/api/admin/funcionarios/{EMPLOYEE_B}/biometria")
        self.assertEqual(response.status_code, 404)
        exists.assert_called_once_with(EMPLOYEE_B, COMPANY_A, active_only=True)

        with (
            patch("utils.auth_decorator.buscar_sessao_access", return_value=auth_context()),
            patch("routes.biometrics._active_biometric") as active,
        ):
            response = client.post(
                "/api/biometria/verificar",
                data={"funcionario_id": EMPLOYEE_B, "empresa_id": COMPANY_B,
                      "imagem": (io.BytesIO(b"irrelevant"), "face.jpg")},
            )
        self.assertEqual(response.status_code, 400)
        active.assert_not_called()

    def test_non_admin_cannot_enroll_or_read_biometrics(self):
        client = app.app.test_client()
        with client.session_transaction() as session:
            session.update({"user_id": USER_A, "funcionario_id": EMPLOYEE_A, "auth_session_id": SESSION_A})
        for role in ("funcionario", "gestor", "rh"):
            with self.subTest(role=role):
                with patch("utils.auth_decorator.buscar_sessao_access", return_value=auth_context(role=role)):
                    self.assertEqual(client.post(f"/api/admin/funcionarios/{EMPLOYEE_A}/biometria").status_code, 403)
                    self.assertEqual(client.get(f"/api/admin/funcionarios/{EMPLOYEE_A}/biometria").status_code, 403)


if __name__ == "__main__":
    unittest.main()
