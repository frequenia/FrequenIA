from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Phase26InterfaceContractTests(unittest.TestCase):
    def test_personal_web_views_offer_optional_private_attachment(self):
        for relative in (
            "templates/minhasSolicitacoes.html",
            "templates/autoatendimento.html",
        ):
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn('type="file"', source)
            self.assertIn("application/pdf,image/jpeg,image/png", source)
            self.assertIn("10 MiB", source)

    def test_personal_web_supports_create_replace_remove_and_safe_download(self):
        for relative in (
            "static/js/minhasSolicitacoes.js",
            "static/js/autoatendimento.js",
        ):
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn('method:"PUT"', source)
            self.assertIn('method:"DELETE"', source)
            self.assertIn("/comprovante/download", source)
            self.assertIn("FormData", source)

    def test_admin_web_only_links_to_download_and_does_not_embed_file(self):
        template = (ROOT / "templates/ocorrencias.html").read_text(encoding="utf-8")
        script = (ROOT / "static/js/ocorrencias.js").read_text(encoding="utf-8")
        self.assertIn("attachment-detail", template)
        self.assertIn("/api/gestao/ocorrencias/", script)
        self.assertIn("/comprovante/download", script)
        self.assertNotIn("createElement(\"iframe\")", script)
        self.assertNotIn("createElement(\"img\")", script)
        self.assertIn("retry-scan", script)
        self.assertIn("Repetir análise de segurança", template)

    def test_flutter_shows_all_workflow_states_and_attachment_controls(self):
        requests = (ROOT / "mobile/lib/requests/requests_page.dart").read_text(
            encoding="utf-8"
        )
        widgets = (ROOT / "mobile/lib/core/widgets.dart").read_text(encoding="utf-8")
        combined = requests + widgets
        for label in (
            "Pendente com gestor",
            "Encaminhada ao RH",
            "Aprovada",
            "Rejeitada",
            "Cancelada",
        ):
            self.assertIn(label, combined)
        for label in (
            "Adicionar comprovante",
            "Substituir comprovante",
            "Remover comprovante",
            "PDF, JPEG ou PNG, com no máximo 10 MiB.",
            "Analisando",
            "Disponível",
            "Bloqueado",
            "Falha temporária",
        ):
            self.assertIn(label, requests)


if __name__ == "__main__":
    unittest.main()
