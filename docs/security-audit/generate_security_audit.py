"""Gera o relatorio de auditoria de seguranca do FrequenIA em PDF.

Uso:
    python docs/security-audit/generate_security_audit.py
"""

from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path
import textwrap

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.legends import Legend
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    XPreformatted,
)
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "docs" / "security-audit" / "relatorio-auditoria-seguranca.pdf"

CRITICAL = HexColor("#B91C1C")
HIGH = HexColor("#EA580C")
MEDIUM = HexColor("#D97706")
LOW = HexColor("#2563EB")
STRONG = HexColor("#059669")
INK = HexColor("#172033")
MUTED = HexColor("#5D6678")
PALE = HexColor("#F3F5F8")
LINE = HexColor("#D8DDE7")
NAVY = HexColor("#10233F")


FINDINGS = [
    {
        "id": "F-01",
        "severity": "Crítica",
        "color": CRITICAL,
        "category": "Inputs sem tratamento",
        "location": "routes/face.py:43, 64-74, 170-185",
        "title": "Travessia de diretório permite exclusão recursiva sem autenticação",
        "description": (
            "O valor nome vem do JSON, é concatenado diretamente a temp_cadastros e o caminho "
            "resultante é entregue a shutil.rmtree. A rota /iniciar_cadastro não possui guarda de "
            "autenticação. Um nome como ../static sai da pasta temporária e pode apagar recursivamente "
            "um diretório acessível ao processo. A exploração exige apenas que o alvo exista e que o "
            "processo tenha permissão de escrita."
        ),
        "snippet": (
            'PASTA_TEMP = "temp_cadastros"\n'
            "def pasta_usuario(nome):\n"
            "    return os.path.join(PASTA_TEMP, str(nome))\n"
            "def limpar_pasta(caminho):\n"
            "    if os.path.exists(caminho):\n"
            "        shutil.rmtree(caminho, ignore_errors=True)\n"
            "# /iniciar_cadastro: nome -> pasta_usuario -> limpar_pasta"
        ),
        "recommendation": (
            "Desativar as rotas legadas. Se forem mantidas, usar identificador UUID derivado da sessão, "
            "resolver o caminho e exigir que ele permaneça sob uma raiz dedicada; nunca aceitar segmentos "
            "de caminho do cliente."
        ),
    },
    {
        "id": "F-02",
        "severity": "Alta",
        "color": HIGH,
        "category": "Permissão no navegador",
        "location": "app.py:114-120; routes/face.py:170-200, 256-257",
        "title": "Rotas legadas de cadastro facial estão registradas sem autorização",
        "description": (
            "O blueprint face é registrado no Flask, mas /iniciar_cadastro, /adicionar_foto e "
            "/finalizar_cadastro não usam require_roles nem access_token_required. A implementação "
            "moderna protege o cadastro facial como administrador, porém um cliente pode chamar as "
            "rotas legadas diretamente. Início e upload temporário são exploráveis sempre; a finalização "
            "também requer a tabela legada fotos e credenciais Cloudinary operacionais."
        ),
        "snippet": (
            "app.register_blueprint(face_bp)\n"
            '@face_bp.route("/iniciar_cadastro", methods=["POST"])\n'
            "def iniciar_cadastro(): ...\n"
            '@face_bp.route("/adicionar_foto", methods=["POST"])\n'
            "def adicionar_foto(): ...\n"
            '@face_bp.route("/finalizar_cadastro", methods=["POST"])\n'
            "def finalizar_cadastro(): ..."
        ),
        "recommendation": (
            "Remover o registro das rotas legadas ou responder 410. Se houver migração temporária, aplicar "
            "require_roles('administrador'), identidade por funcionario_id, limites de upload e o mesmo "
            "serviço 1:1 usado por routes/biometrics.py."
        ),
    },
    {
        "id": "F-03",
        "severity": "Alta",
        "color": HIGH,
        "category": "Banco sem tranca",
        "location": "routes/face.py:118-125, 396-421, 455-481",
        "title": "Reconhecimento facial legado faz busca global sem tenant",
        "description": (
            "O isolamento do projeto é manual: as queries modernas recebem empresa_id de g.auth_context. "
            "A query legada seleciona toda a tabela fotos, sem empresa_id, funcionario_id ou sessão, e a "
            "rota /reconhecer é pública. Com a tabela legada populada, uma imagem pode ser comparada contra "
            "pessoas de todas as empresas e a resposta revela nome e usuario_id."
        ),
        "snippet": (
            "SELECT nome, embedding <=> %s::vector AS distancia\n"
            "FROM fotos\n"
            "ORDER BY distancia\n"
            "LIMIT 5\n"
            "# resposta inclui nome e usuario_id"
        ),
        "recommendation": (
            "Eliminar a identificação global e usar apenas verificação 1:1 do vínculo autenticado. Remover "
            "a tabela/rota legada e manter empresa_id + funcionario_id em todas as consultas biométricas."
        ),
    },
    {
        "id": "F-04",
        "severity": "Alta",
        "color": HIGH,
        "category": "IDOR",
        "location": "routes/face.py:173-185, 261-288, 333-345, 455-459",
        "title": "Nome controlado pelo cliente referencia e envenena identidade biométrica",
        "description": (
            "O fluxo legado trata nome como identificador direto do objeto. Não há vínculo com o usuário, "
            "funcionário ou empresa autenticados. Um chamador pode escolher o nome de outra pessoa, limpar "
            "seu staging, enviar imagens e, se o fluxo legado estiver operacional e houver menos de cinco "
            "registros, acrescentar embeddings associados ao mesmo nome. O reconhecimento ainda associa "
            "usuarios e fotos por igualdade de nome, ampliando colisões e envenenamento."
        ),
        "snippet": (
            "nome = dados.get(\"nome\")\n"
            "pasta = pasta_usuario(nome)\n"
            "SELECT COUNT(*) FROM fotos WHERE nome = %s\n"
            "INSERT INTO fotos (nome, url, embedding) VALUES (%s, %s, %s)\n"
            "INNER JOIN fotos f ON u.nome = f.nome"
        ),
        "recommendation": (
            "Não aceitar nome como autoridade. Receber funcionario_id apenas em rota administrativa, validar "
            "a posse no tenant e persistir por chave composta empresa_id/funcionario_id. Tornar o recadastro "
            "transacional e revogar o template anterior."
        ),
    },
    {
        "id": "F-05",
        "severity": "Alta",
        "color": HIGH,
        "category": "Chaves expostas",
        "location": "app.py:9 no commit 8e0f6e89 (presente em e68467d8)",
        "title": "Segredo Flask foi commitado no histórico Git",
        "description": (
            "O histórico contém app.secret_key com valor literal de 23 caracteres. Embora a versão atual "
            "exija FLASK_SECRET_KEY no ambiente, remover o valor do HEAD não o remove dos commits. Se esse "
            "segredo foi usado ou reutilizado, qualquer pessoa com acesso ao repositório pode forjar cookies "
            "de sessão Flask; o backend aceita sessão como fallback em require_roles. O valor foi redigido "
            "neste relatório (SHA-256 prefixo 95B8D34B4DC6)."
        ),
        "snippet": 'app.secret_key = "[SEGREDO REDIGIDO; 23 caracteres]"',
        "recommendation": (
            "Rotacionar FLASK_SECRET_KEY em todos os ambientes, invalidar sessões, verificar reutilização e "
            "reescrever o histórico se a política do repositório permitir. Adicionar secret scanning em CI "
            "e proteção pre-commit."
        ),
    },
]


ISSUES = [
    {
        "n": 1,
        "title": "[Segurança] Bloquear travessia de diretório no cadastro facial legado",
        "labels": "security, severidade:critica",
        "finding": FINDINGS[0],
        "impact": "Exclusão recursiva de diretórios graváveis pelo processo, indisponibilidade e perda de arquivos da aplicação.",
        "acceptance": [
            "As rotas legadas foram removidas/desativadas ou exigem autenticação e autorização explícitas.",
            "Nenhum valor do cliente participa de um caminho de arquivo sem normalização e allowlist.",
            "O caminho resolvido é rejeitado quando não está contido na raiz temporária dedicada.",
            "Teste automatizado cobre ../, ..\\ e caminhos absolutos sem tocar arquivos fora da raiz.",
        ],
    },
    {
        "n": 2,
        "title": "[Segurança] Remover ou proteger endpoints legados de cadastro facial",
        "labels": "security, severidade:alta",
        "finding": FINDINGS[1],
        "impact": "Uso não autorizado de CPU, disco e Cloudinary, além de alteração indevida de dados biométricos legados.",
        "acceptance": [
            "/iniciar_cadastro, /adicionar_foto e /finalizar_cadastro retornam 404/410 ou exigem administrador autenticado.",
            "O backend deriva empresa e ator da sessão, sem confiar em identidade enviada pelo navegador.",
            "Há testes negativos para anônimo, funcionário, gestor e tenant diferente.",
            "O blueprint legado não expõe rota mutável sem uma guarda equivalente no servidor.",
        ],
    },
    {
        "n": 3,
        "title": "[Segurança] Eliminar busca facial global sem isolamento por tenant",
        "labels": "security, severidade:alta",
        "finding": FINDINGS[2],
        "impact": "Vazamento de identidade entre empresas e comparação biométrica global fora do vínculo autenticado.",
        "acceptance": [
            "Nenhuma query facial percorre pessoas fora do empresa_id autenticado.",
            "O fluxo de produção usa verificação 1:1 por funcionario_id da sessão.",
            "A resposta não revela nome, usuario_id ou vizinho biométrico de outro tenant.",
            "Teste de integração prova que imagens e IDs de outra empresa não produzem diferença observável.",
        ],
    },
    {
        "n": 4,
        "title": "[Segurança] Substituir nome por identidade autorizada no cadastro biométrico",
        "labels": "security, severidade:alta",
        "finding": FINDINGS[3],
        "impact": "Envenenamento de templates biométricos, colisão entre homônimos e associação a usuário incorreto.",
        "acceptance": [
            "O cadastro usa funcionario_id validado no empresa_id da sessão, nunca nome como chave.",
            "Homônimos não compartilham arquivos, embeddings ou registros.",
            "Recadastro bloqueia e substitui o template correto em transação.",
            "Testes cobrem ID de outro tenant, nome duplicado e tentativa anônima.",
        ],
    },
    {
        "n": 5,
        "title": "[Segurança] Rotacionar segredo Flask exposto no histórico Git",
        "labels": "security, severidade:alta",
        "finding": FINDINGS[4],
        "impact": "Forja de cookies de sessão e possível elevação de privilégios caso o segredo histórico ainda seja válido ou reutilizado.",
        "acceptance": [
            "FLASK_SECRET_KEY foi rotacionada em todos os ambientes e sessões antigas foram invalidadas.",
            "Foi confirmado que o valor não é reutilizado em outros serviços.",
            "Secret scanning bloqueia novos commits com segredos reais.",
            "A equipe decidiu e documentou se fará purge do histórico e rotação de forks/caches.",
        ],
    },
]


class AuditDocTemplate(BaseDocTemplate):
    def __init__(self, filename: str):
        super().__init__(
            filename,
            pagesize=A4,
            leftMargin=2 * cm,
            rightMargin=2 * cm,
            topMargin=2.25 * cm,
            bottomMargin=2 * cm,
            title="Relatório de Auditoria de Segurança — FrequenIA",
            author="Codex",
            subject="Auditoria de segurança estática do repositório FrequenIA",
        )
        frame = Frame(
            self.leftMargin,
            self.bottomMargin,
            self.width,
            self.height,
            id="normal",
        )
        self.addPageTemplates(PageTemplate(id="audit", frames=frame))

    def _decorate(self, canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.5)
        canvas.line(2 * cm, A4[1] - 1.45 * cm, A4[0] - 2 * cm, A4[1] - 1.45 * cm)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(2 * cm, A4[1] - 1.15 * cm, "Relatório de Auditoria de Segurança - FrequenIA")
        canvas.drawRightString(A4[0] - 2 * cm, 1.15 * cm, f"Página {doc.page}")
        canvas.line(2 * cm, 1.45 * cm, A4[0] - 2 * cm, 1.45 * cm)
        canvas.restoreState()


styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="CoverTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=27, leading=32, textColor=colors.white, alignment=TA_LEFT, spaceAfter=18))
styles.add(ParagraphStyle(name="CoverMeta", parent=styles["BodyText"], fontSize=11, leading=16, textColor=INK))
styles.add(ParagraphStyle(name="H1Audit", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=19, leading=23, textColor=NAVY, spaceBefore=6, spaceAfter=12))
styles.add(ParagraphStyle(name="H2Audit", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=13, leading=17, textColor=NAVY, spaceBefore=10, spaceAfter=7))
styles.add(ParagraphStyle(name="BodyAudit", parent=styles["BodyText"], fontSize=9.4, leading=13.4, textColor=INK, spaceAfter=7))
styles.add(ParagraphStyle(name="SmallAudit", parent=styles["BodyText"], fontSize=8, leading=11, textColor=MUTED))
styles.add(ParagraphStyle(name="TableHead", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=7.6, leading=9.5, textColor=colors.white, alignment=TA_LEFT))
styles.add(ParagraphStyle(name="TableCell", parent=styles["BodyText"], fontSize=7.4, leading=10, textColor=INK))
styles.add(ParagraphStyle(name="Chip", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=7.2, leading=9, textColor=colors.white, alignment=TA_CENTER))
styles.add(ParagraphStyle(name="AuditCode", fontName="Courier", fontSize=7.2, leading=9.2, textColor=INK, leftIndent=7, rightIndent=7, borderColor=LINE, borderWidth=0.6, borderPadding=7, backColor=HexColor("#F7F8FA"), spaceBefore=4, spaceAfter=8))
styles.add(ParagraphStyle(name="Issue", fontName="Courier", fontSize=6.9, leading=9.2, textColor=INK, borderColor=LINE, borderWidth=0.7, borderPadding=8, backColor=HexColor("#FAFAFB"), spaceBefore=5, spaceAfter=12, splitLongWords=True))


def p(text: str, style: str = "BodyAudit") -> Paragraph:
    return Paragraph(text, styles[style])


def cover() -> list:
    box = Table(
        [[
            Paragraph("Relatório de Auditoria de Segurança — FrequenIA", styles["CoverTitle"]),
        ]],
        colWidths=[A4[0] - 4 * cm],
        rowHeights=[7.1 * cm],
    )
    box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 1.2 * cm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1.2 * cm),
    ]))
    return [
        Spacer(1, 2.1 * cm),
        box,
        Spacer(1, 0.7 * cm),
        p("<b>Data:</b> 17 de setembro de 2026", "CoverMeta"),
        p("<b>Escopo:</b> branch desenvolvimento-mvp, incluindo backend Flask, consultas PostgreSQL/Supabase, templates e JavaScript web, app Flutter, migrations, Dockerfile, configurações e histórico Git.", "CoverMeta"),
        Spacer(1, 0.25 * cm),
        p("<b>Nota metodológica:</b> RLS foi mapeado ao controle efetivamente usado pela stack: filtros manuais com empresa_id derivado de g.auth_context. Gates visuais foram cruzados com decorators do Flask. Todos os handlers registrados foram enumerados para IDOR. Segredos foram buscados na árvore atual, artefatos de deploy, mobile, documentação e histórico Git. Sinks XSS e origens de dados foram rastreados até a renderização.", "CoverMeta"),
        Spacer(1, 2.6 * cm),
        p("Auditoria estática orientada a evidência. Não foram realizadas ações destrutivas, exploração contra ambiente remoto ou leitura de segredos locais fora do repositório.", "SmallAudit"),
        PageBreak(),
        Spacer(1, 2 * cm),
    ]


def donut_chart() -> Drawing:
    d = Drawing(225, 155)
    pie = Pie()
    pie.x = 18
    pie.y = 25
    pie.width = 105
    pie.height = 105
    pie.data = [1, 4]
    pie.labels = ["Crítica", "Alta"]
    pie.slices[0].fillColor = CRITICAL
    pie.slices[1].fillColor = HIGH
    pie.slices.strokeColor = colors.white
    pie.slices.strokeWidth = 1.5
    pie.innerRadiusFraction = 0.57
    d.add(pie)
    d.add(String(70, 76, "5", fontName="Helvetica-Bold", fontSize=20, fillColor=INK, textAnchor="middle"))
    d.add(String(70, 61, "achados", fontName="Helvetica", fontSize=8, fillColor=MUTED, textAnchor="middle"))
    legend = Legend()
    legend.x = 142
    legend.y = 103
    legend.fontName = "Helvetica"
    legend.fontSize = 8
    legend.boxAnchor = "w"
    legend.colorNamePairs = [(CRITICAL, "Crítica: 1"), (HIGH, "Alta: 4")]
    d.add(legend)
    d.add(String(112, 143, "Achados por severidade", fontName="Helvetica-Bold", fontSize=10, fillColor=NAVY, textAnchor="middle"))
    return d


def bar_chart() -> Drawing:
    d = Drawing(270, 155)
    chart = VerticalBarChart()
    chart.x = 35
    chart.y = 35
    chart.height = 90
    chart.width = 215
    chart.data = [[1, 1, 1, 1, 1]]
    chart.categoryAxis.categoryNames = ["Tenant", "Permissão", "IDOR", "Chaves", "Inputs"]
    chart.categoryAxis.labels.fontName = "Helvetica"
    chart.categoryAxis.labels.fontSize = 6.5
    chart.categoryAxis.labels.angle = 18
    chart.categoryAxis.labels.dy = -6
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = 2
    chart.valueAxis.valueStep = 1
    chart.valueAxis.labels.fontSize = 7
    chart.bars[0].fillColor = NAVY
    chart.bars[0].strokeColor = NAVY
    d.add(chart)
    d.add(String(135, 143, "Achados por categoria", fontName="Helvetica-Bold", fontSize=10, fillColor=NAVY, textAnchor="middle"))
    return d


def executive_summary() -> list:
    counts = Table(
        [[p("CRÍTICA", "Chip"), p("ALTA", "Chip"), p("MÉDIA", "Chip"), p("BAIXA", "Chip")],
         [p("1", "H1Audit"), p("4", "H1Audit"), p("0", "H1Audit"), p("0", "H1Audit")]],
        colWidths=[3.9 * cm] * 4,
    )
    counts.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), CRITICAL),
        ("BACKGROUND", (1, 0), (1, 0), HIGH),
        ("BACKGROUND", (2, 0), (2, 0), MEDIUM),
        ("BACKGROUND", (3, 0), (3, 0), LOW),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
        ("ALIGN", (0, 1), (-1, 1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    charts = Table([[donut_chart(), bar_chart()]], colWidths=[7.7 * cm, 8.3 * cm])
    charts.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return [
        p("Resumo executivo", "H1Audit"),
        p("Foram confirmados cinco achados acionáveis: um crítico e quatro altos. O risco dominante está no módulo facial legado, que permanece registrado apesar da arquitetura moderna 1:1 já existente. A versão atual protege a maior parte das rotas por papel e tenant, mas as rotas legadas contornam esses controles. O histórico Git também contém um segredo de sessão real."),
        counts,
        Spacer(1, 0.35 * cm),
        charts,
        p("<b>Prioridade imediata:</b> desregistrar routes/face.py ou devolver 410 nas rotas legadas, rotacionar FLASK_SECRET_KEY e invalidar sessões. Em seguida, remover definitivamente a tabela/integração fotos baseada em nome."),
    ]


def strengths_and_weaknesses() -> list:
    strengths = [
        "JWT HS256 exige claims sub, funcionario_id, sid, iat e exp; a sessão persistida é revalidada no banco (utils/auth_decorator.py:24-55, 95-125).",
        "Segredos atuais obrigatórios falham no startup quando ausentes; CORS curinga é rejeitado e chave de teste é bloqueada em produção (app.py:15-21, 77-88).",
        "Rotas modernas de biometria validam papel, tenant e funcionario_id, rejeitando identidade/decisão enviadas pelo cliente (routes/biometrics.py:62-85, 183-215, 370-390, 442-449).",
        "Ocorrências pessoais e administrativas incluem empresa_id em listas, detalhes e transições; rotas pessoais também incluem funcionario_id e solicitante (routes/occurrences.py:244-260, 277-286, 326-349).",
        "Controle de ponto e exportações derivam empresa da sessão e validam o funcionário na mesma empresa (routes/timekeeping.py:161-178, 287-349).",
        "Sinks XSS dinâmicos relevantes usam textContent/Option.textContent ou escape explícito; não foi confirmado XSS explorável (static/js/ocorrencias.js:27-35; templates/gerenciarUsuario.html:35, 49-53).",
        ".gitignore e .dockerignore excluem .env, chaves privadas, keystores e diretórios temporários.",
    ]
    weaknesses = [
        "Blueprint facial legado público e mutável continua registrado.",
        "Identidade legada é modelada por nome e busca biométrica global, incompatível com tenant isolation.",
        "Caminhos de filesystem aceitam entrada bruta antes de rmtree/cv2.imwrite.",
        "Segredo Flask histórico exige rotação mesmo após remoção do HEAD.",
        "Não há RLS nas migrations; o banco depende integralmente da correção dos filtros da API. Isso não foi tratado como falha autônoma porque não há acesso direto do frontend ao Supabase, mas reduz defesa em profundidade.",
    ]
    data = [[p("PONTOS FORTES", "TableHead"), p("PONTOS FRACOS", "TableHead")], [p("<br/>".join(f"• {x}" for x in strengths), "TableCell"), p("<br/>".join(f"• {x}" for x in weaknesses), "TableCell")]]
    table = Table(data, colWidths=[8 * cm, 8 * cm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), STRONG),
        ("BACKGROUND", (1, 0), (1, 0), HIGH),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return [PageBreak(), Spacer(1, 2 * cm), p("Pontos fortes e pontos fracos", "H1Audit"), table]


def detailed_findings() -> list:
    rows = [[p("Severidade", "TableHead"), p("Arquivo:linha", "TableHead"), p("Descrição", "TableHead")]]
    for finding in FINDINGS:
        chip = Table([[p(finding["severity"].upper(), "Chip")]], colWidths=[1.65 * cm], rowHeights=[0.55 * cm])
        chip.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), finding["color"]), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        rows.append([
            chip,
            p(f"<b>{finding['id']}</b><br/>{finding['location']}", "TableCell"),
            p(f"<b>{finding['title']}</b><br/>{finding['description']}", "TableCell"),
        ])
    table = Table(rows, colWidths=[2 * cm, 4.6 * cm, 9.4 * cm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
    ]))
    story = [PageBreak(), Spacer(1, 2 * cm), p("Achados detalhados", "H1Audit"), table, Spacer(1, 0.25 * cm)]
    for index, finding in enumerate(FINDINGS):
        if index in {2, 4}:
            story.extend([PageBreak(), Spacer(1, 2 * cm)])
        story.extend([
            KeepTogether([
                p(f"{finding['id']} - {finding['title']}", "H2Audit"),
                p(f"<b>Categoria:</b> {finding['category']} &nbsp;&nbsp; <b>Severidade:</b> {finding['severity']}<br/><b>Evidência:</b> {finding['location']}"),
                XPreformatted(finding["snippet"], styles["AuditCode"]),
                p(f"<b>Por que é explorável:</b> {finding['description']}"),
                p(f"<b>Correção recomendada:</b> {finding['recommendation']}"),
            ])
        ])
    return story


def coverage() -> list:
    data = [
        [p("Área", "TableHead"), p("Cobertura e resultado", "TableHead")],
        [p("Stack", "TableCell"), p("Python 3.10, Flask 3, psycopg2/PostgreSQL (schema Supabase), JWT PyJWT + auth_sessions, Jinja/JavaScript, Flutter/Dart, Dockerfile. Sem ORM/query builder; SQL parametrizado manual. Sem CI, Helm ou Terraform versionados.", "TableCell")],
        [p("Rotas", "TableCell"), p("73 handlers e 78 decorators de rota enumerados em app.py e routes/*.py. 52 handlers possuem guarda explícita; os demais foram classificados como públicos intencionais (health, páginas, login/reset/hora) ou legado facial. Todos os handlers com IDs em path/body/query foram revisados.", "TableCell")],
        [p("Tenant/IDOR", "TableCell"), p("Biometria moderna, ocorrências, turnos, jornadas, marcações, gestão de usuários e exportações foram cruzadas com empresa_id da sessão. Os handlers modernos por UUID retornam 404 quando o objeto não pertence ao tenant. A exceção acionável é routes/face.py.", "TableCell")],
        [p("Gates de papel", "TableCell"), p("Menu e páginas administrativas foram cruzados com cadastrar_usuario, atualizar_usuario, status, jornadas, biometria, controle de ponto, exportação e ocorrências. O backend moderno repete os gates. As rotas legadas não repetem.", "TableCell")],
        [p("Segredos", "TableCell"), p("Árvore atual, .env.example, Dockerfile, migrations/scripts, documentação, Flutter e histórico Git pesquisados. Nenhuma chave real foi confirmada no HEAD ou em bundle versionado; um segredo Flask foi confirmado no histórico. Defaults funcionais de porta/timeout não são segredos.", "TableCell")],
        [p("XSS", "TableCell"), p("Pesquisados innerHTML/outerHTML/insertAdjacentHTML, renderização HTML/Markdown, eval/new Function, URLs controladas e templates backend. Não há biblioteca de sanitização instalada; nos pontos atuais ela não é necessária porque os dados dinâmicos são renderizados como texto/autoescaped. O innerHTML de gerenciarEmpresa é inseguro em abstrato, mas a API atual não fornece os campos interpolados e a página está fora do menu, portanto não foi reportado como achado explorável.", "TableCell")],
        [p("Testes", "TableCell"), p("A auditoria foi estática. Tentativas de executar testes unitários falharam antes da coleta porque pytest/Flask não estão instalados nos runtimes Python disponíveis. Nenhuma dependência foi instalada globalmente. A geração do PDF usa o runtime isolado fornecido pelo Codex.", "TableCell")],
    ]
    table = Table(data, colWidths=[3.1 * cm, 12.9 * cm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return [PageBreak(), Spacer(1, 2 * cm), p("Cobertura e pontos verificados como corretos", "H1Audit"), table]


def recommendations() -> list:
    priorities = [
        ("P1", "Desregistrar ou devolver 410 para todas as rotas mutáveis e de reconhecimento de routes/face.py."),
        ("P1", "Rotacionar FLASK_SECRET_KEY em todos os ambientes e invalidar sessões emitidas com o segredo histórico."),
        ("P1", "Eliminar o uso de nome em paths e como chave biométrica; usar empresa_id + funcionario_id validados."),
        ("P2", "Remover a tabela fotos/Cloudinary legados após migração controlada para biometrias e verificação 1:1."),
        ("P2", "Adicionar testes negativos de rota anônima, outro papel, outro tenant, path traversal e homônimos."),
        ("P2", "Adicionar secret scanning no CI e pre-commit; decidir sobre purge do histórico e forks."),
        ("P3", "Criar papel PostgreSQL de mínimo privilégio e avaliar RLS como defesa em profundidade, sem substituir os filtros da API."),
        ("P3", "Adicionar CSP e manter política de evitar innerHTML com dados dinâmicos, ainda que não haja XSS confirmado agora."),
    ]
    rows = [[p("Prioridade", "TableHead"), p("Ação", "TableHead")]]
    for priority, action in priorities:
        color = CRITICAL if priority == "P1" else HIGH if priority == "P2" else LOW
        chip = Table([[p(priority, "Chip")]], colWidths=[1.3 * cm], rowHeights=[0.5 * cm])
        chip.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), color), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        rows.append([chip, p(action, "TableCell")])
    table = Table(rows, colWidths=[2 * cm, 14 * cm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return [PageBreak(), Spacer(1, 2 * cm), p("Recomendações priorizadas", "H1Audit"), table]


def issue_markdown(issue: dict) -> str:
    finding = issue["finding"]
    checks = "\n".join(f"- [ ] {item}" for item in issue["acceptance"])
    return f"""--- ISSUE {issue['n']} ---
# {issue['title']}

**Labels sugeridas:** {issue['labels']}

## Descrição
{finding['description']}

## Evidência
`{finding['location']}`

```text
{finding['snippet']}
```

## Impacto
{issue['impact']}

## Sugestão de correção
{finding['recommendation']}

## Critérios de aceite
{checks}
--- FIM ISSUE {issue['n']} ---"""


def wrap_issue_text(value: str, width: int = 102) -> str:
    """Quebra linhas Markdown sem depender de wrapping do XPreformatted."""
    result = []
    in_fence = False
    for line in value.splitlines():
        if line.startswith("```"):
            in_fence = not in_fence
            result.append(line)
            continue
        if not line or in_fence or len(line) <= width:
            result.append(line)
            continue
        initial = ""
        subsequent = ""
        if line.startswith("- [ ] "):
            initial, line, subsequent = "- [ ] ", line[6:], "      "
        elif line.startswith("**"):
            subsequent = "  "
        wrapped = textwrap.wrap(
            line,
            width=max(20, width - len(initial)),
            break_long_words=False,
            break_on_hyphens=False,
            subsequent_indent=subsequent,
        ) or [""]
        result.append(initial + wrapped[0])
        result.extend(wrapped[1:])
    return "\n".join(result)


def github_issues() -> list:
    story = [PageBreak(), Spacer(1, 2 * cm), p("ISSUES PARA O GITHUB", "H1Audit"), p("Textos completos em Markdown, prontos para copiar e colar. Evidências sensíveis permanecem redigidas.")]
    for index, issue in enumerate(ISSUES):
        if index:
            story.extend([PageBreak(), Spacer(1, 2 * cm)])
        story.append(XPreformatted(wrap_issue_text(issue_markdown(issue)), styles["Issue"]))
    return story


def stamp_header_footer(source: Path, destination: Path) -> None:
    reader = PdfReader(str(source))
    writer = PdfWriter()
    for page_number, page in enumerate(reader.pages, start=1):
        original = page.get_contents()
        if original is not None:
            isolated = DecodedStreamObject()
            isolated.set_data(b"q\n" + original.get_data() + b"\nQ\n")
            page[NameObject("/Contents")] = isolated
        packet = BytesIO()
        stamp = pdf_canvas.Canvas(packet, pagesize=A4)
        stamp.setFillColor(colors.white)
        stamp.rect(0, A4[1] - 1.55 * cm, A4[0], 1.55 * cm, fill=1, stroke=0)
        stamp.rect(0, 0, A4[0], 1.55 * cm, fill=1, stroke=0)
        stamp.setStrokeColor(LINE)
        stamp.setLineWidth(0.5)
        stamp.line(2 * cm, A4[1] - 1.45 * cm, A4[0] - 2 * cm, A4[1] - 1.45 * cm)
        stamp.line(2 * cm, 1.45 * cm, A4[0] - 2 * cm, 1.45 * cm)
        stamp.setFont("Helvetica", 8)
        stamp.setFillColor(MUTED)
        if page_number > 1:
            stamp.drawString(2 * cm, A4[1] - 1.15 * cm, "Relatório de Auditoria de Segurança - FrequenIA")
        stamp.drawRightString(A4[0] - 2 * cm, 1.15 * cm, f"Página {page_number}")
        stamp.save()
        packet.seek(0)
        page.merge_page(PdfReader(packet).pages[0])
        writer.add_page(page)
    writer.add_metadata(reader.metadata or {})
    with destination.open("wb") as stream:
        writer.write(stream)


def build() -> Path:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    base_output = OUTPUT.with_suffix(".base.pdf")
    doc = AuditDocTemplate(str(base_output))
    story = []
    story += cover()
    story += executive_summary()
    story += strengths_and_weaknesses()
    story += detailed_findings()
    story += coverage()
    story += recommendations()
    story += github_issues()
    doc.build(story)
    stamp_header_footer(base_output, OUTPUT)
    base_output.unlink()
    return OUTPUT


if __name__ == "__main__":
    path = build()
    print(path)
