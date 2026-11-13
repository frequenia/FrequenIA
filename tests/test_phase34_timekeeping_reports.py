"""Regressões locais da Fase 34 com dados exclusivamente sintéticos."""

from datetime import date, datetime, timezone
from io import BytesIO
from pathlib import Path
import os
import unittest
from unittest.mock import MagicMock, patch

from flask import Flask
from openpyxl import load_workbook

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("FLASK_SECRET_KEY", "x" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "phase34-local-test-key")

from routes.timekeeping import (  # noqa: E402
    _export_csv,
    _export_mirror_csv,
    _export_mirror_docx,
    _export_mirror_pdf,
    _export_mirror_xlsx,
    _export_xlsx,
    _serialize_daily_records,
    timekeeping_bp,
)
from services.timekeeping_reports import (  # noqa: E402
    build_mirror,
    operational_utc_bounds,
    summarize_mirror,
)


COMPANY = "00000000-0000-0000-0000-000000000001"
EMPLOYEE = "00000000-0000-0000-0000-000000000002"


def auth(role="rh"):
    return {
        "user_id": "00000000-0000-0000-0000-000000000010",
        "funcionario_id": EMPLOYEE,
        "session_id": "00000000-0000-0000-0000-000000000012",
        "familia_id": "00000000-0000-0000-0000-000000000013",
        "empresa_id": COMPANY,
        "perfil": role,
    }


class Phase34ReportPureTests(unittest.TestCase):
    def test_night_journey_stays_on_operational_start_date(self):
        operational_date = date(2026, 10, 20)
        snapshot = "00000000-0000-0000-0000-000000000020"
        snapshots = [
            {
                "snapshot_id": snapshot,
                "data_operacional": operational_date,
                "timezone": "America/Sao_Paulo",
                "origem": "turno",
                "versao": 1,
                "evento_id": "entry",
                "ordem": 1,
                "tipo": "entrada",
                "instante_esperado": datetime(2026, 10, 21, 1, tzinfo=timezone.utc),
                "marcacao_id": "mark-entry",
            },
            {
                "snapshot_id": snapshot,
                "data_operacional": operational_date,
                "timezone": "America/Sao_Paulo",
                "origem": "turno",
                "versao": 1,
                "evento_id": "exit",
                "ordem": 2,
                "tipo": "saida",
                "instante_esperado": datetime(2026, 10, 21, 9, tzinfo=timezone.utc),
                "marcacao_id": "mark-exit",
            },
        ]
        effective = [
            {
                "id": "mark-entry",
                "marcacao_original_id": "mark-entry",
                "tipo": "entrada",
                "instante": datetime(2026, 10, 21, 1, tzinfo=timezone.utc),
                "origem": "mobile",
                "ajustada": False,
                "data_operacional": operational_date,
                "jornada_timezone": "America/Sao_Paulo",
            },
            {
                "id": "mark-exit",
                "marcacao_original_id": "mark-exit",
                "tipo": "saida",
                "instante": datetime(2026, 10, 21, 9, tzinfo=timezone.utc),
                "origem": "mobile",
                "ajustada": False,
                "data_operacional": operational_date,
                "jornada_timezone": "America/Sao_Paulo",
            },
        ]

        mirror = build_mirror(
            snapshots, effective, [], operational_date, operational_date
        )

        self.assertEqual(len(mirror), 1)
        self.assertEqual(mirror[0]["data_operacional"], "2026-10-20")
        self.assertEqual(mirror[0]["estado_informativo"], "completo")
        self.assertEqual(mirror[0]["eventos"][1]["efetiva"]["horario"], "06:00")
        self.assertEqual(mirror[0]["duracao_descritiva"], "8h00")

        legacy = _serialize_daily_records(effective)
        self.assertEqual(len(legacy), 1)
        self.assertEqual(legacy[0]["data"], "2026-10-20")
        self.assertEqual(legacy[0]["saida"], "06:00")

    def test_missing_snapshot_is_evidence_gap_not_assumed_absence(self):
        target = date(2026, 10, 20)
        mirror = build_mirror([], [], [], target, target)
        self.assertEqual(mirror[0]["estado_informativo"], "sem_evidencia")
        self.assertFalse(mirror[0]["indicador_dia_sem_marcacao"])
        summary = summarize_mirror(mirror)
        self.assertEqual(summary["dias_sem_evidencia_snapshot"], 1)
        self.assertEqual(summary["dias_com_jornada_sem_marcacao"], 0)

    def test_indicators_are_factual_and_five_minute_rule_is_pending(self):
        target = date(2026, 10, 20)
        expected = datetime(2026, 10, 20, 11, tzinfo=timezone.utc)
        snapshots = [{
            "snapshot_id": "snapshot",
            "data_operacional": target,
            "timezone": "America/Sao_Paulo",
            "origem": "turno",
            "versao": 1,
            "evento_id": "event",
            "ordem": 1,
            "tipo": "entrada",
            "instante_esperado": expected,
            "marcacao_id": "mark",
        }]
        effective = [{
            "id": "mark",
            "marcacao_original_id": "mark",
            "tipo": "entrada",
            "instante": datetime(2026, 10, 20, 11, 7, tzinfo=timezone.utc),
            "origem": "mobile",
            "ajustada": False,
            "data_operacional": target,
            "jornada_timezone": "America/Sao_Paulo",
        }]
        mirror = build_mirror(snapshots, effective, [], target, target)
        event = mirror[0]["eventos"][0]
        self.assertEqual(event["diferenca_minutos"], 7)
        self.assertEqual(event["indicador_tempo"], "apos_horario")
        self.assertEqual(event["classificacao_trabalhista"], "pendente_rh_juridico")
        self.assertEqual(
            summarize_mirror(mirror)["classificacao_tolerancia_cinco_minutos"],
            "pendente_confirmacao_rh",
        )

    def test_folga_no_schedule_and_incomplete_are_distinct(self):
        days = [date(2026, 10, 20), date(2026, 10, 21), date(2026, 10, 22)]
        snapshots = [
            {
                "snapshot_id": "off",
                "data_operacional": days[0],
                "timezone": "America/Sao_Paulo",
                "origem": "folga",
                "versao": 1,
                "evento_id": None,
            },
            {
                "snapshot_id": "none",
                "data_operacional": days[1],
                "timezone": "America/Sao_Paulo",
                "origem": "sem_jornada",
                "versao": 1,
                "evento_id": None,
            },
            {
                "snapshot_id": "partial",
                "data_operacional": days[2],
                "timezone": "America/Sao_Paulo",
                "origem": "turno",
                "versao": 1,
                "evento_id": "entry",
                "ordem": 1,
                "tipo": "entrada",
                "instante_esperado": datetime(2026, 10, 22, 11, tzinfo=timezone.utc),
                "marcacao_id": "entry-mark",
            },
            {
                "snapshot_id": "partial",
                "data_operacional": days[2],
                "timezone": "America/Sao_Paulo",
                "origem": "turno",
                "versao": 1,
                "evento_id": "exit",
                "ordem": 2,
                "tipo": "saida",
                "instante_esperado": datetime(2026, 10, 22, 20, tzinfo=timezone.utc),
                "marcacao_id": "exit-mark",
            },
        ]
        effective = [{
            "id": "entry-mark",
            "marcacao_original_id": "entry-mark",
            "tipo": "entrada",
            "instante": datetime(2026, 10, 22, 11, tzinfo=timezone.utc),
            "origem": "mobile",
            "ajustada": False,
            "data_operacional": days[2],
            "jornada_timezone": "America/Sao_Paulo",
        }]
        mirror = build_mirror(snapshots, effective, [], days[0], days[2])
        self.assertEqual(
            [item["estado_informativo"] for item in mirror],
            ["folga", "sem_jornada", "incompleto"],
        )
        self.assertIsNone(mirror[2]["duracao_descritiva"])

    def test_dst_bounds_follow_zone_rules_without_fixed_day_assumption(self):
        start, end = operational_utc_bounds(
            date(2026, 3, 8), date(2026, 3, 8), "America/New_York"
        )
        self.assertEqual(start, datetime(2026, 3, 7, 17, tzinfo=timezone.utc))
        self.assertEqual(end, datetime(2026, 3, 9, 16, tzinfo=timezone.utc))
        self.assertEqual(int((end - start).total_seconds() // 3600), 47)

    def test_csv_and_xlsx_neutralize_formula_cells(self):
        records = [{
            "dia": "=HYPERLINK(\"https://example.invalid\")",
            "data": "2026-10-20",
            "entrada": "08:00",
            "saida_intervalo": "12:00",
            "retorno_intervalo": "13:00",
            "saida": "17:00",
            "total": "8h00",
        }]
        csv_text = _export_csv(records).getvalue().decode("utf-8-sig")
        self.assertIn("'=HYPERLINK", csv_text)
        workbook = load_workbook(BytesIO(_export_xlsx(records).getvalue()))
        self.assertEqual(workbook.active["A2"].value, "'=HYPERLINK(\"https://example.invalid\")")
        self.assertEqual(workbook.active["A2"].data_type, "s")

    def test_mirror_formats_receive_the_same_operational_rows(self):
        day = [{
            "data_operacional": "2026-10-20",
            "timezone": "America/Sao_Paulo",
            "estado_informativo": "completo",
            "duracao_descritiva": "8h00",
            "eventos": [
                {"tipo": "entrada", "efetiva": {"horario": "22:00"}},
                {"tipo": "saida", "efetiva": {"horario": "06:00"}},
            ],
        }]
        csv_text = _export_mirror_csv(day).getvalue().decode("utf-8-sig")
        self.assertIn("20/10/2026", csv_text)
        self.assertIn("22:00", csv_text)
        workbook = load_workbook(BytesIO(_export_mirror_xlsx(day).getvalue()))
        self.assertEqual(workbook.active["A2"].value, "20/10/2026")
        self.assertEqual(workbook.active["B2"].value, "22:00")
        self.assertTrue(_export_mirror_pdf(day).getvalue().startswith(b"%PDF"))
        self.assertTrue(_export_mirror_docx(day).getvalue().startswith(b"PK"))

    def test_report_service_has_no_write_statement(self):
        source = (
            Path(__file__).parents[1] / "services" / "timekeeping_reports.py"
        ).read_text(encoding="utf-8").lower()
        for statement in ("insert into", "update ", "delete from", "materialize_snapshot"):
            self.assertNotIn(statement, source)


class Phase34ReportRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY="test")
        self.app.register_blueprint(timekeeping_bp)
        self.client = self.app.test_client()
        self.employee = {
            "funcionario_id": EMPLOYEE,
            "nome": "Pessoa sintética",
            "matricula": "SYN-34",
        }

    def get_as(self, role, path):
        with patch(
            "utils.auth_decorator._load_persistent_authentication",
            return_value=(auth(role), None),
        ):
            return self.client.get(path)

    def test_management_mirror_scopes_identity_and_requires_bounded_period(self):
        with patch(
            "routes.timekeeping._load_mirror", return_value=(self.employee, [])
        ) as loader:
            response = self.get_as(
                "gestor",
                f"/api/gestao/espelho?funcionario_id={EMPLOYEE}&inicio=2026-10-01&fim=2026-10-31",
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["natureza"], "informativa_nao_trabalhista")
        self.assertEqual(loader.call_args.args[0]["empresa_id"], COMPANY)

        missing = self.get_as(
            "rh", f"/api/gestao/espelho?funcionario_id={EMPLOYEE}"
        )
        self.assertEqual(missing.status_code, 400)
        too_long = self.get_as(
            "rh",
            f"/api/gestao/espelho?funcionario_id={EMPLOYEE}&inicio=2025-01-01&fim=2026-10-31",
        )
        self.assertEqual(too_long.status_code, 400)

        with patch("routes.timekeeping._load_mirror", return_value=(None, [])):
            outside = self.get_as(
                "gestor",
                f"/api/gestao/espelho?funcionario_id={EMPLOYEE}&inicio=2026-10-01&fim=2026-10-31",
            )
        self.assertEqual(outside.status_code, 404)

    def test_personal_mirror_never_accepts_client_identity(self):
        injected = self.get_as(
            "funcionario",
            f"/api/me/espelho?funcionario_id={EMPLOYEE}&inicio=2026-10-01&fim=2026-10-31",
        )
        self.assertEqual(injected.status_code, 400)

        with patch(
            "routes.timekeeping._load_mirror", return_value=(self.employee, [])
        ) as loader:
            response = self.get_as(
                "funcionario", "/api/me/espelho?inicio=2026-10-01&fim=2026-10-31"
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(loader.call_args.kwargs["personal"])
        self.assertEqual(loader.call_args.args[1], EMPLOYEE)

    def test_management_and_personal_rbac_are_separate(self):
        management = self.get_as(
            "funcionario",
            f"/api/gestao/espelho?funcionario_id={EMPLOYEE}&inicio=2026-10-01&fim=2026-10-31",
        )
        personal = self.get_as(
            "rh", "/api/me/espelho?inicio=2026-10-01&fim=2026-10-31"
        )
        self.assertEqual(management.status_code, 403)
        self.assertEqual(personal.status_code, 403)

    def test_xlsx_route_has_safe_mime_and_filename(self):
        records = [{
            "dia": "Terça",
            "data": "2026-10-20",
            "entrada": "08:00",
            "saida_intervalo": "12:00",
            "retorno_intervalo": "13:00",
            "volta_intervalo": "13:00",
            "saida": "17:00",
            "total": "8h00",
        }]
        with patch(
            "routes.timekeeping._load_management_records",
            return_value=(self.employee, records),
        ):
            response = self.get_as(
                "rh",
                f"/exportar-pontos?formato=xlsx&funcionario_id={EMPLOYEE}&inicio=2026-10-20&fim=2026-10-20",
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.mimetype,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertIn("controle_ponto.xlsx", response.headers["Content-Disposition"])
        self.assertTrue(response.data.startswith(b"PK"))

    def test_mirror_export_keeps_all_existing_formats_and_safe_headers(self):
        day = [{
            "data_operacional": "2026-10-20",
            "timezone": "America/Sao_Paulo",
            "estado_informativo": "sem_evidencia",
            "duracao_descritiva": None,
            "eventos": [],
        }]
        expectations = {
            "csv": ("text/csv", b"\xef\xbb\xbf"),
            "pdf": ("application/pdf", b"%PDF"),
            "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", b"PK"),
            "docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", b"PK"),
        }
        for export_format, (mimetype, signature) in expectations.items():
            with self.subTest(export_format=export_format), patch(
                "routes.timekeeping._load_mirror",
                return_value=(self.employee, day),
            ):
                response = self.get_as(
                    "rh",
                    f"/api/gestao/espelho/exportar?formato={export_format}&funcionario_id={EMPLOYEE}&inicio=2026-10-20&fim=2026-10-20",
                )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.mimetype, mimetype)
            self.assertTrue(response.data.startswith(signature))
            self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
            self.assertIn("no-store", response.headers["Cache-Control"])

    def test_consolidated_report_is_scoped_paginated_and_informative(self):
        connection = MagicMock()
        cursor = MagicMock()
        connection.cursor.return_value = cursor
        cursor.fetchall.side_effect = [[self.employee], []]
        empty_day = [{
            "data_operacional": "2026-10-20",
            "timezone": "America/Sao_Paulo",
            "snapshot_presente": False,
            "snapshot_versao": None,
            "origem_jornada": None,
            "estado_informativo": "sem_evidencia",
            "eventos": [],
            "marcacoes_sem_evento": [],
            "duracao_descritiva": None,
            "solicitacoes": [],
            "indicador_dia_sem_marcacao": False,
            "classificacao_trabalhista": "pendente_rh_juridico",
        }]
        with patch("routes.timekeeping.conectar_bd", return_value=connection), patch(
            "routes.timekeeping.load_employee_report", return_value=empty_day
        ):
            response = self.get_as(
                "gestor",
                "/api/gestao/relatorios/consolidado?inicio=2026-10-01&fim=2026-10-31&pagina=1&limite=25",
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["regra"]["efeito_trabalhista"], "nao_calculado")
        self.assertEqual(
            response.json["regra"]["tolerancia_cinco_minutos"],
            "pendente_confirmacao_rh",
        )
        self.assertEqual(response.json["itens"][0]["funcionario"]["id"], EMPLOYEE)
        employee_query = cursor.execute.call_args_list[0].args
        self.assertEqual(employee_query[1][0], COMPANY)
        self.assertIn("gestores_escopos", employee_query[0])

        invalid = self.get_as(
            "rh",
            "/api/gestao/relatorios/consolidado?inicio=2026-01-01&fim=2026-10-31",
        )
        self.assertEqual(invalid.status_code, 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
