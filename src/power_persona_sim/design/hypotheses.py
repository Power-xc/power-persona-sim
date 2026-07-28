"""사전 등록 가설 로딩.

가설은 설문의 일부가 아니라 설문에 얹히는 예측이다. 실행 전에 못 박아 두지
않으면 결과를 보고 나서 해석을 고르게 되고, 그건 브리프 §6.1의 "분석 자유도"
실패 모드 그 자체다. 그래서 survey.yaml과 분리된 파일로 둔다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .parsing import check_keys, check_unique, item_list, raise_if, read_mapping, text, text_list
from .schema import Hypothesis, Prediction

_HYPOTHESIS_REQUIRED = {
    "id",
    "name",
    "statement",
    "knowledge_ids",
    "question_ids",
    "predictions",
    "prescription_if_supported",
    "prescription_if_rejected",
}
_PREDICTION_REQUIRED = {"segment", "expect"}


def load_hypotheses(path: Path) -> list[Hypothesis]:
    path = Path(path)
    data = read_mapping(path)
    errors: list[str] = []
    check_keys(data, {"hypotheses"}, set(), path.name, errors)
    items = item_list(data, "hypotheses", path.name, errors)
    hypotheses = [
        built
        for index, item in enumerate(items)
        if (built := _build_hypothesis(item, f"{path.name} hypotheses[{index}]", errors))
    ]
    check_unique([item.id for item in hypotheses], f"{path.name} 가설", errors)
    raise_if(errors, path)
    return hypotheses


def _build_hypothesis(item: Any, spot: str, errors: list[str]) -> Hypothesis | None:
    if not check_keys(item, _HYPOTHESIS_REQUIRED, set(), spot, errors):
        return None
    return Hypothesis(
        id=text(item, "id", spot, errors),
        name=text(item, "name", spot, errors),
        statement=text(item, "statement", spot, errors),
        knowledge_ids=text_list(item, "knowledge_ids", spot, errors),
        question_ids=text_list(item, "question_ids", spot, errors),
        predictions=_build_predictions(item, spot, errors),
        prescription_if_supported=text(item, "prescription_if_supported", spot, errors),
        prescription_if_rejected=text(item, "prescription_if_rejected", spot, errors),
    )


def _build_predictions(item: Any, spot: str, errors: list[str]) -> list[Prediction]:
    predictions = []
    for index, entry in enumerate(item_list(item, "predictions", spot, errors)):
        where = f"{spot} predictions[{index}]"
        if not check_keys(entry, _PREDICTION_REQUIRED, set(), where, errors):
            continue
        predictions.append(
            Prediction(
                segment=text(entry, "segment", where, errors),
                expect=text(entry, "expect", where, errors),
            )
        )
    return predictions
