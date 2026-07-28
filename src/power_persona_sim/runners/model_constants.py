"""LLM 모델 ID·단가 상수.

단가는 2026-07-28 기준 공식 표를 옮긴 추정용 스냅샷이다.
비용 게이트(estimate_cost)의 입력일 뿐 청구 금액이 아니며, 갱신 책임은 이 파일에 있다.
"""

from __future__ import annotations

from typing import TypedDict


class ModelPricing(TypedDict):
    model_id: str
    input_price_per_1m: float  # USD / 1M input tokens
    output_price_per_1m: float  # USD / 1M output tokens


CLAUDE_OPUS_48: ModelPricing = {
    "model_id": "claude-opus-4-8",
    "input_price_per_1m": 5.00,
    "output_price_per_1m": 25.00,
}

CLAUDE_SONNET_5: ModelPricing = {
    "model_id": "claude-sonnet-5",
    "input_price_per_1m": 3.00,
    "output_price_per_1m": 15.00,
}

CLAUDE_HAIKU_45: ModelPricing = {
    "model_id": "claude-haiku-4-5",
    "input_price_per_1m": 1.00,
    "output_price_per_1m": 5.00,
}

GEMINI_2_0_FLASH: ModelPricing = {
    "model_id": "gemini-2-0-flash",
    "input_price_per_1m": 0.075,
    "output_price_per_1m": 0.3,
}

DEFAULT_CLAUDE_MODEL = CLAUDE_OPUS_48
DEFAULT_GEMINI_MODEL = GEMINI_2_0_FLASH

MODELS: dict[str, ModelPricing] = {
    p["model_id"]: p
    for p in (CLAUDE_OPUS_48, CLAUDE_SONNET_5, CLAUDE_HAIKU_45, GEMINI_2_0_FLASH)
}


def get_model_pricing(model_id: str) -> ModelPricing | None:
    return MODELS.get(model_id)


def calculate_cost(model_id: str, prompt_tokens: int, completion_tokens: int) -> float:
    """토큰 수 → 예상 비용(USD). 무료 티어는 일일 쿼터라 요청 단위로 차감하지 않는다."""
    pricing = get_model_pricing(model_id)
    if not pricing:
        raise ValueError(f"단가 미등록 모델: {model_id}")
    return (prompt_tokens / 1_000_000) * pricing["input_price_per_1m"] + (
        completion_tokens / 1_000_000
    ) * pricing["output_price_per_1m"]
