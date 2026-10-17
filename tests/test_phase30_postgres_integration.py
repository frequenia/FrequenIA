"""Fase 30: integração opt-in com PostgreSQL/pgvector real e descartável."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta, timezone
import os
import threading
import unittest
from urllib.parse import urlparse
from uuid import uuid4

import psycopg2
import psycopg2.extras

import test_phase25_postgres_integration as phase25
from services.daily_journey import (
    JourneyError,
    confirm_expected_event,
    materialize_snapshot,
    resolve_next_event,
    resolve_schedule_for_date,
)


URL = os.environ.get("PHASE30_TEST_DATABASE_URL", "").strip()


def _safe_url():
    if not URL:
        return False
    parsed = urlparse(URL)
    allowed = {"localhost", "127.0.0.1", "::1"}
    host = os.environ.get("FREQUENIA_DISPOSABLE_TEST_HOST", "").strip()
    if host:
        allowed.add(host)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in allowed or parsed.path != "/frequenia_phase25_test":
        raise RuntimeError("PHASE30_TEST_DATABASE_URL deve usar frequenia_phase25_test local descartável.")
    return True


ENABLED = _safe_url()
if ENABLED:
    phase25.TEST_DATABASE_URL = URL
    phase25.POSTGRES_ENABLED = True


def connect(dict_rows=True):
    kwargs = {"connect_timeout": 5}
    if dict_rows:
        kwargs["cursor_factory"] = psycopg2.extras.RealDictCursor
    return psycopg2.connect(URL, **kwargs)


@unittest.skipUnless(ENABLED, "requer PHASE30_TEST_DATABASE_URL explícita")
class Phase30PostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        phase25._reset_database()
        phase25._apply_migrations(1, 25)

    def setUp(self):
        self.ids = {name: str(uuid4()) for name in (
            "company", "foreign_company", "unit", "foreign_unit", "team", "foreign_team",
            "user", "employee", "second_user", "second_employee", "foreign_user", "foreign_employee",
            "turn", "other_turn", "assignment",
        )}
        connection = connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("TRUNCATE empresas,usuarios CASCADE")
                self._seed(cursor)
            connection.commit()
        finally:
            connection.close()

    def _seed(self, cursor):
        i = self.ids
        cursor.execute("INSERT INTO empresas(id,nome) VALUES(%s,'Phase30'),(%s,'Foreign')", (i["company"], i["foreign_company"]))
        cursor.execute("INSERT INTO unidades(id,empresa_id,nome) VALUES(%s,%s,'Unit'),(%s,%s,'Foreign Unit')", (i["unit"], i["company"], i["foreign_unit"], i["foreign_company"]))
        cursor.execute("INSERT INTO equipes(id,empresa_id,unidade_id,nome) VALUES(%s,%s,%s,'Team'),(%s,%s,%s,'Foreign Team')", (i["team"], i["company"], i["unit"], i["foreign_team"], i["foreign_company"], i["foreign_unit"]))
        for index, (user, employee, company, unit, team) in enumerate((
            (i["user"], i["employee"], i["company"], i["unit"], i["team"]),
            (i["second_user"], i["second_employee"], i["company"], i["unit"], i["team"]),
            (i["foreign_user"], i["foreign_employee"], i["foreign_company"], i["foreign_unit"], i["foreign_team"]),
        )):
            cursor.execute("INSERT INTO usuarios(id,nome,cpf,senha_hash) VALUES(%s,%s,%s,'fixture')", (user, f"Synthetic {index}", f"{90000000000+index:011d}"))
            cursor.execute("""INSERT INTO funcionarios(id,usuario_id,empresa_id,unidade_id,equipe_id,matricula,perfil)
                              VALUES(%s,%s,%s,%s,%s,%s,'funcionario')""", (employee,user,company,unit,team,f"P30-{index}"))
        cursor.execute("INSERT INTO turnos(id,empresa_id,nome,timezone) VALUES(%s,%s,'Normal','UTC'),(%s,%s,'Excecao','UTC')", (i["turn"],i["company"],i["other_turn"],i["company"]))
        cursor.execute("SELECT current_date AS today")
        database_today = cursor.fetchone()["today"]
        db_day = (database_today.weekday() + 1) % 7
        periods = [(1,"08:00","10:00"),(2,"11:00","13:00"),(3,"14:00","16:00"),(4,"17:00","19:00")]
        for turn in (i["turn"], i["other_turn"]):
            for order,start,end in periods:
                cursor.execute("INSERT INTO periodos_turno(empresa_id,turno_id,dia_semana,ordem,inicio,fim) VALUES(%s,%s,%s,%s,%s,%s)", (i["company"],turn,db_day,order,start,end))
        cursor.execute("""INSERT INTO funcionarios_turnos(id,empresa_id,funcionario_id,turno_id,vigencia_inicio)
                          VALUES(%s,%s,%s,%s,current_date-30)""", (i["assignment"],i["company"],i["employee"],i["turn"]))

    def _attempt(self, cursor, employee=None):
        employee = employee or self.ids["employee"]
        cursor.execute("""INSERT INTO tentativas_faciais(empresa_id,funcionario_id,resultado,motivo_codigo)
                          VALUES(%s,%s,'sucesso','match') RETURNING id""", (self.ids["company"], employee))
        return str(cursor.fetchone()["id"])

    def _confirm(self, connection, *, key=None, employee=None, attempt=None, legacy=None):
        employee = employee or self.ids["employee"]
        with connection.cursor() as cursor:
            attempt = attempt or self._attempt(cursor, employee)
            return confirm_expected_event(
                cursor, self.ids["company"], employee, key=key or str(uuid4()),
                channel="quiosque", facial_attempt_id=attempt, actor_user_id=None,
                legacy_type=legacy, default_timezone="UTC", grace_hours=12,
            )

    def test_00_migration_025_clean_install_and_upgrade_preserve_rows(self):
        phase25._reset_database(); phase25._apply_migrations(1, 24)
        connection = connect()
        marker = str(uuid4())
        try:
            with connection.cursor() as cursor:
                self._seed(cursor)
                cursor.execute("INSERT INTO marcacoes(id,empresa_id,funcionario_id,instante,tipo,origem,estado) VALUES(%s,%s,%s,clock_timestamp(),'entrada','manual','confirmada')", (marker,self.ids["company"],self.ids["employee"]))
            connection.commit()
            with connection.cursor() as cursor:
                cursor.execute("SELECT row_to_json(m)::text snapshot FROM marcacoes m WHERE id=%s", (marker,)); before=cursor.fetchone()["snapshot"]
        finally: connection.close()
        phase25._apply_migrations(25,25)
        connection=connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id,tipo,instante,origem,estado FROM marcacoes WHERE id=%s",(marker,)); self.assertEqual(str(cursor.fetchone()["id"]),marker)
                cursor.execute("SELECT to_regclass('public.jornadas_diarias') j,to_regclass('public.escalas_diarias') e"); row=cursor.fetchone(); self.assertIsNotNone(row["j"]); self.assertIsNotNone(row["e"])
        finally: connection.close()
        phase25._reset_database(); phase25._apply_migrations(1,25)

    def test_01_turn_schedule_four_periods_and_snapshot_has_no_pii(self):
        connection=connect()
        try:
            with connection.cursor() as cursor:
                result=resolve_next_event(cursor,self.ids["company"],self.ids["employee"],default_timezone="UTC",actor_user_id=self.ids["user"])
                self.assertEqual(result["origem"],"turno"); self.assertEqual(result["total_eventos"],8); self.assertEqual(result["proximo"]["tipo"],"entrada")
                cursor.execute("SELECT row_to_json(j)::text value FROM jornadas_diarias j WHERE id=%s",(result["snapshot_id"],)); raw=cursor.fetchone()["value"].lower()
                for forbidden in ("synthetic","p30-","cpf","matricula","embedding"): self.assertNotIn(forbidden,raw)
            connection.commit()
        finally: connection.close()

    def test_02_scale_priority_folga_cancellation_and_tenant_fk(self):
        i=self.ids; connection=connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_date AS today"); today=cursor.fetchone()["today"]
                cursor.execute("""INSERT INTO escalas_diarias(empresa_id,funcionario_id,data_operacional,tipo,origem,turno_id,justificativa,criado_por_usuario_id)
                                  VALUES(%s,%s,%s,'folga','ajuste',NULL,'Folga sintética',%s) RETURNING id""",(i["company"],i["second_employee"],today,i["user"])); scale=cursor.fetchone()["id"]
                result=resolve_next_event(cursor,i["company"],i["second_employee"],default_timezone="UTC",actor_user_id=i["second_user"])
                self.assertEqual((result["origem"],result["estado"],result["total_eventos"]),("folga","folga",0))
                with self.assertRaises(psycopg2.Error):
                    cursor.execute("INSERT INTO escalas_diarias(empresa_id,funcionario_id,data_operacional,tipo,origem,justificativa,criado_por_usuario_id) VALUES(%s,%s,%s,'folga','ajuste','Duplicada',%s)",(i["company"],i["second_employee"],today,i["user"]))
            connection.rollback()
            with connection.cursor() as cursor:
                with self.assertRaises(psycopg2.Error):
                    cursor.execute("INSERT INTO escalas_diarias(empresa_id,funcionario_id,data_operacional,tipo,origem,justificativa,criado_por_usuario_id) VALUES(%s,%s,%s,'folga','ajuste','Cross tenant',%s)",(i["foreign_company"],i["employee"],today+timedelta(days=1),i["foreign_user"]))
        finally: connection.rollback(); connection.close()

    def test_03_snapshot_materialization_is_concurrent_and_immutable(self):
        barrier=threading.Barrier(2)
        def worker(_):
            connection=connect()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT current_date AS today"); today=cursor.fetchone()["today"]
                    barrier.wait(); snapshot,_,_=materialize_snapshot(cursor,self.ids["company"],self.ids["employee"],today,default_timezone="UTC")
                connection.commit(); return str(snapshot["id"])
            finally: connection.close()
        with ThreadPoolExecutor(max_workers=2) as pool: ids=list(pool.map(worker,range(2)))
        self.assertEqual(len(set(ids)),1)
        connection=connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT count(*) total FROM jornadas_diarias"); self.assertEqual(cursor.fetchone()["total"],1)
                cursor.execute("SELECT count(*) total FROM jornada_eventos_esperados"); self.assertEqual(cursor.fetchone()["total"],8)
                with self.assertRaises(psycopg2.Error): cursor.execute("UPDATE jornadas_diarias SET timezone='Etc/UTC' WHERE id=%s",(ids[0],))
        finally: connection.rollback(); connection.close()

    def test_04_server_type_legacy_mismatch_and_original_immutability(self):
        connection=connect()
        try:
            before=None
            result=self._confirm(connection,legacy="entrada")
            self.assertEqual(result["marking"]["tipo"],"entrada")
            marking_id=result["marking"]["id"]
            with connection.cursor() as cursor:
                cursor.execute("SELECT row_to_json(m)::text snapshot FROM marcacoes m WHERE id=%s",(marking_id,)); before=cursor.fetchone()["snapshot"]
            connection.commit()
            with connection.cursor() as cursor:
                attempt=self._attempt(cursor)
                mismatch=confirm_expected_event(cursor,self.ids["company"],self.ids["employee"],key=str(uuid4()),channel="quiosque",facial_attempt_id=attempt,actor_user_id=None,legacy_type="saida",default_timezone="UTC")
                self.assertIsNone(mismatch["marking"]); self.assertEqual(mismatch["code"],"tipo_legado_divergente")
                cursor.execute("SELECT row_to_json(m)::text snapshot FROM marcacoes m WHERE id=%s",(marking_id,)); self.assertEqual(cursor.fetchone()["snapshot"],before)
                cursor.execute("SELECT count(*) total FROM ocorrencias WHERE tipo='ordem_invalida'"); self.assertEqual(cursor.fetchone()["total"],1)
            connection.commit()
        finally: connection.close()

    def test_05_idempotency_reuses_same_operation_and_rejects_different(self):
        connection=connect(); key=str(uuid4())
        try:
            with connection.cursor() as cursor: attempt=self._attempt(cursor)
            first=self._confirm(connection,key=key,attempt=attempt); connection.commit()
            second=self._confirm(connection,key=key,attempt=attempt)
            self.assertTrue(second["reused"]); self.assertEqual(second["marking"]["id"],first["marking"]["id"])
            with connection.cursor() as cursor: other=self._attempt(cursor)
            with self.assertRaises(JourneyError) as raised: self._confirm(connection,key=key,attempt=other)
            self.assertEqual(raised.exception.code,"idempotencia_conflitante")
        finally: connection.rollback(); connection.close()

    def test_06_two_connections_create_only_one_marking_for_event(self):
        barrier=threading.Barrier(2)
        attempts=[]
        seed=connect()
        try:
            with seed.cursor() as cursor: attempts=[self._attempt(cursor),self._attempt(cursor)]
            seed.commit()
        finally: seed.close()
        def worker(index):
            connection=connect()
            try:
                with connection.cursor() as cursor:
                    barrier.wait()
                    try:
                        result=confirm_expected_event(cursor,self.ids["company"],self.ids["employee"],key=str(uuid4()),channel="quiosque",facial_attempt_id=attempts[index],actor_user_id=None,default_timezone="UTC")
                        connection.commit(); return "created" if result["marking"] else "analysis"
                    except JourneyError as exc:
                        connection.rollback(); return exc.code
            finally: connection.close()
        with ThreadPoolExecutor(max_workers=2) as pool: outcomes=list(pool.map(worker,range(2)))
        self.assertEqual(outcomes.count("created"),1); self.assertIn("marcacao_recente",outcomes)
        connection=connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT count(*) total,count(distinct jornada_evento_id) events FROM marcacoes WHERE empresa_id=%s AND funcionario_id=%s",(self.ids["company"],self.ids["employee"])); row=cursor.fetchone(); self.assertEqual((row["total"],row["events"]),(1,1))
        finally: connection.close()

    def test_07_no_schedule_and_completed_attempts_are_preserved_without_mark(self):
        connection=connect()
        try:
            result=self._confirm(connection,employee=self.ids["second_employee"])
            self.assertIsNone(result["marking"]); self.assertEqual(result["decision"]["estado"],"sem_jornada")
            connection.commit()
            with connection.cursor() as cursor:
                cursor.execute("SELECT count(*) total FROM tentativas_jornada WHERE funcionario_id=%s",(self.ids["second_employee"],)); self.assertEqual(cursor.fetchone()["total"],1)
                cursor.execute("SELECT count(*) total FROM marcacoes WHERE funcionario_id=%s",(self.ids["second_employee"],)); self.assertEqual(cursor.fetchone()["total"],0)
        finally: connection.close()

    def test_08_approved_effective_inclusion_advances_sequence_rejected_does_not(self):
        connection=connect()
        try:
            first=self._confirm(connection); connection.commit()
            with connection.cursor() as cursor:
                cursor.execute("""INSERT INTO correcoes(empresa_id,funcionario_id,solicitante_usuario_id,responsavel_decisao_usuario_id,tipo,categoria,instante_proposto,tipo_marcacao_proposto,motivo,estado,decided_at)
                                  VALUES(%s,%s,%s,%s,'inclusao','esquecimento_marcacao',clock_timestamp(),'saida_intervalo','Sintético','aprovada',clock_timestamp())""",(self.ids["company"],self.ids["employee"],self.ids["user"],self.ids["user"]))
                current=resolve_next_event(cursor,self.ids["company"],self.ids["employee"],default_timezone="UTC")
                self.assertEqual(current["proximo"]["tipo"],"retorno_intervalo")
                cursor.execute("""INSERT INTO correcoes(empresa_id,funcionario_id,solicitante_usuario_id,responsavel_decisao_usuario_id,tipo,categoria,instante_proposto,tipo_marcacao_proposto,motivo,estado,decisao,decided_at)
                                  VALUES(%s,%s,%s,%s,'inclusao','esquecimento_marcacao',clock_timestamp(),'saida','Sintético','rejeitada','Negada',clock_timestamp())""",(self.ids["company"],self.ids["employee"],self.ids["user"],self.ids["user"]))
                unchanged=resolve_next_event(cursor,self.ids["company"],self.ids["employee"],default_timezone="UTC")
                self.assertEqual(unchanged["proximo"]["tipo"],"retorno_intervalo")
            connection.commit()
        finally: connection.close()

    def test_09_query_after_midnight_prefers_previous_open_operational_day(self):
        connection=connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT clock_timestamp() AS now, current_date AS today")
                clock=cursor.fetchone()
                operational_day=clock["today"]-timedelta(days=1)
                cursor.execute(
                    """INSERT INTO jornadas_diarias
                       (empresa_id,funcionario_id,data_operacional,timezone,origem,turno_id,atribuicao_turno_id)
                       VALUES(%s,%s,%s,'UTC','turno',%s,%s) RETURNING id""",
                    (self.ids["company"],self.ids["employee"],operational_day,self.ids["turn"],self.ids["assignment"]),
                )
                journey_id=cursor.fetchone()["id"]
                cursor.execute(
                    """INSERT INTO jornada_eventos_esperados
                       (empresa_id,jornada_id,ordem,tipo,instante_esperado)
                       VALUES(%s,%s,1,'entrada',%s),(%s,%s,2,'saida',%s)""",
                    (self.ids["company"],journey_id,clock["now"]-timedelta(hours=3),
                     self.ids["company"],journey_id,clock["now"]+timedelta(hours=3)),
                )
                result=resolve_next_event(cursor,self.ids["company"],self.ids["employee"],now=clock["now"],default_timezone="UTC")
                self.assertEqual(result["data_operacional"],operational_day.isoformat())
                self.assertEqual(result["proximo"]["tipo"],"entrada")
            connection.commit()
        finally: connection.close()

    def test_10_future_turn_override_and_logical_cancel_restore_assignment(self):
        connection=connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_date + 1 AS target")
                target=cursor.fetchone()["target"]
                weekday=(target.weekday()+1)%7
                cursor.execute(
                    """INSERT INTO funcionarios_turnos(empresa_id,funcionario_id,turno_id,vigencia_inicio)
                       VALUES(%s,%s,%s,current_date-1)""",
                    (self.ids["company"],self.ids["second_employee"],self.ids["turn"]),
                )
                for turn in (self.ids["turn"],self.ids["other_turn"]):
                    cursor.execute(
                        """INSERT INTO periodos_turno(empresa_id,turno_id,dia_semana,ordem,inicio,fim)
                           VALUES(%s,%s,%s,1,'09:00','18:00')""",
                        (self.ids["company"],turn,weekday),
                    )
                cursor.execute(
                    """INSERT INTO escalas_diarias
                       (empresa_id,funcionario_id,data_operacional,tipo,origem,turno_id,justificativa,criado_por_usuario_id)
                       VALUES(%s,%s,%s,'turno','troca',%s,'Troca sintética futura',%s) RETURNING id""",
                    (self.ids["company"],self.ids["second_employee"],target,self.ids["other_turn"],self.ids["user"]),
                )
                scale_id=cursor.fetchone()["id"]
                overridden=resolve_schedule_for_date(cursor,self.ids["company"],self.ids["second_employee"],target)
                self.assertEqual(overridden["origem"],"troca")
                self.assertEqual(overridden["turno"]["id"],self.ids["other_turn"])
                cursor.execute(
                    """UPDATE escalas_diarias SET cancelado_at=clock_timestamp(),
                       cancelado_por_usuario_id=%s,cancelamento_justificativa='Cancelamento sintético'
                       WHERE empresa_id=%s AND id=%s""",
                    (self.ids["user"],self.ids["company"],scale_id),
                )
                restored=resolve_schedule_for_date(cursor,self.ids["company"],self.ids["second_employee"],target)
                self.assertEqual(restored["origem"],"turno")
                self.assertEqual(restored["turno"]["id"],self.ids["turn"])
            connection.commit()
        finally: connection.close()

    def test_11_engine_exception_preserves_attempt_and_never_creates_marking(self):
        connection=connect()
        invalid_turn=str(uuid4())
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO turnos(id,empresa_id,nome,timezone) VALUES(%s,%s,'Invalid','Invalid/Zone')",
                    (invalid_turn,self.ids["company"]),
                )
                cursor.execute(
                    """INSERT INTO funcionarios_turnos(empresa_id,funcionario_id,turno_id,vigencia_inicio)
                       VALUES(%s,%s,%s,current_date-1)""",
                    (self.ids["company"],self.ids["second_employee"],invalid_turn),
                )
            result=self._confirm(connection,employee=self.ids["second_employee"])
            self.assertIsNone(result["marking"])
            self.assertEqual(result["decision"]["estado"],"excecao")
            self.assertEqual(result["code"],"timezone_invalido")
            connection.commit()
            with connection.cursor() as cursor:
                cursor.execute("SELECT count(*) total FROM marcacoes WHERE funcionario_id=%s",(self.ids["second_employee"],))
                self.assertEqual(cursor.fetchone()["total"],0)
                cursor.execute("SELECT motivo_codigo FROM tentativas_jornada WHERE funcionario_id=%s",(self.ids["second_employee"],))
                self.assertEqual(cursor.fetchone()["motivo_codigo"],"timezone_invalido")
                cursor.execute("SELECT count(*) total FROM ocorrencias WHERE funcionario_id=%s AND tipo='ordem_invalida'",(self.ids["second_employee"],))
                self.assertEqual(cursor.fetchone()["total"],1)
        finally: connection.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
