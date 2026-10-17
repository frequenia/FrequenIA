import inspect
import json
import logging
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("FLASK_SECRET_KEY", "x" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "phase-31-test-jwt-key")

import app
import routes.biometrics as routes
import routes.kiosk as kiosk
from services.biometric_calibration import CalibrationError, aggregate_authorized_dataset
from services.biometric_governance import BiometricGovernanceError, resolve_governance
from services.biometric_observability import emit_biometric_event


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase" / "migrations" / "026_biometric_governance_lifecycle.sql"


class Phase31GovernanceContractTests(unittest.TestCase):
    def test_migration_number_and_required_states(self):
        self.assertTrue(MIGRATION.exists())
        sql = MIGRATION.read_text(encoding="utf-8")
        for value in ("politicas_biometricas", "perfis_tecnicos_biometricos", "exclusao_pendente", "eliminada", "embedding drop not null"):
            self.assertIn(value, sql)

    def test_policy_is_versioned_append_only_and_overlap_is_checked(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        self.assertIn("politica_biometrica_append_only", sql)
        self.assertIn("politica_biometrica_sobreposta", sql)
        self.assertIn("referencia_base_legal", sql)
        self.assertNotIn("consentimento", sql.lower())

    def test_profile_has_all_server_side_technical_fields(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        for value in ("modelo", "versao_modelo", "dimensao", "metrica", "limiar", "versao_liveness"):
            self.assertIn(value, sql)

    def test_non_finite_or_invalid_threshold_fails_closed_in_service(self):
        for value in (float("nan"), float("inf"), 0, 2.1):
            cursor = MagicMock()
            cursor.fetchone.return_value = {
                "policy_id":"p","policy_version":"1","notice_version":"1",
                "finalidade":"registro_ponto_1a1","retencao_dias":1,
                "canal_atendimento":"x","profile_id":"t","profile_version":"1",
                "modelo":"ArcFace","versao_modelo":"deepface-0.0.99",
                "dimensao":512,"metrica":"cosine_distance","limiar":value,
                "versao_liveness":"1",
            }
            with self.assertRaises(BiometricGovernanceError):
                resolve_governance(cursor,"company")

    def test_client_authority_fields_include_model_policy_and_threshold(self):
        source = inspect.getsource(routes._reject_verification_authority_fields)
        for value in ("empresa_id", "funcionario_id", "embedding", "threshold", "liveness"):
            self.assertIn(value, source)

    def test_personal_response_does_not_select_sensitive_material(self):
        source = inspect.getsource(routes.own_biometric_transparency)
        self.assertNotIn("SELECT b.embedding", source)
        self.assertNotIn("distancia_facial", source)
        self.assertNotIn("referencia_arquivo_privado", source)

    def test_verification_remains_one_to_one_without_vector_search(self):
        source = inspect.getsource(routes._active_biometric) + inspect.getsource(kiosk._active_biometric)
        self.assertNotIn("<=>", source); self.assertNotIn("<->", source)
        self.assertIn("funcionario_id", source); self.assertIn("empresa_id", source)

    def test_kiosk_and_mobile_paths_use_server_governance(self):
        self.assertIn("resolve_verification_material", inspect.getsource(kiosk._active_biometric))
        mobile=(ROOT/"mobile/lib/clock/face_clock_service.dart").read_text(encoding="utf-8")
        self.assertIn("/api/biometria/verificar", mobile)
        self.assertNotIn("embedding", mobile.lower())

    def test_audit_trigger_recursively_blocks_sensitive_keys(self):
        sql=MIGRATION.read_text(encoding="utf-8")
        self.assertIn("jsonb_each(value)",sql)
        self.assertIn("auditoria_metadados_seguros(item.val)",sql)
        for key in ("embedding","imagem","score","cpf","matricula","token","caminho","segredo"):
            self.assertIn(f"'{key}'",sql)

    def test_elimination_constraint_requires_null_material(self):
        sql=MIGRATION.read_text(encoding="utf-8")
        self.assertIn("status = 'eliminada' and embedding is null",sql)
        self.assertIn("referencia_arquivo_privado is null",sql)

    def test_history_is_append_only(self):
        sql=MIGRATION.read_text(encoding="utf-8")
        self.assertIn("historico_biometrico_append_only",sql)
        self.assertIn("before update or delete",sql.lower())

    def test_purge_is_dry_run_by_default_and_uses_skip_locked(self):
        from services.biometric_governance import purge_eligible
        signature=inspect.signature(purge_eligible)
        self.assertFalse(signature.parameters["execute"].default)
        self.assertIn("SKIP LOCKED",inspect.getsource(purge_eligible))

    def test_termination_updates_sessions_and_biometrics_in_callers_transaction(self):
        from services.biometric_governance import change_employee_status
        source=inspect.getsource(change_employee_status)
        self.assertIn("auth_sessions",source)
        self.assertIn("biometrias",source)
        self.assertNotIn("commit()",source)

    def test_away_policy_is_restricted_to_explicit_server_values(self):
        self.assertIn(app.app.config["BIOMETRIC_AWAY_POLICY"],{"bloquear","revogar","preservar"})

    def test_calibration_requires_explicit_authorization(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"dataset.json"; path.write_text("{}",encoding="utf-8")
            with self.assertRaises(CalibrationError):
                aggregate_authorized_dataset(path,repository_root=ROOT,authorized=False,threshold=.68)

    def test_calibration_rejects_dataset_inside_git(self):
        with self.assertRaises(CalibrationError):
            aggregate_authorized_dataset(__file__,repository_root=ROOT,authorized=True,threshold=.68)

    def test_calibration_returns_only_aggregates_and_never_promotes(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"dataset.json"
            path.write_text(json.dumps({"schema_version":1,"authorization_reference":"SYNTHETIC",
                "samples":[{"label":"genuine","distance":.1},{"label":"impostor","distance":.9}]}),encoding="utf-8")
            report=aggregate_authorized_dataset(path,repository_root=ROOT,authorized=True,threshold=.68)
            self.assertFalse(report["automatic_promotion"])
            self.assertNotIn("samples",report); self.assertNotIn("authorization_reference",report)
            self.assertEqual(report["sample_size"],2)

    def test_observability_has_only_low_cardinality_dimensions(self):
        with self.assertLogs("frequenia.biometric_governance",logging.INFO) as logs:
            emit_biometric_event("verification",result="blocked",reason_code="policy_missing")
        event=logs.output[0]
        for forbidden in ("empresa_id","funcionario_id","biometria_id","session_id","embedding","cpf"):
            self.assertNotIn(forbidden,event)

    def test_readiness_payload_is_sanitized(self):
        source=inspect.getsource(routes.biometric_governance_readiness)
        self.assertNotIn("policy_id",source)
        self.assertNotIn('"empresa_id":',source)
        self.assertIn("dependencies",source)

    def test_facial_failure_workflow_is_not_a_retention_trigger(self):
        service=(ROOT/"services/biometric_governance.py").read_text(encoding="utf-8")
        self.assertNotIn("falha_facial",service)


if __name__ == "__main__":
    unittest.main(verbosity=2)
