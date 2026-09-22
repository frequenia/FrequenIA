"""Validação integrada controlada da Fase 16 no PostgreSQL configurado."""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flask import Flask
import psycopg2.extras

from db import conectar_bd
from routes.occurrences import occurrences_bp
from services.effective_timekeeping import fetch_effective_events


def expect(response, status, label):
    if response.status_code != status:
        raise AssertionError(f"{label}: esperado {status}, recebido {response.status_code}: {response.get_data(as_text=True)}")
    return response.get_json()


def main():
    suffix = uuid4().hex[:10]
    ids = {key: str(uuid4()) for key in ("company", "unit", "user", "employee", "manager_user", "manager", "marking", "foreign_company", "foreign_unit", "foreign_user", "foreign_employee", "foreign_marking")}
    conn = conectar_bd()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    created_corrections = []
    created_occurrences = []
    try:
        for prefix in ("", "foreign_"):
            cursor.execute("INSERT INTO empresas (id,nome,status) VALUES (%s,%s,'ativa')", (ids[prefix+"company"], f"Fixture F16 {prefix}{suffix}"))
            cursor.execute("INSERT INTO unidades (id,empresa_id,nome,status) VALUES (%s,%s,%s,'ativa')", (ids[prefix+"unit"], ids[prefix+"company"], f"Unidade {suffix}"))
        for key, name in (("user", "Funcionário F16"), ("manager_user", "Gestor F16"), ("foreign_user", "Externo F16")):
            cursor.execute("INSERT INTO usuarios (id,nome,cpf,email,senha_hash,status) VALUES (%s,%s,%s,%s,'fixture-hash','ativo')", (ids[key], name, str(abs(hash(key+suffix))).zfill(11)[-11:], f"{key}.{suffix}@example.invalid"))
        cursor.execute("""INSERT INTO funcionarios (id,usuario_id,empresa_id,unidade_id,matricula,perfil,status)
            VALUES (%s,%s,%s,%s,%s,'funcionario','ativo'),(%s,%s,%s,%s,%s,'gestor','ativo'),(%s,%s,%s,%s,%s,'funcionario','ativo')""",
            (ids["employee"],ids["user"],ids["company"],ids["unit"],f"F-{suffix}", ids["manager"],ids["manager_user"],ids["company"],ids["unit"],f"G-{suffix}", ids["foreign_employee"],ids["foreign_user"],ids["foreign_company"],ids["foreign_unit"],f"X-{suffix}"))
        for prefix in ("", "foreign_"):
            cursor.execute("""INSERT INTO marcacoes (id,empresa_id,funcionario_id,instante,tipo,origem,estado,chave_idempotencia)
                VALUES (%s,%s,%s,%s,'entrada','manual','confirmada',%s)""",
                (ids[prefix+"marking"], ids[prefix+"company"], ids[prefix+"employee"], datetime(2026,9,12,11,17,tzinfo=timezone.utc), str(uuid4())))
        conn.commit()

        app = Flask(__name__); app.config.update(TESTING=True, SECRET_KEY="fixture")
        app.register_blueprint(occurrences_bp); client = app.test_client()
        personal = {"user_id":ids["user"],"funcionario_id":ids["employee"],"empresa_id":ids["company"],"session_id":str(uuid4()),"familia_id":str(uuid4()),"perfil":"funcionario"}
        manager = {"user_id":ids["manager_user"],"funcionario_id":ids["manager"],"empresa_id":ids["company"],"session_id":str(uuid4()),"familia_id":str(uuid4()),"perfil":"gestor"}

        with patch("utils.auth_decorator._load_persistent_authentication", return_value=(personal,None)):
            correction = expect(client.post("/api/ocorrencias",headers={"Authorization":"Bearer fixture"},json={"tipo":"horario_incorreto","marcacao_id":ids["marking"],"motivo":"Horário correto validado","instante_solicitado":"2026-09-12T08:02:00-03:00"}),201,"create")
            created_corrections.append(correction["id"])
            expect(client.post("/api/ocorrencias",headers={"Authorization":"Bearer fixture"},json={"tipo":"horario_incorreto","marcacao_id":ids["foreign_marking"],"motivo":"Não permitido","instante_solicitado":"2026-09-12T08:02:00-03:00"}),404,"foreign")
        with patch("utils.auth_decorator._load_persistent_authentication", return_value=(manager,None)):
            expect(client.post(f"/api/gestao/ocorrencias/{correction['id']}/aprovar",headers={"Authorization":"Bearer fixture"},json={"observacao":"Validado pela liderança"}),200,"approve")
            expect(client.post(f"/api/gestao/ocorrencias/{correction['id']}/rejeitar",headers={"Authorization":"Bearer fixture"},json={"observacao":"segunda decisão"}),409,"second decision")

        cursor.execute("SELECT instante,tipo,origem FROM marcacoes WHERE id=%s",(ids["marking"],)); original=cursor.fetchone()
        assert original == {"instante":datetime(2026,9,12,11,17,tzinfo=timezone.utc),"tipo":"entrada","origem":"manual"}
        effective = fetch_effective_events(cursor,ids["company"],ids["employee"])
        assert len(effective)==1 and effective[0]["instante"]==datetime(2026,9,12,11,2,tzinfo=timezone.utc) and effective[0]["ajustada"]
        cursor.execute("SELECT ocorrencia_id FROM correcoes WHERE id=%s",(correction["id"],)); occurrence_id=str(cursor.fetchone()["ocorrencia_id"]);created_occurrences.append(occurrence_id)
        cursor.execute("SELECT count(*) AS n FROM auditoria WHERE entidade_id=%s",(correction["id"],)); assert cursor.fetchone()["n"]==2
        cursor.execute("SELECT count(*) AS n FROM notificacoes WHERE usuario_id=%s AND tipo='correcao'",(ids["user"],)); assert cursor.fetchone()["n"]==1
        print("phase16_integration=success")
    finally:
        conn.rollback()
        cursor.execute("DELETE FROM auditoria WHERE empresa_id IN (%s,%s)",(ids["company"],ids["foreign_company"]))
        cursor.execute("DELETE FROM notificacoes WHERE empresa_id IN (%s,%s)",(ids["company"],ids["foreign_company"]))
        cursor.execute("DELETE FROM correcoes WHERE empresa_id IN (%s,%s)",(ids["company"],ids["foreign_company"]))
        cursor.execute("DELETE FROM ocorrencias WHERE empresa_id IN (%s,%s)",(ids["company"],ids["foreign_company"]))
        cursor.execute("DELETE FROM marcacoes WHERE empresa_id IN (%s,%s)",(ids["company"],ids["foreign_company"]))
        cursor.execute("DELETE FROM funcionarios WHERE empresa_id IN (%s,%s)",(ids["company"],ids["foreign_company"]))
        cursor.execute("DELETE FROM usuarios WHERE id IN (%s,%s,%s)",(ids["user"],ids["manager_user"],ids["foreign_user"]))
        cursor.execute("DELETE FROM unidades WHERE empresa_id IN (%s,%s)",(ids["company"],ids["foreign_company"]))
        cursor.execute("DELETE FROM empresas WHERE id IN (%s,%s)",(ids["company"],ids["foreign_company"]))
        conn.commit(); cursor.close(); conn.close()
        print("phase16_cleanup=success")


if __name__ == "__main__":
    main()
