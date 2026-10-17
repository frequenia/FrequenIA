"""Homologacao opt-in da Fase 25 contra PostgreSQL real.

Esta suite nunca usa DATABASE_URL. Ela exige PHASE25_TEST_DATABASE_URL e aceita
somente um PostgreSQL local cujo database seja ``frequenia_phase25_test``.
"""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
import io
import os
from pathlib import Path
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlparse
from uuid import UUID

from docx import Document
from flask import Flask
import psycopg2
import psycopg2.extras

from routes.occurrences import occurrences_bp
from routes.timekeeping import timekeeping_bp
from services.correction_workflow import (
    CorrectionWorkflowError,
    transition_correction,
)
from services.effective_timekeeping import fetch_effective_events


ROOT = Path(__file__).resolve().parents[1]
TEST_DATABASE_URL = os.environ.get("PHASE25_TEST_DATABASE_URL", "").strip()
LOCAL_DATABASE_NAME = "frequenia_phase25_test"
AUTH_HEADER = {"Authorization": "Bearer phase25-fixture"}


def _safe_test_url():
    parsed = urlparse(TEST_DATABASE_URL)
    if not TEST_DATABASE_URL:
        return False
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise RuntimeError("PHASE25_TEST_DATABASE_URL deve apontar para PostgreSQL.")
    allowed_hosts={"localhost", "127.0.0.1", "::1"}
    disposable_host=os.environ.get("FREQUENIA_DISPOSABLE_TEST_HOST","").strip()
    if disposable_host: allowed_hosts.add(disposable_host)
    if parsed.hostname not in allowed_hosts:
        raise RuntimeError("A homologacao da Fase 25 aceita somente PostgreSQL local.")
    if parsed.path != f"/{LOCAL_DATABASE_NAME}":
        raise RuntimeError(
            f"O database descartavel deve se chamar {LOCAL_DATABASE_NAME}."
        )
    return True


POSTGRES_ENABLED = _safe_test_url()


def _connect(dict_rows=False):
    kwargs = {}
    if dict_rows:
        kwargs["cursor_factory"] = psycopg2.extras.RealDictCursor
    return psycopg2.connect(TEST_DATABASE_URL, connect_timeout=5, **kwargs)


def _reset_database():
    connection = _connect()
    connection.autocommit = True
    try:
        with connection.cursor() as cursor:
            cursor.execute("DROP EXTENSION IF EXISTS vector CASCADE")
            cursor.execute("DROP EXTENSION IF EXISTS pgcrypto CASCADE")
            cursor.execute("DROP SCHEMA IF EXISTS public CASCADE")
            cursor.execute("DROP SCHEMA IF EXISTS extensions CASCADE")
            cursor.execute("CREATE SCHEMA public")
    finally:
        connection.close()


def _apply_migrations(first, last):
    connection = _connect()
    connection.autocommit = True
    try:
        with connection.cursor() as cursor:
            for number in range(first, last + 1):
                matches = sorted(
                    (ROOT / "supabase" / "migrations").glob(f"{number:03d}_*.sql")
                )
                if len(matches) != 1:
                    raise AssertionError(
                        f"Esperada uma migration {number:03d}, encontradas {len(matches)}."
                    )
                cursor.execute(matches[0].read_text(encoding="utf-8"))
    finally:
        connection.close()


def _insert_legacy_rows():
    connection = _connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO empresas (id, nome) VALUES "
                "('10000000-0000-0000-0000-000000000001', 'Legacy Fixture')"
            )
            cursor.execute(
                """INSERT INTO unidades (id, empresa_id, nome)
                   VALUES ('10000000-0000-0000-0000-000000000002',
                           '10000000-0000-0000-0000-000000000001', 'Legacy Unit')"""
            )
            cursor.execute(
                """INSERT INTO usuarios (id, nome, cpf, senha_hash)
                   VALUES ('10000000-0000-0000-0000-000000000003',
                           'Legacy User', '90000000001', 'fixture')"""
            )
            cursor.execute(
                """INSERT INTO funcionarios
                   (id, usuario_id, empresa_id, unidade_id, matricula)
                   VALUES ('10000000-0000-0000-0000-000000000004',
                           '10000000-0000-0000-0000-000000000003',
                           '10000000-0000-0000-0000-000000000001',
                           '10000000-0000-0000-0000-000000000002', 'LEGACY')"""
            )
            for offset, state in enumerate(
                ("solicitada", "em_analise_gestor", "em_analise_rh", "encaminhada_rh"),
                start=10,
            ):
                cursor.execute(
                    """INSERT INTO correcoes
                       (id, empresa_id, funcionario_id, solicitante_usuario_id,
                        tipo, categoria, motivo, estado)
                       VALUES (%s,
                               '10000000-0000-0000-0000-000000000001',
                               '10000000-0000-0000-0000-000000000004',
                               '10000000-0000-0000-0000-000000000003',
                               'justificativa', 'justificativa', 'Legacy', %s)""",
                    (f"10000000-0000-0000-0000-{offset:012d}", state),
                )
        connection.commit()
    finally:
        connection.close()


@unittest.skipUnless(
    POSTGRES_ENABLED,
    "requer PHASE25_TEST_DATABASE_URL explicita para frequenia_phase25_test local",
)
class Phase25PostgresIntegrationTests(unittest.TestCase):
    COMPANY = "20000000-0000-0000-0000-000000000001"
    UNIT = "20000000-0000-0000-0000-000000000002"
    TEAM = "20000000-0000-0000-0000-000000000003"
    OTHER_TEAM = "20000000-0000-0000-0000-000000000004"
    FOREIGN_COMPANY = "30000000-0000-0000-0000-000000000001"
    FOREIGN_UNIT = "30000000-0000-0000-0000-000000000002"
    FOREIGN_TEAM = "30000000-0000-0000-0000-000000000003"

    EMPLOYEE_USER = "21000000-0000-0000-0000-000000000001"
    EMPLOYEE = "22000000-0000-0000-0000-000000000001"
    OTHER_USER = "21000000-0000-0000-0000-000000000002"
    OTHER_EMPLOYEE = "22000000-0000-0000-0000-000000000002"
    MANAGER_USER = "21000000-0000-0000-0000-000000000003"
    MANAGER = "22000000-0000-0000-0000-000000000003"
    HR_USER = "21000000-0000-0000-0000-000000000004"
    HR = "22000000-0000-0000-0000-000000000004"
    ADMIN_USER = "21000000-0000-0000-0000-000000000005"
    ADMIN = "22000000-0000-0000-0000-000000000005"
    FOREIGN_USER = "31000000-0000-0000-0000-000000000001"
    FOREIGN_EMPLOYEE = "32000000-0000-0000-0000-000000000001"
    FOREIGN_HR_USER = "31000000-0000-0000-0000-000000000002"
    FOREIGN_HR = "32000000-0000-0000-0000-000000000002"
    FOREIGN_ADMIN_USER = "31000000-0000-0000-0000-000000000003"
    FOREIGN_ADMIN = "32000000-0000-0000-0000-000000000003"

    MARKING = "23000000-0000-0000-0000-000000000001"
    EXIT_MARKING = "23000000-0000-0000-0000-000000000002"
    OTHER_MARKING = "23000000-0000-0000-0000-000000000003"
    FOREIGN_MARKING = "33000000-0000-0000-0000-000000000001"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Homologacao limpa 001-018.
        _reset_database()
        _apply_migrations(1, 18)
        connection = _connect(dict_rows=True)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT conname, contype FROM pg_constraint
                       WHERE conrelid = 'correcoes'::regclass"""
                )
                cls.clean_constraints = {row["conname"]: row["contype"] for row in cursor}
                cursor.execute(
                    """SELECT indexname FROM pg_indexes
                       WHERE schemaname = 'public' AND tablename = 'correcoes'"""
                )
                cls.clean_indexes = {row["indexname"] for row in cursor}
        finally:
            connection.close()

        # Upgrade representativo 001-017 -> 018 com estados legados.
        _reset_database()
        _apply_migrations(1, 17)
        _insert_legacy_rows()
        _apply_migrations(18, 18)
        connection = _connect(dict_rows=True)
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT estado, count(*) AS total FROM correcoes GROUP BY estado")
                cls.legacy_states = {row["estado"]: row["total"] for row in cursor}
        finally:
            connection.close()

        # Base final limpa usada pelos cenarios de integracao. A suíte continua
        # homologando a 018 isoladamente acima, mas roda contra o schema atual
        # para também detectar regressões introduzidas por migrations posteriores.
        _reset_database()
        _apply_migrations(1, 22)
        cls.app = Flask("phase25-integration")
        cls.app.config.update(TESTING=True, SECRET_KEY="phase25-test-only")
        cls.app.register_blueprint(occurrences_bp)
        cls.app.register_blueprint(timekeeping_bp)

    def setUp(self):
        connection = _connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("TRUNCATE empresas, usuarios CASCADE")
                self._seed(cursor)
            connection.commit()
        finally:
            connection.close()

    def _seed(self, cursor):
        cursor.executemany(
            "INSERT INTO empresas (id, nome) VALUES (%s, %s)",
            ((self.COMPANY, "Tenant A"), (self.FOREIGN_COMPANY, "Tenant B")),
        )
        cursor.executemany(
            "INSERT INTO unidades (id, empresa_id, nome) VALUES (%s, %s, %s)",
            (
                (self.UNIT, self.COMPANY, "Unit A"),
                (self.FOREIGN_UNIT, self.FOREIGN_COMPANY, "Unit B"),
            ),
        )
        cursor.executemany(
            """INSERT INTO equipes (id, empresa_id, unidade_id, nome)
               VALUES (%s, %s, %s, %s)""",
            (
                (self.TEAM, self.COMPANY, self.UNIT, "Scoped Team"),
                (self.OTHER_TEAM, self.COMPANY, self.UNIT, "Other Team"),
                (
                    self.FOREIGN_TEAM,
                    self.FOREIGN_COMPANY,
                    self.FOREIGN_UNIT,
                    "Foreign Team",
                ),
            ),
        )
        users = (
            (self.EMPLOYEE_USER, "Employee", "91000000001"),
            (self.OTHER_USER, "Out of Scope", "91000000002"),
            (self.MANAGER_USER, "Manager", "91000000003"),
            (self.HR_USER, "HR", "91000000004"),
            (self.ADMIN_USER, "Admin", "91000000005"),
            (self.FOREIGN_USER, "Foreign Employee", "91000000006"),
            (self.FOREIGN_HR_USER, "Foreign HR", "91000000007"),
            (self.FOREIGN_ADMIN_USER, "Foreign Admin", "91000000008"),
        )
        cursor.executemany(
            """INSERT INTO usuarios (id, nome, cpf, senha_hash)
               VALUES (%s, %s, %s, 'fixture-hash')""",
            users,
        )
        employees = (
            (self.EMPLOYEE, self.EMPLOYEE_USER, self.COMPANY, self.UNIT, self.TEAM, "E1", "funcionario"),
            (self.OTHER_EMPLOYEE, self.OTHER_USER, self.COMPANY, self.UNIT, self.OTHER_TEAM, "E2", "funcionario"),
            (self.MANAGER, self.MANAGER_USER, self.COMPANY, self.UNIT, self.TEAM, "M1", "gestor"),
            (self.HR, self.HR_USER, self.COMPANY, self.UNIT, self.TEAM, "H1", "rh"),
            (self.ADMIN, self.ADMIN_USER, self.COMPANY, self.UNIT, self.TEAM, "A1", "administrador"),
            (self.FOREIGN_EMPLOYEE, self.FOREIGN_USER, self.FOREIGN_COMPANY, self.FOREIGN_UNIT, self.FOREIGN_TEAM, "FE1", "funcionario"),
            (self.FOREIGN_HR, self.FOREIGN_HR_USER, self.FOREIGN_COMPANY, self.FOREIGN_UNIT, self.FOREIGN_TEAM, "FH1", "rh"),
            (self.FOREIGN_ADMIN, self.FOREIGN_ADMIN_USER, self.FOREIGN_COMPANY, self.FOREIGN_UNIT, self.FOREIGN_TEAM, "FA1", "administrador"),
        )
        cursor.executemany(
            """INSERT INTO funcionarios
               (id, usuario_id, empresa_id, unidade_id, equipe_id, matricula, perfil)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            employees,
        )
        cursor.execute(
            """INSERT INTO gestores_escopos
               (empresa_id, gestor_funcionario_id, unidade_id, equipe_id)
               VALUES (%s, %s, %s, %s)""",
            (self.COMPANY, self.MANAGER, self.UNIT, self.TEAM),
        )
        markings = (
            (self.MARKING, self.COMPANY, self.EMPLOYEE, datetime(2026, 9, 12, 11, 0, tzinfo=timezone.utc), "entrada"),
            (self.EXIT_MARKING, self.COMPANY, self.EMPLOYEE, datetime(2026, 9, 12, 20, 0, tzinfo=timezone.utc), "saida"),
            (self.OTHER_MARKING, self.COMPANY, self.OTHER_EMPLOYEE, datetime(2026, 9, 12, 11, 0, tzinfo=timezone.utc), "entrada"),
            (self.FOREIGN_MARKING, self.FOREIGN_COMPANY, self.FOREIGN_EMPLOYEE, datetime(2026, 9, 12, 11, 0, tzinfo=timezone.utc), "entrada"),
        )
        cursor.executemany(
            """INSERT INTO marcacoes
               (id, empresa_id, funcionario_id, instante, tipo, origem, estado)
               VALUES (%s, %s, %s, %s, %s, 'manual', 'confirmada')""",
            markings,
        )

    def _auth(self, role):
        mapping = {
            "funcionario": (self.EMPLOYEE_USER, self.EMPLOYEE, self.COMPANY),
            "outro_funcionario": (self.OTHER_USER, self.OTHER_EMPLOYEE, self.COMPANY),
            "gestor": (self.MANAGER_USER, self.MANAGER, self.COMPANY),
            "rh": (self.HR_USER, self.HR, self.COMPANY),
            "administrador": (self.ADMIN_USER, self.ADMIN, self.COMPANY),
            "funcionario_externo": (self.FOREIGN_USER, self.FOREIGN_EMPLOYEE, self.FOREIGN_COMPANY),
            "rh_externo": (self.FOREIGN_HR_USER, self.FOREIGN_HR, self.FOREIGN_COMPANY),
            "administrador_externo": (self.FOREIGN_ADMIN_USER, self.FOREIGN_ADMIN, self.FOREIGN_COMPANY),
        }
        user, employee, company = mapping[role]
        actual_role = role.replace("_externo", "").replace("outro_", "")
        return {
            "user_id": user,
            "funcionario_id": employee,
            "empresa_id": company,
            "perfil": actual_role,
            "session_id": "24000000-0000-0000-0000-000000000001",
            "familia_id": "24000000-0000-0000-0000-000000000002",
        }

    @contextmanager
    def _database_patches(self, auth):
        with patch(
            "utils.auth_decorator._load_persistent_authentication",
            return_value=(auth, None),
        ), patch("routes.occurrences.conectar_bd", side_effect=_connect), patch(
            "routes.timekeeping.conectar_bd", side_effect=_connect
        ), patch("services.facial_failure_workflow.conectar_bd", side_effect=_connect):
            yield

    def _request(self, auth, method, path, **kwargs):
        with self._database_patches(auth):
            with self.app.test_client() as client:
                return client.open(path, method=method, headers=AUTH_HEADER, **kwargs)

    def _create(self, auth=None, category="horario_incorreto", **overrides):
        payload = {
            "tipo": category,
            "marcacao_id": self.MARKING,
            "motivo": "Fixture de homologacao",
            "instante_solicitado": "2026-09-12T08:15:00-03:00",
        }
        if category == "tipo_incorreto":
            payload.pop("instante_solicitado")
            payload["tipo_marcacao_solicitado"] = "retorno_intervalo"
        elif category == "esquecimento_marcacao":
            payload.pop("marcacao_id")
            payload["tipo_marcacao_solicitado"] = "saida_intervalo"
        elif category == "justificativa":
            payload.pop("instante_solicitado")
        payload.update(overrides)
        response = self._request(
            auth or self._auth("funcionario"), "POST", "/api/ocorrencias", json=payload
        )
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        return response.get_json()["id"]

    def _decide(self, correction_id, action, auth=None, observation=None):
        body = {} if observation is None else {"observacao": observation}
        return self._request(
            auth or self._auth("gestor"),
            "POST",
            f"/api/gestao/ocorrencias/{correction_id}/{action}",
            json=body,
        )

    def _forward(self, correction_id, auth=None):
        response = self._decide(
            correction_id, "encaminhar-rh", auth, "Revisao formal do RH"
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response

    def _state(self, correction_id):
        connection = _connect(dict_rows=True)
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM correcoes WHERE id = %s", (correction_id,))
                return cursor.fetchone()
        finally:
            connection.close()

    def _effective(self):
        connection = _connect(dict_rows=True)
        try:
            with connection.cursor() as cursor:
                return fetch_effective_events(cursor, self.COMPANY, self.EMPLOYEE)
        finally:
            connection.close()

    def _concurrent_decisions(self, actions):
        correction_id = self._create()
        barrier = threading.Barrier(len(actions))

        def factory():
            connection = _connect()
            barrier.wait(timeout=10)
            return connection

        def decide(action):
            target = {"aprovar": "aprovada", "rejeitar": "rejeitada"}[action]
            try:
                transition_correction(
                    factory,
                    self._auth("gestor"),
                    correction_id,
                    target,
                    "Concorrencia" if target == "rejeitada" else None,
                )
                return "ok"
            except CorrectionWorkflowError as exc:
                return exc.status

        with ThreadPoolExecutor(max_workers=len(actions)) as executor:
            results = list(executor.map(decide, actions))
        return correction_id, results

    def test_00_migrations_clean_upgrade_constraints_indexes_and_foreign_keys(self):
        self.assertIn("correcoes_estado_check", self.clean_constraints)
        self.assertIn("correcoes_decisao_estado_check", self.clean_constraints)
        self.assertIn("correcoes_empresa_funcionario_fk", self.clean_constraints)
        self.assertIn("correcoes_empresa_funcionario_marcacao_fk", self.clean_constraints)
        self.assertIn("correcoes_empresa_estado_data_idx", self.clean_indexes)
        self.assertIn("correcoes_aprovadas_marcacao_operacao_unique", self.clean_indexes)
        self.assertEqual(
            self.legacy_states, {"pendente_gestor": 2, "encaminhada_rh": 2}
        )

    def test_01_request_starts_pending_manager(self):
        correction_id = self._create()
        self.assertEqual(self._state(correction_id)["estado"], "pendente_gestor")

    def test_02_scoped_manager_approves(self):
        correction_id = self._create()
        response = self._decide(correction_id, "aprovar", observation="Conferido")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._state(correction_id)["estado"], "aprovada")

    def test_03_scoped_manager_rejects_with_justification(self):
        correction_id = self._create()
        response = self._decide(correction_id, "rejeitar", observation="Documento divergente")
        self.assertEqual(response.status_code, 200)
        row = self._state(correction_id)
        self.assertEqual((row["estado"], row["decisao"]), ("rejeitada", "Documento divergente"))

    def test_04_manager_forwards_to_hr_with_observation(self):
        correction_id = self._create()
        response = self._forward(correction_id)
        self.assertEqual(response.get_json()["status"], "encaminhada_rh")

    def test_05_hr_approves_only_forwarded(self):
        pending = self._create()
        self.assertEqual(self._decide(pending, "aprovar", self._auth("rh")).status_code, 409)
        self._forward(pending)
        self.assertEqual(self._decide(pending, "aprovar", self._auth("rh")).status_code, 200)

    def test_06_hr_rejects_only_forwarded(self):
        pending = self._create()
        direct = self._decide(pending, "rejeitar", self._auth("rh"), "Direta")
        self.assertEqual(direct.status_code, 409)
        self._forward(pending)
        accepted = self._decide(pending, "rejeitar", self._auth("rh"), "Revisado")
        self.assertEqual(accepted.status_code, 200)

    def test_07_admin_follows_forwarded_policy_in_own_company(self):
        correction_id = self._create()
        self.assertEqual(
            self._decide(correction_id, "aprovar", self._auth("administrador")).status_code,
            409,
        )
        self._forward(correction_id)
        self.assertEqual(
            self._decide(correction_id, "aprovar", self._auth("administrador")).status_code,
            200,
        )

    def test_08_final_state_never_transitions(self):
        correction_id = self._create()
        self.assertEqual(self._decide(correction_id, "aprovar").status_code, 200)
        self.assertEqual(
            self._decide(correction_id, "rejeitar", observation="Tardia").status_code,
            409,
        )

    def test_09_invalid_transition_is_coherent(self):
        with self.assertRaises(CorrectionWorkflowError) as raised:
            transition_correction(
                _connect, self._auth("gestor"), str(UUID(int=99)), "reaberta"
            )
        self.assertEqual(raised.exception.status, 400)

    def test_10_out_of_scope_manager_gets_non_enumerable_404(self):
        correction_id = self._create(
            self._auth("outro_funcionario"),
            marcacao_id=self.OTHER_MARKING,
        )
        detail = self._request(
            self._auth("gestor"),
            "GET",
            f"/api/gestao/ocorrencias/{correction_id}",
        )
        decision = self._decide(correction_id, "aprovar")
        self.assertEqual((detail.status_code, decision.status_code), (404, 404))
        self.assertEqual(detail.get_json(), decision.get_json())

    def test_11_foreign_hr_and_admin_cannot_read_or_change(self):
        correction_id = self._create()
        self._forward(correction_id)
        for role in ("rh_externo", "administrador_externo"):
            auth = self._auth(role)
            with self.subTest(role=role):
                detail = self._request(auth, "GET", f"/api/gestao/ocorrencias/{correction_id}")
                decision = self._decide(correction_id, "aprovar", auth)
                self.assertEqual((detail.status_code, decision.status_code), (404, 404))

    def test_12_employee_cannot_decide(self):
        correction_id = self._create()
        response = self._decide(correction_id, "aprovar", self._auth("funcionario"))
        self.assertEqual(response.status_code, 403)

    def test_13_employee_reads_only_own_request(self):
        own = self._create()
        other = self._create(
            self._auth("outro_funcionario"),
            marcacao_id=self.OTHER_MARKING,
        )
        auth = self._auth("funcionario")
        own_response = self._request(auth, "GET", f"/api/ocorrencias/{own}")
        other_response = self._request(auth, "GET", f"/api/ocorrencias/{other}")
        self.assertEqual((own_response.status_code, other_response.status_code), (200, 404))

    def test_14_employee_cancels_only_pending(self):
        pending = self._create()
        cancelled = self._request(
            self._auth("funcionario"), "POST", f"/api/ocorrencias/{pending}/cancelar"
        )
        self.assertEqual(cancelled.status_code, 200)
        forwarded = self._create()
        self._forward(forwarded)
        conflict = self._request(
            self._auth("funcionario"), "POST", f"/api/ocorrencias/{forwarded}/cancelar"
        )
        self.assertEqual(conflict.status_code, 409)

    def test_15_original_marking_is_byte_for_byte_unchanged(self):
        connection = _connect(dict_rows=True)
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT row_to_json(m)::text AS snapshot FROM marcacoes m WHERE id=%s", (self.MARKING,))
                before = cursor.fetchone()["snapshot"]
        finally:
            connection.close()
        correction_id = self._create()
        self.assertEqual(self._decide(correction_id, "aprovar").status_code, 200)
        connection = _connect(dict_rows=True)
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT row_to_json(m)::text AS snapshot FROM marcacoes m WHERE id=%s", (self.MARKING,))
                after = cursor.fetchone()["snapshot"]
        finally:
            connection.close()
        self.assertEqual(after, before)

    def test_16_effective_view_reflects_approved_time(self):
        correction_id = self._create()
        self._decide(correction_id, "aprovar")
        event = next(row for row in self._effective() if str(row["marcacao_original_id"]) == self.MARKING)
        self.assertEqual(event["instante"], datetime(2026, 9, 12, 11, 15, tzinfo=timezone.utc))
        self.assertTrue(event["ajustada"])

    def test_17_effective_view_reflects_approved_type(self):
        correction_id = self._create(category="tipo_incorreto")
        self._decide(correction_id, "aprovar")
        event = next(row for row in self._effective() if str(row["marcacao_original_id"]) == self.MARKING)
        self.assertEqual(event["tipo"], "retorno_intervalo")

    def test_18_effective_view_reflects_approved_inclusion(self):
        correction_id = self._create(category="esquecimento_marcacao")
        self._decide(correction_id, "aprovar")
        included = [row for row in self._effective() if row["marcacao_original_id"] is None]
        self.assertEqual(len(included), 1)
        self.assertEqual(included[0]["origem"], "ajuste_administrativo")

    def test_19_exports_use_same_effective_view(self):
        correction_id = self._create()
        self._decide(correction_id, "aprovar")
        query = {
            "funcionario_id": self.EMPLOYEE,
            "inicio": "2026-09-12",
            "fim": "2026-09-12",
        }
        auth = self._auth("gestor")
        listing = self._request(auth, "GET", "/api/gestao/pontos", query_string=query)
        csv_response = self._request(
            auth, "GET", "/exportar-pontos", query_string={**query, "formato": "csv"}
        )
        docx_response = self._request(
            auth, "GET", "/exportar-pontos", query_string={**query, "formato": "docx"}
        )
        self.assertEqual((listing.status_code, csv_response.status_code, docx_response.status_code), (200, 200, 200))
        self.assertEqual(listing.get_json()[0]["entrada"], "08:15")
        self.assertIn("08:15", csv_response.get_data(as_text=True))
        text = " ".join(
            cell.text
            for table in Document(io.BytesIO(docx_response.data)).tables
            for row in table.rows
            for cell in row.cells
        )
        self.assertIn("08:15", text)

    def test_20_rejected_and_cancelled_do_not_change_effective_view(self):
        baseline = [(row["instante"], row["tipo"]) for row in self._effective()]
        rejected = self._create()
        self._decide(rejected, "rejeitar", observation="Nao procede")
        cancelled = self._create(category="tipo_incorreto")
        self._request(
            self._auth("funcionario"), "POST", f"/api/ocorrencias/{cancelled}/cancelar"
        )
        current = [(row["instante"], row["tipo"]) for row in self._effective()]
        self.assertEqual(current, baseline)

    def test_21_each_transition_generates_exactly_one_audit_event(self):
        correction_id = self._create()
        self._forward(correction_id)
        self._decide(correction_id, "aprovar", self._auth("rh"))
        connection = _connect(dict_rows=True)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT acao, count(*) AS total FROM auditoria
                       WHERE entidade_id=%s GROUP BY acao ORDER BY acao""",
                    (correction_id,),
                )
                counts = {row["acao"]: row["total"] for row in cursor}
        finally:
            connection.close()
        self.assertEqual(
            counts,
            {
                "correcao.aprovada": 1,
                "correcao.criada": 1,
                "correcao.encaminhada_rh": 1,
            },
        )

    def test_22_audit_records_actor_role_tenant_employee_states_and_reason(self):
        correction_id = self._create()
        self._decide(correction_id, "rejeitar", observation="Evidencia insuficiente")
        connection = _connect(dict_rows=True)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT * FROM auditoria
                       WHERE entidade_id=%s AND acao='correcao.rejeitada'""",
                    (correction_id,),
                )
                event = cursor.fetchone()
        finally:
            connection.close()
        metadata = event["metadados"]
        self.assertEqual(str(event["ator_usuario_id"]), self.MANAGER_USER)
        self.assertEqual(str(event["empresa_id"]), self.COMPANY)
        self.assertEqual(metadata["papel"], "gestor")
        self.assertEqual(metadata["funcionario_id"], self.EMPLOYEE)
        self.assertEqual(metadata["estado_anterior"], "pendente_gestor")
        self.assertEqual(metadata["estado_novo"], "rejeitada")
        self.assertEqual(metadata["justificativa"], "Evidencia insuficiente")

    def test_23_official_timestamps_are_generated_by_postgresql(self):
        correction_id = self._create()
        self._decide(correction_id, "aprovar")
        connection = _connect(dict_rows=True)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT c.decided_at, a.ocorrido_at, clock_timestamp() AS database_now
                       FROM correcoes c JOIN auditoria a ON a.entidade_id=c.id
                       WHERE c.id=%s AND a.acao='correcao.aprovada'""",
                    (correction_id,),
                )
                row = cursor.fetchone()
        finally:
            connection.close()
        self.assertIsNotNone(row["decided_at"])
        self.assertIsNotNone(row["ocorrido_at"])
        self.assertLessEqual(row["decided_at"], row["database_now"])
        self.assertLessEqual(row["ocorrido_at"], row["database_now"])

    def test_24_internal_notification_is_created_when_applicable(self):
        correction_id = self._create()
        self._forward(correction_id)
        self._decide(correction_id, "aprovar", self._auth("rh"))
        connection = _connect(dict_rows=True)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT count(*) AS total FROM notificacoes
                       WHERE empresa_id=%s AND usuario_id=%s AND tipo='correcao'""",
                    (self.COMPANY, self.EMPLOYEE_USER),
                )
                total = cursor.fetchone()["total"]
        finally:
            connection.close()
        self.assertEqual(total, 2)

    def test_25_two_simultaneous_decisions_have_one_winner(self):
        correction_id, results = self._concurrent_decisions(("aprovar", "rejeitar"))
        self.assertCountEqual(results, ["ok", 409])
        self.assertIn(self._state(correction_id)["estado"], {"aprovada", "rejeitada"})

    def test_26_concurrent_approval_and_rejection_do_not_overwrite(self):
        correction_id, results = self._concurrent_decisions(("aprovar", "rejeitar"))
        self.assertCountEqual(results, ["ok", 409])
        connection = _connect(dict_rows=True)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT count(*) AS total FROM auditoria
                       WHERE entidade_id=%s AND acao IN ('correcao.aprovada','correcao.rejeitada')""",
                    (correction_id,),
                )
                total = cursor.fetchone()["total"]
        finally:
            connection.close()
        self.assertEqual(total, 1)

    def test_27_two_concurrent_approvals_do_not_duplicate_application(self):
        correction_id, results = self._concurrent_decisions(("aprovar", "aprovar"))
        self.assertCountEqual(results, ["ok", 409])
        events = [row for row in self._effective() if str(row["correcao_id"]) == correction_id]
        self.assertEqual(len(events), 1)

    def test_28_http_conflict_is_409(self):
        correction_id = self._create()
        self.assertEqual(self._decide(correction_id, "aprovar").status_code, 200)
        conflict = self._decide(correction_id, "aprovar")
        self.assertEqual(conflict.status_code, 409)

    def test_29_manual_calls_cannot_override_server_authority(self):
        response = self._request(
            self._auth("funcionario"),
            "POST",
            "/api/ocorrencias",
            json={
                "tipo": "justificativa",
                "motivo": "Tentativa",
                "empresa_id": self.FOREIGN_COMPANY,
                "estado": "aprovada",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._state(str(UUID(int=0))), None)

    def test_30_facial_failure_workflow_remains_independent(self):
        occurrence_id = "25000000-0000-0000-0000-000000000001"
        connection = _connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO ocorrencias
                       (id, empresa_id, funcionario_id, tipo, descricao, estado,
                        primeira_ocorrencia_at, ciclo_falha_facial_id)
                       VALUES (%s, %s, %s, 'falha_facial', 'Fixture automatica',
                               'aberta', clock_timestamp(), %s)""",
                    (occurrence_id, self.COMPANY, self.EMPLOYEE, str(UUID(int=501))),
                )
            connection.commit()
        finally:
            connection.close()
        started = self._request(
            self._auth("gestor"),
            "POST",
            f"/api/gestao/ocorrencias/falhas-faciais/{occurrence_id}/iniciar-analise",
            json={},
        )
        resolved = self._request(
            self._auth("gestor"),
            "POST",
            f"/api/gestao/ocorrencias/falhas-faciais/{occurrence_id}/resolver",
            json={"justificativa": "Tratada sem correcao de ponto"},
        )
        self.assertEqual((started.status_code, resolved.status_code), (200, 200))
        self.assertEqual(resolved.get_json()["estado"], "resolvida")
        connection = _connect(dict_rows=True)
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT count(*) AS total FROM correcoes")
                total = cursor.fetchone()["total"]
        finally:
            connection.close()
        self.assertEqual(total, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
