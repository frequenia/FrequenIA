"""Contrato seguro do quiosque: terminal -> empresa -> matrícula -> biometria 1:1."""

import io
import os
import inspect
import unittest
from unittest.mock import MagicMock, patch

from flask import Flask, g

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("FLASK_SECRET_KEY", "x" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "kiosk-test-jwt-key")

from routes.kiosk import create_kiosk_facial_clock
from utils.terminal_auth import terminal_required

COMPANY_A = "00000000-0000-0000-0000-000000000001"
COMPANY_B = "00000000-0000-0000-0000-000000000002"
EMPLOYEE_A = "00000000-0000-0000-0000-000000000003"
TERMINAL_A = "00000000-0000-0000-0000-000000000004"
VECTOR = [1.0] + [0.0] * 511


class Cursor:
    def __init__(self, rows): self.rows, self.calls = list(rows), []
    def execute(self, sql, params=None): self.calls.append((" ".join(sql.split()), params))
    def fetchone(self): return self.rows.pop(0) if self.rows else None
    def fetchall(self): return []
    def close(self): pass
    def __enter__(self): return self
    def __exit__(self, *_args): self.close()


class Connection:
    def __init__(self, cursor): self.cursor_value, self.commits, self.rollbacks = cursor, 0, 0
    def cursor(self, **_kwargs): return self.cursor_value
    def commit(self): self.commits += 1
    def rollback(self): self.rollbacks += 1
    def close(self): pass


def form(**extra):
    data = {"matricula": "A-01", "tipo": "entrada", "imagem": (io.BytesIO(b"image"), "face.png", "image/png")}
    data.update(extra); return data


class KioskClockTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__); self.app.config.update(SECRET_KEY="test", FACE_VERIFICATION_MAX_COSINE_DISTANCE=0.68)

    def call(self, connection, data=None, key="00000000-0000-0000-0000-000000000005"):
        with self.app.test_request_context("/api/quiosque/marcacoes/facial", method="POST", data=data or form(), headers={"Idempotency-Key": key}):
            g.terminal_context = {"terminal_id": TERMINAL_A, "empresa_id": COMPANY_A}
            with patch("routes.kiosk.conectar_bd", return_value=connection), patch("routes.kiosk.register_vector"), patch("routes.kiosk.verify_passive_liveness", return_value=(True, .99)), patch("routes.kiosk.generate_biometric_embedding", return_value=VECTOR):
                return create_kiosk_facial_clock.__wrapped__()

    def test_active_terminal_company_a_marks_only_employee_resolved_in_company_a(self):
        marking = {"id": "00000000-0000-0000-0000-000000000006", "tentativa_facial_id": "00000000-0000-0000-0000-000000000007", "tipo": "entrada", "origem": "facial", "estado": "confirmada", "instante": __import__("datetime").datetime.now(__import__("datetime").timezone.utc), "chave_idempotencia": "00000000-0000-0000-0000-000000000005"}
        cursor = Cursor([{"id": EMPLOYEE_A}, None, {"embedding": VECTOR}, None, ("00000000-0000-0000-0000-000000000007",), marking])
        response, status = self.call(Connection(cursor))
        self.assertEqual(status, 201)
        employee_query = cursor.calls[0]
        self.assertIn("empresa_id=%s AND matricula=%s", employee_query[0])
        self.assertEqual(employee_query[1], (COMPANY_A, "A-01"))
        self.assertIn("funcionario_id=%s", cursor.calls[3][0])
        self.assertNotIn("<=>", " ".join(call[0] for call in cursor.calls))

    def test_company_b_employee_does_not_resolve_and_company_field_is_rejected(self):
        connection = Connection(Cursor([None]))
        response, status = self.call(connection)
        self.assertEqual(status, 404)
        self.assertEqual(connection.cursor_value.calls[0][1], (COMPANY_A, "A-01"))
        response, status = self.call(Connection(Cursor([])), form(empresa_id=COMPANY_B))
        self.assertEqual(status, 400)

    def test_liveness_and_non_match_never_insert_marking(self):
        cursor = Cursor([{"id": EMPLOYEE_A}, None, {"embedding": VECTOR}, ("00000000-0000-0000-0000-000000000007",)])
        connection = Connection(cursor)
        with self.app.test_request_context("/api/quiosque/marcacoes/facial", method="POST", data=form(), headers={"Idempotency-Key": "00000000-0000-0000-0000-000000000005"}):
            g.terminal_context = {"terminal_id": TERMINAL_A, "empresa_id": COMPANY_A}
            with patch("routes.kiosk.conectar_bd", return_value=connection), patch("routes.kiosk.register_vector"), patch("routes.kiosk.verify_passive_liveness", return_value=(False, .1)), patch("routes.kiosk.generate_biometric_embedding") as embedding:
                _, status = create_kiosk_facial_clock.__wrapped__()
        self.assertEqual(status, 422); embedding.assert_not_called()
        self.assertNotIn("INSERT INTO marcacoes", " ".join(call[0] for call in cursor.calls))

        cursor = Cursor([{"id": EMPLOYEE_A}, None, {"embedding": VECTOR}, ("00000000-0000-0000-0000-000000000007",)])
        connection = Connection(cursor)
        with self.app.test_request_context("/api/quiosque/marcacoes/facial", method="POST", data=form(), headers={"Idempotency-Key": "00000000-0000-0000-0000-000000000005"}):
            g.terminal_context = {"terminal_id": TERMINAL_A, "empresa_id": COMPANY_A}
            with patch("routes.kiosk.conectar_bd", return_value=connection), patch("routes.kiosk.register_vector"), patch("routes.kiosk.verify_passive_liveness", return_value=(True, .99)), patch("routes.kiosk.generate_biometric_embedding", return_value=VECTOR), patch("routes.kiosk.compare_face_embeddings", return_value=(False, .9)):
                _, status = create_kiosk_facial_clock.__wrapped__()
        self.assertEqual(status, 409)
        self.assertNotIn("INSERT INTO marcacoes", " ".join(call[0] for call in cursor.calls))

    def test_same_idempotency_key_reuses_official_marking_without_new_face_attempt(self):
        marking = {"id": "00000000-0000-0000-0000-000000000006", "tentativa_facial_id": "00000000-0000-0000-0000-000000000007", "funcionario_id": EMPLOYEE_A, "tipo": "entrada", "origem": "facial", "estado": "confirmada", "instante": __import__("datetime").datetime.now(__import__("datetime").timezone.utc), "chave_idempotencia": "00000000-0000-0000-0000-000000000005"}
        cursor = Cursor([{"id": EMPLOYEE_A}, marking])
        connection = Connection(cursor)
        response, status = self.call(connection)
        self.assertEqual(status, 200)
        self.assertTrue(response.get_json()["reutilizada"])
        sql = " ".join(call[0] for call in cursor.calls)
        self.assertIn("pg_advisory_xact_lock", sql)
        self.assertNotIn("INSERT INTO marcacoes", sql)

    def test_terminal_decorator_rejects_revoked_or_missing_terminal(self):
        app = Flask(__name__); app.secret_key = "test"
        protected = terminal_required(lambda: "ok")
        with app.test_request_context():
            response = protected(); self.assertEqual(response[1], 401)
        cursor = Cursor([None]); connection = Connection(cursor)
        with app.test_request_context():
            from flask import session
            session["terminal_ponto_id"] = TERMINAL_A
            with patch("utils.terminal_auth.conectar_bd", return_value=connection):
                response = protected()
        self.assertEqual(response[1], 401)

    def test_source_contains_only_one_to_one_biometric_lookup_and_official_locking(self):
        source = inspect.getsource(create_kiosk_facial_clock)
        self.assertIn("_active_biometric(cursor, company_id, employee_id)", source)
        self.assertIn("bloquear_funcionario_para_marcacao", source)
        self.assertIn("buscar_marcacao_por_idempotencia", source)
        self.assertNotIn("FROM fotos", source)
        self.assertNotIn("<=>", source)


if __name__ == "__main__": unittest.main(verbosity=2)
