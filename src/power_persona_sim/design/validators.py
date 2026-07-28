"""문항 유형별 무결성 검사.

여기서 잡는 것은 **구조 결함**이다 — 형식이 요구하는 값이 없거나 범위를 벗어난
경우. 설계 규율(커버리지) 위반은 `coverage.py`가 따로 본다. 둘을 섞지 않는 이유는
전자는 파일이 잘못 쓰인 것이고 후자는 설계가 잘못 짜인 것이라, 고치는 사람도
고치는 방법도 다르기 때문이다.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from ..contracts import Question, QuestionType
from .schema import (
    KNOWN_TRUTH_KINDS,
    MAXDIFF_ATTRIBUTE_COUNT,
    MAXDIFF_ITEMS_PER_SET_RANGE,
    MAXDIFF_MIN_APPEARANCES,
    SECTIONS,
    VW_ROLES,
)

_NO_OPTION_TYPES = (QuestionType.OPEN, QuestionType.NUMERIC, QuestionType.VAN_WESTENDORP)

_KNOWN_TRUTH_REQUIRED = {"source", "claim", "expect"}
_KNOWN_TRUTH_OPTIONAL = {"note"}
_KNOWN_TRUTH_FIELDS = {
    "top_option": ("value",),
    "rank_order": ("order",),
    "segment_gap": ("segment_by", "option", "higher", "lower"),
}
# 기대값이 선택지 라벨을 직접 가리키는 키 (rank_order는 order 리스트라 따로 다룬다)
_OPTION_REF_KEY = {"top_option": "value", "segment_gap": "option"}


def question_config(question: Question) -> dict[str, Any]:
    """QuestionSpec이면 config를, 순수 Question이면 빈 매핑을 준다."""
    return getattr(question, "config", None) or {}


def validate_questions(questions: list[Question], errors: list[str]) -> None:
    for question in questions:
        where = f"문항 {question.id}"
        _validate_common(question, where, errors)
        _QTYPE_RULES[question.qtype](question, where, errors)
        if question.known_truth is not None:
            _validate_known_truth(question, where, errors)
    _validate_van_westendorp_sets(questions, errors)


def _validate_common(question: Question, where: str, errors: list[str]) -> None:
    if question.section not in SECTIONS:
        errors.append(f"{where}: 섹션 '{question.section}'은 {list(SECTIONS)} 중 하나여야 함")
    if question.scale_points is not None and question.qtype != QuestionType.SCALE:
        errors.append(f"{where}: scale_points는 scale 문항에만 쓴다")
    if question.options and question.qtype in _NO_OPTION_TYPES:
        errors.append(f"{where}: {question.qtype.value} 문항은 options를 갖지 않는다")


def _rule_choice(question: Question, where: str, errors: list[str]) -> None:
    if len(question.options) < 2:
        errors.append(f"{where}: {question.qtype.value} 문항은 선택지가 2개 이상이어야 함")


def _rule_rank(question: Question, where: str, errors: list[str]) -> None:
    _rule_choice(question, where, errors)
    top_n = question_config(question).get("top_n")
    if top_n is None:
        return
    if not isinstance(top_n, int) or not 2 <= top_n <= len(question.options):
        errors.append(
            f"{where}: config.top_n은 2 이상 선택지 수({len(question.options)}) 이하의 정수여야 함"
        )


def _rule_maxdiff(question: Question, where: str, errors: list[str]) -> None:
    attributes = len(question.options)
    if attributes != MAXDIFF_ATTRIBUTE_COUNT:
        errors.append(
            f"{where}: MaxDiff 속성은 정확히 {MAXDIFF_ATTRIBUTE_COUNT}개여야 함 (현재 {attributes}개)"
        )
    config = question_config(question)
    sets, per_set = config.get("sets"), config.get("items_per_set")
    low, high = MAXDIFF_ITEMS_PER_SET_RANGE
    if not isinstance(sets, int) or sets < 1:
        errors.append(f"{where}: config.sets(세트 수)는 1 이상의 정수여야 함")
        return
    if not isinstance(per_set, int) or not low <= per_set <= high:
        errors.append(f"{where}: config.items_per_set은 {low}~{high} 사이의 정수여야 함")
        return
    if per_set > attributes:
        errors.append(f"{where}: 세트당 제시 수({per_set})가 속성 수({attributes})보다 많음")
        return
    slots, needed = sets * per_set, MAXDIFF_MIN_APPEARANCES * attributes
    if slots < needed:
        errors.append(
            f"{where}: 세트 구성 부족 — {sets}세트 × {per_set}개 = {slots}슬롯이지만 "
            f"속성당 {MAXDIFF_MIN_APPEARANCES}회 노출에는 {needed}슬롯이 필요함"
        )


def _rule_van_westendorp(question: Question, where: str, errors: list[str]) -> None:
    config = question_config(question)
    if not isinstance(config.get("vw_set"), str):
        errors.append(f"{where}: config.vw_set(가격 세트 식별자)이 필요함")
    if config.get("vw_role") not in VW_ROLES:
        errors.append(f"{where}: config.vw_role은 {list(VW_ROLES)} 중 하나여야 함")


def _rule_scale(question: Question, where: str, errors: list[str]) -> None:
    if not isinstance(question.scale_points, int) or question.scale_points < 3:
        errors.append(f"{where}: scale 문항은 scale_points가 3 이상의 정수여야 함")


def _rule_numeric(question: Question, where: str, errors: list[str]) -> None:
    config = question_config(question)
    low, high = config.get("min"), config.get("max")
    numeric = (int, float)
    if isinstance(low, numeric) and isinstance(high, numeric) and low >= high:
        errors.append(f"{where}: config.min({low})은 config.max({high})보다 작아야 함")


def _rule_open(question: Question, where: str, errors: list[str]) -> None:
    """개방형은 공통 검사(options·scale_points 금지)로 충분하다."""


_QTYPE_RULES = {
    QuestionType.SINGLE: _rule_choice,
    QuestionType.MULTI: _rule_choice,
    QuestionType.RANK: _rule_rank,
    QuestionType.MAXDIFF: _rule_maxdiff,
    QuestionType.VAN_WESTENDORP: _rule_van_westendorp,
    QuestionType.SCALE: _rule_scale,
    QuestionType.NUMERIC: _rule_numeric,
    QuestionType.OPEN: _rule_open,
}


def _validate_van_westendorp_sets(questions: list[Question], errors: list[str]) -> None:
    """VW는 4문항이 한 벌로만 의미가 있다 — 한 문항만 있으면 가격대 추정이 불가능하다."""
    groups: dict[Any, list[Question]] = defaultdict(list)
    for question in questions:
        if question.qtype == QuestionType.VAN_WESTENDORP:
            groups[question_config(question).get("vw_set")].append(question)
    for set_id, members in groups.items():
        roles = sorted(str(question_config(q).get("vw_role")) for q in members)
        if roles != sorted(VW_ROLES):
            errors.append(
                f"Van Westendorp 세트 '{set_id}': {list(VW_ROLES)} 4문항이 정확히 "
                f"한 번씩 있어야 함 — 현재 {roles}"
            )


def _validate_known_truth(question: Question, where: str, errors: list[str]) -> None:
    known_truth = question.known_truth
    if not isinstance(known_truth, dict):
        errors.append(f"{where}: known_truth는 매핑이어야 함")
        return
    missing = sorted(_KNOWN_TRUTH_REQUIRED - known_truth.keys())
    unknown = sorted(known_truth.keys() - _KNOWN_TRUTH_REQUIRED - _KNOWN_TRUTH_OPTIONAL)
    if missing:
        errors.append(f"{where}: known_truth 필수 키 누락 {missing}")
    if unknown:
        errors.append(f"{where}: known_truth에 알 수 없는 키 {unknown}")
    expect = known_truth.get("expect")
    if not isinstance(expect, dict) or expect.get("kind") not in KNOWN_TRUTH_KINDS:
        errors.append(
            f"{where}: known_truth.expect.kind는 {list(KNOWN_TRUTH_KINDS)} 중 하나여야 함"
        )
        return
    kind = expect["kind"]
    absent = [key for key in _KNOWN_TRUTH_FIELDS[kind] if key not in expect]
    if absent:
        errors.append(f"{where}: known_truth.expect({kind})에 {absent} 누락")
        return
    _validate_known_truth_options(question, kind, expect, where, errors)


def _validate_known_truth_options(
    question: Question, kind: str, expect: dict[str, Any], where: str, errors: list[str]
) -> None:
    """기대값이 실재하지 않는 선택지를 가리키면 검증 자체가 항상 실패한다."""
    if not question.options:
        return
    if kind == "rank_order":
        referenced = list(expect["order"])
    else:
        referenced = [expect[_OPTION_REF_KEY[kind]]]
    unknown = [label for label in referenced if label not in question.options]
    if unknown:
        errors.append(f"{where}: known_truth가 존재하지 않는 선택지를 가리킴 {unknown}")
