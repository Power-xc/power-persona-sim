"""시뮬레이션 실행 모듈 — 어댑터 계층, 프롬프트 조립, 배치 실행, 비용 게이트."""

from pathlib import Path

from ..contracts import PersonaRecord, ResponseRecord, RunConfig, Survey
from .adapters import (
    ClaudeAdapter,
    CostEstimate,
    GeminiAdapter,
    LLMAdapter,
    MockAdapter,
    OllamaAdapter,
    create_adapter,
    estimate_cost,
)
from .survey_runner import (
    SurveyRunner,
    assemble_system_prompt,
    build_run_id,
    calculate_prompt_hash,
    derive_seed,
    parse_response,
)

__all__ = [
    "ClaudeAdapter",
    "CostEstimate",
    "GeminiAdapter",
    "LLMAdapter",
    "MockAdapter",
    "OllamaAdapter",
    "SurveyRunner",
    "assemble_system_prompt",
    "build_run_id",
    "calculate_prompt_hash",
    "create_adapter",
    "derive_seed",
    "estimate_cost",
    "parse_response",
    "run_survey",
]


def run_survey(
    survey: Survey,
    personas: list[PersonaRecord],
    config: RunConfig,
    log_dir: Path | None = None,
) -> list[ResponseRecord]:
    """RunnerFacade.run_survey 구현. log_dir을 주면 jsonl 로깅 + resume."""
    adapter = create_adapter(config.adapter, dry_run=config.dry_run)
    runner = SurveyRunner(adapter, log_dir=log_dir)
    return runner.run_survey(survey, personas, config)
