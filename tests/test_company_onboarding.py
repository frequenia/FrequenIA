import unittest
from unittest.mock import MagicMock, patch

from flask import Flask

from routes.views import views_bp
from services.company_onboarding import (
    CompanyOnboardingConflict,
    create_company_with_initial_admin,
)
from services.email_service import EmailDeliveryError


COMPANY = "11111111-1111-4111-8111-111111111111"
UNIT = "22222222-2222-4222-8222-222222222222"
TEAM = "33333333-3333-4333-8333-333333333333"
ROLE = "44444444-4444-4444-8444-444444444444"
USER = "55555555-5555-4555-8555-555555555555"
EMPLOYEE = "66666666-6666-4666-8666-666666666666"


def platform_context():
    return {
        "user_id": "77777777-7777-4777-8777-777777777777",
        "funcionario_id": None,
        "session_id": "session",
        "familia_id": "family",
        "empresa_id": None,
        "perfil": "administrador_geral",
    }


def onboarding_response():
    return {
        "empresa": {
            "id": COMPANY,
            "cnpj": "12345678000190",
            "nome": "Empresa Piloto",
            "status": "ativa",
        },
        "administrador": {
            "id": USER,
            "nome": "Responsável RH",
            "email": "responsavel@example.com",
            "status": "bloqueado",
            "primeiro_acesso_pendente": True,
            "funcionario_id": EMPLOYEE,
            "perfil": "administrador",
            "matricula": "GDRH-000001",
        },
        "estrutura": {
            "unidade": {"id": UNIT, "nome": "Matriz", "codigo": "MATRIZ"},
            "equipe": {"id": TEAM, "nome": "Administração/RH"},
            "cargo": {"id": ROLE, "nome": "Gestor de RH", "codigo_matricula": "GDRH"},
        },
    }


class CompanyOnboardingServiceTest(unittest.TestCase):
    @patch("services.company_onboarding.allocate_registration", return_value="GDRH-000001")
    def test_creates_default_structure_blocked_admin_and_audit(self, allocate):
        cursor = MagicMock()
        cursor.fetchone.side_effect = [
            None,
            None,
            {"id": COMPANY, "cnpj": "12345678000190", "nome": "Empresa Piloto", "status": "ativa"},
            {"id": UNIT, "nome": "Matriz", "codigo": "MATRIZ"},
            {"id": TEAM, "nome": "Administração/RH"},
            {"id": ROLE, "nome": "Gestor de RH", "codigo_matricula": "GDRH"},
            {"id": USER, "nome": "Responsável RH", "email": "responsavel@example.com", "status": "bloqueado", "primeiro_acesso_pendente": True},
            {"id": EMPLOYEE},
        ]

        result = create_company_with_initial_admin(
            cursor,
            company_name="Empresa Piloto",
            cnpj="12345678000190",
            administrator={
                "nome": "Responsável RH",
                "cpf": "52998224725",
                "email": "responsavel@example.com",
                "telefone": None,
            },
            credentials={"password_hash": "random-hash", "token_hash": "a" * 64},
            actor_user_id="77777777-7777-4777-8777-777777777777",
            invitation_minutes=30,
        )

        self.assertEqual(result["administrador"]["matricula"], "GDRH-000001")
        self.assertEqual(result["administrador"]["perfil"], "administrador")
        allocate.assert_called_once_with(cursor, COMPANY, ROLE)
        statements = "\n".join(call.args[0] for call in cursor.execute.call_args_list)
        self.assertIn("'bloqueado', true", statements)
        self.assertIn("'administrador', 'ativo'", statements)
        self.assertIn("'first_access'", statements)
        self.assertEqual(statements.count("INSERT INTO auditoria"), 3)

    def test_duplicate_company_is_rejected_before_any_insert(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = {"exists": True}
        with self.assertRaisesRegex(CompanyOnboardingConflict, "CNPJ já cadastrado"):
            create_company_with_initial_admin(
                cursor,
                company_name="Empresa Piloto",
                cnpj="12345678000190",
                administrator={"nome": "Admin", "cpf": "52998224725", "email": "admin@example.com", "telefone": None},
                credentials={"password_hash": "hash", "token_hash": "a" * 64},
                actor_user_id=USER,
                invitation_minutes=30,
            )
        self.assertFalse(any("INSERT INTO" in call.args[0] for call in cursor.execute.call_args_list))

    def test_duplicate_admin_cpf_or_email_is_rejected_before_any_insert(self):
        cases = (
            ({"cpf": "52998224725", "email": "other@example.com"}, "CPF"),
            ({"cpf": "11144477735", "email": "admin@example.com"}, "E-mail"),
        )
        for duplicate, expected in cases:
            with self.subTest(expected=expected):
                cursor = MagicMock()
                cursor.fetchone.side_effect = [None, duplicate]
                with self.assertRaisesRegex(CompanyOnboardingConflict, expected):
                    create_company_with_initial_admin(
                        cursor,
                        company_name="Empresa Piloto",
                        cnpj="12345678000190",
                        administrator={
                            "nome": "Admin",
                            "cpf": "52998224725",
                            "email": "admin@example.com",
                            "telefone": None,
                        },
                        credentials={"password_hash": "hash", "token_hash": "a" * 64},
                        actor_user_id=USER,
                        invitation_minutes=30,
                    )
                self.assertFalse(
                    any("INSERT INTO" in call.args[0] for call in cursor.execute.call_args_list)
                )


class CompanyOnboardingRouteTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__, template_folder="../templates")
        self.app.config.update(
            TESTING=True,
            SECRET_KEY="test",
            PASSWORD_RESET_TOKEN_MINUTES=30,
            JWT_SECRET_KEY="jwt-test-secret-with-at-least-32-bytes",
            JWT_ACCESS_TOKEN_MINUTES=15,
            JWT_REFRESH_TOKEN_DAYS=30,
            REFRESH_COOKIE_SECURE=False,
        )
        self.app.register_blueprint(views_bp)
        self.client = self.app.test_client()
        self.payload = {
            "cnpj": "12.345.678/0001-90",
            "razao": "Empresa Piloto",
            "administrador": {
                "nome": "Responsável RH",
                "cpf": "529.982.247-25",
                "email": "RESPONSAVEL@example.com",
                "telefone": "(11) 99999-9999",
            },
        }

    @patch("routes.views.send_password_reset_email")
    @patch("routes.views.create_company_with_initial_admin")
    @patch("routes.views.first_access_credentials")
    @patch("routes.views.conectar_bd")
    @patch("utils.auth_decorator._load_persistent_authentication")
    def test_company_creation_commits_and_sends_invite(
        self, auth, connect, credentials, create_onboarding, send
    ):
        auth.return_value = (platform_context(), None)
        connection = MagicMock()
        connection.cursor.return_value = MagicMock()
        connect.return_value = connection
        credentials.return_value = {
            "password_hash": "random-hash",
            "raw_token": "raw-token",
            "token_hash": "a" * 64,
        }
        create_onboarding.return_value = onboarding_response()

        response = self.client.post("/cadastrar_empresa", json=self.payload)

        self.assertEqual(response.status_code, 201, response.get_json())
        self.assertEqual(response.get_json()["matricula"], "GDRH-000001")
        self.assertEqual(response.get_json()["convite"]["status"], "enviado")
        connection.commit.assert_called_once_with()
        send.assert_called_once_with("responsavel@example.com", "raw-token", 30)
        passed_admin = create_onboarding.call_args.kwargs["administrator"]
        self.assertEqual(passed_admin["cpf"], "52998224725")
        self.assertEqual(passed_admin["email"], "responsavel@example.com")

    @patch("routes.views.send_password_reset_email", side_effect=EmailDeliveryError("falha"))
    @patch("routes.views.create_company_with_initial_admin")
    @patch("routes.views.first_access_credentials")
    @patch("routes.views.conectar_bd")
    @patch("utils.auth_decorator._load_persistent_authentication")
    def test_email_failure_keeps_created_company_and_returns_resend_state(
        self, auth, connect, credentials, create_onboarding, _send
    ):
        auth.return_value = (platform_context(), None)
        connection = MagicMock()
        connection.cursor.return_value = MagicMock()
        connect.return_value = connection
        credentials.return_value = {
            "password_hash": "random-hash",
            "raw_token": "raw-token",
            "token_hash": "a" * 64,
        }
        create_onboarding.return_value = onboarding_response()

        response = self.client.post("/cadastrar_empresa", json=self.payload)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["status"], "aviso")
        self.assertEqual(response.get_json()["convite"]["status"], "falhou")
        connection.commit.assert_called_once_with()
        connection.rollback.assert_not_called()

    @patch(
        "routes.views.create_company_with_initial_admin",
        side_effect=CompanyOnboardingConflict("CPF do administrador já cadastrado."),
    )
    @patch("routes.views.first_access_credentials")
    @patch("routes.views.conectar_bd")
    @patch("utils.auth_decorator._load_persistent_authentication")
    def test_validation_failure_rolls_back_everything(
        self, auth, connect, credentials, _create_onboarding
    ):
        auth.return_value = (platform_context(), None)
        connection = MagicMock()
        connection.cursor.return_value = MagicMock()
        connect.return_value = connection
        credentials.return_value = {
            "password_hash": "random-hash",
            "raw_token": "raw-token",
            "token_hash": "a" * 64,
        }

        response = self.client.post("/cadastrar_empresa", json=self.payload)

        self.assertEqual(response.status_code, 409)
        self.assertIn("CPF", response.get_json()["mensagem"])
        connection.rollback.assert_called_once_with()
        connection.commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
