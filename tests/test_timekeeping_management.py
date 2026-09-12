import io
import os
from datetime import date, datetime, timezone
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from flask import Flask

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("FLASK_SECRET_KEY", "timekeeping-test-flask-key")
os.environ.setdefault("JWT_SECRET_KEY", "timekeeping-test-jwt-key")

from routes.timekeeping import (
    _daily_total,
    _export_csv,
    _export_docx,
    _export_pdf,
    _fetch_employee_records,
    _serialize_daily_records,
    _utc_bounds,
    timekeeping_bp,
)
from routes.views import views_bp

COMPANY_ID = "00000000-0000-0000-0000-000000000001"
EMPLOYEE_ID = "00000000-0000-0000-0000-000000000002"
FOREIGN_EMPLOYEE_ID = "00000000-0000-0000-0000-000000000003"


def auth_context(role):
    return {
        "user_id": "00000000-0000-0000-0000-000000000010",
        "funcionario_id": "00000000-0000-0000-0000-000000000011",
        "session_id": "00000000-0000-0000-0000-000000000012",
        "familia_id": "00000000-0000-0000-0000-000000000013",
        "empresa_id": COMPANY_ID,
        "perfil": role,
    }


def row(identifier, event_type, instant):
    return {"id": identifier, "tipo": event_type, "instante": instant}


class RecordingCursor:
    def __init__(self, employee, rows):
        self.employee = employee
        self.rows = rows
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def fetchone(self):
        return self.employee

    def fetchall(self):
        return self.rows


class TimekeepingPureTests(unittest.TestCase):
    def test_groups_semantic_types_in_sao_paulo_and_calculates_total(self):
        records = _serialize_daily_records(
            [
                row("1", "entrada", datetime(2026, 9, 12, 11, 0, tzinfo=timezone.utc)),
                row(
                    "2",
                    "saida_intervalo",
                    datetime(2026, 9, 12, 15, 0, tzinfo=timezone.utc),
                ),
                row(
                    "3",
                    "retorno_intervalo",
                    datetime(2026, 9, 12, 16, 0, tzinfo=timezone.utc),
                ),
                row("4", "saida", datetime(2026, 9, 12, 20, 0, tzinfo=timezone.utc)),
            ]
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["data"], "2026-09-12")
        self.assertEqual(records[0]["entrada"], "08:00")
        self.assertEqual(records[0]["saida_intervalo"], "12:00")
        self.assertEqual(records[0]["retorno_intervalo"], "13:00")
        self.assertEqual(records[0]["saida"], "17:00")
        self.assertEqual(records[0]["total"], "8h00")

    def test_utc_near_midnight_belongs_to_previous_local_day(self):
        records = _serialize_daily_records(
            [row("1", "entrada", datetime(2026, 9, 13, 1, 30, tzinfo=timezone.utc))]
        )
        self.assertEqual(records[0]["data"], "2026-09-12")
        self.assertEqual(records[0]["entrada"], "22:30")

    def test_duplicate_type_keeps_first_confirmed_event_deterministically(self):
        records = _serialize_daily_records(
            [
                row(
                    "later",
                    "entrada",
                    datetime(2026, 9, 12, 12, 5, tzinfo=timezone.utc),
                ),
                row(
                    "first",
                    "entrada",
                    datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc),
                ),
            ]
        )
        self.assertEqual(records[0]["entrada"], "09:00")

    def test_missing_or_incomplete_events_do_not_invent_total(self):
        instant = datetime(2026, 9, 12, 8, 0, tzinfo=timezone.utc)
        self.assertEqual(_daily_total({"entrada": instant}), "--")
        self.assertEqual(
            _daily_total(
                {
                    "entrada": instant,
                    "saida_intervalo": instant.replace(hour=10),
                    "saida": instant.replace(hour=17),
                }
            ),
            "--",
        )

    def test_local_date_filters_become_correct_utc_bounds(self):
        start, end = _utc_bounds(date(2026, 9, 12), date(2026, 9, 12))
        self.assertEqual(start, datetime(2026, 9, 12, 3, 0, tzinfo=timezone.utc))
        self.assertEqual(end, datetime(2026, 9, 13, 3, 0, tzinfo=timezone.utc))

    def test_query_uses_marcacoes_confirmed_and_same_company(self):
        cursor = RecordingCursor(
            {"funcionario_id": EMPLOYEE_ID, "nome": "Fixture", "matricula": "F-1"},
            [],
        )
        employee, records = _fetch_employee_records(
            cursor, COMPANY_ID, EMPLOYEE_ID, date(2026, 9, 12), date(2026, 9, 12)
        )
        self.assertEqual(employee["funcionario_id"], EMPLOYEE_ID)
        self.assertEqual(records, [])
        sql, params = cursor.calls[1]
        normalized = " ".join(sql.lower().split())
        self.assertIn("from marcacoes", normalized)
        self.assertIn("estado = 'confirmada'", normalized)
        self.assertIn("instante >= %s", normalized)
        self.assertIn("instante < %s", normalized)
        self.assertNotIn("from ponto", normalized)
        self.assertEqual(params[0:2], (COMPANY_ID, EMPLOYEE_ID))

    def test_absent_employee_returns_no_records_without_querying_events(self):
        cursor = RecordingCursor(None, [])
        employee, records = _fetch_employee_records(
            cursor, COMPANY_ID, FOREIGN_EMPLOYEE_ID, None, None
        )
        self.assertIsNone(employee)
        self.assertEqual(records, [])
        self.assertEqual(len(cursor.calls), 1)

    def test_all_export_formats_use_serialized_records(self):
        records = [
            {
                "dia": "Sábado",
                "data": "2026-09-12",
                "entrada": "08:00",
                "saida_intervalo": "12:00",
                "retorno_intervalo": "13:00",
                "volta_intervalo": "13:00",
                "saida": "17:00",
                "total": "8h00",
            }
        ]
        self.assertIn("08:00", _export_csv(records).getvalue().decode("utf-8-sig"))
        self.assertTrue(_export_pdf(records).getvalue().startswith(b"%PDF"))
        self.assertTrue(_export_docx(records).getvalue().startswith(b"PK"))


class TimekeepingRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(
            __name__, template_folder=str(Path(__file__).parents[1] / "templates")
        )
        self.app.config.update(TESTING=True, SECRET_KEY="test")
        self.app.register_blueprint(timekeeping_bp)
        self.client = self.app.test_client()
        self.employee = {
            "funcionario_id": EMPLOYEE_ID,
            "nome": "Fixture",
            "matricula": "F-1",
        }
        self.records = [
            {
                "dia": "Sábado",
                "data": "2026-09-12",
                "entrada": "08:00",
                "saida_intervalo": "12:00",
                "retorno_intervalo": "13:00",
                "volta_intervalo": "13:00",
                "saida": "17:00",
                "total": "8h00",
            }
        ]

    def request_as(self, role, path):
        with patch(
            "utils.auth_decorator._load_persistent_authentication",
            return_value=(auth_context(role), None),
        ):
            return self.client.get(path)

    def test_management_roles_can_query_own_company(self):
        for role in ("administrador", "gestor", "rh"):
            with self.subTest(role=role), patch(
                "routes.timekeeping._load_management_records",
                return_value=(self.employee, self.records),
            ) as loader:
                response = self.request_as(
                    role, f"/api/gestao/pontos?funcionario_id={EMPLOYEE_ID}"
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(loader.call_args.args[0], COMPANY_ID)

    def test_employee_selector_is_scoped_to_authenticated_company(self):
        for role in ("administrador", "gestor", "rh"):
            connection = MagicMock()
            cursor = MagicMock()
            connection.cursor.return_value = cursor
            cursor.fetchall.return_value = [self.employee]
            with self.subTest(role=role), patch(
                "routes.timekeeping.conectar_bd", return_value=connection
            ):
                response = self.request_as(role, "/api/gestao/funcionarios")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()[0]["funcionario_id"], EMPLOYEE_ID)
            self.assertEqual(cursor.execute.call_args.args[1], (COMPANY_ID,))

    def test_regular_employee_is_forbidden(self):
        response = self.request_as(
            "funcionario", f"/api/gestao/pontos?funcionario_id={EMPLOYEE_ID}"
        )
        self.assertEqual(response.status_code, 403)

    def test_invalid_uuid_returns_400_without_database_call(self):
        with patch("routes.timekeeping._load_management_records") as loader:
            response = self.request_as(
                "administrador", "/api/gestao/pontos?funcionario_id=nao-e-uuid"
            )
        self.assertEqual(response.status_code, 400)
        loader.assert_not_called()

    def test_foreign_or_missing_employee_returns_404(self):
        with patch(
            "routes.timekeeping._load_management_records", return_value=(None, [])
        ):
            response = self.request_as(
                "administrador",
                f"/api/gestao/pontos?funcionario_id={FOREIGN_EMPLOYEE_ID}",
            )
        self.assertEqual(response.status_code, 404)

    def test_employee_without_marks_returns_empty_list(self):
        with patch(
            "routes.timekeeping._load_management_records",
            return_value=(self.employee, []),
        ):
            response = self.request_as(
                "rh", f"/api/gestao/pontos?funcionario_id={EMPLOYEE_ID}"
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), [])

    def test_browser_cannot_override_company(self):
        response = self.request_as(
            "administrador",
            f"/api/gestao/pontos?funcionario_id={EMPLOYEE_ID}&empresa_id=outra",
        )
        self.assertEqual(response.status_code, 400)

    def test_export_uses_the_same_employee_and_date_filters(self):
        with patch(
            "routes.timekeeping._load_management_records",
            return_value=(self.employee, self.records),
        ) as loader:
            response = self.request_as(
                "gestor",
                f"/exportar-pontos?formato=csv&funcionario_id={EMPLOYEE_ID}&inicio=2026-09-12&fim=2026-09-12",
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "text/csv")
        self.assertEqual(loader.call_args.args[0:2], (COMPANY_ID, EMPLOYEE_ID))
        self.assertEqual(
            loader.call_args.args[2:], (date(2026, 9, 12), date(2026, 9, 12))
        )


class TimekeepingPageAndScheduleTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).parents[1]
        self.app = Flask(
            __name__,
            template_folder=str(root / "templates"),
            static_folder=str(root / "static"),
        )
        self.app.config.update(TESTING=True, SECRET_KEY="test")
        self.app.register_blueprint(views_bp)
        self.client = self.app.test_client()

    def request_as(self, role, path):
        with patch(
            "utils.auth_decorator._load_persistent_authentication",
            return_value=(auth_context(role), None),
        ):
            return self.client.get(path)

    def test_management_page_rbac(self):
        for role in ("administrador", "gestor", "rh"):
            with self.subTest(role=role):
                self.assertEqual(
                    self.request_as(role, "/controleponto").status_code, 200
                )
        self.assertEqual(
            self.request_as("funcionario", "/controleponto").status_code, 403
        )

    def test_selected_employee_schedule_is_available_to_management_roles(self):
        connection = MagicMock()
        cursor = MagicMock()
        connection.cursor.return_value = cursor
        cursor.fetchone.return_value = {"exists": 1}
        schedule = {
            "turno": {"id": "turno", "nome": "Administrativo"},
            "vigencia": {"inicio": "2026-01-01", "fim": None},
            "periodos": [
                {
                    "dia_semana": 6,
                    "ordem": 1,
                    "inicio": "08:00",
                    "fim": "12:00",
                    "fim_dia_offset": 0,
                },
                {
                    "dia_semana": 6,
                    "ordem": 2,
                    "inicio": "13:00",
                    "fim": "17:00",
                    "fim_dia_offset": 0,
                },
            ],
        }
        for role in ("administrador", "gestor", "rh"):
            with self.subTest(role=role), patch(
                "routes.views.conectar_bd", return_value=connection
            ), patch("routes.views.buscar_jornada_data", return_value=schedule):
                response = self.request_as(
                    role,
                    f"/api/admin/funcionarios/{EMPLOYEE_ID}/jornada?data=2026-09-12",
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.get_json()["jornada"], schedule)

    def test_schedule_rejects_invalid_or_foreign_employee(self):
        invalid = self.request_as(
            "administrador", "/api/admin/funcionarios/invalido/jornada"
        )
        self.assertEqual(invalid.status_code, 400)

        connection = MagicMock()
        cursor = MagicMock()
        connection.cursor.return_value = cursor
        cursor.fetchone.return_value = None
        with patch("routes.views.conectar_bd", return_value=connection):
            foreign = self.request_as(
                "rh", f"/api/admin/funcionarios/{FOREIGN_EMPLOYEE_ID}/jornada"
            )
        self.assertEqual(foreign.status_code, 404)

    def test_frontend_updates_schedule_and_points_on_employee_change(self):
        root = Path(__file__).parents[1]
        javascript = (root / "static" / "js" / "controleponto.js").read_text(
            encoding="utf-8"
        )
        template = (root / "templates" / "controleponto.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("/api/gestao/pontos", javascript)
        self.assertIn("/api/admin/funcionarios/", javascript)
        self.assertIn(
            'addEventListener("change", atualizarFuncionarioSelecionado)', javascript
        )
        self.assertIn(
            "Promise.all([carregarJornada(funcionarioId), carregarTabelaPontos()])",
            javascript,
        )
        self.assertNotIn("/jornada?user_id", javascript)
        self.assertNotIn("function carregarJornada", template)

    def test_active_timekeeping_source_has_no_legacy_table_queries(self):
        root = Path(__file__).parents[1]
        source = (
            (root / "routes" / "timekeeping.py").read_text(encoding="utf-8").lower()
        )
        for legacy_table in (
            "from ponto",
            "from presenca",
            "from horarios",
            "from fotos",
        ):
            self.assertNotIn(legacy_table, source)
        views_source = (
            (root / "routes" / "views.py").read_text(encoding="utf-8").lower()
        )
        self.assertNotIn("from ponto", views_source)
        self.assertIn("fluxo legado desativado", views_source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
