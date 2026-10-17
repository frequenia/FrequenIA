"""Eventos e métricas EMF sanitizados, sem dados pessoais ou chaves."""
import json
import logging
import time

LOGGER=logging.getLogger("frequenia.attachments")
ALLOWED={
    "event", "attachment_id", "correction_id", "job_id", "message_id",
    "result", "reason", "duration_ms", "count", "age_seconds",
}
METRIC_DIMENSIONS={"environment","process","result"}

def emit(event, **fields):
    payload={"event":event}
    payload.update({key:value for key,value in fields.items() if key in ALLOWED and value is not None})
    LOGGER.info(json.dumps(payload,sort_keys=True,separators=(",",":")))


def metric(name, value, unit="Count", **dimensions):
    """Emite EMF com dimensões deliberadamente limitadas e de baixa cardinalidade."""
    safe_dimensions={
        key:str(value)[:64] for key,value in dimensions.items()
        if key in METRIC_DIMENSIONS and value is not None
    }
    dimension_names=sorted(safe_dimensions)
    payload={
        "_aws":{
            "Timestamp":int(time.time()*1000),
            "CloudWatchMetrics":[{
                "Namespace":"FrequenIA/Attachments",
                "Dimensions":[dimension_names],
                "Metrics":[{"Name":str(name),"Unit":str(unit)}],
            }],
        },
        str(name):float(value),
        **safe_dimensions,
    }
    LOGGER.info(json.dumps(payload,sort_keys=True,separators=(",",":")))

class Timer:
    def __enter__(self): self.started=time.monotonic(); return self
    def __exit__(self,*_): self.duration_ms=round((time.monotonic()-self.started)*1000,2)
