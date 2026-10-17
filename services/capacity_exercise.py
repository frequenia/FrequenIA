"""Carga sintética limitada, determinística e sem I/O externo."""
import math
import os
import time
from concurrent.futures import ThreadPoolExecutor

class CapacityExerciseError(ValueError): pass

def _percentile(values,percentile):
    ordered=sorted(values); index=max(0,min(len(ordered)-1,math.ceil(percentile*len(ordered))-1)); return ordered[index]

def run_capacity_exercise(message_count=100,workers=2,clock=None,processor=None):
    if os.getenv("APP_ENV","").strip().lower() not in {"test","testing"}: raise CapacityExerciseError("Carga sintética só é permitida em teste.")
    count=int(message_count); worker_count=int(workers)
    if not 1<=count<=10000 or not 1<=worker_count<=32: raise CapacityExerciseError("Limite de carga inválido.")
    processor=processor or (lambda _index:None); max_backlog=count
    if clock is not None:
        started=clock(); latencies=[]; waits=[]
        for index in range(count):
            item_started=clock(); waits.append(0.0); processor(index); latencies.append(max((clock()-item_started)*1000,0.001))
        elapsed=max(clock()-started,0.000001)
    else:
        started=time.monotonic()
        def measured(index):
            item_started=time.monotonic(); wait=max((item_started-started)*1000,0.001)
            processor(index); return wait,max((time.monotonic()-item_started)*1000,0.001)
        with ThreadPoolExecutor(max_workers=worker_count) as pool: samples=list(pool.map(measured,range(count)))
        waits=[sample[0] for sample in samples]; latencies=[sample[1] for sample in samples]
        elapsed=max(time.monotonic()-started,0.000001)
    return {"evidence":"local_synthetic_not_production_slo","messages":count,"workers":worker_count,
        "throughput_per_second":count/elapsed,"p50_ms":_percentile(latencies,.50),"p95_ms":_percentile(latencies,.95),"p99_ms":_percentile(latencies,.99),
        "wait_p50_ms":_percentile(waits,.50),"wait_p95_ms":_percentile(waits,.95),"wait_p99_ms":_percentile(waits,.99),
        "backlog_peak":max_backlog,"backlog_drained":count,"recovery_seconds":elapsed,"retry_rate":0.0,"dlq_rate":0.0,"error_rate":0.0}
