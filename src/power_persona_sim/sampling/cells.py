"""1·3단계 — 하드 필터와 셀 할당 (브리프 §5.1).

실측 교훈이 이 모듈의 설계를 정했다. `family_type`은 브리프가 가정한 4종이
아니라 **39종**이고, 브리프가 적은 값 중 `3세대 이상`·`부모와 거주`는 데이터에
아예 없다(실제 값은 `기타3세대`·`부모와 동거`). 리터럴 열거는 조용히 표본을
날려먹으므로 이 모듈은 **부분문자열 패턴 매칭**으로 판정한다.

셀은 굵게 유지한다 — 데이터셋이 변수 간 독립성을 가정하므로(§2.4) 교차 셀을
잘게 쪼개면 없는 교호작용을 있는 것처럼 읽게 된다. 3(연령) × 2(지역) × 2(가구).
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Any

import yaml

from ..contracts import CellSpec

WILDCARD = "*"


# ── 값 매처 ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ValueMatcher:
    """설정 파일이 쓰는 세 가지 표기를 하나로 다룬다.

    [서울, 경기, 인천]          정확히 일치
    {match_any: [자녀, 3세대]}  부분문자열 중 하나라도 포함
    "*"                        나머지 전부 (와일드카드)
    """

    exact: frozenset[str] = frozenset()
    contains: tuple[str, ...] = ()
    excludes: tuple[str, ...] = ()
    wildcard: bool = False

    @classmethod
    def parse(cls, spec: Any) -> ValueMatcher:
        if spec == WILDCARD:
            return cls(wildcard=True)
        if isinstance(spec, (list, tuple)):
            return cls(exact=frozenset(str(v) for v in spec))
        if isinstance(spec, dict):
            return cls(
                exact=frozenset(str(v) for v in (spec.get("in") or [])),
                contains=tuple(str(v) for v in (spec.get("match_any") or [])),
                excludes=tuple(str(v) for v in (spec.get("exclude_any") or [])),
            )
        raise ValueError(f"알 수 없는 매처 표기: {spec!r}")

    def matches(self, value: str) -> bool:
        if any(pat in value for pat in self.excludes):
            return False
        if self.wildcard:
            return True
        if value in self.exact:
            return True
        return any(pat in value for pat in self.contains)


# ── 설정 ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AgeBand:
    label: str
    min: int
    max: int

    def contains(self, age: int) -> bool:
        return self.min <= age <= self.max


@dataclass(frozen=True)
class CellsConfig:
    age_min: int
    age_max: int
    family_filter: ValueMatcher
    single_household: ValueMatcher
    keep_single_household_cell: bool
    age_bands: tuple[AgeBand, ...]
    regions: tuple[tuple[str, ValueMatcher], ...]
    households: tuple[tuple[str, ValueMatcher], ...]
    quota_survey: int
    quota_survey_min: int
    quota_idi: int
    quota_idi_min: int
    weight_source: str
    raw: dict[str, Any]


def _ordered_matchers(spec: dict[str, Any]) -> tuple[tuple[str, ValueMatcher], ...]:
    """와일드카드 수준은 항상 마지막으로 밀어 낸다 — '나머지 전부'가 먼저 먹으면 안 된다."""
    items = [(str(k), ValueMatcher.parse(v)) for k, v in spec.items()]
    return tuple(sorted(items, key=lambda kv: kv[1].wildcard))


def load_cells(path: Path | str) -> CellsConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TypeError(f"셀 설정이 매핑이 아닙니다: {path}")

    hard = raw.get("hard_filter") or {}
    age = hard.get("age") or {}
    single = hard.get("single_household") or {}
    axes = raw.get("axes") or {}
    quota = raw.get("quota") or {}

    age_bands = tuple(
        AgeBand(label=str(label), min=int(band["min"]), max=int(band["max"]))
        for label, band in (axes.get("age") or {}).items()
    )
    if not age_bands:
        raise ValueError(f"axes.age 가 비어 있습니다: {path}")

    survey = quota.get("survey") or {}
    idi = quota.get("idi") or {}

    return CellsConfig(
        age_min=int(age.get("min", 0)),
        age_max=int(age.get("max", 200)),
        family_filter=ValueMatcher.parse(hard.get("family_type") or {"match_any": []}),
        single_household=ValueMatcher.parse(single or {"in": []}),
        keep_single_household_cell=bool(single.get("keep_as_cell", False)),
        age_bands=age_bands,
        regions=_ordered_matchers(axes.get("region") or {}),
        households=_ordered_matchers(axes.get("household") or {}),
        quota_survey=int(survey.get("max", 40)),
        quota_survey_min=int(survey.get("min", 0)),
        quota_idi=int(idi.get("max", 2)),
        quota_idi_min=int(idi.get("min", 0)),
        weight_source=str(raw.get("weight_source", "")),
        raw=raw,
    )


# ── 1단계 하드 필터 ──────────────────────────────────────────────────


def is_single_household(family_type: str, config: CellsConfig) -> bool:
    return config.single_household.matches(family_type or "")


def passes_hard_filter(row: dict[str, Any], config: CellsConfig) -> bool:
    """연령대 + 가구 형태 하드 필터.

    1인 가구는 가족 동거 패턴에 걸리지 않지만, keep_single_household_cell이
    켜져 있으면 통과시켜 별도 소수 셀로 보낸다 (혼밥 프리미엄 수요 검증용).
    설정이 꺼져 있는데 통과시키면 브리프 의도와 어긋나므로 여기서 갈린다.
    """
    try:
        age = int(row.get("age"))
    except (TypeError, ValueError):
        return False
    if not config.age_min <= age <= config.age_max:
        return False

    family = str(row.get("family_type") or "")
    if is_single_household(family, config):
        return config.keep_single_household_cell
    return config.family_filter.matches(family)


# ── 3단계 셀 할당 ────────────────────────────────────────────────────


def _level(value: str, levels: tuple[tuple[str, ValueMatcher], ...]) -> str | None:
    for label, matcher in levels:
        if matcher.matches(value):
            return label
    return None


def cell_id_of(axes: dict[str, str]) -> str:
    return f"{axes['age']}_{axes['region']}_{axes['household']}"


def assign_axes(row: dict[str, Any], config: CellsConfig) -> dict[str, str] | None:
    """레코드 → 축 3개. 어느 한 축이라도 수준이 없으면 None (셀 밖)."""
    age = int(row["age"])
    band = next((b.label for b in config.age_bands if b.contains(age)), None)
    region = _level(str(row.get("province") or ""), config.regions)
    household = _level(str(row.get("family_type") or ""), config.households)
    if band is None or region is None or household is None:
        return None
    return {"age": band, "region": region, "household": household}


def build_cell_specs(config: CellsConfig) -> list[CellSpec]:
    """축의 곱집합으로 12셀을 만든다. 순서는 설정 파일 기재 순서를 따른다 —
    manifest 바이트 동일성이 여기 걸려 있다."""
    specs: list[CellSpec] = []
    for band, (region, _), (household, _) in product(
        config.age_bands, config.regions, config.households
    ):
        axes = {"age": band.label, "region": region, "household": household}
        specs.append(
            CellSpec(
                cell_id=cell_id_of(axes),
                axes=axes,
                quota_survey=config.quota_survey,
                quota_idi=config.quota_idi,
            )
        )
    return specs
