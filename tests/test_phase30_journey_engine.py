import os
import unittest
from datetime import date, datetime, time, timezone
from pathlib import Path


os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("FLASK_SECRET_KEY", "x" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "phase30-jwt-secret-different")

from services.daily_journey import JourneyError, build_planned_events, local_wall_time
from utils.schedules import validate_periods


ROOT = Path(__file__).resolve().parents[1]


class Phase30JourneyEngineTests(unittest.TestCase):
    def test_one_period_maps_entry_and_final_exit(self):
        events = build_planned_events(
            date(2026, 10, 19), "America/Sao_Paulo",
            [{"ordem": 1, "inicio": time(8), "fim": time(17), "fim_dia_offset": 0}],
        )
        self.assertEqual([item.event_type for item in events], ["entrada", "saida"])

    def test_multiple_periods_repeat_intermediate_exit_and_return(self):
        periods = [
            {"ordem": index + 1, "inicio": time(6 + index * 3), "fim": time(7 + index * 3), "fim_dia_offset": 0}
            for index in range(4)
        ]
        events = build_planned_events(date(2026, 10, 19), "UTC", periods)
        self.assertEqual(
            [item.event_type for item in events],
            ["entrada", "saida_intervalo", "retorno_intervalo", "saida_intervalo", "retorno_intervalo", "saida_intervalo", "retorno_intervalo", "saida"],
        )
        self.assertEqual([item.order for item in events], list(range(1, 9)))

    def test_overnight_event_keeps_operational_start_date(self):
        events = build_planned_events(
            date(2026, 10, 19), "UTC",
            [{"ordem": 1, "inicio": time(22), "fim": time(6), "fim_dia_offset": 1}],
        )
        self.assertEqual(events[0].expected_at.date(), date(2026, 10, 19))
        self.assertEqual(events[1].expected_at.date(), date(2026, 10, 20))

    def test_timezone_is_not_fixed_and_changes_utc_instant(self):
        sao_paulo = local_wall_time(date(2026, 10, 19), time(8), "America/Sao_Paulo")
        tokyo = local_wall_time(date(2026, 10, 19), time(8), "Asia/Tokyo")
        self.assertNotEqual(sao_paulo, tokyo)
        self.assertEqual(sao_paulo.tzinfo, timezone.utc)

    def test_nonexistent_and_ambiguous_local_times_fail_closed(self):
        with self.assertRaisesRegex(JourneyError, "inexistente"):
            local_wall_time(date(2026, 3, 8), time(2, 30), "America/New_York")
        with self.assertRaisesRegex(JourneyError, "ambíguo"):
            local_wall_time(date(2026, 11, 1), time(1, 30), "America/New_York")

    def test_overlap_and_non_sequential_periods_remain_rejected(self):
        with self.assertRaisesRegex(ValueError, "sobrepor"):
            validate_periods([
                {"dia_semana": 1, "ordem": 1, "inicio": "08:00", "fim": "12:00"},
                {"dia_semana": 1, "ordem": 2, "inicio": "11:00", "fim": "15:00"},
            ])
        with self.assertRaisesRegex(ValueError, "sequencial"):
            validate_periods([
                {"dia_semana": 1, "ordem": 1, "inicio": "08:00", "fim": "09:00"},
                {"dia_semana": 1, "ordem": 3, "inicio": "10:00", "fim": "11:00"},
            ])

    def test_migration_has_tenant_constraints_uniqueness_and_immutable_snapshot(self):
        sql = (ROOT / "supabase/migrations/025_daily_journey_engine.sql").read_text(encoding="utf-8").lower()
        for expected in (
            "create table public.escalas_diarias",
            "create table public.jornadas_diarias",
            "create table public.jornada_eventos_esperados",
            "create table public.tentativas_jornada",
            "escalas_diarias_ativa_unique",
            "jornadas_diarias_empresa_funcionario_data_unique",
            "jornadas_diarias_immutable",
            "jornada_eventos_immutable",
            "on delete restrict",
        ):
            self.assertIn(expected, sql)
        self.assertNotRegex(sql, r"(?i)\b(nome|cpf|matricula|embedding|imagem)\b")

    def test_clients_no_longer_send_or_select_authoritative_type(self):
        dart_service = (ROOT / "mobile/lib/clock/face_clock_service.dart").read_text(encoding="utf-8")
        dart_page = (ROOT / "mobile/lib/clock/clock_page.dart").read_text(encoding="utf-8")
        kiosk_html = (ROOT / "templates/reconhecimentoFacial.html").read_text(encoding="utf-8")
        kiosk_js = (ROOT / "static/js/reconhecimento.js").read_text(encoding="utf-8")
        self.assertNotIn("'tipo': operation", dart_service)
        self.assertNotIn("DropdownButtonFormField<ClockEventType>", dart_page)
        self.assertNotIn('name="tipo"', kiosk_html)
        self.assertNotIn('formData.append("tipo"', kiosk_js)

    def test_domain_uses_effective_view_and_postgresql_clock(self):
        source = (ROOT / "services/daily_journey.py").read_text(encoding="utf-8")
        self.assertIn("fetch_effective_events", source)
        self.assertIn("clock_timestamp()", source)
        self.assertIn("pg_advisory_xact_lock", source)
        self.assertNotIn("America/Sao_Paulo", source)

    def test_facial_failure_domain_remains_separate(self):
        source = (ROOT / "services/daily_journey.py").read_text(encoding="utf-8")
        self.assertNotIn("falha_facial", source)
        self.assertIn("ordem_invalida", (ROOT / "supabase/migrations/025_daily_journey_engine.sql").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
