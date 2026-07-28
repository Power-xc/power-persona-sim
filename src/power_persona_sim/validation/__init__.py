"""타당성 검증 모듈 — 4종 체크를 조합해 ValidationReport를 생산한다.

verdict 규칙(§6.2): known-truth 실패 또는 (기준분포가 주어졌을 때) 분포 부적합이면
"discard" — 시뮬레이션 결과 전체를 폐기한다. 자기일관성 미달 문항은 폐기 대신
excluded_question_ids로 빼고, 멀티모델 불일치는 details에 기록해 일치 항목만 채택하게 한다.
"""

from ..contracts import ResponseRecord, SampleManifest, Survey, ValidationReport
from .benchmark import load_benchmark
from .checks import (
    check_cross_model,
    check_distribution,
    check_known_truth,
    check_self_consistency,
)

__all__ = [
    "check_cross_model",
    "check_distribution",
    "check_known_truth",
    "check_self_consistency",
    "load_benchmark",
    "validate",
]


def validate(
    responses: list[ResponseRecord],
    manifest: SampleManifest,
    survey: Survey,
    benchmark: dict[str, float] | None = None,
) -> ValidationReport:
    """종합 검증. 시그니처는 contracts.ValidationFacade와 동일하며
    benchmark(셀별 기대 비율, configs/benchmarks/ 산출물)만 선택 인자로 받는다."""
    dist_check = check_distribution(manifest, benchmark)
    truth_check = check_known_truth(responses, survey, manifest=manifest)
    consistency_check, excluded = check_self_consistency(responses, survey)
    cross_check = check_cross_model(responses, survey)

    if not truth_check.passed or not dist_check.passed:
        verdict = "discard"
    else:
        verdict = "adopt"

    return ValidationReport(
        checks=[dist_check, truth_check, consistency_check, cross_check],
        verdict=verdict,
        excluded_question_ids=excluded,
    )
