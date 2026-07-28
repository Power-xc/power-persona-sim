"""모듈 간 계약 — 병렬 개발의 단일 기준점.

이 파일은 메인 세션이 소유한다. 각 모듈(dataset·sampling·design·runners·
validation·report)은 여기 정의된 데이터 구조를 소비/생산하고, 파일 하단의
파사드 시그니처를 자기 서브패키지 최상위(`__init__.py`)에서 export 한다.
필드 추가가 필요하면 이 파일을 직접 고치지 말고 작업 보고에 제안으로 남긴다.

식별자는 항상 `uuid`다 — 데이터셋 동명이인 비율이 약 79%라 이름은 못 쓴다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

# ── 데이터셋 스키마 (실측 26컬럼) ──────────────────────────────────────

NARRATIVE_COLUMNS = (
    "persona",
    "culinary_persona",
    "family_persona",
    "professional_persona",
    "travel_persona",
    "sports_persona",
    "arts_persona",
)

ATTRIBUTE_COLUMNS = (
    "cultural_background",
    "skills_and_expertise",
    "skills_and_expertise_list",
    "hobbies_and_interests",
    "hobbies_and_interests_list",
    "career_goals_and_ambitions",
)

DEMOGRAPHIC_COLUMNS = (
    "sex",
    "age",
    "marital_status",
    "military_status",
    "family_type",
    "housing_type",
    "education_level",
    "bachelors_field",
    "occupation",
    "district",
    "province",
    "country",
)

ALL_COLUMNS = NARRATIVE_COLUMNS + ATTRIBUTE_COLUMNS + DEMOGRAPHIC_COLUMNS + ("uuid",)

HF_DATASET_ID = "nvidia/Nemotron-Personas-Korea"


@dataclass(frozen=True)
class PersonaRecord:
    """데이터셋 1행. 프롬프트 조립에 쓰는 필드만 명시하고 나머지는 raw에 보존."""

    uuid: str
    sex: str
    age: int
    marital_status: str
    family_type: str
    housing_type: str
    education_level: str
    occupation: str
    district: str
    province: str
    persona: str
    culinary_persona: str
    family_persona: str
    hobbies_and_interests: str
    raw: dict[str, Any] = field(default_factory=dict)


# ── 표본 (sampling) ──────────────────────────────────────────────────


@dataclass(frozen=True)
class CellSpec:
    """셀 정의. axes 예: {"age": "30-44", "region": "수도권", "household": "자녀동거"}"""

    cell_id: str
    axes: dict[str, str]
    quota_survey: int
    quota_idi: int


@dataclass(frozen=True)
class CellAssignment:
    uuid: str
    cell_id: str
    signal_score: float
    price_sensitivity_score: float
    weight: float = 1.0  # KREI 분포 사후 보정 가중치


@dataclass(frozen=True)
class SampleManifest:
    """재현 가능한 표본의 전부. 같은 seed + 같은 config → 동일 manifest."""

    seed: int
    source: str  # "remote-duckdb" | "local-parquet" | "fixture"
    signals_config: dict[str, Any]
    cells_config: dict[str, Any]
    cells: list[CellSpec]
    assignments: list[CellAssignment]
    created_at: str  # ISO 8601, 호출자가 주입


# ── 조사 설계 (design) ───────────────────────────────────────────────


class QuestionType(str, Enum):
    SINGLE = "single"
    MULTI = "multi"
    RANK = "rank"
    MAXDIFF = "maxdiff"
    VAN_WESTENDORP = "van_westendorp"
    SCALE = "scale"
    NUMERIC = "numeric"
    OPEN = "open"


@dataclass(frozen=True)
class Lever:
    """GOAL의 의사결정 레버. 예: 인지·도달 / 제품 사양 / 가격 / 유통 / 메시지"""

    id: str
    name: str


@dataclass(frozen=True)
class Goal:
    business_goal: str
    decision: str
    levers: list[Lever]
    success_criteria: str
    one_sentence: str  # "X를 사는 사람이 우리를 안 사는 이유는 …" 꼴


@dataclass(frozen=True)
class Knowledge:
    """K 블록. lever_ids가 비어 있으면 커버리지 규율 위반 — 삭제 대상."""

    id: str  # "K1" …
    statement: str
    lever_ids: list[str]
    judgement_rule: str  # "이 결과면 이렇게 한다"


@dataclass(frozen=True)
class Question:
    id: str
    section: str  # "S" | "A" | "B" | "C" | "D" | "E" | "F"
    text: str
    qtype: QuestionType
    knowledge_ids: list[str]
    options: list[str] = field(default_factory=list)
    scale_points: int | None = None
    known_truth: dict[str, Any] | None = None  # 실제 값을 아는 검증 문항이면 기대값 명세


@dataclass(frozen=True)
class Survey:
    id: str
    goal: Goal
    knowledge: list[Knowledge]
    questions: list[Question]


@dataclass(frozen=True)
class GuideBlock:
    t_start_min: int
    t_end_min: int
    knowledge_ids: list[str]
    script: str
    probes: list[str]


@dataclass(frozen=True)
class InterviewGuide:
    id: str
    duration_min: int
    blocks: list[GuideBlock]


# ── 실행 (runners) ───────────────────────────────────────────────────


@dataclass(frozen=True)
class RunConfig:
    adapter: str  # "mock" | "ollama" | "claude" | "gemini"
    model: str
    temperature: float
    seed: int
    repetitions: int  # 자기일관성 검증용 반복 횟수 (기본 3)
    prompt_version: str  # PREREG 등록 버전
    awareness_condition: str  # "natural" | "forced_unaware" (미인지 강제 주입 집단)
    dry_run: bool = True  # 유료 어댑터는 dry_run=False + 명시 승인 없이는 호출 불가


@dataclass(frozen=True)
class ResponseRecord:
    run_id: str
    persona_uuid: str
    question_id: str
    repetition: int
    seed: int
    model: str
    prompt_hash: str  # 시스템 프롬프트+문항의 fingerprint — PREREG 대조용
    raw_text: str
    parsed: Any  # 문항 유형별 파싱 결과 (순위 리스트, 척도 정수, 금액 등)


# ── 검증 (validation) ────────────────────────────────────────────────


@dataclass(frozen=True)
class ValidationCheck:
    name: str  # "distribution" | "known_truth" | "self_consistency" | "cross_model"
    passed: bool
    metrics: dict[str, float]
    details: str


@dataclass(frozen=True)
class ValidationReport:
    checks: list[ValidationCheck]
    verdict: str  # "adopt" | "discard" — known-truth 실패 시 무조건 discard
    excluded_question_ids: list[str]  # 자기일관성 τ<0.6 문항


# ── 모듈 파사드 — 각 서브패키지 __init__.py 가 이 이름들을 export ──────


class SamplingFacade(Protocol):
    def build_sample(
        self, signals_path: Path, cells_path: Path, seed: int, source: str
    ) -> SampleManifest: ...

    def load_personas(self, manifest: SampleManifest) -> list[PersonaRecord]: ...


class DesignFacade(Protocol):
    def load_survey(self, path: Path) -> Survey: ...

    def load_interview_guide(self, path: Path) -> InterviewGuide: ...

    def check_coverage(self, survey: Survey) -> list[str]:
        """커버리지 규율 위반 목록. 빈 리스트면 통과.
        위반 = 어떤 K에도 매핑 안 된 레버, 어떤 레버에도 매핑 안 된 K,
        어떤 문항에도 매핑 안 된 K."""
        ...


class RunnerFacade(Protocol):
    def assemble_system_prompt(self, persona: PersonaRecord, condition: str) -> str: ...

    def run_survey(
        self, survey: Survey, personas: list[PersonaRecord], config: RunConfig
    ) -> list[ResponseRecord]: ...


class ValidationFacade(Protocol):
    def validate(
        self,
        responses: list[ResponseRecord],
        manifest: SampleManifest,
        survey: Survey,
    ) -> ValidationReport: ...


class ReportFacade(Protocol):
    def render_report(
        self,
        survey: Survey,
        manifest: SampleManifest,
        responses: list[ResponseRecord],
        validation: ValidationReport,
        out_dir: Path,
    ) -> Path: ...
