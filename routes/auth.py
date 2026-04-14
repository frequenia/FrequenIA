from flask import Blueprint, request, jsonify, session, render_template, redirect
import psycopg2.extras
from db import conectar_bd

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect("/login-page")

@auth_bp.route("/login-page")
def login_page():
    if "user_id" in session:
        return redirect("/menu")
    return render_template("login.html")

# =========================
# CADASTRO DE USUÁRIO
# =========================
@auth_bp.route('/cadastrar_usuario', methods=['POST'])
def cadastrar_usuario():
    try:
        dados = request.get_json()

        conn = conectar_bd()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # USUARIO
        cursor.execute("""
            INSERT INTO usuarios (nome, email, telefone, cpf, cargo_id, setor_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            dados['nome'],
            dados['email'],
            dados['telefone'],
            dados['cpf'],
            dados['cargo_id'],
            dados['setor_id']
        ))

        usuario_id = cursor.fetchone()['id']

        # FUNCIONARIO
        cursor.execute("""
            INSERT INTO funcionarios (
                usuario_id, tipo_perfil,
                matricula, data_admissao, tipo_contrato,
                carga_horaria, jornada_padrao
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (
            usuario_id,
            dados['tipo_perfil'],
            dados['matricula'],
            dados['data_admissao'],
            dados['tipo_contrato'],
            dados['carga_horaria'],
            dados['jornada']
        ))

        # 🔥 HORARIOS (AGORA CORRETO)
        horarios = dados.get('horarios', [])

        if not horarios:
            return jsonify({"status": "erro", "mensagem": "Nenhum horário informado"})

        for h in horarios:
            cursor.execute("""
                INSERT INTO horarios (
                    usuario_id,
                    dia_semana,
                    inicio_expediente,
                    inicio_intervalo,
                    termino_intervalo,
                    termino_expediente
                )
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                usuario_id,
                h['dia_semana'],
                h['inicio_expediente'],
                h['inicio_intervalo'],
                h['termino_intervalo'],
                h['termino_expediente']
            ))

        # COMMIT
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            "status": "ok",
            "mensagem": "Usuário cadastrado com sucesso"
        })

    except Exception as e:
        return jsonify({
            "status": "erro",
            "mensagem": str(e)
        })

@auth_bp.route('/cadastrar_empresa', methods=['POST'])
def cadastrar_empresa():
    try:
        dadosEmp = request.get_json()

        conn = conectar_bd()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute("""
            INSERT INTO empresas_teste (cnpj, razao)
            VALUES (%s, %s)
        """, (
            dadosEmp['cnpj'],
            dadosEmp['razao']
        ))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            "status": "ok",
            "mensagem": "Empresa cadastrada com sucesso"
        })

    except Exception as e:
        return jsonify({
            "status": "erro",
            "mensagem": str(e)
        })


# =========================
# LISTAR CARGOS DO BANCO
# =========================
@auth_bp.route('/listar_cargos', methods=['GET'])
def listar_cargos():
    conn = conectar_bd()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cursor.execute("SELECT id, nome FROM cargos ORDER BY nome")
    cargos = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(cargos)

# =========================
# LISTAR SETORES DO BANCO
# =========================
@auth_bp.route('/listar_setores', methods=['GET'])
def listar_setores():
    conn = conectar_bd()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cursor.execute("SELECT id, nome FROM setores ORDER BY nome")
    setores = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(setores)