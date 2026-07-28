"""청와연 케이스가 브리프 §4를 실제로 만족하는지 검사한다.

케이스는 엔진의 회귀 테스트 겸 참조 구현이다. 여기가 깨지면 브리프와
케이스 파일이 어긋났다는 뜻이다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from power_persona_sim.contracts import QuestionType
from power_persona_sim.design import (
    MAXDIFF_ATTRIBUTE_COUNT,
    VW_ROLES,
    check_coverage,
    load_hypotheses,
    load_interview_guide,
    load_survey,
    question_config,
)

CASE = Path(__file__).parents[1] / "cases" / "cheongwayeon" / "design"


@pytest.fixture(scope="module")
def survey():
    return load_survey(CASE / "survey.yaml")


@pytest.fixture(scope="module")
def guide():
    return load_interview_guide(CASE / "interview-guide.yaml")


def test_case_passes_coverage(survey):
    assert check_coverage(survey) == []


def test_goal_has_five_levers(survey):
    assert [lever.id for lever in survey.goal.levers] == ["L1", "L2", "L3", "L4", "L5"]


def test_knowledge_is_k1_to_k10(survey):
    assert [block.id for block in survey.knowledge] == [f"K{n}" for n in range(1, 11)]


def test_every_knowledge_block_carries_a_judgement_rule(survey):
    """판단 규칙 없는 K는 '알아두면 좋은 것'이지 조사 대상이 아니다."""
    assert all(block.judgement_rule.strip() for block in survey.knowledge)


def test_sections_follow_the_brief(survey):
    assert {question.section for question in survey.questions} == set("SABCDEF")


def test_only_screener_questions_may_skip_knowledge(survey):
    unmapped = [q.id for q in survey.questions if not q.knowledge_ids]
    assert all(q_id.startswith("S") for q_id in unmapped)


def test_has_at_least_two_known_truth_questions(survey):
    """브리프 §6.2 ② — 실제 값을 아는 문항을 심어 두고 재현 실패 시 폐기한다."""
    anchors = [question for question in survey.questions if question.known_truth]
    assert len(anchors) >= 2
    kinds = {question.known_truth["expect"]["kind"] for question in anchors}
    assert "top_option" in kinds
    assert "segment_gap" in kinds


def test_known_truth_sources_are_cited(survey):
    for question in survey.questions:
        if question.known_truth:
            assert question.known_truth["source"].strip()
            assert question.known_truth["claim"].strip()


def test_maxdiff_matches_the_brief(survey):
    maxdiff = [q for q in survey.questions if q.qtype == QuestionType.MAXDIFF]
    assert len(maxdiff) == 1
    assert len(maxdiff[0].options) == MAXDIFF_ATTRIBUTE_COUNT
    assert question_config(maxdiff[0])["sets"] == 8


def test_van_westendorp_is_a_complete_set(survey):
    roles = [
        question_config(q)["vw_role"]
        for q in survey.questions
        if q.qtype == QuestionType.VAN_WESTENDORP
    ]
    assert sorted(roles) == sorted(VW_ROLES)


def test_conversion_intent_uses_eleven_point_scale(survey):
    intent = next(question for question in survey.questions if question.id == "E4")
    assert intent.scale_points == 11


def test_profile_questions_can_be_checked_against_persona(survey):
    """페르소나가 이미 아는 값을 되물어 역할 이탈을 잡는다."""
    checks = {question_config(q).get("persona_check") for q in survey.questions if q.section == "F"}
    assert {"age", "family_type", "province"} <= checks


def test_guide_is_sixty_minutes_without_gaps(guide):
    assert guide.duration_min == 60
    assert guide.blocks[0].t_start_min == 0
    assert guide.blocks[-1].t_end_min == 60


def test_guide_covers_k1_through_k9(guide):
    covered = {kid for block in guide.blocks for kid in block.knowledge_ids}
    assert covered == {f"K{n}" for n in range(1, 10)}


def test_guide_states_the_probing_principle(guide):
    assert any("사건" in principle for principle in guide.principles)


def test_brand_is_not_mentioned_before_the_funnel_block(guide):
    """20분 전에 브랜드를 꺼내면 이후 회상이 전부 오염된다."""
    early = [block for block in guide.blocks if block.t_end_min <= 20]
    assert early, "20분 이전 블록이 있어야 한다"
    for block in early:
        assert "청와연" not in block.script
        assert not any("청와연" in probe for probe in block.probes)


def test_hypotheses_reference_real_questions_and_knowledge(survey):
    hypotheses = load_hypotheses(CASE / "hypotheses.yaml")
    question_ids = {question.id for question in survey.questions}
    knowledge_ids = {block.id for block in survey.knowledge}
    assert {item.id for item in hypotheses} >= {"H1"}
    for item in hypotheses:
        assert set(item.question_ids) <= question_ids
        assert set(item.knowledge_ids) <= knowledge_ids
        assert item.predictions
        assert item.prescription_if_supported.strip()
        assert item.prescription_if_rejected.strip()


def test_h1_sits_on_the_k1_k4_intersection(survey):
    h1 = next(item for item in load_hypotheses(CASE / "hypotheses.yaml") if item.id == "H1")
    assert set(h1.knowledge_ids) == {"K1", "K4"}
