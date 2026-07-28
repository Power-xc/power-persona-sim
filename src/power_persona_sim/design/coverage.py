"""커버리지 규율 — 백워드 디자인에서 문항 수 폭증을 막는 유일한 장치.

브리프 §4.2가 규정한 세 방향을 모두 본다.

  (a) 어떤 K에도 매핑되지 않은 레버   → 의사결정을 뒷받침할 지식이 없다
  (b) 어떤 레버에도 매핑되지 않은 K   → 물어도 쓸 데가 없다, 삭제 대상
  (c) 어떤 문항도 묻지 않는 K         → 알아야 한다고 해놓고 안 물었다

빈 리스트가 통과다. 위반은 사람이 읽고 바로 고칠 수 있게 무엇을 어떻게 하라는
문장으로 돌려준다.
"""

from __future__ import annotations

from ..contracts import Survey


def check_coverage(survey: Survey) -> list[str]:
    """커버리지 규율 위반 목록. 빈 리스트면 통과."""
    lever_ids = {lever.id for lever in survey.goal.levers}
    covered_levers = {
        lever_id for block in survey.knowledge for lever_id in block.lever_ids
    } & lever_ids
    asked = {kid for question in survey.questions for kid in question.knowledge_ids}

    violations = [
        f"레버 {lever.id}({lever.name}): 어떤 지식 블록도 이 레버를 지지하지 않음 "
        "— K를 추가하거나 레버를 목표에서 내려라"
        for lever in survey.goal.levers
        if lever.id not in covered_levers
    ]
    violations += [
        f"{block.id}: 어떤 레버에도 매핑되지 않음 — 삭제 대상"
        for block in survey.knowledge
        if not set(block.lever_ids) & lever_ids
    ]
    violations += [
        f"{block.id}: 어떤 문항도 이 지식을 묻지 않음 — 문항을 추가하거나 K를 삭제하라"
        for block in survey.knowledge
        if block.id not in asked
    ]
    return violations
