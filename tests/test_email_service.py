import unittest
from unittest.mock import MagicMock, patch

import requests
from flask import Flask

from services.email_service import EmailDeliveryError, send_password_reset_email


class EmailServiceTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(
            EMAILJS_SERVICE_ID="service-test",
            EMAILJS_TEMPLATE_ID="template-test",
            EMAILJS_PUBLIC_KEY="public-key",
            EMAILJS_PRIVATE_KEY="",
            EMAILJS_TIMEOUT_SECONDS=10,
        )

    @patch("services.email_service.requests.post")
    def test_sends_existing_emailjs_template_without_exposing_token(self, post):
        post.return_value = MagicMock()
        with self.app.app_context():
            send_password_reset_email("pessoa@example.com", "token-seguro", 30)

        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["service_id"], "service-test")
        self.assertEqual(payload["template_id"], "template-test")
        self.assertEqual(payload["template_params"]["to_email"], "pessoa@example.com")
        self.assertEqual(payload["template_params"]["token"], "token-seguro")
        self.assertEqual(payload["template_params"]["email"], "pessoa@example.com")
        self.assertEqual(payload["template_params"]["passcode"], "token-seguro")
        self.assertNotIn("accessToken", payload)
        self.assertTrue(post.call_args.kwargs["headers"]["User-Agent"].startswith("Mozilla/5.0"))
        post.return_value.raise_for_status.assert_called_once_with()

    @patch("services.email_service.requests.post")
    def test_wraps_emailjs_delivery_failure(self, post):
        post.side_effect = requests.Timeout("timeout")
        with self.app.app_context(), self.assertRaises(EmailDeliveryError):
            send_password_reset_email("pessoa@example.com", "token", 30)

    def test_rejects_missing_emailjs_configuration(self):
        self.app.config["EMAILJS_PUBLIC_KEY"] = ""
        with self.app.app_context(), self.assertRaises(EmailDeliveryError):
            send_password_reset_email("pessoa@example.com", "token", 30)


if __name__ == "__main__":
    unittest.main()
