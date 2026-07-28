"""sampling — 3단계 필터, 셀 할당, 쿼터, 가중치 보정.

파사드는 contracts.SamplingFacade 시그니처를 그대로 따른다.

재현성 계약: **같은 seed + 같은 config → 바이트 단위로 동일한 SampleManifest.**
이를 위해 무작위 추출을 아예 쓰지 않는다. 정렬 키가 곧 표본이고, 동점은
seed로 소금친 해시로 깬다 — 난수 생성기의 구현·버전에 의존하지 않는 결정성이다.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ..contracts import CellAssignment, PersonaRecord, SampleManifest
from ..dataset import FixtureSource, get_source, to_persona_records
from .cells import (
    CellsConfig,
    ValueMatcher,
    assign_axes,
    build_cell_specs,
    cell_id_of,
    is_single_household,
    load_cells,
    passes_hard_filter,
)
from .manifest import dumps, load_manifest, loads, save_manifest
from .signals import ScoreResult, SignalConfig, load_signals, score_text
from .weights import apply_weights, compute_weights, load_reference_shares, weighting_note

__all__ = [
    "CellsConfig",
    "ScoreResult",
    "SignalConfig",
    "ValueMatcher",
    "apply_weights",
    "assign_axes",
    "build_cell_specs",
    "build_sample",
    "cell_id_of",
    "compute_weights",
    "dumps",
    "is_single_household",
    "load_cells",
    "load_manifest",
    "load_personas",
    "load_reference_shares",
    "load_signals",
    "loads",
    "passes_hard_filter",
    "sample_diagnostics",
    "save_manifest",
    "score_text",
    "select_idi",
    "weighting_note",
]

#: 계약이 규정한 created_at 부재 시의 표식. 시각을 여기서 읽으면 재현성이 깨진다.
UNSET_CREATED_AT = "unset"


def _tiebreak(seed: int, uuid: str) -> str:
    """동점자 순서를 seed에 종속시킨다.

    uuid 사전순으로만 자르면 seed를 바꿔도 같은 사람이 뽑혀 시드의 의미가 없다.
    난수 대신 해시를 쓰는 이유는 파이썬 버전이 바뀌어도 값이 고정되기 때문이다.
    """
    return hashlib.blake2b(f"{seed}:{uuid}".encode(), digest_size=16).hexdigest()


def _rank_key(seed: int, uuid: str, score: float) -> tuple[float, str, str]:
    # 점수 내림차순 → seed 해시 오름차순 → uuid 오름차순 (완전 순서, 동점 없음)
    return (-score, _tiebreak(seed, uuid), uuid)


def build_sample(
    signals_path: Path,
    cells_path: Path,
    seed: int,
    source: str,
    *,
    created_at: str = UNSET_CREATED_AT,
    rows: Sequence[dict[str, Any]] | None = None,
    source_kwargs: dict[str, Any] | None = None,
    reference_shares: dict[str, float] | None = None,
) -> SampleManifest:
    """3단계 필터를 돌려 재현 가능한 표본을 만든다.

    rows를 직접 주면 그것을 쓰고(테스트·오프라인), 아니면 source 문자열로
    접근 경로를 되살려 가져온다.
    """
    signals = load_signals(signals_path)
    cells = load_cells(cells_path)

    if rows is None:
        rows = get_source(source, **(source_kwargs or {})).fetch()

    # 1단계 하드 필터 → 2단계 스코어링 → 3단계 셀 할당
    scored: dict[str, list[tuple[tuple[float, str, str], CellAssignment]]] = defaultdict(list)
    for row in rows:
        if not passes_hard_filter(row, cells):
            continue
        axes = assign_axes(row, cells)
        if axes is None:
            continue
        result = score_text(str(row.get(signals.text_field) or ""), signals)
        uuid = str(row["uuid"])
        assignment = CellAssignment(
            uuid=uuid,
            cell_id=cell_id_of(axes),
            signal_score=result.total,
            price_sensitivity_score=result.price_sensitivity,
        )
        scored[assignment.cell_id].append((_rank_key(seed, uuid, result.total), assignment))

    # 셀당 쿼터. 셀 순서는 설정 파일 축 순서를 따르고, 셀 내부는 랭크 순서다.
    specs = build_cell_specs(cells)
    assignments: list[CellAssignment] = []
    for spec in specs:
        bucket = sorted(scored.get(spec.cell_id, []), key=lambda item: item[0])
        assignments.extend(a for _, a in bucket[: spec.quota_survey])

    reference = reference_shares if reference_shares is not None else {}
    assignments = apply_weights(assignments, reference)

    return SampleManifest(
        seed=seed,
        source=source,
        signals_config=signals.raw,
        cells_config=cells.raw,
        cells=specs,
        assignments=assignments,
        created_at=created_at,
    )


def select_idi(manifest: SampleManifest) -> list[CellAssignment]:
    """IDI 대상 — 셀별 상위 quota_idi명.

    manifest.assignments는 이미 셀별 랭크 순서라 앞에서 자르면 된다.
    별도 저장하지 않는 이유는 CellAssignment에 역할 필드가 없기 때문이다
    (contracts 변경 제안 참고). 파생 규칙이 결정적이라 저장과 동치다.
    """
    quotas = {c.cell_id: c.quota_idi for c in manifest.cells}
    seen: dict[str, int] = defaultdict(int)
    picked: list[CellAssignment] = []
    for a in manifest.assignments:
        if seen[a.cell_id] < quotas.get(a.cell_id, 0):
            seen[a.cell_id] += 1
            picked.append(a)
    return picked


def sample_diagnostics(manifest: SampleManifest) -> dict[str, Any]:
    """쿼터 미달 셀을 드러낸다. 조용한 미달은 '표본을 채웠다'는 착시를 만든다."""
    counts: dict[str, int] = defaultdict(int)
    for a in manifest.assignments:
        counts[a.cell_id] += 1
    cells_cfg = manifest.cells_config.get("quota", {}).get("survey", {})
    floor = int(cells_cfg.get("min", 0))
    short = {
        c.cell_id: {"selected": counts.get(c.cell_id, 0), "floor": floor}
        for c in manifest.cells
        if counts.get(c.cell_id, 0) < floor
    }
    return {
        "total": len(manifest.assignments),
        "per_cell": {c.cell_id: counts.get(c.cell_id, 0) for c in manifest.cells},
        "cells_below_floor": short,
        "empty_cells": [c.cell_id for c in manifest.cells if not counts.get(c.cell_id)],
    }


def load_personas(
    manifest: SampleManifest,
    *,
    rows: Sequence[dict[str, Any]] | None = None,
    source_kwargs: dict[str, Any] | None = None,
) -> list[PersonaRecord]:
    """manifest의 uuid 순서 그대로 PersonaRecord를 복원한다.

    manifest에 원본 위치(파일 경로·샤드)를 적을 필드가 없어서 source 문자열만으로
    되살린다 — fixture 경로는 기본 경로를 쓴다 (contracts 변경 제안 참고).
    """
    if rows is None:
        kwargs = source_kwargs or {}
        src = (
            FixtureSource(**kwargs)
            if manifest.source == "fixture"
            else get_source(manifest.source, **kwargs)
        )
        rows = src.fetch()

    by_uuid = {str(r["uuid"]): r for r in rows}
    missing = [a.uuid for a in manifest.assignments if a.uuid not in by_uuid]
    if missing:
        raise KeyError(
            f"원본에 없는 uuid {len(missing)}개 (예: {missing[:3]}) — "
            f"manifest의 source({manifest.source})와 실제 데이터가 어긋납니다."
        )
    return to_persona_records([by_uuid[a.uuid] for a in manifest.assignments])
