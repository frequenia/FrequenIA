"""Validação unitária do comprovante privado da Fase 26."""

from io import BytesIO
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

from werkzeug.datastructures import FileStorage

from services.correction_attachments import (
    CorrectionAttachmentError,
    MAX_ATTACHMENT_BYTES,
    normalize_filename,
    validate_attachment,
)
from services.correction_attachment_storage import (
    AttachmentStorageError,
    AttachmentStorageNotConfigured,
    LocalPrivateAttachmentStorage,
    get_attachment_storage,
)


PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
JPEG = b"\xff\xd8\xff\xe0fixture\xff\xd9"
PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x00\x00\x00\x00IEND\xaeB\x60\x82"
)


def upload(name, content, mime):
    return FileStorage(stream=BytesIO(content), filename=name, content_type=mime)


class AttachmentValidationTests(unittest.TestCase):
    def test_pdf_jpeg_and_png_are_accepted_by_extension_mime_and_signature(self):
        for name, content, mime in (
            ("documento.pdf", PDF, "application/pdf"),
            ("foto.jpg", JPEG, "image/jpeg"),
            ("foto.jpeg", JPEG, "image/jpeg"),
            ("imagem.png", PNG, "image/png"),
        ):
            with self.subTest(name=name):
                result = validate_attachment(upload(name, content, mime))
                self.assertEqual(result["tipo_mime"], mime)
                self.assertEqual(result["tamanho_bytes"], len(content))
                self.assertEqual(len(result["sha256"]), 64)

    def test_empty_oversized_extension_mime_and_signature_are_rejected(self):
        invalid = (
            upload("vazio.pdf", b"", "application/pdf"),
            upload("grande.pdf", b"x" * (MAX_ATTACHMENT_BYTES + 1), "application/pdf"),
            upload("script.exe", PDF, "application/pdf"),
            upload("arquivo.pdf", PDF, "text/plain"),
            upload("arquivo.pdf", JPEG, "application/pdf"),
            upload("arquivo.png", PNG[:-4], "image/png"),
        )
        for file_storage in invalid:
            with self.subTest(name=file_storage.filename), self.assertRaises(
                CorrectionAttachmentError
            ):
                validate_attachment(file_storage)

    def test_filename_is_display_only_normalized_and_bounded(self):
        normalized = normalize_filename("..\\..\\pasta/\x00 comprovante   final.pdf")
        self.assertEqual(normalized, "comprovante final.pdf")
        self.assertLessEqual(len(normalize_filename("a" * 300 + ".pdf")), 200)


class PrivateStorageTests(unittest.TestCase):
    def test_key_is_server_generated_and_path_traversal_is_inert(self):
        with TemporaryDirectory() as directory:
            storage = LocalPrivateAttachmentStorage(directory)
            key = storage.generate_key("pdf", uuid4())
            self.assertRegex(key, r"^development/[0-9a-f-]{36}/quarantine/[0-9a-f-]{36}\.pdf$")
            storage.put(key, PDF)
            self.assertEqual(storage.read(key), PDF)
            self.assertTrue((Path(directory) / key).is_file())
            for malicious in ("../../fora.pdf", "/absoluto.pdf", "correcoes/../fora.pdf"):
                with self.subTest(key=malicious), self.assertRaises(AttachmentStorageError):
                    storage.put(malicious, PDF)

    def test_storage_must_be_explicitly_configured(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(
            AttachmentStorageNotConfigured
        ):
            get_attachment_storage()

    def test_public_static_directory_is_rejected(self):
        public = Path(__file__).resolve().parents[1] / "static" / "attachments"
        with self.assertRaises(AttachmentStorageNotConfigured):
            LocalPrivateAttachmentStorage(public)

    def test_delete_is_private_and_idempotent(self):
        with TemporaryDirectory() as directory:
            storage = LocalPrivateAttachmentStorage(directory)
            key = storage.generate_key("png", uuid4())
            storage.put(key, PNG)
            storage.delete(key)
            storage.delete(key)
            self.assertFalse((Path(directory) / key).exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
