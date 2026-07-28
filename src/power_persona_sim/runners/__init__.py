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
    DEFAULT_NARRATIVE,
    PersonaNarrative,
    SurveyRunner,
    assemble_system_prompt,
    build_run_id,
    calculate_prompt_hash,
    derive_seed,
    load_responses,
    parse_response,
    render_question,
)

__all__ = [
    "DEFAULT_NARRATIVE",
    "ClaudeAdapter",
    "CostEstimate",
    "GeminiAdapter",
    "LLMAdapter",
    "MockAdapter",
    "OllamaAdapter",
    "PersonaNarrative",
    "SurveyRunner",
    "assemble_system_prompt",
    "build_run_id",
    "calculate_prompt_hash",
    "create_adapter",
    "derive_seed",
    "estimate_cost",
    "load_responses",
    "parse_response",
    "render_question",
    "run_survey",
]


def run_survey(
    survey: Survey,
    personas: list[PersonaRecord],
    config: RunConfig,
    log_dir: Path | None = None,
    narrative: PersonaNarrative | None = None,
) -> list[ResponseRecord]:
    """RunnerFacade.run_survey 구현. log_dir을 주면 jsonl 로깅 + resume.

    narrative를 주면 페르소나 서사 블록을 케이스에 맞게 갈아끼운다 (기본: 식생활).
    """
    # ollama는 config.model을 어댑터까지 전달해야 한다 — 빠뜨리면 어댑터 기본값
    # "llama3"로 조용히 다른 모델을 부른다(대개 404). 유료 어댑터는 모델을
    # 생성자가 아니라 호출부에서 받으므로 여기서 넘기지 않는다.
    kwargs = {"model": config.model} if config.adapter == "ollama" else {}
    adapter = create_adapter(config.adapter, dry_run=config.dry_run, **kwargs)
    runner = SurveyRunner(adapter, log_dir=log_dir, narrative=narrative)
    return runner.run_survey(survey, personas, config)
