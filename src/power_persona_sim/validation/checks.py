"""타당성 검증 4종 (PROJECT-BRIEF §6.2).

metrics는 계약(dict[str, float])에 맞춰 수치만 담고, 서술은 details에 둔다.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from itertools import combinations
from statistics import mean, pstdev

from scipy import stats

from ..contracts import (
    Question,
    QuestionType,
    ResponseRecord,
    SampleManifest,
    Survey,
    ValidationCheck,
)

RANK_TYPES = (QuestionType.RANK, QuestionType.MAXDIFF)
NUMERIC_TYPES = (QuestionType.SCALE, QuestionType.NUMERIC)


def check_distribution(
    manifest: SampleManifest, benchmark: dict[str, float] | None = None
) -> ValidationCheck:
    """표본 셀 분포 vs 기준 분포 χ² 적합도.

    benchmark는 {cell_id: 기대 비율}. configs/benchmarks/의 KOSIS·KREI 실측이
    들어온다. 미제공이면 검정을 수행할 수 없으므로 스킵으로 통과 처리하고
    details에 명시한다 — 균등분포 같은 임의 기준과의 비교는 무의미해서 하지 않는다.
    """
    counts = Counter(a.cell_id for a in manifest.assignments)
    if not counts:
        return ValidationCheck(
            name="distribution",
            passed=False,
            metrics={"cells": 0.0},
            details="표본이 비어 있다 — manifest.assignments가 0건.",
        )
    if not benchmark:
        return ValidationCheck(
            name="distribution",
            passed=True,
            metrics={"cells": float(len(counts)), "skipped": 1.0},
            details="기준 분포(benchmark) 미제공 — χ² 검정 스킵. "
            "configs/benchmarks/population-kr.yaml 연결 후 재검증할 것.",
        )

    cell_ids = sorted(set(counts) | set(benchmark))
    total = sum(counts.values())
    observed = [counts.get(c, 0) for c in cell_ids]
    bench_total = sum(benchmark.get(c, 0.0) for c in cell_ids) or 1.0
    expected = [total * benchmark.get(c, 0.0) / bench_total for c in cell_ids]
    # 기대도수 0 셀은 검정식에서 폭발하므로 최소값으로 보정
    expected = [max(e, 1e-9) for e in expected]

    chi2, p_value = stats.chisquare(observed, expected)
    passed = bool(p_value > 0.05)
    return ValidationCheck(
        name="distribution",
        passed=passed,
        metrics={
            "chi2": float(chi2),
            "p_value": float(p_value),
            "cells": float(len(cell_ids)),
            "n": float(total),
        },
        details=f"χ²={chi2:.2f}, p={p_value:.4f}, 셀 {len(cell_ids)}개 · 표본 {total}명. "
        + ("기준 분포와 적합." if passed else "기준 분포와 유의하게 다름 — 표본 재추출 필요."),
    )


#: 셀 ID("35-44_수도권_전체")를 만든 축 순서. segment_gap의 segment_by가 이걸 가리킨다.
_CELL_AXIS_INDEX = {"age_band": 0, "region": 1, "household": 2}


def _segments_of(manifest: SampleManifest | None, axis: str) -> dict[str, str]:
    """uuid → 세그먼트 라벨. 축을 모르면 빈 매핑(= 평가 불가)."""
    if manifest is None or axis not in _CELL_AXIS_INDEX:
        return {}
    index = _CELL_AXIS_INDEX[axis]
    segments = {}
    for assignment in manifest.assignments:
        parts = assignment.cell_id.split("_")
        if index < len(parts):
            segments[assignment.uuid] = parts[index]
    return segments


def _share(values: list, option: str) -> float | None:
    """해당 선택지를 고른 비율. 다지선다는 리스트 포함 여부로 본다."""
    counted = [v for v in values if v is not None]
    if not counted:
        return None
    hits = sum(
        1
        for v in counted
        if (option in v if isinstance(v, (list, tuple)) else v == option)
    )
    return hits / len(counted)


def _expect_matches(
    question: Question,
    expect: dict,
    values: list,
    uuids: list[str],
    segments: dict[str, str],
) -> int | None:
    """설계 YAML의 known_truth.expect 스키마를 채점한다.

    반환은 '재현으로 인정한 응답 수'이며, 채점 자체가 불가능하면 None이다.
    None을 0으로 뭉개면 "판정 불가"가 "재현 실패"로 둔갑해 결과를 폐기시킨다.
    """
    kind = expect.get("kind")

    if kind == "top_option":
        # 최빈 응답이 실제 1위와 일치하는가 — 전부 인정 아니면 전부 불인정
        counter = Counter(v for v in values if isinstance(v, str))
        if not counter:
            return 0
        return len(values) if counter.most_common(1)[0][0] == expect.get("value") else 0

    if kind == "rank_order":
        order = list(expect.get("order") or [])
        if not order:
            return None
        return sum(
            1
            for v in values
            if isinstance(v, (list, tuple)) and list(v[: len(order)]) == order
        )

    if kind == "segment_gap":
        # 절대 수치가 아니라 두 세그먼트 간 '방향'만 본다 (§6.3).
        if not segments:
            return None
        higher, lower = expect.get("higher"), expect.get("lower")
        option = expect.get("option")
        buckets: dict[str, list] = defaultdict(list)
        for value, uuid in zip(values, uuids, strict=True):
            label = segments.get(uuid)
            if label in (higher, lower):
                buckets[label].append(value)
        share_high = _share(buckets.get(higher, []), option)
        share_low = _share(buckets.get(lower, []), option)
        if share_high is None or share_low is None:
            return None
        return len(values) if share_high > share_low else 0

    return None


def _known_truth_matches(
    question: Question,
    values: list,
    uuids: list[str] | None = None,
    segments: dict[str, str] | None = None,
) -> int | None:
    expected = question.known_truth
    assert expected is not None
    # 설계 YAML이 싣는 형식 — {source, claim, expect:{kind, ...}, note}
    if isinstance(expected, dict) and isinstance(expected.get("expect"), dict):
        return _expect_matches(
            question, expected["expect"], values, uuids or [], segments or {}
        )
    if isinstance(expected, dict) and "range" in expected:
        lo, hi = expected["range"]
        return sum(1 for v in values if isinstance(v, (int, float)) and lo <= v <= hi)
    if isinstance(expected, dict) and "top_option" in expected:
        # 분포 재현 검사: 최빈 응답이 실제 1위 선택지와 일치하는가
        counter = Counter(v for v in values if isinstance(v, str))
        if not counter:
            return 0
        return len(values) if counter.most_common(1)[0][0] == expected["top_option"] else 0
    if isinstance(expected, list):
        return sum(1 for v in values if isinstance(v, list) and set(v) == set(expected))
    return sum(1 for v in values if v == expected)


def check_known_truth(
    responses: list[ResponseRecord],
    survey: Survey,
    min_reproduction_rate: float = 0.5,
    manifest: SampleManifest | None = None,
) -> ValidationCheck:
    """알려진 정답 대조 — 재현율이 임계치 미만인 문항이 하나라도 있으면 실패.

    "매치 0건일 때만 실패"는 수백 응답 중 1건 우연 일치로 통과해 버리므로
    비율 임계치를 쓴다. 실패 시 시뮬레이션 전체를 폐기한다(§6.2 ②).
    """
    kt_questions = [q for q in survey.questions if q.known_truth is not None]
    if not kt_questions:
        return ValidationCheck(
            name="known_truth",
            passed=True,
            metrics={"questions": 0.0},
            details="known-truth 문항 없음 — 대조 불가. 설계에 검증 문항을 심을 것.",
        )

    by_question: dict[str, list[ResponseRecord]] = defaultdict(list)
    for r in responses:
        by_question[r.question_id].append(r)

    # segment_gap 문항이 요구하는 축만 골라 uuid → 세그먼트 매핑을 만든다.
    segments: dict[str, dict[str, str]] = {}
    for q in kt_questions:
        expect = q.known_truth.get("expect") if isinstance(q.known_truth, dict) else None
        if isinstance(expect, dict) and expect.get("kind") == "segment_gap":
            axis = str(expect.get("segment_by", ""))
            segments.setdefault(axis, _segments_of(manifest, axis))

    failures: list[str] = []
    unscorable: list[str] = []
    rates: dict[str, float] = {}
    for q in kt_questions:
        records = by_question.get(q.id, [])
        if not records:
            failures.append(q.id)
            rates[q.id] = 0.0
            continue
        expect = q.known_truth.get("expect") if isinstance(q.known_truth, dict) else None
        axis = str(expect.get("segment_by", "")) if isinstance(expect, dict) else ""
        matches = _known_truth_matches(
            q,
            [r.parsed for r in records],
            [r.persona_uuid for r in records],
            segments.get(axis, {}),
        )
        if matches is None:
            # 채점 불가는 통과도 실패도 아니다 — 설계·입력을 고치라고 드러낸다.
            unscorable.append(q.id)
            rates[q.id] = 0.0
            failures.append(q.id)
            continue
        rate = matches / len(records)
        rates[q.id] = rate
        if rate < min_reproduction_rate:
            failures.append(q.id)

    passed = not failures
    detail_rates = ", ".join(
        f"{qid}=" + ("채점불가" if qid in unscorable else f"{rate:.0%}")
        for qid, rate in rates.items()
    )
    return ValidationCheck(
        name="known_truth",
        passed=passed,
        metrics={
            "questions": float(len(kt_questions)),
            "failed": float(len(failures)),
            "unscorable": float(len(unscorable)),
            "min_rate": min_reproduction_rate,
            **{f"rate_{qid}": rate for qid, rate in rates.items()},
        },
        details=f"재현율 [{detail_rates}], 임계치 {min_reproduction_rate:.0%}. "
        + ("전 문항 재현." if passed else f"실패 문항 {failures} — 결과 전체 폐기 대상.")
        + (
            f" 채점 불가 {unscorable} — 기대값 형식 또는 세그먼트 정보가 없어 대조하지 못했다."
            if unscorable
            else ""
        ),
    )


def _pairwise_tau(rank_lists: list[list]) -> list[float]:
    taus: list[float] = []
    for a, b in combinations(rank_lists, 2):
        pos_a = {item: i for i, item in enumerate(a)}
        pos_b = {item: i for i, item in enumerate(b)}
        common = sorted(set(pos_a) & set(pos_b))
        if len(common) < 2:
            continue
        tau, _ = stats.kendalltau(
            [pos_a[c] for c in common], [pos_b[c] for c in common]
        )
        if not math.isnan(tau):
            taus.append(float(tau))
    return taus


def check_self_consistency(
    responses: list[ResponseRecord],
    survey: Survey,
    tau_threshold: float = 0.6,
    numeric_std_threshold: float = 1.5,
) -> tuple[ValidationCheck, list[str]]:
    """자기일관성 — 동일 페르소나×문항 반복 간 안정성.

    순위형: 전 반복 쌍별 Kendall τ 평균 < 임계치면 문항 제외.
    수치형: 페르소나별 반복 표준편차 평균 > 임계치면 문항 제외.
    반환: (check, 제외 문항 id 목록)
    """
    grouped: dict[str, dict[str, list[ResponseRecord]]] = defaultdict(lambda: defaultdict(list))
    for r in responses:
        grouped[r.question_id][r.persona_uuid].append(r)

    excluded: list[str] = []
    q_scores: dict[str, float] = {}
    for question in survey.questions:
        per_persona = grouped.get(question.id)
        if not per_persona:
            continue

        if question.qtype in RANK_TYPES:
            taus: list[float] = []
            for recs in per_persona.values():
                ranks = [
                    r.parsed
                    for r in sorted(recs, key=lambda x: x.repetition)
                    if isinstance(r.parsed, list) and r.parsed
                ]
                if len(ranks) >= 2:
                    taus.extend(_pairwise_tau(ranks))
            if taus:
                avg = mean(taus)
                q_scores[question.id] = avg
                if avg < tau_threshold:
                    excluded.append(question.id)

        elif question.qtype in NUMERIC_TYPES:
            stds: list[float] = []
            for recs in per_persona.values():
                nums = [r.parsed for r in recs if isinstance(r.parsed, (int, float))]
                if len(nums) >= 2:
                    stds.append(pstdev(nums))
            if stds:
                avg_std = mean(stds)
                q_scores[question.id] = avg_std
                if avg_std > numeric_std_threshold:
                    excluded.append(question.id)

    passed = not excluded
    return (
        ValidationCheck(
            name="self_consistency",
            passed=passed,
            metrics={
                "tau_threshold": tau_threshold,
                "numeric_std_threshold": numeric_std_threshold,
                "excluded": float(len(excluded)),
                **{f"score_{qid}": score for qid, score in q_scores.items()},
            },
            details="일관성 미달 문항 없음."
            if passed
            else f"제외 문항 {excluded} — 순위형 τ<{tau_threshold} 또는 "
            f"수치형 σ>{numeric_std_threshold}. 해당 문항은 해석에서 뺀다.",
        ),
        excluded,
    )


def _question_conclusion(question: Question, values: list):
    """모델별 '결론' 요약 — 교차검증 비교 단위."""
    if question.qtype in NUMERIC_TYPES:
        nums = [v for v in values if isinstance(v, (int, float))]
        return round(mean(nums), 1) if nums else None
    if question.qtype in RANK_TYPES:
        firsts = [v[0] for v in values if isinstance(v, list) and v]
        return Counter(firsts).most_common(1)[0][0] if firsts else None
    texts = [v for v in values if isinstance(v, str)]
    return Counter(texts).most_common(1)[0][0] if texts else None


def check_cross_model(
    responses: list[ResponseRecord],
    survey: Survey,
    min_agreement: float = 0.7,
    numeric_tolerance: float = 1.0,
) -> ValidationCheck:
    """멀티모델 교차검증 — 문항별 결론이 모델 간 일치하는 비율(§6.2 ⑤).

    수치형은 모델별 평균 차가 tolerance 이내면 일치, 그 외는 최빈 결론 동일 여부.
    단일 모델 실행이면 적용 불가로 통과 처리한다.
    """
    models = sorted({r.model for r in responses})
    if len(models) < 2:
        return ValidationCheck(
            name="cross_model",
            passed=True,
            metrics={"models": float(len(models)), "skipped": 1.0},
            details=f"모델 {len(models)}개 — 교차검증 적용 불가(2개 이상 필요).",
        )

    by_q_model: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for r in responses:
        by_q_model[r.question_id][r.model].append(r.parsed)

    agreed = 0
    comparable = 0
    disagreed: list[str] = []
    for question in survey.questions:
        per_model = by_q_model.get(question.id)
        if not per_model or len(per_model) < 2:
            continue
        conclusions = [
            _question_conclusion(question, vals) for vals in per_model.values()
        ]
        if any(c is None for c in conclusions):
            continue
        comparable += 1
        if question.qtype in NUMERIC_TYPES:
            ok = max(conclusions) - min(conclusions) <= numeric_tolerance
        else:
            ok = len(set(conclusions)) == 1
        if ok:
            agreed += 1
        else:
            disagreed.append(question.id)

    rate = agreed / comparable if comparable else 0.0
    passed = bool(comparable and rate >= min_agreement)
    return ValidationCheck(
        name="cross_model",
        passed=passed,
        metrics={
            "models": float(len(models)),
            "comparable": float(comparable),
            "agreement_rate": rate,
            "min_agreement": min_agreement,
        },
        details=f"모델 {models} 간 결론 일치율 {rate:.0%} ({agreed}/{comparable}). "
        + ("" if passed else f"불일치 문항 {disagreed} — 일치 항목만 채택할 것."),
    )
