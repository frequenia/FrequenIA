from flask import (
    Blueprint,
    app,
    render_template,
    redirect,
    url_for,
    Flask,
    jsonify,
    session,
    request,
    send_file,
)
from datetime import datetime, date
from zoneinfo import ZoneInfo
from utils.auth_decorator import login_required, admin_required
import psycopg2.extras
import secrets
from werkzeug.security import generate_password_hash, check_password_hash
from db import (
    buscar_usuario_por_email,
    salvar_token,
    conectar_bd,
    atualizar_senha,
    limpar_token,
)
from routes.face import pasta_usuario
from collections import defaultdict
import os
import csv
import io

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from docx import Document

views_bp = Blueprint("views", __name__)


@views_bp.route("/")
def home():
    return redirect(url_for("views.login_page"))


# ==================================================================================================
# RENDERIZAÇÃO - PÁGINAS DO SISTEMA
# ==================================================================================================
@views_bp.route("/controleponto")
@login_required
def controle_ponto():
    return render_template("controleponto.html")


@views_bp.route("/inicio")
def inicio():
    return render_template("inicio.html")


@views_bp.route("/cadastroUsuario")
def cadastro_usuario():
    return render_template("cadastroUsuario.html")


@views_bp.route("/reconhecimentoFacial")
def reconhecimento_facial():
    return render_template("reconhecimentoFacial.html")


@views_bp.route("/cadastrarFoto")
@login_required
def cadastrar_foto():
    return render_template("cadastrarFoto.html")


@views_bp.route("/redefinicaoSenha")
def redefinicao_senha():
    return render_template("redefinicaoSenha.html")


@views_bp.route("/gerenciarUsuario")
@login_required
@admin_required
def gerenciar_usuario():
    return render_template("gerenciarUsuario.html")


@views_bp.route("/gerenciarEmpresa")
@login_required
@admin_required
def gerenciar_empresa():
    return render_template("gerenciarEmpresa.html")


@views_bp.route("/configuracoes")
@login_required
def configuracoes():
    return render_template("configuracoes.html")


@views_bp.route("/cadastroEmpresas")
@login_required
def cadastroEmpresas():
    return render_template("cadastroEmpresas.html")


@views_bp.route("/recuperacaoSenha")
def recuperacao_senha():
    return render_template("recuperacaoSenha.html")


@views_bp.route("/inserirToken")
def inserir_token():
    return render_template("inserirToken.html")


# ==================================================================================================
# FUNÇÃO PRINCIPAL - LOGIN
# ==================================================================================================
@views_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json()

    cpf = data.get("cpf")
    senha = data.get("senha")

    cpf = cpf.replace(".", "").replace("-", "").strip()
    senha = senha.strip()

    print("CPF recebido:", cpf)

    conn = conectar_bd()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cursor.execute(
        """
        SELECT u.id, u.nome, u.cpf, u.senha_hash, f.tipo_perfil
        FROM usuarios u
        INNER JOIN funcionarios f ON u.id = f.usuario_id
        WHERE REPLACE(REPLACE(u.cpf, '.', ''), '-', '') = %s
        """,
        (cpf,),
    )

    user = cursor.fetchone()
    cursor.close()
    conn.close()

    print("Usuário encontrado:", user)

    if not user:
        return jsonify({"erro": "CPF não encontrado"}), 404

    if not user["senha_hash"]:
        return jsonify({"erro": "Usuário ainda não definiu senha"}), 400

    resultado = check_password_hash(user["senha_hash"], senha)

    if not resultado:
        return jsonify({"erro": "Senha incorreta"}), 401

    session["user_id"] = user["id"]
    session["nome"] = user["nome"]
    session["tipo"] = user["tipo_perfil"]

    return jsonify(
        {
            "ok": True,
            "nome": user["nome"],
            "tipo": user["tipo_perfil"],
        }
    ), 200


# ==================================================================================================
# FUNÇÃO PRINCIPAL - CADASTRO DE USUÁRIOS
# ==================================================================================================
@views_bp.route("/cadastrar_usuario", methods=["POST"])
def cadastrar_usuario():
    conn = None
    cursor = None

    try:
        dados = request.get_json()

        conn = conectar_bd()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute(
            """
            INSERT INTO usuarios (nome, email, telefone, cpf, cargo_id, setor_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                dados["nome"],
                dados["email"],
                dados["telefone"],
                dados["cpf"],
                dados["cargo_id"],
                dados["setor_id"],
            ),
        )

        usuario_id = cursor.fetchone()["id"]

        cursor.execute(
            """
            INSERT INTO funcionarios (
                usuario_id, tipo_perfil,
                matricula, data_admissao, tipo_contrato,
                carga_horaria, jornada_padrao
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                usuario_id,
                dados["tipo_perfil"],
                dados["matricula"],
                dados["data_admissao"],
                dados["tipo_contrato"],
                dados["carga_horaria"],
                dados["jornada"],
            ),
        )

        horarios = dados.get("horarios", [])

        if not horarios:
            return jsonify({"status": "erro", "mensagem": "Nenhum horário informado"})

        for h in horarios:
            cursor.execute(
                """
                INSERT INTO horarios (
                    usuario_id,
                    dia_semana,
                    inicio_expediente,
                    inicio_intervalo,
                    termino_intervalo,
                    termino_expediente
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    usuario_id,
                    h["dia_semana"],
                    h["inicio_expediente"],
                    h["inicio_intervalo"],
                    h["termino_intervalo"],
                    h["termino_expediente"],
                ),
            )

        conn.commit()

        return jsonify({"status": "ok", "mensagem": "Usuário cadastrado com sucesso"})

    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({"status": "erro", "mensagem": str(e)})

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# ==================================================================================================
# FUNÇÃO PRINCIPAL - CADASTRO DE EMPRESAS
# ==================================================================================================
@views_bp.route("/cadastrar_empresa", methods=["POST"])
def cadastrar_empresa():
    conn = None
    cursor = None

    try:
        dadosEmp = request.get_json()

        conn = conectar_bd()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute(
            """
            INSERT INTO empresas_teste (cnpj, razao)
            VALUES (%s, %s)
            """,
            (dadosEmp["cnpj"], dadosEmp["razao"]),
        )

        conn.commit()

        return jsonify({"status": "ok", "mensagem": "Empresa cadastrada com sucesso"})

    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({"status": "erro", "mensagem": str(e)})

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# ==================================================================================================
# FUNÇÃO - CHAMADA DO MENU PRINCIPAL
# ==================================================================================================
@views_bp.route("/menu")
@login_required
def menu():
    conn = conectar_bd()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cursor.execute("SELECT nome FROM usuarios WHERE id = %s", (session["user_id"],))
    cursor.fetchone()

    cursor.close()
    conn.close()

    return render_template(
        "menu.html",
        nome=session.get("nome"),
        tipo=session.get("tipo"),
    )


# ==================================================================================================
# FUNÇÃO - RENDERIZAÇÃO DO MENU JÁ AUTENTICADO
# ==================================================================================================
@views_bp.route("/login-page")
def login_page():
    if "user_id" in session:
        return redirect("/menu")
    return render_template("login.html")


# ==================================================================================================
# FUNÇÃO - LOGOUT
# ==================================================================================================
@views_bp.route("/logout")
def logout():
    session.clear()
    return redirect("/login-page")


# ==================================================================================================
# FUNÇÃO - MEU PERFIL
# ==================================================================================================
@views_bp.route("/perfil")
@login_required
def perfil():
    conn = conectar_bd()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cursor.execute(
        """
        SELECT 
            u.nome, u.cpf, u.email, u.telefone,
            c.nome AS cargo_nome,
            s.nome AS setor_nome,
            f.tipo_perfil,
            f.data_admissao, f.tipo_contrato,
            f.matricula, f.carga_horaria, f.jornada_padrao
        FROM usuarios u
        LEFT JOIN funcionarios f ON u.id = f.usuario_id
        LEFT JOIN cargos c ON u.cargo_id = c.id
        LEFT JOIN setores s ON u.setor_id = s.id
        WHERE u.id = %s
        """,
        (session["user_id"],),
    )

    user = cursor.fetchone()

    cursor.close()
    conn.close()

    return render_template("perfil.html", user=user)


# ==================================================================================================
# FUNÇÃO - LISTAGEM DE USUÁRIOS (GERENCIAMENTO)
# ==================================================================================================
@views_bp.route("/listarUsuarios")
@login_required
def listar_usuarios():
    try:
        conn = conectar_bd()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute(
            """
            SELECT id, nome, cpf, 'ativo' as status
            FROM usuarios
            """
        )

        usuarios = cursor.fetchall()

        cursor.close()
        conn.close()

        return jsonify(usuarios)

    except Exception as e:
        print("ERRO:", e)
        return jsonify([]), 500


# ==================================================================================================
# FUNÇÃO - LISTAGEM DE EMPRESAS (GERENCIAMENTO)
# ==================================================================================================
@views_bp.route("/listarEmpresas")
@login_required
def listar_empresas():
    try:
        conn = conectar_bd()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute(
            """
            SELECT cnpj, razao
            FROM empresas_teste
            """
        )

        empresas_teste = cursor.fetchall()

        cursor.close()
        conn.close()

        return jsonify(empresas_teste)

    except Exception as e:
        print("ERRO:", e)
        return jsonify([]), 500


# ==================================================================================================
# FUNÇÃO - ALTERAÇÃO DE DADOS DO USUÁRIO
# ==================================================================================================
@views_bp.route("/atualizar_usuario", methods=["POST"])
def atualizar_usuario():
    try:
        dados = request.get_json()

        user_id = dados.get("id")
        nome = dados.get("nome")
        email = dados.get("email")
        telefone = dados.get("telefone")
        cargo_id = dados.get("cargo_id")

        conn = conectar_bd()
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE usuarios
            SET nome = %s, email = %s, telefone = %s, cargo_id = %s
            WHERE id = %s
            """,
            (nome, email, telefone, cargo_id, user_id),
        )

        conn.commit()

        cursor.close()
        conn.close()

        return jsonify({"status": "ok"})

    except Exception as e:
        print("ERRO:", e)
        return jsonify({"status": "erro"})


# ==================================================================================================
# FUNÇÕES - ENVIO E VALIDAÇÃO DE TOKEN PARA RECUPERAÇÃO DE SENHA
# ==================================================================================================
@views_bp.route("/enviar-token", methods=["POST"])
def enviar_token():
    data = request.get_json()
    email = data["email"]

    user = buscar_usuario_por_email(email)

    if not user:
        return jsonify({"erro": "Email não encontrado"}), 404

    token = secrets.token_hex(3)

    salvar_token(user["id"], token)

    print("TOKEN GERADO:", token)

    return jsonify({"ok": True, "token": token}), 200


@views_bp.route("/validar-token", methods=["POST"])
def validar_token():
    data = request.get_json()

    email = data["email"]
    token = data["token"]

    user = buscar_usuario_por_email(email)

    if not user:
        return {"erro": "Usuário não encontrado"}, 404

    if user["token_reset"] != token:
        return {"erro": "Token inválido"}, 400

    return {"ok": True}, 200


# ==================================================================================================
# FUNÇÃO - REDEFINIÇÃO DE SENHA
# ==================================================================================================
@views_bp.route("/resetar-senha", methods=["POST"])
def resetar_senha():
    data = request.get_json()

    email = data.get("email")
    token = data.get("token")
    senha = data.get("senha")

    user = buscar_usuario_por_email(email)

    if not user:
        return jsonify({"erro": "Usuário não encontrado"}), 404

    if user["token_reset"] != token:
        return jsonify({"erro": "Token inválido"}), 400

    senha_hash = generate_password_hash(senha)

    atualizar_senha(user["id"], senha_hash)
    limpar_token(user["id"])

    session.clear()

    return jsonify({"ok": True}), 200


# ==================================================================================================
# FUNÇÃO - LISTAGEM DE USUÁRIOS NO CADASTRO DE FOTOS (APENAS USUÁRIOS SEM FOTO)
# ==================================================================================================
@views_bp.route("/listar_usuarios_select", methods=["GET"])
def listar_usuarios_select():
    try:
        conn = conectar_bd()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT u.id, u.nome
            FROM usuarios u
            WHERE NOT EXISTS (
                SELECT 1 FROM fotos f WHERE f.nome = u.nome
            )
            """
        )

        usuarios = cursor.fetchall()

        lista = [{"id": u[0], "nome": u[1]} for u in usuarios]

        cursor.close()
        conn.close()

        return jsonify(lista)

    except Exception as e:
        print("ERRO:", e)
        return jsonify([])


# ==================================================================================================
# FUNÇÃO - RETORNO DO HORÁRIO DO SERVIDOR
# ==================================================================================================
@views_bp.route("/hora-servidor")
def hora_servidor():
    agora = datetime.now(ZoneInfo("America/Sao_Paulo"))

    dias = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
    dia_semana = dias[agora.weekday()]

    return {
        "data": agora.strftime("%d/%m/%Y"),
        "hora": agora.strftime("%H:%M:%S"),
        "dia": dia_semana,
    }


# ==================================================================================================
# FUNÇÃO - PUXAR HORÁRIOS-PADRÃO DO USUÁRIO
# ==================================================================================================
@views_bp.route("/jornada", methods=["GET"])
@login_required
def get_jornada():
    user_id = session["user_id"]

    conn = conectar_bd()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cursor.execute(
        """
        SELECT 
            TO_CHAR(inicio_expediente, 'HH24:MI') AS entrada,
            TO_CHAR(inicio_intervalo, 'HH24:MI') AS saida_intervalo,
            TO_CHAR(termino_intervalo, 'HH24:MI') AS volta_intervalo,
            TO_CHAR(termino_expediente, 'HH24:MI') AS saida
        FROM horarios
        WHERE usuario_id = %s
        """,
        (user_id,),
    )

    jornada = cursor.fetchone()

    cursor.close()
    conn.close()

    if not jornada:
        return jsonify({"erro": "Jornada não encontrada"}), 404

    return jsonify(jornada), 200


def formatar_hora(hora):
    return hora.strftime("%H:%M") if hora else "--:--"


def calcular_total(entrada, saida, saida_intervalo=None, volta_intervalo=None):
    try:
        if not entrada or not saida:
            return "--"

        dt_entrada = datetime.combine(date.today(), entrada)
        dt_saida = datetime.combine(date.today(), saida)

        total = dt_saida - dt_entrada

        if saida_intervalo and volta_intervalo:
            dt_saida_intervalo = datetime.combine(date.today(), saida_intervalo)
            dt_volta_intervalo = datetime.combine(date.today(), volta_intervalo)
            total -= (dt_volta_intervalo - dt_saida_intervalo)

        total_segundos = int(total.total_seconds())

        if total_segundos < 0:
            return "--"

        horas_total = total_segundos // 3600
        minutos_total = (total_segundos % 3600) // 60

        return f"{horas_total}h{minutos_total:02d}"
    except Exception:
        return "--"


def montar_registros_ponto(user_id, data_inicio=None, data_fim=None, formato_data="iso"):
    conn = None
    cursor = None

    try:
        conn = conectar_bd()
        cursor = conn.cursor()

        query = """
            SELECT data_registro, horario_registro
            FROM ponto
            WHERE usuario_id = %s
        """
        params = [user_id]

        if data_inicio:
            query += " AND data_registro >= %s"
            params.append(data_inicio)

        if data_fim:
            query += " AND data_registro <= %s"
            params.append(data_fim)

        query += " ORDER BY data_registro ASC, horario_registro ASC"

        cursor.execute(query, tuple(params))
        registros = cursor.fetchall()

        dias = defaultdict(list)

        for data_registro, horario_registro in registros:
            dias[data_registro].append(horario_registro)

        mapa_dias = {
            "Monday": "Segunda",
            "Tuesday": "Terça",
            "Wednesday": "Quarta",
            "Thursday": "Quinta",
            "Friday": "Sexta",
            "Saturday": "Sábado",
            "Sunday": "Domingo",
        }

        resultado = []

        for data_registro in sorted(dias.keys()):
            horarios = dias[data_registro]

            entrada = None
            saida_intervalo = None
            volta_intervalo = None
            saida = None

            if len(horarios) == 1:
                entrada = horarios[0]
            elif len(horarios) == 2:
                entrada = horarios[0]
                saida = horarios[1]
            elif len(horarios) == 3:
                entrada = horarios[0]
                saida_intervalo = horarios[1]
                saida = horarios[2]
            elif len(horarios) >= 4:
                entrada = horarios[0]
                saida_intervalo = horarios[1]
                volta_intervalo = horarios[2]
                saida = horarios[3]

            nome_dia_en = data_registro.strftime("%A")

            if formato_data == "br":
                data_formatada = data_registro.strftime("%d/%m/%Y")
            else:
                data_formatada = data_registro.strftime("%Y-%m-%d")

            resultado.append(
                {
                    "data": data_formatada,
                    "dia": mapa_dias.get(nome_dia_en, nome_dia_en),
                    "entrada": formatar_hora(entrada),
                    "saida_intervalo": formatar_hora(saida_intervalo),
                    "volta_intervalo": formatar_hora(volta_intervalo),
                    "saida": formatar_hora(saida),
                    "total": calcular_total(
                        entrada,
                        saida,
                        saida_intervalo,
                        volta_intervalo,
                    ),
                }
            )

        return resultado

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@views_bp.route("/pontos", methods=["GET"])
@login_required
def listar_pontos():
    try:
        user_id = session["user_id"]

        data_inicio = request.args.get("inicio")
        data_fim = request.args.get("fim")

        resultado = montar_registros_ponto(
            user_id=user_id,
            data_inicio=data_inicio,
            data_fim=data_fim,
            formato_data="iso",
        )

        return jsonify(resultado), 200

    except Exception as e:
        return jsonify({"erro": str(e)}), 500


@views_bp.route("/exportar-pontos", methods=["GET"])
@login_required
def exportar_pontos():
    user_id = session["user_id"]

    formato = request.args.get("formato", "").lower()
    data_inicio = request.args.get("inicio")
    data_fim = request.args.get("fim")

    registros = montar_registros_ponto(
        user_id=user_id,
        data_inicio=data_inicio,
        data_fim=data_fim,
        formato_data="br",
    )

    if not registros:
        return jsonify({"erro": "Nenhum registro encontrado para exportação."}), 404

    if formato == "csv":
        output = io.StringIO()
        writer = csv.writer(output, delimiter=";")
        writer.writerow(["Dia", "Data", "Entrada", "Saída Int.", "Volta Int.", "Saída", "Total"])

        for item in registros:
            writer.writerow(
                [
                    item["dia"],
                    item["data"],
                    item["entrada"],
                    item["saida_intervalo"],
                    item["volta_intervalo"],
                    item["saida"],
                    item["total"],
                ]
            )

        mem = io.BytesIO()
        mem.write(output.getvalue().encode("utf-8-sig"))
        mem.seek(0)

        return send_file(
            mem,
            as_attachment=True,
            download_name="controle_ponto.csv",
            mimetype="text/csv",
        )

    elif formato == "pdf":
        mem = io.BytesIO()
        pdf = canvas.Canvas(mem, pagesize=A4)
        largura, altura = A4

        y = altura - 40
        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawString(40, y, "Relatório de Controle de Ponto")

        y -= 30
        pdf.setFont("Helvetica", 9)
        pdf.drawString(40, y, "Dia")
        pdf.drawString(95, y, "Data")
        pdf.drawString(160, y, "Entrada")
        pdf.drawString(220, y, "Saída Int.")
        pdf.drawString(295, y, "Volta Int.")
        pdf.drawString(370, y, "Saída")
        pdf.drawString(430, y, "Total")

        y -= 15
        pdf.line(40, y, 550, y)

        for item in registros:
            y -= 18

            if y < 50:
                pdf.showPage()
                y = altura - 40
                pdf.setFont("Helvetica", 9)

            pdf.drawString(40, y, str(item["dia"]))
            pdf.drawString(95, y, str(item["data"]))
            pdf.drawString(160, y, str(item["entrada"]))
            pdf.drawString(220, y, str(item["saida_intervalo"]))
            pdf.drawString(295, y, str(item["volta_intervalo"]))
            pdf.drawString(370, y, str(item["saida"]))
            pdf.drawString(430, y, str(item["total"]))

        pdf.save()
        mem.seek(0)

        return send_file(
            mem,
            as_attachment=True,
            download_name="controle_ponto.pdf",
            mimetype="application/pdf",
        )

    elif formato in ["word", "doc"]:
        doc = Document()
        doc.add_heading("Relatório de Controle de Ponto", level=1)

        table = doc.add_table(rows=1, cols=7)
        table.style = "Table Grid"

        hdr = table.rows[0].cells
        hdr[0].text = "Dia"
        hdr[1].text = "Data"
        hdr[2].text = "Entrada"
        hdr[3].text = "Saída Int."
        hdr[4].text = "Volta Int."
        hdr[5].text = "Saída"
        hdr[6].text = "Total"

        for item in registros:
            row = table.add_row().cells
            row[0].text = item["dia"]
            row[1].text = item["data"]
            row[2].text = item["entrada"]
            row[3].text = item["saida_intervalo"]
            row[4].text = item["volta_intervalo"]
            row[5].text = item["saida"]
            row[6].text = item["total"]

        mem = io.BytesIO()
        doc.save(mem)
        mem.seek(0)

        return send_file(
            mem,
            as_attachment=True,
            download_name="controle_ponto.docx",
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    return jsonify({"erro": "Formato inválido."}), 400


# ==================================================================================================
# FUNÇÃO - LISTAGEM DE SETORES DO BANCO DE DADOS
# ==================================================================================================
@views_bp.route("/listar_setores", methods=["GET"])
def listar_setores():
    conn = conectar_bd()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cursor.execute("SELECT id, nome FROM setores ORDER BY nome")
    setores = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(setores)


# ==================================================================================================
# FUNÇÃO - LISTAGEM DE CARGOS DO BANCO DE DADOS
# ==================================================================================================
@views_bp.route("/listar_cargos", methods=["GET"])
def listar_cargos():
    conn = conectar_bd()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cursor.execute("SELECT id, nome FROM cargos ORDER BY nome")
    cargos = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(cargos)


@views_bp.route("/editarUsuario")
@login_required
def editar_usuario():
    user_id = request.args.get("id")

    conn = conectar_bd()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cursor.execute(
        """
        SELECT 
            u.id,
            u.nome,
            u.email,
            u.telefone,
            u.cpf,
            u.cargo_id,
            c.nome AS cargo,
            f.setor,
            f.tipo_perfil,
            f.tipo_contrato,
            f.data_admissao
        FROM usuarios u
        LEFT JOIN funcionarios f ON u.id = f.usuario_id
        LEFT JOIN cargos c ON u.cargo_id = c.id
        WHERE u.id = %s
        """,
        (user_id,),
    )

    usuario = cursor.fetchone()

    cursor.close()
    conn.close()

    if not usuario:
        return "Usuário não encontrado", 404

    return render_template("editarUsuario.html", usuario=usuario)


@views_bp.route("/editarHorarios")
@login_required
def editar_horarios():
    user_id = request.args.get("id")

    conn = conectar_bd()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Busca apenas o nome para exibir na tela
    cursor.execute("SELECT id, nome FROM usuarios WHERE id = %s", (user_id,))
    usuario = cursor.fetchone()

    if not usuario:
        cursor.close()
        conn.close()
        return "Usuário não encontrado", 404

    # Busca os horários do usuário
    cursor.execute("""
    SELECT dia_semana, inicio_expediente, inicio_intervalo,
           termino_intervalo, termino_expediente
    FROM horarios
    WHERE usuario_id = %s
    ORDER BY dia_semana
""", (user_id,))

    horarios = cursor.fetchall()
    horario = horarios[0] if horarios else None
    dias = [h['dia_semana'] for h in horarios]

    cursor.close()
    conn.close()

    return render_template("editarHorarios.html", usuario=usuario, horario=horario, dias=dias)


# =========================
# STATUS (MOCK)
# =========================
contador = 0


@views_bp.route("/status")
def status():
    global contador

    estados = ["expediente", "intervalo", "fora"]
    estado = estados[contador % 3]

    contador += 1

    return {"status": estado}


if __name__ == "__main__":
    app.run(debug=True)