"""LLM 어댑터 계층.

- MockAdapter: 인자만으로 결정되는 응답 — CI·개발 기본값
- OllamaAdapter: 로컬 ollama 서버 (미실행 시 명확한 에러)
- ClaudeAdapter / GeminiAdapter: 유료 API. dry_run=True가 기본이며,
  dry_run에서는 응답을 생성하지 않는다 — 비용 추정은 estimate_cost()가 담당한다.
  실호출은 PPS_ALLOW_API_CALLS=1 승인 없이는 불가능하다.
"""

from __future__ import annotations

import json
import os
import random
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar

from ..contracts import PersonaRecord, RunConfig, Survey
from .model_constants import calculate_cost, get_model_pricing

_APPROVAL_ENV = "PPS_ALLOW_API_CALLS"


class LLMAdapter(ABC):
    """LLM 어댑터 공통 인터페이스."""

    @abstractmethod
    def generate(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.7,
        seed: int | None = None,
    ) -> str:
        """페르소나 응답 텍스트 생성."""


class MockAdapter(LLMAdapter):
    """결정적 모의 응답 — 오직 (user_message, seed)로만 결정된다.

    호출 순서·인스턴스 상태에 의존하지 않으므로 resume·병렬 실행에서도 재현된다.
    """

    _RANK_ITEMS: ClassVar[list[str]] = [
        "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L",
    ]
    _OPEN_RESPONSES: ClassVar[list[str]] = [
        "좋은 맛이 나서요",
        "가족이 좋아해요",
        "가격이 합리적이에요",
        "편하게 조리할 수 있어서요",
        "신뢰할 수 있는 브랜드라서요",
        "친구 추천으로 알았어요",
        "건강식이라고 생각해서요",
    ]

    def generate(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.7,
        seed: int | None = None,
    ) -> str:
        rng = random.Random(f"{seed if seed is not None else 42}|{user_message}")
        msg = user_message.lower()

        if "점수" in msg or "1~10" in msg or "얼마나" in msg:
            return str(rng.randint(1, 10))
        if "순위" in msg or "순서" in msg or "rank" in msg:
            items = self._RANK_ITEMS[: rng.randint(3, 5)]
            rng.shuffle(items)
            return ", ".join(items)
        if "금액" in msg or "가격" in msg or "원" in msg:
            return str(rng.randint(10000, 40000))
        if "개수" in msg or "횟수" in msg:
            return str(rng.randint(1, 20))
        return rng.choice(self._OPEN_RESPONSES)


class OllamaAdapter(LLMAdapter):
    """로컬 ollama 서버 어댑터 (무과금)."""

    #: 응답 길이 상한. 설문 응답은 선택지 한 줄이거나 두어 문장이다. 상한이 없으면
    #: 소형 모델이 문단을 쏟아내 배치 시간이 몇 배로 늘고 파싱도 어려워진다.
    DEFAULT_NUM_PREDICT = 192

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3",
        num_predict: int = DEFAULT_NUM_PREDICT,
    ):
        self.base_url = base_url
        self.model = model
        self.num_predict = num_predict

    def generate(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.7,
        seed: int | None = None,
    ) -> str:
        payload = json.dumps(
            {
                "model": self.model,
                "system": system_prompt,
                "prompt": user_message,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "seed": seed,
                    "num_predict": self.num_predict,
                },
            }
        ).encode()
        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read())["response"]
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"ollama 서버에 연결할 수 없다 ({self.base_url}). "
                "`ollama serve`로 서버를 먼저 실행하거나 MockAdapter를 사용하라."
            ) from e


class _PaidAdapter(LLMAdapter):
    """유료 API 어댑터 공통 골격 — 과금 게이트가 본체다."""

    provider: str = ""
    api_key_env: str = ""

    def __init__(self, dry_run: bool = True, api_key: str | None = None):
        self.dry_run = dry_run
        self.api_key = api_key or os.getenv(self.api_key_env)

    def generate(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.7,
        seed: int | None = None,
    ) -> str:
        if self.dry_run:
            raise RuntimeError(
                f"{self.provider} 어댑터는 dry_run 모드다 — 응답을 생성하지 않는다. "
                "비용 추정은 estimate_cost()를 사용하고, 실행은 승인 후 dry_run=False로."
            )
        if os.getenv(_APPROVAL_ENV) != "1":
            raise RuntimeError(
                f"{self.provider} API 실호출 금지. 명시적 승인이 필요하다: "
                f"export {_APPROVAL_ENV}=1"
            )
        raise RuntimeError(
            f"{self.provider} 실호출 구현은 파일럿 승인 후 붙인다. "
            "현 단계에서는 MockAdapter 또는 OllamaAdapter를 사용하라."
        )


class ClaudeAdapter(_PaidAdapter):
    provider = "Claude"
    api_key_env = "ANTHROPIC_API_KEY"


class GeminiAdapter(_PaidAdapter):
    provider = "Gemini"
    api_key_env = "GOOGLE_API_KEY"


def create_adapter(adapter_type: str, dry_run: bool = True, **kwargs: Any) -> LLMAdapter:
    """어댑터 팩토리."""
    if adapter_type == "mock":
        return MockAdapter()
    if adapter_type == "ollama":
        return OllamaAdapter(**kwargs)
    if adapter_type == "claude":
        return ClaudeAdapter(dry_run=dry_run, **kwargs)
    if adapter_type == "gemini":
        return GeminiAdapter(dry_run=dry_run, **kwargs)
    raise ValueError(f"알 수 없는 어댑터: {adapter_type}")


# ── 비용 추정 (dry-run 게이트) ──────────────────────────────────────


@dataclass(frozen=True)
class CostEstimate:
    model: str
    request_count: int
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: float

    def summary(self) -> str:
        return (
            f"[비용 추정] 모델={self.model} 요청 {self.request_count:,}건, "
            f"입력 ~{self.prompt_tokens:,}tok / 출력 ~{self.completion_tokens:,}tok "
            f"→ 약 ${self.estimated_cost_usd:,.2f} (단가표 스냅샷 기준 추정치)"
        )


def _rough_tokens(text: str) -> int:
    # 한국어 혼합 텍스트의 보수적 근사 — 문자 수 / 2. 정밀 측정은 실행 직전 count_tokens로.
    return max(1, len(text) // 2)


def estimate_cost(
    survey: Survey, personas: list[PersonaRecord], config: RunConfig
) -> CostEstimate:
    """배치 실행 전 예상 요청 수·토큰·비용. 실호출 없이 계산한다."""
    from .survey_runner import assemble_system_prompt, render_question

    request_count = len(personas) * len(survey.questions) * config.repetitions
    prompt_tokens = 0
    for persona in personas:
        system_tokens = _rough_tokens(
            assemble_system_prompt(persona, config.awareness_condition)
        )
        for question in survey.questions:
            # 실제로 보내는 것은 문항 본문이 아니라 선택지·형식 지시가 붙은 렌더링 결과다
            question_tokens = _rough_tokens(render_question(question))
            prompt_tokens += (system_tokens + question_tokens) * config.repetitions
    completion_tokens = request_count * 150  # 설문 응답은 짧다 — 문항당 ~150tok 가정

    if get_model_pricing(config.model):
        cost = calculate_cost(config.model, prompt_tokens, completion_tokens)
    else:
        cost = 0.0  # mock·ollama 등 무과금 백엔드
    return CostEstimate(
        model=config.model,
        request_count=request_count,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        estimated_cost_usd=round(cost, 4),
    )
