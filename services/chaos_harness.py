"""Falhas determinísticas exclusivamente para testes."""
import os

class ChaosDisabled(RuntimeError): pass
class InjectedFault(RuntimeError): pass

class ControlledClock:
    def __init__(self,value=0.0): self.value=float(value)
    def __call__(self): return self.value
    def advance(self,seconds): self.value+=float(seconds)

class ChaosHarness:
    ALLOWED={"db_before_commit","db_after_commit","storage_unavailable","storage_slow","checksum_mismatch","sqs_unavailable","worker_before_scan","worker_after_scan","worker_before_ack","scanner_timeout","scanner_unknown","stale_signature","manifest_truncated","restore_interrupted"}
    def __init__(self,scenario):
        if os.getenv("APP_ENV","").strip().lower() not in {"test","testing"} or os.getenv("FREQUENIA_CHAOS_TEST_TOKEN")!="phase29-test-only":
            raise ChaosDisabled("Caos só pode ser ativado por fixture explícita de teste.")
        if scenario not in self.ALLOWED: raise ChaosDisabled("Cenário de caos inválido.")
        self.scenario=scenario; self.triggered=False
    def checkpoint(self,name):
        if name==self.scenario:
            self.triggered=True; raise InjectedFault(name)
