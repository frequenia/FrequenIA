"""One-shot localhost form for saving the DuckDNS token without terminal echo."""

from __future__ import annotations

import html
import re
import secrets
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_PATH = PROJECT_ROOT / ".secrets" / "duckdns-token.txt"
TOKEN_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
NONCE = secrets.token_urlsafe(24)


class TokenHandler(BaseHTTPRequestHandler):
    server_version = "FrequenIALocalSecret/1"

    def log_message(self, _format: str, *_args: object) -> None:
        # Do not write request contents or paths to stdout/stderr.
        return

    def _send_html(self, status: int, body: str) -> None:
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Pragma", "no-cache")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if urlparse(self.path).path != f"/{NONCE}":
            self.send_error(404)
            return
        self._send_html(
            200,
            f"""<!doctype html>
<html lang="pt-BR"><meta charset="utf-8"><title>Salvar token DuckDNS</title>
<style>body{{font:16px system-ui;max-width:620px;margin:60px auto;padding:24px}}input,button{{font:inherit;padding:12px;width:100%;box-sizing:border-box;margin-top:12px}}small{{color:#555}}</style>
<h1>Salvar token do DuckDNS</h1>
<p>Cole o token novo abaixo. Ele será salvo somente neste computador.</p>
<form method="post" action="/{html.escape(NONCE)}" autocomplete="off">
<input type="password" name="token" required autofocus autocomplete="off" aria-label="Token novo do DuckDNS">
<button type="submit">Salvar token localmente</button>
</form>
<p><small>Endereço local 127.0.0.1. O valor não será exibido nem registrado.</small></p></html>""",
        )

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if urlparse(self.path).path != f"/{NONCE}":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > 1024:
            self._send_html(400, "<h1>Valor inválido</h1><p>Volte e tente novamente.</p>")
            return
        fields = parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True)
        token = fields.get("token", [""])[0].strip()
        if not TOKEN_PATTERN.fullmatch(token):
            self._send_html(400, "<h1>Formato inválido</h1><p>Volte e copie o token completo do DuckDNS.</p>")
            return
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(token, encoding="utf-8")
        token = ""
        self._send_html(200, "<h1>Token salvo com segurança</h1><p>Você pode fechar esta aba e voltar à conversa.</p>")
        threading.Thread(target=self.server.shutdown, daemon=True).start()


def main() -> None:
    server = HTTPServer(("127.0.0.1", 0), TokenHandler)
    host, port = server.server_address
    print(f"http://{host}:{port}/{NONCE}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
