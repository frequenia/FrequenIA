"""Fase 34: espelho somente leitura em PostgreSQL/pgvector descartável."""

from datetime import date, datetime, timezone
import os
import unittest
from unittest.mock import patch
from urllib.parse import urlparse
from uuid import uuid4

import psycopg2
import psycopg2.extras
from flask import Flask

import test_phase25_postgres_integration as phase25
import test_phase30_postgres_integration as phase30
from routes.timekeeping import _load_mirror, timekeeping_bp
from services.timekeeping_reports import load_employee_report, summarize_mirror


URL = os.environ.get("PHASE34_TEST_DATABASE_URL", "").strip()


def _safe_url():
    if not URL:
        return False
    parsed = urlparse(URL)
    allowed = {"localhost", "127.0.0.1", "::1"}
    disposable = os.environ.get("FREQUENIA_DISPOSABLE_TEST_HOST", "").strip()
    if disposable:
        allowed.add(disposable)
    if (
        parsed.scheme not in {"postgres", "postgresql"}
        or parsed.hostname not in allowed
        or parsed.path != "/frequenia_phase25_test"
    ):
        raise RuntimeError(
            "PHASE34_TEST_DATABASE_URL deve usar frequenia_phase25_test local descartável."
        )
    return True


ENABLED = _safe_url()
if ENABLED:
    phase25.TEST_DATABASE_URL = URL
    phase25.POSTGRES_ENABLED = True
    phase30.URL = URL
    phase30.ENABLED = True


def connect():
    return psycopg2.connect(
        URL,
        connect_timeout=5,
        sslmode="require",
        options="-c search_path=public,extensions",
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


@unittest.skipUnless(ENABLED, "requer PHASE34_TEST_DATABASE_URL explícita")
class Phase34PostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        phase25._reset_database()
        phase25._apply_migrations(1, 26)

    def setUp(self):
        self.ids = {
            name: str(uuid4())
            for name in (
                "company",
                "foreign_company",
                "unit",
                "foreign_unit",
                "team",
                "foreign_team",
                "user",
                "employee",
                "second_user",
                "second_employee",
                "foreign_user",
                "foreign_employee",
                "turn",
                "other_turn",
                "assignment",
            )
        }
        helper = phase30.Phase30PostgresIntegrationTests()
        helper.ids = self.ids
        connection = connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("TRUNCATE empresas,usuarios CASCADE")
                helper._seed(cursor)
            connection.commit()
        finally:
            connection.close()

    def _seed_night_snapshot(self, cursor):
        operational_date = date(2026, 10, 20)
        cursor.execute(
            """INSERT INTO jornadas_diarias
               (empresa_id,funcionario_id,data_operacional,timezone,origem,
                turno_id,atribuicao_turno_id)
               VALUES(%s,%s,%s,'America/Sao_Paulo','turno',%s,%s)
               RETURNING id""",
            (
                self.ids["company"],
                self.ids["employee"],
                operational_date,
                self.ids["turn"],
                self.ids["assignment"],
            ),
        )
        journey_id = cursor.fetchone()["id"]
        expected = (
            datetime(2026, 10, 21, 1, tzinfo=timezone.utc),
            datetime(2026, 10, 21, 9, tzinfo=timezone.utc),
        )
        event_ids = []
        for order, event_type, instant in (
            (1, "entrada", expected[0]),
            (2, "saida", expected[1]),
        ):
            cursor.execute(
                """INSERT INTO jornada_eventos_esperados
                   (empresa_id,jornada_id,ordem,tipo,instante_esperado)
                   VALUES(%s,%s,%s,%s,%s) RETURNING id""",
                (self.ids["company"], journey_id, order, event_type, instant),
            )
            event_ids.append(cursor.fetchone()["id"])
        marking_ids = []
        for event_id, event_type, instant in zip(
            event_ids, ("entrada", "saida"), expected
        ):
            cursor.execute(
                """INSERT INTO marcacoes
                   (empresa_id,funcionario_id,instante,tipo,origem,estado,
                    jornada_evento_id)
                   VALUES(%s,%s,%s,%s,'manual','confirmada',%s) RETURNING id""",
                (
                    self.ids["company"],
                    self.ids["employee"],
                    instant,
                    event_type,
                    event_id,
                ),
            )
            marking_id = cursor.fetchone()["id"]
            marking_ids.append(marking_id)
            cursor.execute(
                """UPDATE jornada_eventos_esperados
                   SET marcacao_id=%s,cumprido_at=%s WHERE id=%s""",
                (marking_id, instant, event_id),
            )
        return operational_date, marking_ids

    def test_night_mirror_uses_effective_view_and_does_not_write(self):
        connection = connect()
        try:
            with connection.cursor() as cursor:
                operational_date, markings = self._seed_night_snapshot(cursor)
                cursor.execute(
                    """INSERT INTO correcoes
                       (empresa_id,funcionario_id,marcacao_original_id,
                        solicitante_usuario_id,responsavel_decisao_usuario_id,
                        tipo,categoria,instante_proposto,motivo,estado,decided_at)
                       VALUES(%s,%s,%s,%s,%s,'alteracao_instante',
                        'horario_incorreto',%s,'Sintético','aprovada',clock_timestamp())""",
                    (
                        self.ids["company"],
                        self.ids["employee"],
                        markings[1],
                        self.ids["user"],
                        self.ids["user"],
                        datetime(2026, 10, 21, 9, 5, tzinfo=timezone.utc),
                    ),
                )
                cursor.execute(
                    """INSERT INTO correcoes
                       (empresa_id,funcionario_id,solicitante_usuario_id,
                        responsavel_decisao_usuario_id,tipo,categoria,
                        instante_proposto,tipo_marcacao_proposto,motivo,estado,
                        decisao,decided_at)
                       VALUES(%s,%s,%s,%s,'inclusao','esquecimento_marcacao',
                        %s,'saida_intervalo','Sintético','rejeitada','Negada',
                        clock_timestamp())""",
                    (
                        self.ids["company"],
                        self.ids["employee"],
                        self.ids["user"],
                        self.ids["user"],
                        datetime(2026, 10, 21, 4, tzinfo=timezone.utc),
                    ),
                )
            connection.commit()

            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT count(*) AS markings,
                              (SELECT count(*) FROM correcoes) AS corrections,
                              (SELECT count(*) FROM jornadas_diarias) AS snapshots,
                              md5(string_agg(row_to_json(m)::text,'' ORDER BY m.id)) AS digest
                       FROM marcacoes m"""
                )
                before = cursor.fetchone()
                mirror = load_employee_report(
                    cursor,
                    self.ids["company"],
                    self.ids["employee"],
                    operational_date,
                    operational_date,
                )
                cursor.execute(
                    """SELECT count(*) AS markings,
                              (SELECT count(*) FROM correcoes) AS corrections,
                              (SELECT count(*) FROM jornadas_diarias) AS snapshots,
                              md5(string_agg(row_to_json(m)::text,'' ORDER BY m.id)) AS digest
                       FROM marcacoes m"""
                )
                after = cursor.fetchone()

            self.assertEqual(before, after)
            self.assertEqual(len(mirror), 1)
            self.assertEqual(mirror[0]["data_operacional"], "2026-10-20")
            self.assertEqual(mirror[0]["eventos"][1]["efetiva"]["horario"], "06:05")
            self.assertEqual(
                mirror[0]["eventos"][1]["efetiva"]["origem"],
                "correcao_aprovada",
            )
            self.assertEqual(
                {item["estado"] for item in mirror[0]["solicitacoes"]},
                {"aprovada", "rejeitada"},
            )
            self.assertEqual(summarize_mirror(mirror)["eventos_apos_horario"], 1)
        finally:
            connection.close()

    def test_loader_enforces_tenant_scope_and_read_only_transaction(self):
        seed = connect()
        try:
            with seed.cursor() as cursor:
                operational_date, _ = self._seed_night_snapshot(cursor)
            seed.commit()
        finally:
            seed.close()

        auth_context = {
            "empresa_id": self.ids["company"],
            "perfil": "rh",
            "funcionario_id": self.ids["employee"],
        }
        with patch("routes.timekeeping.conectar_bd", side_effect=connect):
            employee, mirror = _load_mirror(
                auth_context,
                self.ids["employee"],
                operational_date,
                operational_date,
            )
            foreign, foreign_mirror = _load_mirror(
                auth_context,
                self.ids["foreign_employee"],
                operational_date,
                operational_date,
            )
        self.assertEqual(str(employee["funcionario_id"]), self.ids["employee"])
        self.assertEqual(len(mirror), 1)
        self.assertIsNone(foreign)
        self.assertEqual(foreign_mirror, [])

    def test_consolidated_route_executes_real_scoped_queries(self):
        seed = connect()
        try:
            with seed.cursor() as cursor:
                operational_date, _ = self._seed_night_snapshot(cursor)
            seed.commit()
        finally:
            seed.close()

        app = Flask(__name__)
        app.config.update(TESTING=True, SECRET_KEY="phase34")
        app.register_blueprint(timekeeping_bp)
        auth_context = {
            "user_id": self.ids["user"],
            "funcionario_id": self.ids["employee"],
            "session_id": str(uuid4()),
            "familia_id": str(uuid4()),
            "empresa_id": self.ids["company"],
            "perfil": "rh",
        }
        path = (
            "/api/gestao/relatorios/consolidado"
            f"?inicio={operational_date.isoformat()}&fim={operational_date.isoformat()}"
            "&pagina=1&limite=25"
        )
        with patch(
            "utils.auth_decorator._load_persistent_authentication",
            return_value=(auth_context, None),
        ), patch("routes.timekeeping.conectar_bd", side_effect=connect):
            response = app.test_client().get(path)
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.json["regra"]["efeito_trabalhista"], "nao_calculado")
        identifiers = {item["funcionario"]["id"] for item in response.json["itens"]}
        self.assertIn(self.ids["employee"], identifiers)


if __name__ == "__main__":
    unittest.main(verbosity=2)
