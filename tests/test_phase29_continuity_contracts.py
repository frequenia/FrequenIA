from datetime import datetime,timezone,timedelta
import json,os,tempfile,unittest
import time
from pathlib import Path
from unittest.mock import patch

from services.backup_manifest import ManifestError,load_and_verify_manifest
from services.capacity_exercise import CapacityExerciseError,run_capacity_exercise
from services.chaos_harness import ChaosDisabled,ChaosHarness,ControlledClock,InjectedFault
from services.continuity_backup import ContinuityBackupError,prepare_backup_set,restore_backup_set
from services.continuity_policy import ContinuityPolicyError,load_continuity_policy
from services.continuity_postgres import PostgresContinuityError,export_custom,parse_disposable_database,restore_custom

ROOT=Path(__file__).resolve().parents[1]

class Phase29ContinuityContractTests(unittest.TestCase):
    def test_policy_is_validated_and_production_values_remain_pending(self):
        with patch.dict(os.environ,{"APP_ENV":"development"},clear=False):
            policy=load_continuity_policy(); self.assertEqual(policy.production_status,"aprovacao_corporativa_pendente")
        with patch.dict(os.environ,{"CONTINUITY_RPO_SECONDS":"0"},clear=False):
            with self.assertRaises(ContinuityPolicyError): load_continuity_policy()
        with patch.dict(os.environ,{"APP_ENV":"production","CONTINUITY_PRODUCTION_APPROVED":"true","CONTINUITY_APPROVAL_REFERENCE":""},clear=False):
            with self.assertRaises(ContinuityPolicyError): load_continuity_policy()

    def _bundle(self):
        source=tempfile.TemporaryDirectory(); destination=tempfile.TemporaryDirectory(); restore=tempfile.TemporaryDirectory()
        Path(destination.name).rmdir(); Path(restore.name).rmdir()
        artifact=Path(source.name)/"synthetic.bin"; artifact.write_bytes(b"synthetic-phase29")
        with patch.dict(os.environ,{"APP_ENV":"test"},clear=False):
            result=prepare_backup_set(destination.name,[{"source":artifact,"component":"postgresql"}],list(range(1,25)),"test",True)
        return source,destination,restore,result

    def test_manifest_is_versioned_opaque_sanitized_and_verified(self):
        resources=self._bundle()
        try:
            manifest=load_and_verify_manifest(resources[1].name)
            self.assertEqual(manifest["schema_version"],1); self.assertTrue(resources[3]["verified"])
            serialized=json.dumps(manifest).lower()
            for forbidden in ("cpf","email","password","secret","signed_url","chave_objeto","synthetic-phase29"):
                self.assertNotIn(forbidden,serialized)
        finally:
            for resource in resources[:3]: resource.cleanup()

    def test_manifest_tampering_unknown_version_and_partial_set_fail_closed(self):
        resources=self._bundle(); manifest_path=Path(resources[1].name)/"manifest.json"
        try:
            envelope=json.loads(manifest_path.read_text(encoding="utf-8")); envelope["manifest"]["schema_version"]=2
            manifest_path.write_text(json.dumps(envelope),encoding="utf-8")
            with self.assertRaises(ManifestError): load_and_verify_manifest(resources[1].name)
        finally:
            for resource in resources[:3]: resource.cleanup()
        resources=self._bundle()
        try:
            (Path(resources[1].name)/"artifact-0001.bin").unlink()
            with self.assertRaises(ManifestError): load_and_verify_manifest(resources[1].name)
        finally:
            for resource in resources[:3]: resource.cleanup()

    def test_backup_and_restore_are_dry_run_explicit_isolated_and_resumable(self):
        source=tempfile.TemporaryDirectory(); destination=tempfile.TemporaryDirectory(); restored=tempfile.TemporaryDirectory()
        try:
            Path(destination.name).rmdir(); Path(restored.name).rmdir(); artifact=Path(source.name)/"db.dump"; artifact.write_bytes(b"db")
            plan=prepare_backup_set(destination.name,[{"source":artifact,"component":"postgresql"}],[],"test",False)
            self.assertTrue(plan["dry_run"]); self.assertFalse(Path(destination.name).exists())
            prepare_backup_set(destination.name,[{"source":artifact,"component":"postgresql"}],[],"test",True)
            self.assertTrue(restore_backup_set(destination.name,restored.name,"test",False)["dry_run"])
            with self.assertRaises(ContinuityBackupError): restore_backup_set(destination.name,restored.name,"test",True,interrupt_after=1)
            resumed=restore_backup_set(destination.name,restored.name,"test",True,allow_nonempty=True)
            self.assertTrue(resumed["resumed"]); self.assertTrue(resumed["verified"])
            self.assertEqual((Path(restored.name)/"artifact-0001.bin").read_bytes(),b"db")
            load_and_verify_manifest(restored.name)
            with self.assertRaises(ContinuityBackupError): restore_backup_set(destination.name,destination.name,"test",False)
            with self.assertRaises(ContinuityBackupError): prepare_backup_set(restored.name,[],[],"test",False)
            with self.assertRaises(ContinuityBackupError): prepare_backup_set(destination.name,[],[],"production",False)
        finally:
            source.cleanup(); destination.cleanup(); restored.cleanup()

    def test_chaos_requires_explicit_test_token_and_clock_is_deterministic(self):
        with patch.dict(os.environ,{"APP_ENV":"production","FREQUENIA_CHAOS_TEST_TOKEN":"phase29-test-only"},clear=False):
            with self.assertRaises(ChaosDisabled): ChaosHarness("db_before_commit")
        clock=ControlledClock(100)
        with patch.dict(os.environ,{"APP_ENV":"test","FREQUENIA_CHAOS_TEST_TOKEN":"phase29-test-only"},clear=False):
            harness=ChaosHarness("scanner_timeout")
            with self.assertRaises(InjectedFault): harness.checkpoint("scanner_timeout")
        clock.advance(30); self.assertEqual(clock(),130); self.assertTrue(harness.triggered)

    def test_capacity_is_bounded_percentile_based_and_not_a_production_slo(self):
        clock=ControlledClock();
        def process(_): clock.advance(.001)
        with patch.dict(os.environ,{"APP_ENV":"test"},clear=False):
            result=run_capacity_exercise(100,4,clock,process)
            self.assertEqual(result["backlog_drained"],100); self.assertGreaterEqual(result["p99_ms"],result["p95_ms"])
            self.assertEqual(result["evidence"],"local_synthetic_not_production_slo")
            with self.assertRaises(CapacityExerciseError): run_capacity_exercise(10001,1)
            single=run_capacity_exercise(20,1,processor=lambda _:time.sleep(.003))
            multiple=run_capacity_exercise(20,4,processor=lambda _:time.sleep(.003))
            self.assertGreater(multiple["throughput_per_second"],single["throughput_per_second"])
            self.assertIn("wait_p99_ms",multiple)

    def test_postgres_commands_are_argument_safe_and_credentials_are_environment_only(self):
        calls=[]
        class Result:returncode=0
        def runner(args,**kwargs):
            calls.append((args,kwargs)); Path(args[args.index("--file")+1]).write_bytes(b"PGDMP-synthetic") if "--file" in args else None
            return Result()
        with tempfile.TemporaryDirectory() as directory:
            dump=Path(directory)/"database.dump"
            url="postgresql://runner:ephemeral@127.0.0.1:55437/frequenia_phase29_test"
            export_custom(url,dump,runner); restore_custom(url,dump,runner)
        rendered=json.dumps(calls,default=str)
        self.assertNotIn("ephemeral",json.dumps([item[0] for item in calls]))
        self.assertEqual(calls[0][1]["env"]["PGPASSWORD"],"ephemeral")
        self.assertNotIn("shell",calls[0][1]); self.assertNotIn(url,rendered)
        with self.assertRaises(PostgresContinuityError): parse_disposable_database("postgresql://x:y@example.com/production")

    def test_cloudformation_guard_iam_alarms_and_ci_contract(self):
        template=(ROOT/"infra/aws/attachments.template.yaml").read_text(encoding="utf-8")
        guard=(ROOT/"infra/aws/attachments.guard").read_text(encoding="utf-8")
        workflow=(ROOT/".github/workflows/phase26-quality.yml").read_text(encoding="utf-8")
        for expected in ("AttachmentBackupPolicy","AttachmentRestorePolicy","AttachmentPurgeTaggingPolicy","AttachmentEvidencePolicy","BackupAgeAlarm","RestoreDurationP99Alarm","ExtendedStatistic: p99","TreatMissingData: breaching","TreatMissingData: notBreaching"):
            self.assertIn(expected,template)
        for expected in ("PublicAccessBlockConfiguration","aws:SecureTransport","BucketEncryption","DeletionPolicy","RedrivePolicy","SqsManagedSseEnabled"):
            self.assertIn(expected,guard)
        self.assertIn("test_phase29_postgres_integration.py",workflow)
        self.assertNotIn("secrets.",workflow.lower())

    def test_policy_documentation_distinguishes_continuity_terms(self):
        text=(ROOT/"docs/FASE_29_CONTINUIDADE_CAOS_BACKUP.md").read_text(encoding="utf-8").lower()
        for term in ("backup operacional","snapshot","restauração","exercício de continuidade","disaster recovery","alta disponibilidade","retenção","versionamento"):
            self.assertIn(term,text)
        self.assertIn("aprovação corporativa pendente",text)

if __name__=="__main__": unittest.main()
