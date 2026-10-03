import requests
from flask import current_app


class EmailDeliveryError(RuntimeError):
    """Raised when an application e-mail cannot be delivered."""


EMAILJS_SEND_URL = "https://api.emailjs.com/api/v1.0/email/send"


def _emailjs_config():
    config = {
        "service_id": str(current_app.config.get("EMAILJS_SERVICE_ID") or "").strip(),
        "template_id": str(current_app.config.get("EMAILJS_TEMPLATE_ID") or "").strip(),
        "public_key": str(current_app.config.get("EMAILJS_PUBLIC_KEY") or "").strip(),
        "private_key": str(current_app.config.get("EMAILJS_PRIVATE_KEY") or ""),
        "timeout": int(current_app.config["EMAILJS_TIMEOUT_SECONDS"]),
    }
    if not all(
        config[key] for key in ("service_id", "template_id", "public_key")
    ):
        raise EmailDeliveryError("EmailJS não configurado.")
    return config


def send_password_reset_email(recipient, token, expires_in_minutes):
    config = _emailjs_config()
    payload = {
        "service_id": config["service_id"],
        "template_id": config["template_id"],
        "user_id": config["public_key"],
        "template_params": {
            "to_email": recipient,
            "token": token,
            "expires_in_minutes": expires_in_minutes,
            # Aliases kept for the existing FrequenIA template.
            "email": recipient,
            "passcode": token,
        },
    }
    if config["private_key"]:
        payload["accessToken"] = config["private_key"]

    try:
        response = requests.post(
            EMAILJS_SEND_URL,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (compatible; FrequenIA/1.0)",
            },
            timeout=config["timeout"],
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise EmailDeliveryError("Falha ao enviar o e-mail de recuperação.") from exc
