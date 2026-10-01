"""Ciclos automáticos de cinco falhas faciais válidas."""

from datetime import datetime, timedelta, timezone
import unittest

from services.facial_failure_occurrences import (
    COUNTED_FAILURE_REASONS,
    FAILURE_CYCLE_SIZE,
    consume_facial_failure_cycle,
)

COMPANY_A = "00000000-0000-0000-0000-000000000001"
COMPANY_B = "00000000-0000-0000-0000-000000000002"
EMPLOYEE_A = "00000000-0000-0000-0000-000000000003"
EMPLOYEE_B = "00000000-0000-0000-0000-000000000004"


class Cursor:
    def __init__(self, attempts):
        self.attempts, self.calls, self.rowcount = attempts, [], FAILURE_CYCLE_SIZE
        self.occurrence = {"id": "00000000-0000-0000-0000-000000000099", "primeira_ocorrencia_at": attempts[0]["instante"]} if attempts else None
    def execute(self, sql, params=None): self.calls.append((" ".join(sql.split()), params))
    def fetchall(self): return self.attempts
    def fetchone(self): return self.occurrence


def attempts(company=COMPANY_A, employee=EMPLOYEE_A, count=5):
    start = datetime(2026, 9, 24, 11, 0, tzinfo=timezone.utc)
    return [
        {"id": f"00000000-0000-0000-0000-{index:012d}", "instante": start + timedelta(minutes=index)}
        for index in range(1, count + 1)
    ]


class FacialFailureOccurrenceTests(unittest.TestCase):
    def test_first_four_valid_failures_create_nothing(self):
        cursor = Cursor(attempts(count=4))
        self.assertIsNone(consume_facial_failure_cycle(cursor, COMPANY_A, EMPLOYEE_A))
        sql = " ".join(call[0] for call in cursor.calls)
        self.assertNotIn("INSERT INTO ocorrencias", sql)

    def test_fifth_creates_one_occurrence_at_first_attempt_and_consumes_exactly_five(self):
        batch = attempts()
        cursor = Cursor(batch)
        occurrence = consume_facial_failure_cycle(cursor, COMPANY_A, EMPLOYEE_A)
        self.assertEqual(occurrence["primeira_ocorrencia_at"], batch[0]["instante"])
        sql = " ".join(call[0] for call in cursor.calls)
        self.assertIn("pg_advisory_xact_lock", sql)
        self.assertIn("INSERT INTO ocorrencias", sql)
        self.assertIn("UPDATE tentativas_faciais", sql)
        self.assertIn("INSERT INTO auditoria", sql)
        insert = next(params for query, params in cursor.calls if "INSERT INTO ocorrencias" in query)
        self.assertEqual(insert[0:2], (COMPANY_A, EMPLOYEE_A))
        self.assertEqual(insert[3], batch[0]["instante"])

    def test_new_cycle_isolated_by_company_and_employee(self):
        cursor_a = Cursor(attempts(COMPANY_A, EMPLOYEE_A))
        cursor_b = Cursor(attempts(COMPANY_B, EMPLOYEE_B, 4))
        self.assertIsNotNone(consume_facial_failure_cycle(cursor_a, COMPANY_A, EMPLOYEE_A))
        self.assertIsNone(consume_facial_failure_cycle(cursor_b, COMPANY_B, EMPLOYEE_B))
        self.assertEqual(cursor_b.calls[1][1][0:2], (COMPANY_B, EMPLOYEE_B))

    def test_only_liveness_and_one_to_one_mismatch_count(self):
        self.assertEqual(COUNTED_FAILURE_REASONS, {"liveness_reprovado", "nao_corresponde"})
        self.assertNotIn("biometria_ausente", COUNTED_FAILURE_REASONS)
        self.assertNotIn("infraestrutura", COUNTED_FAILURE_REASONS)

    def test_reprocessing_consumed_attempts_cannot_create_a_second_occurrence(self):
        cursor = Cursor([])
        self.assertIsNone(consume_facial_failure_cycle(cursor, COMPANY_A, EMPLOYEE_A))
        self.assertNotIn("INSERT INTO ocorrencias", " ".join(call[0] for call in cursor.calls))


if __name__ == "__main__": unittest.main(verbosity=2)
