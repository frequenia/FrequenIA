"""Harness local de calibracao: somente agregados, sem promover limiares."""

from __future__ import annotations

import json
import math
from pathlib import Path
from statistics import mean


class CalibrationError(ValueError):
    pass


def aggregate_authorized_dataset(dataset_path, *, repository_root, authorized, threshold):
    path = Path(dataset_path).resolve()
    root = Path(repository_root).resolve()
    if not authorized:
        raise CalibrationError("dataset exige autorizacao explicita")
    if path == root or root in path.parents:
        raise CalibrationError("dataset de calibracao nao pode ficar dentro do Git")
    try:
        limit = float(threshold)
    except (TypeError, ValueError) as exc:
        raise CalibrationError("limiar invalido") from exc
    if not math.isfinite(limit) or not 0 < limit <= 2:
        raise CalibrationError("limiar invalido")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise CalibrationError("dataset invalido ou versao desconhecida")
    if data.get("authorization_reference") in (None, ""):
        raise CalibrationError("referencia de autorizacao ausente")
    samples = data.get("samples")
    if not isinstance(samples, list) or not samples:
        raise CalibrationError("amostra vazia")
    genuine = []
    impostor = []
    for sample in samples:
        if not isinstance(sample, dict) or set(sample) != {"label", "distance"}:
            raise CalibrationError("amostra contem campos proibidos")
        distance = float(sample["distance"])
        if not math.isfinite(distance) or not 0 <= distance <= 2:
            raise CalibrationError("distancia invalida")
        if sample["label"] == "genuine":
            genuine.append(distance)
        elif sample["label"] == "impostor":
            impostor.append(distance)
        else:
            raise CalibrationError("rotulo invalido")
    if not genuine or not impostor:
        raise CalibrationError("amostra deve conter pares genuinos e impostores")
    return {
        "schema_version": 1,
        "sample_size": len(samples),
        "genuine_count": len(genuine),
        "impostor_count": len(impostor),
        "threshold_evaluated": limit,
        "false_rejection_rate": sum(value > limit for value in genuine) / len(genuine),
        "false_acceptance_rate": sum(value <= limit for value in impostor) / len(impostor),
        "aggregate_distance": {
            "genuine_mean": mean(genuine), "impostor_mean": mean(impostor),
            "minimum": min(genuine + impostor), "maximum": max(genuine + impostor),
        },
        "automatic_promotion": False,
        "limitations": "Evidencia local; nao demonstra precisao ou equidade em producao.",
    }
