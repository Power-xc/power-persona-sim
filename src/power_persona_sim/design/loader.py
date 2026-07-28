"""설계 YAML → contracts 데이터클래스.

survey.yaml이 goal.yaml·knowledge.yaml을 상대 경로로 참조하는 구조다. 셋을
한 파일에 몰아넣지 않은 이유는 고의로 깨뜨린 fixture를 만들 때 온전한 쪽을
그대로 재사용하기 위해서고, 실제 케이스에서도 목표는 그대로 둔 채 설문만
개정하는 일이 흔하기 때문이다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..contracts import GuideBlock, Lever, Question, QuestionType, Survey
from .parsing import (
    check_keys,
    check_unique,
    integer,
    item_list,
    raise_if,
    read_mapping,
    text,
    text_list,
)
from .schema import SCREENER_SECTION, GoalSpec, InterviewGuideSpec, KnowledgeSpec, QuestionSpec
from .validators import validate_questions

_GOAL_REQUIRED = {"business_goal", "decision", "success_criteria", "one_sentence", "levers"}
_GOAL_OPTIONAL = {"screening"}
_LEVER_REQUIRED = {"id", "name"}
_KNOWLEDGE_REQUIRED = {"id", "statement", "lever_ids", "judgement_rule"}
_KNOWLEDGE_OPTIONAL = {"decision_link"}
_SURVEY_REQUIRED = {"id", "goal", "knowledge", "questions"}
_QUESTION_REQUIRED = {"id", "section", "text", "qtype", "knowledge_ids"}
_QUESTION_OPTIONAL = {"options", "scale_points", "known_truth", "config"}
_GUIDE_REQUIRED = {"id", "duration_min", "blocks"}
_GUIDE_OPTIONAL = {"principles"}
_BLOCK_REQUIRED = {"t_start_min", "t_end_min", "knowledge_ids", "script", "probes"}


# ── GOAL ─────────────────────────────────────────────────────────────


def load_goal(path: Path) -> GoalSpec:
    path = Path(path)
    data = read_mapping(path)
    errors: list[str] = []
    check_keys(data, _GOAL_REQUIRED, _GOAL_OPTIONAL, path.name, errors)
    levers = _build_levers(item_list(data, "levers", path.name, errors), path.name, errors)
    screening = data.get("screening") or {}
    if not isinstance(screening, dict):
        errors.append(f"{path.name}: 'screening'은 매핑이어야 함")
        screening = {}
    goal = GoalSpec(
        business_goal=text(data, "business_goal", path.name, errors),
        decision=text(data, "decision", path.name, errors),
        levers=levers,
        success_criteria=text(data, "success_criteria", path.name, errors),
        one_sentence=text(data, "one_sentence", path.name, errors),
        screening=screening,
    )
    raise_if(errors, path)
    return goal


def _build_levers(items: list[Any], where: str, errors: list[str]) -> list[Lever]:
    levers = []
    for index, item in enumerate(items):
        spot = f"{where} levers[{index}]"
        if not check_keys(item, _LEVER_REQUIRED, set(), spot, errors):
            continue
        levers.append(
            Lever(id=text(item, "id", spot, errors), name=text(item, "name", spot, errors))
        )
    check_unique([lever.id for lever in levers], f"{where} 레버", errors)
    return levers


# ── KNOWLEDGE ────────────────────────────────────────────────────────


def load_knowledge(path: Path) -> list[KnowledgeSpec]:
    path = Path(path)
    data = read_mapping(path)
    errors: list[str] = []
    check_keys(data, {"knowledge"}, set(), path.name, errors)
    blocks = _build_knowledge(item_list(data, "knowledge", path.name, errors), path.name, errors)
    raise_if(errors, path)
    return blocks


def _build_knowledge(items: list[Any], where: str, errors: list[str]) -> list[KnowledgeSpec]:
    blocks = []
    for index, item in enumerate(items):
        spot = f"{where} knowledge[{index}]"
        if not check_keys(item, _KNOWLEDGE_REQUIRED, _KNOWLEDGE_OPTIONAL, spot, errors):
            continue
        blocks.append(
            KnowledgeSpec(
                id=text(item, "id", spot, errors),
                statement=text(item, "statement", spot, errors),
                lever_ids=text_list(item, "lever_ids", spot, errors),
                judgement_rule=text(item, "judgement_rule", spot, errors),
                decision_link=str(item.get("decision_link", "")),
            )
        )
    check_unique([block.id for block in blocks], f"{where} 지식 블록", errors)
    return blocks


# ── SURVEY ───────────────────────────────────────────────────────────


def load_survey(path: Path) -> Survey:
    path = Path(path)
    data = read_mapping(path)
    errors: list[str] = []
    check_keys(data, _SURVEY_REQUIRED, set(), path.name, errors)
    raise_if(errors, path)

    goal = load_goal(path.parent / data["goal"])
    knowledge = load_knowledge(path.parent / data["knowledge"])
    questions = _build_questions(item_list(data, "questions", path.name, errors), path.name, errors)
    validate_questions(questions, errors)
    _check_references(goal, knowledge, questions, errors)
    raise_if(errors, path)
    return Survey(
        id=text(data, "id", path.name, errors), goal=goal, knowledge=knowledge, questions=questions
    )


def _build_questions(items: list[Any], where: str, errors: list[str]) -> list[Question]:
    questions = []
    for index, item in enumerate(items):
        spot = f"{where} questions[{index}]"
        if not check_keys(item, _QUESTION_REQUIRED, _QUESTION_OPTIONAL, spot, errors):
            continue
        qtype = _question_type(item, spot, errors)
        if qtype is None:
            continue
        questions.append(_build_question(item, qtype, spot, errors))
    check_unique([question.id for question in questions], f"{where} 문항", errors)
    return questions


def _build_question(
    item: dict[str, Any], qtype: QuestionType, spot: str, errors: list[str]
) -> QuestionSpec:
    return QuestionSpec(
        id=text(item, "id", spot, errors),
        section=text(item, "section", spot, errors),
        text=text(item, "text", spot, errors),
        qtype=qtype,
        knowledge_ids=text_list(item, "knowledge_ids", spot, errors),
        options=text_list(item, "options", spot, errors) if "options" in item else [],
        scale_points=item.get("scale_points"),
        known_truth=item.get("known_truth"),
        config=item.get("config") or {},
    )


def _question_type(item: dict[str, Any], where: str, errors: list[str]) -> QuestionType | None:
    try:
        return QuestionType(item.get("qtype"))
    except ValueError:
        allowed = [member.value for member in QuestionType]
        errors.append(f"{where}: qtype '{item.get('qtype')}'은 {allowed} 중 하나여야 함")
        return None


def _check_references(
    goal: GoalSpec, knowledge: list[KnowledgeSpec], questions: list[Question], errors: list[str]
) -> None:
    lever_ids = {lever.id for lever in goal.levers}
    knowledge_ids = {block.id for block in knowledge}
    for block in knowledge:
        dangling = sorted(set(block.lever_ids) - lever_ids)
        if dangling:
            errors.append(f"{block.id}: 존재하지 않는 레버 참조 {dangling}")
    for question in questions:
        _check_question_references(question, knowledge_ids, errors)


def _check_question_references(
    question: Question, knowledge_ids: set[str], errors: list[str]
) -> None:
    dangling = sorted(set(question.knowledge_ids) - knowledge_ids)
    if dangling:
        errors.append(f"문항 {question.id}: 존재하지 않는 지식 블록 참조 {dangling}")
    # 스크리너만 예외 — 나머지 문항이 K로 되짚어지지 않으면 백워드 디자인이 아니다.
    if not question.knowledge_ids and question.section != SCREENER_SECTION:
        errors.append(
            f"문항 {question.id}: 어떤 지식 블록도 가리키지 않음 "
            f"— knowledge_ids를 채우거나 문항을 삭제하라(섹션 {SCREENER_SECTION}만 예외)"
        )


# ── INTERVIEW GUIDE ──────────────────────────────────────────────────


def load_interview_guide(path: Path) -> InterviewGuideSpec:
    path = Path(path)
    data = read_mapping(path)
    errors: list[str] = []
    check_keys(data, _GUIDE_REQUIRED, _GUIDE_OPTIONAL, path.name, errors)
    duration = integer(data, "duration_min", path.name, errors)
    blocks = _build_blocks(item_list(data, "blocks", path.name, errors), path.name, errors)
    _check_timeline(blocks, duration, path.name, errors)
    guide = InterviewGuideSpec(
        id=text(data, "id", path.name, errors),
        duration_min=duration,
        blocks=blocks,
        principles=text_list(data, "principles", path.name, errors),
    )
    raise_if(errors, path)
    return guide


def _build_blocks(items: list[Any], where: str, errors: list[str]) -> list[GuideBlock]:
    blocks = []
    for index, item in enumerate(items):
        spot = f"{where} blocks[{index}]"
        if not check_keys(item, _BLOCK_REQUIRED, set(), spot, errors):
            continue
        blocks.append(
            GuideBlock(
                t_start_min=integer(item, "t_start_min", spot, errors),
                t_end_min=integer(item, "t_end_min", spot, errors),
                knowledge_ids=text_list(item, "knowledge_ids", spot, errors),
                script=text(item, "script", spot, errors),
                probes=text_list(item, "probes", spot, errors),
            )
        )
    return blocks


def _check_timeline(blocks: list[GuideBlock], duration: int, where: str, errors: list[str]) -> None:
    """빈 구간이나 겹치는 구간은 진행자가 현장에서 시간을 잃는다."""
    if not blocks:
        return
    cursor = 0
    for block in blocks:
        if block.t_start_min != cursor:
            errors.append(
                f"{where}: {cursor}분에서 블록이 끊김 — 다음 블록이 {block.t_start_min}분에서 시작함"
            )
        if block.t_end_min <= block.t_start_min:
            errors.append(f"{where}: 블록 {block.t_start_min}~{block.t_end_min}분의 길이가 0 이하")
        cursor = max(cursor, block.t_end_min)
    if cursor != duration:
        errors.append(f"{where}: 블록 합계 {cursor}분이 duration_min({duration})과 다름")
