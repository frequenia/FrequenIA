from io import BytesIO
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

from services.attachment_observability import LOGGER, emit
from services.attachment_scanner import ClamAVScanner, FakeScanner, ScannerError, get_attachment_scanner
from services.correction_attachment_storage import (
    AttachmentStorageError, AttachmentStorageNotConfigured,
    LocalPrivateAttachmentStorage, S3PrivateAttachmentStorage, get_attachment_storage,
)

CONTENT=b"%PDF-1.4\nfixture\n%%EOF\n"

class Body(BytesIO):
    pass

class FakeS3:
    def __init__(self): self.objects={}; self.calls=[]
    def put_object(self, **kwargs):
        self.calls.append(("put",kwargs)); self.objects[kwargs["Key"]]=(bytes(kwargs["Body"]),kwargs["Metadata"])
    def get_object(self, **kwargs):
        content,metadata=self.objects[kwargs["Key"]]
        return {"Body":Body(content),"ContentLength":len(content),"Metadata":metadata}
    def copy_object(self, **kwargs):
        self.calls.append(("copy",kwargs)); self.objects[kwargs["Key"]]=self.objects[kwargs["CopySource"]["Key"]]
    def delete_object(self, **kwargs): self.calls.append(("delete",kwargs)); self.objects.pop(kwargs["Key"],None)
    def list_objects_v2(self, **kwargs): self.calls.append(("list",kwargs)); return {"KeyCount":0}

class Phase27StorageSecurityTests(unittest.TestCase):
    def test_local_is_development_only(self):
        with TemporaryDirectory() as root, patch.dict(os.environ,{"APP_ENV":"test"}):
            storage=LocalPrivateAttachmentStorage(root); key=storage.generate_key("pdf",uuid4())
            storage.put(key,CONTENT); self.assertEqual(storage.read(key,len(CONTENT),__import__('hashlib').sha256(CONTENT).hexdigest()),CONTENT)
        with TemporaryDirectory() as root, patch.dict(os.environ,{"APP_ENV":"production"}):
            with self.assertRaises(AttachmentStorageNotConfigured): LocalPrivateAttachmentStorage(root)

    def test_s3_private_put_read_promote_delete_and_integrity(self):
        client=FakeS3()
        with patch.dict(os.environ,{"APP_ENV":"test"}):
            storage=S3PrivateAttachmentStorage("private","local","http://minio",client=client)
            key=storage.generate_key("pdf",uuid4()); digest=__import__('hashlib').sha256(CONTENT).hexdigest()
            storage.put(key,CONTENT,"application/pdf",digest)
            put=client.calls[0][1]; self.assertEqual(put["ServerSideEncryption"],"AES256"); self.assertNotIn("ACL",put)
            self.assertEqual(storage.read(key,len(CONTENT),digest),CONTENT)
            promoted=storage.promote(key); self.assertIn("/clean/",promoted); storage.delete(promoted); self.assertFalse(client.objects)
            self.assertTrue(storage.healthcheck())
            self.assertEqual(client.calls[-1][1]["Prefix"],"test/")
            self.assertEqual(client.calls[-1][1]["MaxKeys"],1)

    def test_s3_promotion_can_be_compensated_without_orphan(self):
        client=FakeS3()
        with patch.dict(os.environ,{"APP_ENV":"test"}):
            storage=S3PrivateAttachmentStorage("private","local","http://s3",client=client)
            original=storage.generate_key("pdf",uuid4()); storage.put(original,CONTENT)
            promoted=storage.promote(original); storage.restore_promotion(promoted,original)
        self.assertIn(original,client.objects); self.assertNotIn(promoted,client.objects)

    def test_s3_read_fails_closed_on_size_or_checksum(self):
        client=FakeS3(); storage=S3PrivateAttachmentStorage("private","local",client=client)
        key=storage.generate_key("pdf",uuid4()); storage.put(key,CONTENT)
        client.objects[key]=(CONTENT,{"length":str(len(CONTENT)),"sha256":"0"*64})
        with self.assertRaises(AttachmentStorageError): storage.read(key,len(CONTENT),"0"*64)

    def test_server_configuration_rejects_missing_invalid_and_production_local(self):
        for env in (
            {"APP_ENV":"production","ATTACHMENT_STORAGE_PROVIDER":"local","ATTACHMENT_STORAGE_ROOT":"x"},
            {"APP_ENV":"test","ATTACHMENT_STORAGE_PROVIDER":"unknown"},
            {"APP_ENV":"test","ATTACHMENT_STORAGE_PROVIDER":"s3","ATTACHMENT_S3_BUCKET":"","ATTACHMENT_S3_REGION":""},
        ):
            with self.subTest(env=env), patch.dict(os.environ,env,clear=True), self.assertRaises(AttachmentStorageNotConfigured): get_attachment_storage()

    def test_key_is_opaque_and_contains_no_identity(self):
        with TemporaryDirectory() as root, patch.dict(os.environ,{"APP_ENV":"test"}):
            key=LocalPrivateAttachmentStorage(root).generate_key("png",uuid4())
        for forbidden in ("cpf","nome","matricula","@","\\",".."):
            self.assertNotIn(forbidden,key.lower())

    def test_clamav_protocol_is_fail_closed(self):
        class Connection:
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def settimeout(self,value): pass
            def sendall(self,value): pass
            def recv(self,size): return b"stream: Eicar-Test-Signature FOUND\0"
        with patch("socket.create_connection",return_value=Connection()):
            self.assertEqual(ClamAVScanner("clamav").scan(CONTENT).status,"infectado")
        with patch("socket.create_connection",side_effect=TimeoutError):
            with self.assertRaises(ScannerError): ClamAVScanner("clamav").scan(CONTENT)

    def test_fake_scanner_cannot_be_enabled_outside_tests(self):
        with patch.dict(os.environ,{"APP_ENV":"production","ATTACHMENT_SCANNER_PROVIDER":"fake-clean"},clear=True):
            with self.assertRaises(ScannerError): get_attachment_scanner()
        self.assertEqual(FakeScanner("limpo").scan(CONTENT).status,"limpo")

    def test_observability_drops_forbidden_fields(self):
        stream=__import__('io').StringIO(); handler=logging.StreamHandler(stream); LOGGER.addHandler(handler); LOGGER.setLevel(logging.INFO)
        try: emit("upload",attachment_id="opaque",cpf="forbidden",key="secret",reason="accepted")
        finally: LOGGER.removeHandler(handler)
        payload=json.loads(stream.getvalue()); self.assertEqual(payload["attachment_id"],"opaque"); self.assertNotIn("cpf",payload); self.assertNotIn("key",payload)

    def test_cloudformation_is_private_encrypted_tls_and_prefix_scoped(self):
        source=(Path(__file__).resolve().parents[1]/"infra/aws/attachments.template.yaml").read_text(encoding="utf-8")
        for required in ("BlockPublicAcls: true","BlockPublicPolicy: true","IgnorePublicAcls: true","RestrictPublicBuckets: true","BucketEncryption:","aws:SecureTransport: false","s3:GetObject","/${Environment}/*"):
            self.assertIn(required,source)
        self.assertNotIn("WebsiteConfiguration",source)
        self.assertIn("s3:ListBucket",source); self.assertIn("s3:prefix:",source)

    def test_liveness_is_local_and_readiness_fails_closed(self):
        environment=os.environ.copy()
        environment.update({"APP_ENV":"production","FLASK_SECRET_KEY":"x"*32,"JWT_SECRET_KEY":"j"*32})
        for name in ("ATTACHMENT_STORAGE_PROVIDER","ATTACHMENT_STORAGE_ROOT","ATTACHMENT_S3_BUCKET","ATTACHMENT_S3_REGION","CLAMAV_HOST","PASSWORD_RESET_TEST_KEY"):
            environment.pop(name,None)
        script=("import dotenv; dotenv.load_dotenv=lambda *a,**k:None; import app; "
                "c=app.app.test_client(); print(c.get('/health').status_code,c.get('/ready').status_code)")
        result=subprocess.run([sys.executable,"-c",script],cwd=Path(__file__).resolve().parents[1],env=environment,capture_output=True,text=True,timeout=60,check=False)
        self.assertEqual(result.returncode,0,result.stderr); self.assertEqual(result.stdout.strip(),"200 503")

if __name__=="__main__": unittest.main()
