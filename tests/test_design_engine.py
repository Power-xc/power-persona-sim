"""설계 엔진 — 로더·유형 검증·커버리지 규율.

커버리지 검사의 값어치는 "통과한다"가 아니라 "고의로 깨뜨리면 잡는다"에 있다.
아래 fixture 세 벌은 브리프 §4.2가 규정한 위반 (a)(b)(c)를 하나씩 단독으로 재현한다.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from power_persona_sim.design import (
    DesignError,
    check_coverage,
    load_interview_guide,
    load_survey,
)

FIXTURES = Path(__file__).parent / "fixtures" / "design"


def _load(name: str):
    return load_survey(FIXTURES / name / "survey.yaml")


def test_minimal_fixture_passes_coverage():
    assert check_coverage(_load("minimal")) == []


def test_uncovered_lever_is_caught():
    """(a) 어떤 K에도 매핑되지 않은 레버."""
    violations = check_coverage(_load("uncovered_lever"))
    assert len(violations) == 1
    assert "L3" in violations[0]
    assert "유통 채널" in violations[0]


def test_orphan_knowledge_is_caught():
    """(b) 어떤 레버에도 매핑되지 않은 K — 삭제 대상."""
    violations = check_coverage(_load("orphan_knowledge"))
    assert len(violations) == 1
    assert violations[0].startswith("K3")
    assert "삭제" in violations[0]


def test_unasked_knowledge_is_caught():
    """(c) 알아야 한다고 해놓고 어떤 문항도 묻지 않는 K."""
    violations = check_coverage(_load("unasked_knowledge"))
    assert len(violations) == 1
    assert violations[0].startswith("K2")


def test_dangling_lever_reference_counts_as_orphan():
    """존재하지 않는 레버만 가리키는 K도 고아로 잡혀야 한다."""
    loaded = _load("minimal")
    broken = [replace(block, lever_ids=["L99"]) for block in loaded.knowledge]
    violations = check_coverage(replace(loaded, knowledge=broken))
    assert sum(1 for item in violations if "삭제 대상" in item) == 2


@pytest.mark.parametrize(
    ("fixture", "expected"),
    [
        ("bad_maxdiff", "MaxDiff 속성은 정확히 12개"),
        ("bad_maxdiff", "세트 구성 부족"),
        ("bad_van_westendorp", "Van Westendorp 세트"),
        ("bad_scale", "scale_points가 3 이상"),
        ("bad_known_truth", "존재하지 않는 선택지"),
        ("dangling_and_orphan", "존재하지 않는 지식 블록 참조"),
        ("dangling_and_orphan", "어떤 지식 블록도 가리키지 않음"),
    ],
)
def test_invalid_survey_is_rejected(fixture: str, expected: str):
    with pytest.raises(DesignError) as caught:
        load_survey(FIXTURES / "invalid" / f"{fixture}.yaml")
    assert expected in str(caught.value)


def test_unknown_key_is_rejected(tmp_path: Path):
    """오타 난 키를 조용히 무시하면 '썼는데 반영 안 되는' 설계 파일이 된다."""
    survey = tmp_path / "survey.yaml"
    survey.write_text(
        "id: typo-survey\n"
        f"goal: {FIXTURES / 'minimal' / 'goal.yaml'}\n"
        f"knowledge: {FIXTURES / 'minimal' / 'knowledge.yaml'}\n"
        "questions:\n"
        "  - id: Q1\n"
        "    section: B\n"
        "    text: 들어본 적 있나요?\n"
        "    qtype: single\n"
        "    knowledge_ids: [K1]\n"
        "    optoins: [있다, 없다]\n",
        encoding="utf-8",
    )
    with pytest.raises(DesignError, match="알 수 없는 키"):
        load_survey(survey)


def test_missing_file_reports_path(tmp_path: Path):
    with pytest.raises(DesignError, match="찾을 수 없음"):
        load_survey(tmp_path / "nope.yaml")


def test_interview_guide_timeline_must_be_contiguous(tmp_path: Path):
    guide = tmp_path / "guide.yaml"
    guide.write_text(
        "id: gappy\n"
        "duration_min: 30\n"
        "blocks:\n"
        "  - t_start_min: 0\n"
        "    t_end_min: 10\n"
        "    knowledge_ids: []\n"
        "    script: 라포\n"
        "    probes: [요즘 어떠세요]\n"
        "  - t_start_min: 15\n"
        "    t_end_min: 30\n"
        "    knowledge_ids: [K1]\n"
        "    script: 본론\n"
        "    probes: [그날 무슨 일이 있었죠]\n",
        encoding="utf-8",
    )
    with pytest.raises(DesignError, match="끊김"):
        load_interview_guide(guide)


def test_facade_signature_is_exported():
    """contracts.DesignFacade가 요구하는 세 이름이 모듈 최상위에 있어야 한다."""
    from power_persona_sim import design

    for name in ("load_survey", "load_interview_guide", "check_coverage"):
        assert callable(getattr(design, name))
