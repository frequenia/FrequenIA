import json
import logging
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

from services.attachment_observability import metric
from services.attachment_outbox import OutboxDispatchError, asynchronous_scan_enabled
from services.attachment_queue import (
    InMemoryAttachmentQueue,
    InvalidScanMessage,
    SQSAttachmentQueue,
    build_scan_payload,
    get_attachment_queue,
    parse_scan_payload,
)
from services.attachment_scanner import ClamAVScanner, ScannerError


ROOT=Path(__file__).resolve().parents[1]


class _Socket:
    def __init__(self,response): self.response=response; self.sent=[]
    def __enter__(self): return self
    def __exit__(self,*_): return False
    def settimeout(self,_): pass
    def sendall(self,value): self.sent.append(value)
    def recv(self,_): return self.response


class Phase28AsyncContractTests(unittest.TestCase):
    def setUp(self):
        self.job,self.attachment,self.company=uuid4(),uuid4(),uuid4()

    def test_payload_contains_only_opaque_ids_and_version(self):
        body=build_scan_payload(self.job,self.attachment,self.company)
        self.assertEqual(set(json.loads(body)),{"v","job_id","attachment_id","company_id"})
        for forbidden in ("name","cpf","mime","sha256","bucket","key","path"):
            self.assertNotIn(forbidden,body.lower())

    def test_unknown_schema_or_extra_field_is_rejected(self):
        for value in ({"v":2,"job_id":str(self.job),"attachment_id":str(self.attachment),"company_id":str(self.company)},
                      {"v":1,"job_id":str(self.job),"attachment_id":str(self.attachment),"company_id":str(self.company),"key":"x"}):
            with self.assertRaises(InvalidScanMessage): parse_scan_payload(json.dumps(value))

    def test_memory_queue_models_visibility_duplicate_and_dlq(self):
        now=[0.0]; queue=InMemoryAttachmentQueue(visibility_timeout=5,max_receive_count=2,clock=lambda:now[0])
        queue.send(build_scan_payload(self.job,self.attachment,self.company))
        first=queue.receive()[0]; self.assertEqual(queue.receive(),[])
        now[0]=6; second=queue.receive()[0]; self.assertEqual(second.message_id,first.message_id)
        now[0]=12; self.assertEqual(queue.receive(),[]); self.assertEqual(len(queue.dlq),1)

    def test_memory_and_sync_modes_are_rejected_outside_tests(self):
        with patch.dict(os.environ,{"APP_ENV":"production","ATTACHMENT_QUEUE_PROVIDER":"memory"},clear=False):
            with self.assertRaises(Exception): get_attachment_queue()
        with patch.dict(os.environ,{"APP_ENV":"production","ATTACHMENT_SCAN_MODE":"sync"},clear=False):
            with self.assertRaises(OutboxDispatchError): asynchronous_scan_enabled()

    def test_sqs_adapter_uses_limited_batch_long_poll_and_receipt(self):
        class Client:
            def receive_message(inner,**kwargs):
                inner.kwargs=kwargs
                return {"Messages":[{"Body":build_scan_payload(self.job,self.attachment,self.company),"ReceiptHandle":"r","MessageId":"m","Attributes":{"ApproximateReceiveCount":"2"}}]}
        client=Client(); queue=SQSAttachmentQueue("https://queue.local/q",client=client)
        message=queue.receive(99,99)[0]
        self.assertEqual((client.kwargs["MaxNumberOfMessages"],client.kwargs["WaitTimeSeconds"],message.receive_count),(10,20,2))

    def test_clamav_signature_current_stale_missing_and_invalid(self):
        scanner=ClamAVScanner("clamav",timeout=1)
        current=_Socket(b"ClamAV 1.4.3/27834/Thu, 15 Oct 2026 12:00:00 +0000\0")
        with patch("socket.create_connection",return_value=current), patch("services.attachment_scanner.datetime") as mocked:
            from datetime import datetime,timezone
            mocked.now.return_value=datetime(2026,10,15,13,0,tzinfo=timezone.utc)
            self.assertLess(scanner.signature_info().age_hours,2)
        stale=_Socket(b"ClamAV 1.4.3/20000/Thu, 01 Jan 2026 00:00:00 +0000\0")
        with patch("socket.create_connection",return_value=stale), patch.dict(os.environ,{"CLAMAV_SIGNATURE_MAX_AGE_HOURS":"1"}):
            self.assertFalse(scanner.signatures_current())
        for response in (b"",b"unexpected\0"):
            with patch("socket.create_connection",return_value=_Socket(response)):
                with self.assertRaises(ScannerError): scanner.signature_info()

    def test_emf_dimensions_are_low_cardinality(self):
        with self.assertLogs("frequenia.attachments",logging.INFO) as captured:
            metric("ScanDuration",12,unit="Milliseconds",process="worker",result="clean",attachment_id="forbidden",company_id="forbidden")
        payload=json.loads(captured.output[-1].split("INFO:frequenia.attachments:",1)[-1])
        dimensions=payload["_aws"]["CloudWatchMetrics"][0]["Dimensions"][0]
        self.assertEqual(dimensions,["process","result"])
        self.assertNotIn("attachment_id",payload); self.assertNotIn("company_id",payload)

    def test_cloudformation_declares_private_encrypted_queues_alarms_and_p99(self):
        template=(ROOT/"infra/aws/attachments.template.yaml").read_text(encoding="utf-8")
        for expected in ("AWS::SQS::Queue","RedrivePolicy","SqsManagedSseEnabled: true","ReceiveMessageWaitTimeSeconds: 20","TreatMissingData","DatapointsToAlarm","ExtendedStatistic: p99","WorkerHeartbeatAlarm","DlqMessagesAlarm"):
            self.assertIn(expected,template)
        self.assertNotIn("AWS::SNS::Subscription",template)
        self.assertNotIn("Action: '*'",template)
        self.assertNotIn("Resource: '*'",template)

    def test_lifecycle_is_only_abort_and_tagged_safety_net(self):
        template=(ROOT/"infra/aws/attachments.template.yaml").read_text(encoding="utf-8")
        self.assertIn("AbortIncompleteMultipartUpload",template)
        self.assertIn("frequenia-purge-eligible",template)
        self.assertIn("PurgeSafetyMarginDays",template)
        self.assertNotIn("VersioningConfiguration",template)

    def test_worker_is_separate_and_web_has_no_consumer_thread(self):
        app=(ROOT/"app.py").read_text(encoding="utf-8")
        worker=(ROOT/"services/attachment_worker.py").read_text(encoding="utf-8")
        self.assertNotIn("run_worker(",app)
        self.assertIn("connection.commit()",worker)
        self.assertIn("if result.acknowledge:\n                queue.delete",worker)

    def test_reconciliation_is_dry_run_and_repair_is_explicit(self):
        tool=(ROOT/"tools/reconcile_correction_attachments.py").read_text(encoding="utf-8")
        service=(ROOT/"services/attachment_reconciliation.py").read_text(encoding="utf-8")
        self.assertIn('action="store_true"',tool)
        self.assertIn("Reparo exige --execute",service)
        self.assertIn("get_paginator",(ROOT/"services/correction_attachment_storage.py").read_text(encoding="utf-8"))

    def test_runbooks_cover_eight_incident_classes(self):
        text=(ROOT/"docs/runbooks/FASE_28_OPERACAO_ANEXOS.md").read_text(encoding="utf-8")
        for title in ("Backlog","DLQ","Scanner","Assinaturas","Storage","Malware","Reconciliação","Continuidade"):
            self.assertIn(title,text)
        for section in ("Sintomas","Métricas","Diagnóstico","Contenção","Recuperação","Validação","Evidências"):
            self.assertGreaterEqual(text.count(section),8)


if __name__=="__main__": unittest.main()
