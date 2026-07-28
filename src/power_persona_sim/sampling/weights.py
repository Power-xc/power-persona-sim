"""셀 가중치 사후 보정 — KREI 식품소비행태조사(2024) 훅.

지금은 **인터페이스만** 있다. 실제 KREI 셀별 모집단 비율표가 확보되면
`load_reference_shares()`가 그것을 읽고 `compute_weights()`가 그대로 동작한다.
기준 분포가 없을 때 임의의 숫자를 채워 넣으면 "가중치 보정을 했다"는 거짓
신호가 되므로, 그 경우 모든 가중치는 1.0으로 두고 명시적으로 미보정임을 남긴다.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

from ..contracts import CellAssignment


def load_reference_shares(path: Path | str | None) -> dict[str, float]:
    """셀별 모집단 비율표(YAML: {cell_id: share}). 없으면 빈 dict."""
    if path is None:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    shares = {str(k): float(v) for k, v in (raw.get("shares") or raw).items()}
    total = sum(shares.values())
    if total <= 0:
        return {}
    return {k: v / total for k, v in shares.items()}


def compute_weights(
    assignments: Sequence[CellAssignment], reference: dict[str, float]
) -> dict[str, float]:
    """셀별 가중치 = (모집단 비율) / (표본 비율).

    기준 분포가 비어 있으면 전 셀 1.0 — 미보정 상태를 숨기지 않는다.
    """
    if not assignments:
        return {}
    counts = Counter(a.cell_id for a in assignments)
    n = sum(counts.values())
    if not reference:
        return {cell: 1.0 for cell in counts}
    return {cell: (reference.get(cell, 0.0) / (c / n)) if c else 0.0 for cell, c in counts.items()}


def apply_weights(
    assignments: Sequence[CellAssignment], reference: dict[str, float]
) -> list[CellAssignment]:
    """CellAssignment.weight를 채운 새 리스트. 입력은 frozen이라 교체 생성한다."""
    weights = compute_weights(assignments, reference)
    return [
        CellAssignment(
            uuid=a.uuid,
            cell_id=a.cell_id,
            signal_score=a.signal_score,
            price_sensitivity_score=a.price_sensitivity_score,
            weight=round(weights.get(a.cell_id, 1.0), 6),
        )
        for a in assignments
    ]


def weighting_note(reference: dict[str, Any]) -> str:
    return (
        "KREI 실제 분포로 사후 보정됨"
        if reference
        else "미보정 (기준 분포 미확보 — 전 셀 weight=1.0)"
    )
