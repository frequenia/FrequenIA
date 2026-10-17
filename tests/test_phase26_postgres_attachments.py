"""Integração opt-in da Fase 26 contra PostgreSQL/pgvector descartável.

Reusa apenas os fixtures homologados da Fase 25. O opt-in continua sendo
``PHASE25_TEST_DATABASE_URL`` e nunca há fallback para ``DATABASE_URL``/.env.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from io import BytesIO
import gc
import os
from pathlib import Path
import tempfile
import threading
import unittest
import warnings
from unittest.mock import patch
from uuid import UUID

from flask import Flask
from werkzeug.datastructures import FileStorage

import test_phase25_postgres_integration as phase25
from routes.occurrences import occurrences_bp
from routes.timekeeping import timekeeping_bp
from services.correction_attachment_storage import AttachmentStorageError
from services.correction_attachments import upload_attachment


PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF\n"
JPEG = b"\xff\xd8\xff\xe0JFIF\x00fixture\xff\xd9"
PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x00\x00\x00\x00IEND\xaeB\x60\x82"
)


@unittest.skipUnless(
    phase25.POSTGRES_ENABLED,
    "requer PHASE25_TEST_DATABASE_URL explicita para frequenia_phase25_test local",
)
class Phase26PostgresAttachmentTests(unittest.TestCase):
    # O mesmo universo multi-tenant da homologação anterior.
    for _name in (
        "COMPANY", "UNIT", "TEAM", "OTHER_TEAM", "FOREIGN_COMPANY",
        "FOREIGN_UNIT", "FOREIGN_TEAM", "EMPLOYEE_USER", "EMPLOYEE",
        "OTHER_USER", "OTHER_EMPLOYEE", "MANAGER_USER", "MANAGER",
        "HR_USER", "HR", "ADMIN_USER", "ADMIN", "FOREIGN_USER",
        "FOREIGN_EMPLOYEE", "FOREIGN_HR_USER", "FOREIGN_HR",
        "FOREIGN_ADMIN_USER", "FOREIGN_ADMIN", "MARKING", "EXIT_MARKING",
        "OTHER_MARKING", "FOREIGN_MARKING",
    ):
        locals()[_name] = getattr(phase25.Phase25PostgresIntegrationTests, _name)
    del _name

    _seed = phase25.Phase25PostgresIntegrationTests._seed
    _auth = phase25.Phase25PostgresIntegrationTests._auth
    _database_patches = phase25.Phase25PostgresIntegrationTests._database_patches
    _request = phase25.Phase25PostgresIntegrationTests._request
    _create = phase25.Phase25PostgresIntegrationTests._create
    _decide = phase25.Phase25PostgresIntegrationTests._decide
    _forward = phase25.Phase25PostgresIntegrationTests._forward
    _state = phase25.Phase25PostgresIntegrationTests._state
    _effective = phase25.Phase25PostgresIntegrationTests._effective

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Upgrade real a partir de todo o schema anterior, preservando uma
        # correção já existente.
        phase25._reset_database()
        phase25._apply_migrations(1, 20)
        fixture = cls(methodName="runTest")
        connection = phase25._connect()
        try:
            with connection.cursor() as cursor:
                fixture._seed(cursor)
                cursor.execute(
                    """INSERT INTO correcoes
                       (empresa_id, funcionario_id, solicitante_usuario_id,
                        tipo, categoria, motivo, estado)
                       VALUES (%s,%s,%s,'justificativa','justificativa',
                               'Registro anterior a 021','pendente_gestor')
                       RETURNING id""",
                    (cls.COMPANY, cls.EMPLOYEE, cls.EMPLOYEE_USER),
                )
                cls.upgrade_correction_id = str(cursor.fetchone()[0])
            connection.commit()
        finally:
            connection.close()
        phase25._apply_migrations(21, 21)
        connection = phase25._connect(dict_rows=True)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT to_regclass('public.anexos_correcao') AS tabela,
                              EXISTS (SELECT 1 FROM correcoes WHERE id=%s) AS preservada""",
                    (cls.upgrade_correction_id,),
                )
                cls.upgrade_evidence = cursor.fetchone()
        finally:
            connection.close()

        # Instalação limpa 001-021 usada por todos os cenários.
        phase25._reset_database()
        phase25._apply_migrations(1, 22)
        cls.app = Flask("phase26-integration")
        cls.app.config.update(TESTING=True, SECRET_KEY="phase26-test-only")
        cls.app.register_blueprint(occurrences_bp)
        cls.app.register_blueprint(timekeeping_bp)

    def setUp(self):
        connection = phase25._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("TRUNCATE empresas, usuarios CASCADE")
                self._seed(cursor)
            connection.commit()
        finally:
            connection.close()
        self._storage_temp = tempfile.TemporaryDirectory(prefix="frequenia-phase26-")
        self._environment = patch.dict(
            os.environ, {
                "APP_ENV": "test",
                "ATTACHMENT_STORAGE_PROVIDER": "local",
                "ATTACHMENT_STORAGE_ROOT": self._storage_temp.name,
                "ATTACHMENT_SCANNER_PROVIDER": "fake-clean",
                "ATTACHMENT_SCAN_MODE": "sync",
            }
        )
        self._environment.start()

    def tearDown(self):
        self._environment.stop()
        self._storage_temp.cleanup()

    def _file(self, content=PDF, name="comprovante.pdf", mime="application/pdf"):
        return (BytesIO(content), name, mime)

    def _upload(self, correction_id, content=PDF, name="comprovante.pdf",
                mime="application/pdf", auth=None, method="PUT"):
        return self._request(
            auth or self._auth("funcionario"), method,
            f"/api/ocorrencias/{correction_id}/comprovante",
            data={"comprovante": self._file(content, name, mime)},
            content_type="multipart/form-data",
        )

    def _rows(self, correction_id):
        connection = phase25._connect(dict_rows=True)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM anexos_correcao WHERE correcao_id=%s ORDER BY created_at",
                    (correction_id,),
                )
                return cursor.fetchall()
        finally:
            connection.close()

    def _snapshot_marking(self):
        connection = phase25._connect(dict_rows=True)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT row_to_json(m)::text AS snapshot FROM marcacoes m WHERE id=%s",
                    (self.MARKING,),
                )
                return cursor.fetchone()["snapshot"]
        finally:
            connection.close()

    def test_00_migration_021_clean_upgrade_constraints_and_indexes(self):
        self.assertEqual(self.upgrade_evidence["tabela"], "anexos_correcao")
        self.assertTrue(self.upgrade_evidence["preservada"])
        connection = phase25._connect(dict_rows=True)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT conname FROM pg_constraint
                       WHERE conrelid='anexos_correcao'::regclass"""
                )
                constraints = {row["conname"] for row in cursor}
                cursor.execute(
                    """SELECT indexname FROM pg_indexes
                       WHERE tablename='anexos_correcao'"""
                )
                indexes = {row["indexname"] for row in cursor}
        finally:
            connection.close()
        self.assertIn("anexos_correcao_empresa_funcionario_correcao_fk", constraints)
        self.assertIn("anexos_correcao_tamanho_check", constraints)
        self.assertIn("anexos_correcao_mime_check", constraints)
        self.assertIn("anexos_correcao_estado_check", constraints)
        self.assertIn("anexos_correcao_ativo_unique", indexes)
        self.assertIn("anexos_correcao_empresa_correcao_idx", indexes)

    def test_01_request_without_attachment_remains_valid(self):
        correction_id = self._create()
        detail = self._request(
            self._auth("funcionario"), "GET", f"/api/ocorrencias/{correction_id}"
        )
        self.assertEqual(detail.status_code, 200)
        self.assertIsNone(detail.get_json()["comprovante"])

    def test_02_pdf_jpeg_and_png_are_accepted(self):
        fixtures = (
            (PDF, "proof.pdf", "application/pdf"),
            (JPEG, "proof.jpeg", "image/jpeg"),
            (PNG, "proof.png", "image/png"),
        )
        for content, name, mime in fixtures:
            with self.subTest(name=name):
                correction_id = self._create()
                response = self._upload(correction_id, content, name, mime)
                self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
                self.assertEqual(response.get_json()["tipo_mime"], mime)

    def test_02b_attachment_can_be_sent_atomically_during_creation(self):
        response = self._request(
            self._auth("funcionario"),
            "POST",
            "/api/ocorrencias",
            data={
                "tipo": "horario_incorreto",
                "marcacao_id": self.MARKING,
                "motivo": "Criacao multipart",
                "instante_solicitado": "2026-09-12T08:15:00-03:00",
                "comprovante": self._file(PDF, "proof.pdf", "application/pdf"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        body = response.get_json()
        self.assertEqual(body["status"], "pendente_gestor")
        self.assertEqual(body["comprovante"]["tipo_mime"], "application/pdf")
        self.assertEqual(len(self._rows(body["id"])), 1)

    def test_03_invalid_empty_oversized_extension_mime_signature_and_truncation(self):
        invalid = (
            (b"", "proof.pdf", "application/pdf"),
            (b"x" * (10 * 1024 * 1024 + 1), "proof.pdf", "application/pdf"),
            (PDF, "proof.exe", "application/pdf"),
            (PDF, "proof.pdf", "text/plain"),
            (PNG, "proof.pdf", "application/pdf"),
            (PNG[:-8], "proof.png", "image/png"),
        )
        for content, name, mime in invalid:
            with self.subTest(name=name, mime=mime, size=len(content)):
                correction_id = self._create()
                response = self._upload(correction_id, content, name, mime)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(self._rows(correction_id), [])
                response.close()
                del response
                # Werkzeug usa um arquivo temporário para o payload > 10 MiB;
                # force o descarte dentro da própria subexecução de teste.
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", ResourceWarning)
                    gc.collect()

    def test_04_name_and_path_are_inert_and_metadata_has_no_storage_secret(self):
        correction_id = self._create()
        response = self._upload(correction_id, PDF, "../../evil\x00name.pdf")
        self.assertEqual(response.status_code, 200)
        metadata = response.get_json()
        self.assertEqual(metadata["nome"], "evilname.pdf")
        self.assertFalse({"chave_objeto", "caminho", "url", "token"} & set(metadata))
        row = self._rows(correction_id)[0]
        self.assertRegex(row["chave_objeto"], r"^test/[0-9a-f-]+/clean/[0-9a-f-]+\.pdf$")
        resolved = (Path(self._storage_temp.name) / row["chave_objeto"]).resolve()
        self.assertIn(Path(self._storage_temp.name).resolve(), resolved.parents)
        self.assertNotIn("evil", row["chave_objeto"])

    def test_05_owner_can_upload_replace_and_remove_only_while_pending(self):
        correction_id = self._create()
        first = self._upload(correction_id)
        second = self._upload(correction_id, PNG, "replacement.png", "image/png")
        self.assertEqual((first.status_code, second.status_code), (200, 200))
        rows = self._rows(correction_id)
        self.assertEqual([row["estado"] for row in rows], ["substituido", "ativo"])
        removed = self._request(
            self._auth("funcionario"), "DELETE",
            f"/api/ocorrencias/{correction_id}/comprovante",
        )
        self.assertEqual(removed.status_code, 204)
        self.assertEqual([row["estado"] for row in self._rows(correction_id)],
                         ["substituido", "removido"])

    def test_06_forwarded_and_final_states_block_attachment_mutation(self):
        for final_action in (None, "aprovar", "rejeitar"):
            with self.subTest(final_action=final_action):
                correction_id = self._create()
                self.assertEqual(self._upload(correction_id).status_code, 200)
                if final_action is None:
                    self._forward(correction_id)
                else:
                    self.assertEqual(
                        self._decide(
                            correction_id,
                            final_action,
                            observation="Justificativa obrigatoria" if final_action == "rejeitar" else None,
                        ).status_code,
                        200,
                    )
                self.assertEqual(self._upload(correction_id).status_code, 409)
                removal = self._request(
                    self._auth("funcionario"), "DELETE",
                    f"/api/ocorrencias/{correction_id}/comprovante",
                )
                self.assertEqual(removal.status_code, 409)

    def test_07_employee_authorization_is_non_enumerable(self):
        correction_id = self._create()
        self.assertEqual(self._upload(correction_id).status_code, 200)
        for auth in (self._auth("outro_funcionario"), self._auth("funcionario_externo")):
            for suffix in ("", "/download"):
                response = self._request(
                    auth, "GET", f"/api/ocorrencias/{correction_id}/comprovante{suffix}"
                )
                self.assertEqual(response.status_code, 404)

    def test_08_manager_scope_hr_admin_and_cross_tenant_authorization(self):
        scoped_id = self._create()
        self.assertEqual(self._upload(scoped_id).status_code, 200)
        for role in ("gestor", "rh", "administrador"):
            response = self._request(
                self._auth(role), "GET",
                f"/api/gestao/ocorrencias/{scoped_id}/comprovante/download",
            )
            self.assertEqual(response.status_code, 200, role)

        outside_id = self._create(
            auth=self._auth("outro_funcionario"), marcacao_id=self.OTHER_MARKING
        )
        self.assertEqual(
            self._upload(outside_id, auth=self._auth("outro_funcionario")).status_code,
            200,
        )
        outside = self._request(
            self._auth("gestor"), "GET",
            f"/api/gestao/ocorrencias/{outside_id}/comprovante/download",
        )
        self.assertEqual(outside.status_code, 404)
        for role in ("rh_externo", "administrador_externo"):
            response = self._request(
                self._auth(role), "GET",
                f"/api/gestao/ocorrencias/{scoped_id}/comprovante/download",
            )
            self.assertEqual(response.status_code, 404)

    def test_09_download_has_safe_headers_and_does_not_inline_render(self):
        correction_id = self._create()
        self._upload(correction_id, PNG, "evidence.png", "image/png")
        response = self._request(
            self._auth("funcionario"), "GET",
            f"/api/ocorrencias/{correction_id}/comprovante/download",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, PNG)
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertTrue(response.headers["Content-Disposition"].startswith("attachment;"))
        self.assertIn("private", response.headers["Cache-Control"])

    def test_10_attachment_actions_have_sanitized_audit(self):
        correction_id = self._create()
        self._upload(correction_id)
        self._upload(correction_id, PNG, "replacement.png", "image/png")
        self._request(
            self._auth("gestor"), "GET",
            f"/api/gestao/ocorrencias/{correction_id}/comprovante/download",
        )
        self._request(
            self._auth("funcionario"), "DELETE",
            f"/api/ocorrencias/{correction_id}/comprovante",
        )
        connection = phase25._connect(dict_rows=True)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT acao, ator_usuario_id, empresa_id, metadados
                       FROM auditoria WHERE entidade_id=%s
                         AND acao LIKE 'correcao.anexo_%%' ORDER BY ocorrido_at""",
                    (correction_id,),
                )
                events = cursor.fetchall()
        finally:
            connection.close()
        self.assertEqual(
            [row["acao"] for row in events],
            ["correcao.anexo_incluido", "correcao.anexo_varredura",
             "correcao.anexo_substituido", "correcao.anexo_varredura",
             "correcao.anexo_download_gestao", "correcao.anexo_removido"],
        )
        for event in events:
            metadata = event["metadados"]
            self.assertEqual(str(event["empresa_id"]), self.COMPANY)
            self.assertEqual(metadata["empresa_id"], self.COMPANY)
            self.assertEqual(metadata["funcionario_id"], self.EMPLOYEE)
            self.assertIn(metadata["papel"], {"funcionario", "gestor"})
            self.assertIn("sha256", metadata)
            self.assertIn("tamanho_bytes", metadata)
            self.assertIn("tipo_mime", metadata)
            self.assertFalse({"chave_objeto", "caminho", "url", "conteudo"} & set(metadata))

    def test_11_database_failure_compensates_new_object(self):
        correction_id = self._create()
        with patch("services.correction_attachments._audit", side_effect=RuntimeError("fixture")):
            # TESTING propaga falhas inesperadas: é justamente a prova de que a
            # compensação ocorre mesmo antes de a camada HTTP convertê-la em 500.
            with self.assertRaisesRegex(RuntimeError, "fixture"):
                self._upload(correction_id)
        self.assertEqual(self._rows(correction_id), [])
        self.assertEqual([path for path in Path(self._storage_temp.name).rglob("*") if path.is_file()], [])

    def test_12_storage_failure_does_not_create_orphan_metadata(self):
        class FailingStorage:
            def generate_key(self, extension, company_id=None, area="quarantine"):
                return f"test/{company_id}/{area}/{UUID(int=901)}.{extension}"

            def put(self, key, content, mime_type=None, checksum=None):
                raise AttachmentStorageError("Falha controlada de armazenamento.")

        correction_id = self._create()
        with patch(
            "services.correction_attachments.get_attachment_storage",
            return_value=FailingStorage(),
        ):
            response = self._upload(correction_id)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self._rows(correction_id), [])

    def test_13_two_real_concurrent_uploads_leave_one_active_attachment(self):
        correction_id = self._create()
        barrier = threading.Barrier(2)

        def connection_factory():
            connection = phase25._connect()
            barrier.wait(timeout=10)
            return connection

        def send(content, name, mime):
            storage = FileStorage(stream=BytesIO(content), filename=name, content_type=mime)
            return upload_attachment(
                connection_factory, self._auth("funcionario"), correction_id, storage
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = (
                executor.submit(send, PDF, "one.pdf", "application/pdf"),
                executor.submit(send, PNG, "two.png", "image/png"),
            )
            results = [future.result(timeout=20) for future in futures]
        self.assertEqual(len(results), 2)
        rows = self._rows(correction_id)
        self.assertEqual(len(rows), 2)
        self.assertEqual(sum(row["estado"] == "ativo" for row in rows), 1)
        self.assertEqual(sum(row["estado"] == "substituido" for row in rows), 1)

    def test_14_workflow_marking_effective_view_and_export_ignore_attachment(self):
        before_marking = self._snapshot_marking()
        before_effective = [(row["instante"], row["tipo"]) for row in self._effective()]
        correction_id = self._create()
        self.assertEqual(self._upload(correction_id).status_code, 200)
        after_attachment = [(row["instante"], row["tipo"]) for row in self._effective()]
        self.assertEqual(after_attachment, before_effective)
        query = {"funcionario_id": self.EMPLOYEE, "inicio": "2026-09-12", "fim": "2026-09-12"}
        prior_export = self._request(
            self._auth("gestor"), "GET", "/exportar-pontos",
            query_string={**query, "formato": "csv"},
        ).data
        self.assertEqual(self._decide(correction_id, "aprovar").status_code, 200)
        current_export = self._request(
            self._auth("gestor"), "GET", "/exportar-pontos",
            query_string={**query, "formato": "csv"},
        )
        self.assertEqual(current_export.status_code, 200)
        self.assertNotEqual(current_export.data, prior_export)
        self.assertIn(b"08:15", current_export.data)
        self.assertEqual(self._snapshot_marking(), before_marking)

    def test_15_facial_failure_workflow_remains_independent(self):
        occurrence_id = "26000000-0000-0000-0000-000000000001"
        connection = phase25._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO ocorrencias
                       (id, empresa_id, funcionario_id, tipo, descricao, estado,
                        primeira_ocorrencia_at, ciclo_falha_facial_id)
                       VALUES (%s,%s,%s,'falha_facial','Fixture fase 26','aberta',
                               clock_timestamp(),%s)""",
                    (occurrence_id, self.COMPANY, self.EMPLOYEE, str(UUID(int=601))),
                )
            connection.commit()
        finally:
            connection.close()
        started = self._request(
            self._auth("gestor"), "POST",
            f"/api/gestao/ocorrencias/falhas-faciais/{occurrence_id}/iniciar-analise",
            json={},
        )
        resolved = self._request(
            self._auth("gestor"), "POST",
            f"/api/gestao/ocorrencias/falhas-faciais/{occurrence_id}/resolver",
            json={"justificativa": "Fluxo independente preservado"},
        )
        self.assertEqual((started.status_code, resolved.status_code), (200, 200))
        self.assertEqual(resolved.get_json()["estado"], "resolvida")


if __name__ == "__main__":
    unittest.main()
