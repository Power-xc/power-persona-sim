"""SampleManifest 직렬화 — 재현성의 물증.

같은 seed + 같은 config → **바이트 단위로 동일한** JSON이어야 한다.
그래서 세 가지를 못 박는다:

1. `sort_keys=True` — dict 삽입 순서에 결과가 흔들리지 않게.
2. 점수는 저장 전에 고정 자릿수로 반올림 — 부동소수 표현 차이 차단.
3. `created_at`은 계약대로 **호출자가 주입**한다. 여기서 시각을 읽으면
   재현성이 원천적으로 깨진다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..contracts import CellAssignment, CellSpec, SampleManifest

SCORE_PRECISION = 6


def _round(value: float) -> float:
    return round(float(value), SCORE_PRECISION)


def manifest_to_dict(manifest: SampleManifest) -> dict[str, Any]:
    return {
        "seed": manifest.seed,
        "source": manifest.source,
        "created_at": manifest.created_at,
        "signals_config": manifest.signals_config,
        "cells_config": manifest.cells_config,
        "cells": [
            {
                "cell_id": c.cell_id,
                "axes": c.axes,
                "quota_survey": c.quota_survey,
                "quota_idi": c.quota_idi,
            }
            for c in manifest.cells
        ],
        "assignments": [
            {
                "uuid": a.uuid,
                "cell_id": a.cell_id,
                "signal_score": _round(a.signal_score),
                "price_sensitivity_score": _round(a.price_sensitivity_score),
                "weight": _round(a.weight),
            }
            for a in manifest.assignments
        ],
    }


def manifest_from_dict(data: dict[str, Any]) -> SampleManifest:
    return SampleManifest(
        seed=int(data["seed"]),
        source=str(data["source"]),
        signals_config=data.get("signals_config") or {},
        cells_config=data.get("cells_config") or {},
        cells=[
            CellSpec(
                cell_id=c["cell_id"],
                axes=dict(c["axes"]),
                quota_survey=int(c["quota_survey"]),
                quota_idi=int(c["quota_idi"]),
            )
            for c in data.get("cells") or []
        ],
        assignments=[
            CellAssignment(
                uuid=a["uuid"],
                cell_id=a["cell_id"],
                signal_score=float(a["signal_score"]),
                price_sensitivity_score=float(a["price_sensitivity_score"]),
                weight=float(a.get("weight", 1.0)),
            )
            for a in data.get("assignments") or []
        ],
        created_at=str(data["created_at"]),
    )


def dumps(manifest: SampleManifest) -> str:
    """바이트 동일성이 걸린 유일한 직렬화 지점. 옵션을 바꾸면 재현성이 깨진다."""
    return (
        json.dumps(
            manifest_to_dict(manifest),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )


def loads(text: str) -> SampleManifest:
    return manifest_from_dict(json.loads(text))


def save_manifest(manifest: SampleManifest, path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(manifest), encoding="utf-8")
    return path


def load_manifest(path: Path | str) -> SampleManifest:
    return loads(Path(path).read_text(encoding="utf-8"))
