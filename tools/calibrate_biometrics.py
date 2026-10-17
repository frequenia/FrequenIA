"""Executa calibracao agregada sem gravar dataset ou alterar perfil tecnico."""

import argparse
import json
from pathlib import Path

from services.biometric_calibration import aggregate_authorized_dataset


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset")
    parser.add_argument("--threshold", type=float, default=0.68)
    parser.add_argument("--authorized", action="store_true")
    args = parser.parse_args()
    result = aggregate_authorized_dataset(
        args.dataset,
        repository_root=Path(__file__).resolve().parents[1],
        authorized=args.authorized,
        threshold=args.threshold,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
