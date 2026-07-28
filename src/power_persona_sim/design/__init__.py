"""Goal → Knowledge → Question 백워드 디자인 엔진.

`contracts.DesignFacade`의 세 함수(load_survey·load_interview_guide·check_coverage)를
모듈 최상위에서 그대로 export 한다. 나머지는 케이스 저작과 테스트에 필요한 보조다.
"""

from .coverage import check_coverage
from .hypotheses import load_hypotheses
from .loader import load_goal, load_interview_guide, load_knowledge, load_survey
from .parsing import DesignError
from .schema import (
    KNOWN_TRUTH_KINDS,
    MAXDIFF_ATTRIBUTE_COUNT,
    VW_ROLES,
    GoalSpec,
    Hypothesis,
    InterviewGuideSpec,
    KnowledgeSpec,
    Prediction,
    QuestionSpec,
)
from .validators import question_config

__all__ = [
    "KNOWN_TRUTH_KINDS",
    "MAXDIFF_ATTRIBUTE_COUNT",
    "VW_ROLES",
    "DesignError",
    "GoalSpec",
    "Hypothesis",
    "InterviewGuideSpec",
    "KnowledgeSpec",
    "Prediction",
    "QuestionSpec",
    "check_coverage",
    "load_goal",
    "load_hypotheses",
    "load_interview_guide",
    "load_knowledge",
    "load_survey",
    "question_config",
]
