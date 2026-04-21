from flask import Blueprint, app, render_template, redirect, url_for, Flask, jsonify, session, request
from datetime import datetime
from zoneinfo import ZoneInfo
from utils.auth_decorator import login_required, admin_required
import psycopg2.extras
import secrets
from werkzeug.security import generate_password_hash, check_password_hash
from db import buscar_usuario_por_email, salvar_token, conectar_bd, atualizar_senha, limpar_token
from routes.face import pasta_usuario
import os

views_bp = Blueprint("views", __name__)

@views_bp.route("/")
def home():
    return redirect(url_for("auth.login_page"))

# =========================
# PAGINA DE LOGIN
# =========================
@views_bp.route("/login-page")
def login_page():
    return render_template("login.html")

# =========================
# FUNÇÃO DE LOGIN
# =========================
@views_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()

    cpf = data.get('cpf')
    senha = data.get('senha')

    cpf = cpf.replace('.', '').replace('-', '').strip()
    senha = senha.strip()

    print("CPF recebido:", cpf)

    conn = conectar_bd()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cursor.execute("""
    SELECT u.id, u.nome, u.cpf, u.senha_hash, f.tipo_perfil
    FROM usuarios u
    INNER JOIN funcionarios f ON u.id = f.usuario_id
    WHERE REPLACE(REPLACE(u.cpf, '.', ''), '-', '') = %s
""", (cpf,))

    user = cursor.fetchone()
    conn.close()

    print("Usuário encontrado:", user)

    if not user:
        return jsonify({'erro': 'CPF não encontrado'}), 404

    if not user['senha_hash']:
        return jsonify({'erro': 'Usuário ainda não definiu senha'}), 400

    resultado = check_password_hash(user['senha_hash'], senha)

    if not resultado:
        return jsonify({'erro': 'Senha incorreta'}), 401

    session['user_id'] = user['id']
    session['nome'] = user['nome']
    session['tipo'] = user['tipo_perfil']

    return jsonify({
    'ok': True,
    'nome': user['nome'],
    'tipo': user['tipo_perfil']
}), 200

@views_bp.route("/recuperacaoSenha")
def recuperacao_senha():
    return render_template("recuperacaoSenha.html")

# =========================
# MENU
# =========================
@views_bp.route("/menu")
@login_required
def menu():
    print(session)
    conn = conectar_bd()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cursor.execute("SELECT nome FROM usuarios WHERE id = %s", (session['user_id'],))
    user = cursor.fetchone()
    conn.close()

    return render_template(
    "menu.html",
    nome=session.get('nome'),
    tipo=session.get('tipo')
)

# =========================
# TELAS DENTRO DO MENU
# =========================

@views_bp.route("/controleponto")
def controle_ponto():
    return render_template("controleponto.html")

@views_bp.route("/inicio")
def inicio():
    return render_template("inicio.html")


@views_bp.route("/perfil")
@login_required
def perfil():
    conn = conectar_bd()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cursor.execute("""
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
    """, (session['user_id'],))

    user = cursor.fetchone()

    conn.close()

    return render_template("perfil.html", user=user)

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

@views_bp.route('/gerenciarUsuario')
@login_required
@admin_required
def gerenciar_usuario():
    return render_template('gerenciarUsuario.html')

@views_bp.route('/gerenciarEmpresa')
@login_required
@admin_required
def gerenciar_empresa():
    return render_template('gerenciarEmpresa.html')

@views_bp.route("/configuracoes")
@login_required
def configuracoes():
    return render_template("configuracoes.html")

@views_bp.route("/cadastroEmpresas")
@login_required
def cadastroEmpresas():
    return render_template("cadastroEmpresas.html")

@views_bp.route("/editarUsuario")
@login_required
def editar_usuario():
    user_id = request.args.get("id")

    conn = conectar_bd()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cursor.execute("""
        SELECT 
            u.id,
            u.nome,
            u.email,
            u.telefone,
            u.cpf,
            f.cargo,
            f.setor,
            f.tipo_perfil,
            f.tipo_contrato,
            f.data_admissao
        FROM usuarios u
        LEFT JOIN funcionarios f ON u.id = f.usuario_id
        WHERE u.id = %s
    """, (user_id,))

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

    cursor.execute("""
        SELECT 
            u.id,
            u.nome,
            u.email,
            u.telefone,
            u.cpf,
            f.cargo,
            f.setor,
            f.tipo_perfil,
            f.tipo_contrato,
            f.data_admissao
        FROM usuarios u
        LEFT JOIN funcionarios f ON u.id = f.usuario_id
        WHERE u.id = %s
    """, (user_id,))

    usuario = cursor.fetchone()

    cursor.close()
    conn.close()

    if not usuario:
        return "Usuário não encontrado", 404

    return render_template("editarHorarios.html", usuario=usuario)

# =========================
# LISTAGEM DE USUÁRIOS
# =========================
@views_bp.route("/listarUsuarios")
@login_required
def listar_usuarios():
    try:
        conn = conectar_bd()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute("""
            SELECT id, nome, cpf, 'ativo' as status
            FROM usuarios
        """)

        usuarios = cursor.fetchall()

        cursor.close()
        conn.close()

        return jsonify(usuarios)

    except Exception as e:
        print("ERRO:", e)
        return jsonify([]), 500

# =========================
# LISTAGEM DE EMPRESAS
# =========================
@views_bp.route("/listarEmpresas")
@login_required
def listar_empresas():
    try:
        conn = conectar_bd()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute("""
            SELECT cnpj, razao
            FROM empresas_teste
        """)

        empresas_teste = cursor.fetchall()

        cursor.close()
        conn.close()

        return jsonify(empresas_teste)

    except Exception as e:
        print("ERRO:", e)
        return jsonify([]), 500

# =========================
# ALTERAÇÃO NO BANCO DE DADOS
# =========================

@views_bp.route("/atualizar_usuario", methods=["POST"])
def atualizar_usuario():
    try:
        dados = request.get_json()

        user_id = dados.get("id")
        nome = dados.get("nome")
        email = dados.get("email")

        conn = conectar_bd()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE usuarios
            SET nome = %s, email = %s
            WHERE id = %s
        """, (nome, email, user_id))

        conn.commit()

        cursor.close()
        conn.close()

        return jsonify({"status": "ok"})

    except Exception as e:
        print("ERRO:", e)
        return jsonify({"status": "erro"})


# =========================
# RECUPERAÇÃO DE SENHA
# =========================

@views_bp.route("/inserirToken")
def inserir_token():
    return render_template("inserirToken.html")


@views_bp.route('/enviar-token', methods=['POST'])
def enviar_token():
    data = request.get_json()
    email = data['email']

    user = buscar_usuario_por_email(email)

    if not user:
        return jsonify({'erro': 'Email não encontrado'}), 404

    token = secrets.token_hex(3)

    salvar_token(user['id'], token)

    print("TOKEN GERADO:", token)

    return jsonify({'ok': True}), 200


@views_bp.route('/validar-token', methods=['POST'])
def validar_token():
    data = request.get_json()

    email = data['email']
    token = data['token']

    user = buscar_usuario_por_email(email)

    if not user:
        return {'erro': 'Usuário não encontrado'}, 404

    if user['token_reset'] != token:
        return {'erro': 'Token inválido'}, 400

    return {'ok': True}, 200


# =========================
# ALTERAÇÃO DE SENHA
# =========================

@views_bp.route('/resetar-senha', methods=['POST'])
def resetar_senha():
    from flask import request, jsonify
    from werkzeug.security import generate_password_hash
    from db import buscar_usuario_por_email, atualizar_senha, limpar_token

    data = request.get_json()

    email = data.get('email')
    token = data.get('token')
    senha = data.get('senha')

    user = buscar_usuario_por_email(email)

    if not user:
        return jsonify({'erro': 'Usuário não encontrado'}), 404

    if user['token_reset'] != token:
        return jsonify({'erro': 'Token inválido'}), 400

    senha_hash = generate_password_hash(senha)

    atualizar_senha(user['id'], senha_hash)

    limpar_token(user['id'])

    session.clear();

    return jsonify({'ok': True}), 200

# =========================
# FUNÇÃO QUE RETORNA A HORA DO SERVIDOR
# =========================
@views_bp.route("/hora-servidor")
def hora_servidor():
    agora = datetime.now(ZoneInfo("America/Sao_Paulo"))

    dias = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
    dia_semana = dias[agora.weekday()]

    return {
        "data": agora.strftime("%d/%m/%Y"),
        "hora": agora.strftime("%H:%M:%S"),
        "dia": dia_semana
    }

@views_bp.route("/listar_usuarios_select", methods=["GET"])
def listar_usuarios_select():
    try:
        conn = conectar_bd()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT u.id, u.nome
            FROM usuarios u
            WHERE NOT EXISTS (
                SELECT 1 FROM fotos f WHERE f.nome = u.nome
            )
        """)

        usuarios = cursor.fetchall()

        lista = [{"id": u[0], "nome": u[1]} for u in usuarios]

        cursor.close()
        conn.close()

        return jsonify(lista)

    except Exception as e:
        print("ERRO:", e)
        return jsonify([])

# =========================
# RETORNAR HORARIOS DO USUARIO LOGADO
# =========================

@views_bp.route('/jornada', methods=['GET'])
def get_jornada():
    if 'user_id' not in session:
        return jsonify({'erro': 'Não autenticado'}), 401

    user_id = session['user_id']

    conn = conectar_bd()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cursor.execute("""
        SELECT 
            TO_CHAR(inicio_expediente, 'HH24:MI') AS entrada,
            TO_CHAR(inicio_intervalo, 'HH24:MI') AS saida_intervalo,
            TO_CHAR(termino_intervalo, 'HH24:MI') AS volta_intervalo,
            TO_CHAR(termino_expediente, 'HH24:MI') AS saida
        FROM horarios
        WHERE usuario_id = %s
    """, (user_id,))

    jornada = cursor.fetchone()
    conn.close()

    if not jornada:
        return jsonify({'erro': 'Jornada não encontrada'}), 404

    return jsonify(jornada), 200

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

    return {
        "status": estado
    }

if __name__ == '__main__':
    app.run(debug=True)