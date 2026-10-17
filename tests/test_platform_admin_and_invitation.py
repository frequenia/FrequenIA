import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from werkzeug.security import generate_password_hash

from flask import Flask

from routes.views import views_bp


COMPANY = "11111111-1111-4111-8111-111111111111"
UNIT = "22222222-2222-4222-8222-222222222222"
TEAM = "33333333-3333-4333-8333-333333333333"
ROLE = "44444444-4444-4444-8444-444444444444"


def context(role, company=COMPANY):
    return {
        "user_id": "55555555-5555-4555-8555-555555555555",
        "funcionario_id": None if role == "administrador_geral" else "employee",
        "session_id": "session",
        "familia_id": "family",
        "empresa_id": None if role == "administrador_geral" else company,
        "perfil": role,
    }


class PlatformAdminAndInvitationTest(unittest.TestCase):
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

    @patch("routes.views.criar_auth_session")
    @patch("routes.views.conectar_bd")
    @patch("routes.views.buscar_vinculos_ativos")
    @patch("routes.views.buscar_usuario_login_por_cpf")
    def test_general_admin_login_does_not_require_employee_link(
        self, find_user, find_links, connect, create_session
    ):
        find_user.return_value = {
            "id": uuid4(),
            "nome": "Desenvolvedor",
            "senha_hash": generate_password_hash("senha-muito-segura"),
            "status": "ativo",
            "perfil_sistema": "administrador_geral",
        }
        connection = MagicMock()
        connect.return_value = connection
        create_session.return_value = ({"id": uuid4()}, "refresh-token")

        response = self.client.post(
            "/login",
            json={"cpf": "52998224725", "senha": "senha-muito-segura"},
        )

        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()["tipo"], "administrador_geral")
        self.assertIsNone(response.get_json()["funcionario_id"])
        find_links.assert_not_called()
        platform_link = create_session.call_args.args[2]
        self.assertIsNone(platform_link["empresa_id"])
        self.assertIsNone(platform_link["funcionario_id"])

    @patch("routes.views.criar_auth_session")
    @patch("routes.views.conectar_bd")
    @patch("routes.views.buscar_vinculos_ativos")
    @patch("routes.views.buscar_usuario_login_por_cpf")
    def test_employee_can_login_on_web(
        self, find_user, find_links, connect, create_session
    ):
        find_user.return_value = {
            "id": uuid4(), "nome": "Funcionário",
            "senha_hash": generate_password_hash("Funcionario@2026"),
            "status": "ativo", "perfil_sistema": None,
        }
        find_links.return_value = [{
            "empresa_id": COMPANY,
            "funcionario_id": "77777777-7777-4777-8777-777777777777",
            "perfil": "funcionario",
        }]

        connection = MagicMock()
        connect.return_value = connection
        auth_session_id = uuid4()
        create_session.return_value = ({"id": auth_session_id}, "web-refresh-token")

        response = self.client.post(
            "/login", json={"cpf": "92000000533", "senha": "Funcionario@2026"}
        )

        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()["tipo"], "funcionario")
        with self.client.session_transaction() as web_session:
            self.assertEqual(web_session["tipo"], "funcionario")
            self.assertEqual(web_session["auth_session_id"], str(auth_session_id))

    @patch("routes.views.criar_auth_session")
    @patch("routes.views.conectar_bd")
    @patch("routes.views.buscar_vinculos_ativos")
    @patch("routes.views.buscar_usuario_login_por_cpf")
    def test_employee_can_login_through_token_only_mobile_endpoint(
        self, find_user, find_links, connect, create_session
    ):
        find_user.return_value = {
            "id": uuid4(), "nome": "Funcionário",
            "senha_hash": generate_password_hash("Funcionario@2026"),
            "status": "ativo", "perfil_sistema": None,
        }
        find_links.return_value = [{
            "empresa_id": COMPANY,
            "funcionario_id": "77777777-7777-4777-8777-777777777777",
            "perfil": "funcionario",
        }]
        connection = MagicMock()
        connect.return_value = connection
        create_session.return_value = ({"id": uuid4()}, "mobile-refresh-token")

        response = self.client.post(
            "/api/mobile/login",
            json={"cpf": "92000000533", "senha": "Funcionario@2026"},
        )

        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()["tipo"], "funcionario")
        self.assertNotIn("frequenia_refresh_token", response.headers.get("Set-Cookie", ""))
        with self.client.session_transaction() as web_session:
            self.assertNotIn("user_id", web_session)

    @patch("utils.auth_decorator._load_persistent_authentication")
    def test_hr_cannot_open_platform_company_registration(self, auth):
        auth.return_value = (context("rh"), None)
        self.assertEqual(self.client.get("/cadastroEmpresas").status_code, 403)

    @patch("utils.auth_decorator._load_persistent_authentication")
    def test_settings_are_available_to_general_admin_and_hr(self, auth):
        for role in ("administrador_geral", "rh"):
            with self.subTest(role=role):
                auth.return_value = (context(role), None)
                self.assertEqual(self.client.get("/configuracoes").status_code, 200)

    @patch("utils.auth_decorator._load_persistent_authentication")
    def test_employee_can_open_web_self_service(self, auth):
        auth.return_value = (context("funcionario"), None)
        point = self.client.get("/meu-ponto")
        requests = self.client.get("/minhas-solicitacoes")
        self.assertEqual(point.status_code, 200)
        self.assertEqual(requests.status_code, 200)
        self.assertIn("Ponto somente no quiosque", point.get_data(as_text=True))
        self.assertIn("Nova solicitação", requests.get_data(as_text=True))
        self.assertNotIn("Nova solicitação", point.get_data(as_text=True))

    @patch("utils.auth_decorator._load_persistent_authentication")
    def test_management_cannot_open_employee_self_service(self, auth):
        auth.return_value = (context("rh"), None)
        self.assertEqual(self.client.get("/meu-ponto").status_code, 403)
        self.assertEqual(self.client.get("/minhas-solicitacoes").status_code, 403)

    @patch("utils.auth_decorator._load_persistent_authentication")
    def test_manual_clock_creation_is_not_available(self, auth):
        auth.return_value = (context("funcionario"), None)
        self.assertEqual(
            self.client.post("/api/marcacoes", json={"tipo": "entrada"}).status_code,
            405,
        )

        facial = self.client.post(
            "/api/marcacoes/facial",
            json={"tipo": "entrada", "tentativa_facial_id": str(uuid4()), "empresa_id": COMPANY},
        )
        self.assertEqual(facial.status_code, 400)
        self.assertIn("identificadores", facial.get_json()["erro"])

    @patch("utils.auth_decorator._load_persistent_authentication")
    def test_platform_dashboard_is_general_admin_only(self, auth):
        auth.return_value = (context("administrador_geral"), None)
        self.assertEqual(self.client.get("/plataforma").status_code, 200)
        auth.return_value = (context("rh"), None)
        self.assertEqual(self.client.get("/plataforma").status_code, 403)

    @patch("utils.auth_decorator._load_persistent_authentication")
    def test_company_form_collects_first_administrator(self, auth):
        auth.return_value = (context("administrador_geral"), None)
        response = self.client.get("/cadastroEmpresas")
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        for field in ("adminNome", "adminCpf", "adminEmail", "adminTelefone"):
            self.assertIn(f'id="{field}"', body)
        self.assertIn("Administração/RH", body)
        self.assertIn("GDRH automática", body)

    @patch("utils.auth_decorator._load_persistent_authentication")
    def test_hr_cannot_change_company_status(self, auth):
        auth.return_value = (context("rh"), None)
        response = self.client.patch(
            f"/api/plataforma/empresas/{COMPANY}/status", json={"status": "inativa"}
        )
        self.assertEqual(response.status_code, 403)

    @patch("routes.views.conectar_bd")
    @patch("utils.auth_decorator._load_persistent_authentication")
    def test_general_admin_can_change_company_status(self, auth, connect):
        auth.return_value = (context("administrador_geral"), None)
        connection = MagicMock()
        cursor = MagicMock()
        cursor.fetchone.return_value = {
            "id": COMPANY,
            "nome": "Empresa",
            "cnpj": "99000000000101",
            "status": "inativa",
            "updated_at": None,
        }
        connection.cursor.return_value.__enter__.return_value = cursor
        connect.return_value = connection

        response = self.client.patch(
            f"/api/plataforma/empresas/{COMPANY}/status", json={"status": "inativa"}
        )

        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()["empresa"]["status"], "inativa")
        self.assertIn("empresa.status_alterado", cursor.execute.call_args_list[-1].args[0])

    @patch("routes.views.conectar_bd")
    @patch("utils.auth_decorator._load_persistent_authentication")
    def test_general_admin_summary_returns_only_aggregates(self, auth, connect):
        auth.return_value = (context("administrador_geral"), None)
        connection = MagicMock()
        cursor = MagicMock()
        cursor.fetchone.return_value = {
            "empresas_total": 2,
            "empresas_ativas": 1,
            "empresas_inativas": 1,
            "funcionarios_ativos": 8,
            "terminais_ativos": 2,
            "terminais_revogados": 1,
            "primeiros_acessos_pendentes": 3,
        }
        connection.cursor.return_value.__enter__.return_value = cursor
        connect.return_value = connection

        response = self.client.get("/api/plataforma/resumo")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["resumo"]["funcionarios_ativos"], 8)
        self.assertNotIn("funcionarios", response.get_json())

    @patch("routes.views.conectar_bd")
    @patch("utils.auth_decorator._load_persistent_authentication")
    def test_company_detail_exposes_admins_and_terminal_metadata(self, auth, connect):
        auth.return_value = (context("administrador_geral"), None)
        connection = MagicMock()
        cursor = MagicMock()
        cursor.fetchone.side_effect = [
            {"id": COMPANY, "nome": "Empresa", "cnpj": "99000000000101", "status": "ativa"},
            {"unidades": 1, "equipes": 1, "funcionarios": 4, "funcionarios_ativos": 4, "terminais": 1, "terminais_ativos": 1},
        ]
        cursor.fetchall.side_effect = [
            [{"id": "admin", "nome": "Responsável", "email": "admin@example.invalid", "primeiro_acesso_pendente": False}],
            [{"id": "terminal", "nome": "Recepção", "status": "ativo"}],
        ]
        connection.cursor.return_value.__enter__.return_value = cursor
        connect.return_value = connection

        response = self.client.get(f"/api/plataforma/empresas/{COMPANY}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["administradores"][0]["nome"], "Responsável")
        self.assertEqual(response.get_json()["terminais"][0]["status"], "ativo")

    @patch("routes.views.conectar_bd")
    @patch("utils.auth_decorator._load_persistent_authentication")
    def test_platform_audit_escapes_like_wildcard_for_psycopg(self, auth, connect):
        auth.return_value = (context("administrador_geral"), None)
        connection = MagicMock()
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        connection.cursor.return_value.__enter__.return_value = cursor
        connect.return_value = connection

        response = self.client.get("/api/plataforma/auditoria?limite=10")

        self.assertEqual(response.status_code, 200)
        self.assertIn("LIKE 'empresa.%%'", cursor.execute.call_args.args[0])

    @patch("routes.views.send_password_reset_email")
    @patch("routes.views.first_access_credentials")
    @patch("routes.views.conectar_bd")
    @patch("utils.auth_decorator._load_persistent_authentication")
    def test_general_admin_can_resend_pending_company_admin_invite(
        self, auth, connect, credentials, send
    ):
        auth.return_value = (context("administrador_geral"), None)
        connection = MagicMock()
        cursor = MagicMock()
        cursor.fetchone.return_value = {"id": "admin-user", "email": "admin@example.invalid"}
        connection.cursor.return_value.__enter__.return_value = cursor
        connect.return_value = connection
        credentials.return_value = {
            "password_hash": "random-hash",
            "raw_token": "invite-token",
            "token_hash": "b" * 64,
        }

        response = self.client.post(
            f"/api/plataforma/empresas/{COMPANY}/administradores/"
            "66666666-6666-4666-8666-666666666666/reenviar-convite"
        )

        self.assertEqual(response.status_code, 200, response.get_json())
        send.assert_called_once_with("admin@example.invalid", "invite-token", 30)

    @patch("routes.views.send_password_reset_email")
    @patch("routes.views.first_access_credentials")
    @patch("routes.views.allocate_registration")
    @patch("routes.views.conectar_bd")
    @patch("utils.auth_decorator._load_persistent_authentication")
    def test_employee_creation_generates_registration_and_sends_first_access(
        self, auth, connect, allocate, credentials, send
    ):
        auth.return_value = (context("administrador"), None)
        connection = MagicMock()
        cursor = MagicMock()
        cursor.fetchone.side_effect = [None, {"ok": 1}, {"id": "new-user"}]
        connection.cursor.return_value = cursor
        connect.return_value = connection
        allocate.return_value = "RH-000001"
        credentials.return_value = {
            "password_hash": "random-password-hash",
            "raw_token": "first-access-token",
            "token_hash": "a" * 64,
        }

        response = self.client.post(
            "/cadastrar_usuario",
            json={
                "nome": "Pessoa Teste",
                "email": "pessoa@example.com",
                "telefone": "11999999999",
                "cpf": "52998224725",
                "empresa_id": COMPANY,
                "unidade_id": UNIT,
                "equipe_id": TEAM,
                "cargo_id": ROLE,
                "perfil": "rh",
                "tipo_contrato": "efetivo",
                "data_admissao": "2026-10-06",
                "carga_horaria_semanal": "40",
            },
        )

        self.assertEqual(response.status_code, 201, response.get_json())
        self.assertEqual(response.get_json()["matricula"], "RH-000001")
        send.assert_called_once_with("pessoa@example.com", "first-access-token", 30)
        sql = "\n".join(call.args[0] for call in cursor.execute.call_args_list)
        self.assertIn("primeiro_acesso_pendente", sql)
        self.assertIn("'first_access'", sql)
        self.assertNotIn("senha", response.get_json())


if __name__ == "__main__":
    unittest.main()
