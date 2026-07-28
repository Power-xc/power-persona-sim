"""설계 문서(YAML)가 싣는 확장 스키마.

`contracts`의 Goal/Knowledge/Question/InterviewGuide는 병렬 개발의 고정점이라
건드리지 않는다. 브리프 §4가 요구하지만 계약에 자리가 없는 값 — 스크리닝 정의,
지식의 의사결정 연결 문구, 문항 유형별 파라미터, 프로빙 원칙 — 은 계약
데이터클래스를 **상속한** *Spec 으로 얹는다. 상속이라 isinstance 상 여전히 계약
타입이고, 다른 모듈은 이 파일을 몰라도 Survey를 그대로 소비할 수 있다.
계약 승격 제안은 작업 보고로 올린다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..contracts import Goal, InterviewGuide, Knowledge, Question

# 브리프 §4.3(a) — MaxDiff는 12속성 × 8세트로 고정 설계돼 있다.
MAXDIFF_ATTRIBUTE_COUNT = 12
MAXDIFF_ITEMS_PER_SET_RANGE = (3, 5)
# 속성 하나가 최소 두 번은 노출돼야 개인별 효용 추정이 선다.
MAXDIFF_MIN_APPEARANCES = 2

VW_ROLES = ("too_cheap", "cheap", "expensive", "too_expensive")

KNOWN_TRUTH_KINDS = ("top_option", "rank_order", "segment_gap")

SCREENER_SECTION = "S"
SECTIONS = ("S", "A", "B", "C", "D", "E", "F")


@dataclass(frozen=True)
class GoalSpec(Goal):
    """screening: 브리프 §4.1의 포함·세분·제외 정의."""

    screening: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class KnowledgeSpec(Knowledge):
    """decision_link: 이 지식이 어느 의사결정에 쓰이는지의 산문 설명.

    lever_ids가 형식적 연결이라면 이쪽은 사람이 읽는 근거다.
    """

    decision_link: str = ""


@dataclass(frozen=True)
class QuestionSpec(Question):
    """config: 문항 유형별 파라미터.

    maxdiff → sets·items_per_set / van_westendorp → vw_set·vw_role
    rank → top_n / numeric → unit·min·max / scale → anchor_low·anchor_high
    프로파일 문항 → persona_check(응답을 페르소나 원속성과 대조할 컬럼명)
    """

    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InterviewGuideSpec(InterviewGuide):
    """principles: 브리프 §4.3(b) 프로빙 원칙 — 이유 말고 사건을 물어라."""

    principles: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Prediction:
    """가설이 참일 때 특정 세그먼트에서 관측될 것으로 기대되는 방향."""

    segment: str
    expect: str


@dataclass(frozen=True)
class Hypothesis:
    id: str
    name: str
    statement: str
    knowledge_ids: list[str]
    question_ids: list[str]
    predictions: list[Prediction]
    prescription_if_supported: str
    prescription_if_rejected: str
