"""runners 모듈 테스트."""

import subprocess
import sys
from dataclasses import replace
from typing import ClassVar

import pytest

import power_persona_sim.runners as pps_runners
from power_persona_sim.contracts import (
    Goal,
    Knowledge,
    Lever,
    Question,
    QuestionType,
    ResponseRecord,
    RunConfig,
    Survey,
)
from power_persona_sim.design.schema import QuestionSpec
from power_persona_sim.runners import (
    DEFAULT_NARRATIVE,
    ClaudeAdapter,
    GeminiAdapter,
    MockAdapter,
    OllamaAdapter,
    PersonaNarrative,
    SurveyRunner,
    assemble_system_prompt,
    build_run_id,
    calculate_prompt_hash,
    create_adapter,
    derive_seed,
    estimate_cost,
    parse_response,
    render_question,
)
from tests.fixtures.runner.runner_persona_fixture import get_test_personas


def make_config(**overrides) -> RunConfig:
    base = {
        "adapter": "mock",
        "model": "mock",
        "temperature": 0.7,
        "seed": 42,
        "repetitions": 1,
        "prompt_version": "v1",
        "awareness_condition": "natural",
        "dry_run": True,
    }
    base.update(overrides)
    return RunConfig(**base)


@pytest.fixture
def mini_survey() -> Survey:
    goal = Goal(
        business_goal="갈비찜 구매자 전환",
        decision="마케팅 예산 배분",
        levers=[Lever(id="L1", name="인지")],
        success_criteria="가설 3개 도출",
        one_sentence="X를 사는 사람이 우리를 안 사는 이유는 [인지]이다",
    )
    knowledge = [
        Knowledge(id="K1", statement="언제 구매하는가", lever_ids=["L1"], judgement_rule="명절 80% 이상")
    ]
    questions = [
        Question(
            id="Q1",
            section="A",
            text="최근에 언제 갈비찜을 구매하셨어요? 1~10점으로 평가해주세요",
            qtype=QuestionType.SCALE,
            knowledge_ids=["K1"],
            scale_points=10,
        ),
        Question(
            id="Q2",
            section="B",
            text="구매 시점을 순위로 정렬해주세요: 명절, 주말, 평일",
            qtype=QuestionType.RANK,
            knowledge_ids=["K1"],
            options=["명절", "주말", "평일"],
        ),
    ]
    return Survey(id="mini_survey", goal=goal, knowledge=knowledge, questions=questions)


class TestAssembleSystemPrompt:
    def test_natural_condition(self):
        persona = get_test_personas()[0]
        prompt = assemble_system_prompt(persona, condition="natural")
        assert persona.sex in prompt
        assert str(persona.age) in prompt
        assert persona.persona in prompt
        assert persona.culinary_persona in prompt
        assert "식생활 서사와 모순" in prompt
        assert "모르는 브랜드" in prompt
        assert "실제 쓰는 말투" in prompt
        assert "경험이 없으면" in prompt

    def test_forced_unaware_condition(self):
        persona = get_test_personas()[0]
        prompt = assemble_system_prompt(persona, condition="forced_unaware")
        assert "특수 조건" in prompt
        assert "들어본 적도 없습니다" in prompt


class TestPersonaNarrative:
    """서사 블록 교체 — 업무 도구 조사에 식생활 서사가 실리면 그 자체가 오염이다."""

    NARRATIVE = PersonaNarrative(
        fields=(("인물", "persona"), ("직무", "professional_persona")),
        consistency_rule="위 직무 서사와 모순되는 답을 하지 마세요.",
    )

    def test_default_narrative_is_unchanged(self):
        persona = get_test_personas()[0]
        assert assemble_system_prompt(persona) == assemble_system_prompt(
            persona, narrative=DEFAULT_NARRATIVE
        )

    def test_custom_narrative_reads_raw_columns(self):
        """professional_persona는 PersonaRecord 필드가 아니라 raw에만 있다."""
        base = get_test_personas()[0]
        persona = replace(base, raw={**base.raw, "professional_persona": "데이터 집계 담당"})
        prompt = assemble_system_prompt(persona, narrative=self.NARRATIVE)
        assert "데이터 집계 담당" in prompt
        assert "직무 서사와 모순" in prompt

    def test_custom_narrative_drops_food_block(self):
        persona = get_test_personas()[0]
        prompt = assemble_system_prompt(persona, narrative=self.NARRATIVE)
        assert persona.culinary_persona not in prompt
        assert "식생활" not in prompt

    def test_missing_column_is_skipped_not_rendered_empty(self):
        persona = get_test_personas()[0]
        narrative = PersonaNarrative(
            fields=(("없는것", "no_such_column"), ("인물", "persona")), consistency_rule="규칙"
        )
        prompt = assemble_system_prompt(persona, narrative=narrative)
        assert "없는것" not in prompt
        assert persona.persona in prompt


class TestOllamaModelWiring:
    """--model이 ollama 어댑터까지 가지 않으면 기본값 llama3를 부른다 (무과금 경로 전체가 막힌다)."""

    def test_factory_accepts_model(self):
        assert create_adapter("ollama", model="gemma3:12b").model == "gemma3:12b"
        assert isinstance(create_adapter("ollama"), OllamaAdapter)

    def test_run_survey_forwards_model_to_ollama(self, monkeypatch, mini_survey):
        captured: dict = {}

        def spy(adapter_type, dry_run=True, **kwargs):
            captured["type"] = adapter_type
            captured.update(kwargs)
            return MockAdapter()

        monkeypatch.setattr(pps_runners, "create_adapter", spy)
        config = make_config(adapter="ollama", model="gemma3:12b", dry_run=False)
        pps_runners.run_survey(mini_survey, get_test_personas()[:1], config)
        assert captured["model"] == "gemma3:12b"

    def test_run_survey_sends_no_model_kwarg_to_paid_adapters(self, monkeypatch, mini_survey):
        """유료 어댑터 생성자는 model을 받지 않는다 — 넘기면 TypeError로 죽는다."""
        captured: dict = {}

        def spy(adapter_type, dry_run=True, **kwargs):
            captured.update(kwargs)
            return MockAdapter()

        monkeypatch.setattr(pps_runners, "create_adapter", spy)
        config = make_config(adapter="claude", model="claude-opus-4-8", dry_run=False)
        pps_runners.run_survey(mini_survey, get_test_personas()[:1], config)
        assert "model" not in captured


class TestDeterminism:
    def test_derive_seed_stable_in_process(self):
        assert derive_seed(42, "abc-123", "S1", 0) == derive_seed(42, "abc-123", "S1", 0)
        assert derive_seed(42, "abc-123", "S1", 0) != derive_seed(42, "abc-123", "S1", 1)

    def test_derive_seed_stable_across_processes(self):
        """내장 hash() 회귀 방지 — 새 인터프리터에서도 같은 시드가 나와야 한다."""
        code = (
            "from power_persona_sim.runners import derive_seed;"
            "print(derive_seed(42, 'abc-123', 'S1', 0))"
        )
        out = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, check=True
        )
        assert int(out.stdout.strip()) == derive_seed(42, "abc-123", "S1", 0)

    def test_prompt_hash_consistency(self):
        h1 = calculate_prompt_hash("sys", "q", "mock", 42)
        h2 = calculate_prompt_hash("sys", "q", "mock", 42)
        assert h1 == h2
        assert calculate_prompt_hash("sys", "q2", "mock", 42) != h1

    def test_run_id_is_deterministic(self, mini_survey):
        assert build_run_id(mini_survey, make_config()) == build_run_id(mini_survey, make_config())


class TestParseResponse:
    def test_parse_scale(self):
        assert parse_response("7점을 주고 싶습니다", QuestionType.SCALE) == 7

    def test_parse_rank(self):
        result = parse_response("A, B, C, D", QuestionType.RANK)
        assert isinstance(result, list)
        assert "A" in result

    def test_parse_numeric(self):
        assert parse_response("25000원입니다", QuestionType.NUMERIC) == 25000

    def test_parse_open(self):
        text = "이 브랜드가 좋아서입니다"
        assert parse_response(text, QuestionType.OPEN) == text

    def test_parse_single_with_options(self):
        options = ["명절", "주말", "평일"]
        assert parse_response("주말에 사요", QuestionType.SINGLE, options=options) == "주말"

    def test_parse_van_westendorp_numbers(self):
        result = parse_response(
            "10000, 15000, 25000, 40000", QuestionType.VAN_WESTENDORP
        )
        assert result == {
            "too_cheap": 10000,
            "cheap": 15000,
            "expensive": 25000,
            "too_expensive": 40000,
        }


class TestRenderQuestion:
    """응답자가 실제로 보는 문항. 선택지를 안 보여주면 돌아오는 건 선택이 아니라 서술이다."""

    def test_single_shows_options_and_format_rule(self):
        q = Question(
            id="Q1", section="A", text="주로 쓰는 도구는?", qtype=QuestionType.SINGLE,
            knowledge_ids=["K1"], options=["엑셀", "SQL"],
        )
        rendered = render_question(q)
        assert "엑셀" in rendered and "SQL" in rendered
        assert "하나만" in rendered

    def test_rank_states_top_n(self):
        q = QuestionSpec(
            id="Q2", section="A", text="순위는?", qtype=QuestionType.RANK,
            knowledge_ids=["K1"], options=["a", "b", "c", "d"], config={"top_n": 3},
        )
        assert "3개" in render_question(q)

    def test_scale_states_anchors(self):
        q = QuestionSpec(
            id="Q3", section="A", text="얼마나?", qtype=QuestionType.SCALE,
            knowledge_ids=["K1"], scale_points=7,
            config={"anchor_low": "전혀", "anchor_high": "매우"},
        )
        rendered = render_question(q)
        assert "1(전혀)" in rendered and "7(매우)" in rendered

    def test_open_has_no_option_block(self):
        q = Question(
            id="Q4", section="B", text="무엇을 입력하시겠습니까?", qtype=QuestionType.OPEN,
            knowledge_ids=["K1"],
        )
        assert "선택지" not in render_question(q)


class TestParseRankWithOptions:
    """여러 단어짜리 선택지를 공백으로 쪼개면 순위 데이터가 통째로 사라진다."""

    OPTIONS: ClassVar[list[str]] = [
        "숫자가 들어 있는 표",
        "차트 그림",
        "한두 문장으로 요약된 설명",
    ]

    def test_multiword_options_survive(self):
        raw = "1. 숫자가 들어 있는 표, 차트 그림, 한두 문장으로 요약된 설명"
        assert parse_response(raw, QuestionType.RANK, options=self.OPTIONS) == self.OPTIONS

    def test_order_follows_response_not_option_order(self):
        raw = "차트 그림, 숫자가 들어 있는 표"
        assert parse_response(raw, QuestionType.RANK, options=self.OPTIONS) == [
            "차트 그림", "숫자가 들어 있는 표",
        ]

    def test_unlisted_text_is_dropped(self):
        raw = "차트 그림, 그리고 잘 모르겠어요"
        assert parse_response(raw, QuestionType.RANK, options=self.OPTIONS) == ["차트 그림"]

    def test_maxdiff_best_worst_labels(self):
        raw = "가장중요: 차트 그림, 가장덜중요: 한두 문장으로 요약된 설명"
        assert parse_response(raw, QuestionType.MAXDIFF, options=self.OPTIONS) == [
            "차트 그림", "한두 문장으로 요약된 설명",
        ]


class TestMockAdapter:
    def test_strictly_deterministic(self):
        """상태 없이 (message, seed)만으로 결정 — 인스턴스·호출 순서 무관."""
        a, b = MockAdapter(), MockAdapter()
        msg = "1~10점 척도에서 점수를 주세요"
        first = a.generate("sys", msg, seed=42)
        assert a.generate("sys", msg, seed=42) == first
        assert b.generate("sys", msg, seed=42) == first

    def test_scale_detection(self):
        result = MockAdapter().generate("sys", "1~10점 척도에서 점수를 주세요", seed=42)
        assert result.isdigit()
        assert int(result) in range(1, 11)


class TestPaidAdapterGates:
    def test_dry_run_generate_raises(self):
        for adapter in (ClaudeAdapter(dry_run=True), GeminiAdapter(dry_run=True)):
            with pytest.raises(RuntimeError, match="dry_run"):
                adapter.generate("sys", "질문")

    def test_live_call_blocked_without_approval(self, monkeypatch):
        monkeypatch.delenv("PPS_ALLOW_API_CALLS", raising=False)
        with pytest.raises(RuntimeError, match="PPS_ALLOW_API_CALLS"):
            ClaudeAdapter(dry_run=False).generate("sys", "질문")

    def test_create_adapter_factory(self):
        assert isinstance(create_adapter("mock"), MockAdapter)
        assert isinstance(create_adapter("claude", dry_run=True), ClaudeAdapter)
        with pytest.raises(ValueError):
            create_adapter("unknown_type")


class TestEstimateCost:
    def test_counts_and_paid_cost(self, mini_survey):
        personas = get_test_personas()
        config = make_config(adapter="claude", model="claude-opus-4-8", repetitions=3)
        est = estimate_cost(mini_survey, personas, config)
        assert est.request_count == len(personas) * len(mini_survey.questions) * 3
        assert est.prompt_tokens > 0
        assert est.estimated_cost_usd > 0
        assert "비용 추정" in est.summary()

    def test_free_backend_costs_zero(self, mini_survey):
        est = estimate_cost(mini_survey, get_test_personas(), make_config())
        assert est.estimated_cost_usd == 0.0


class TestSurveyRunner:
    def test_run_survey_with_mock(self, mini_survey):
        personas = get_test_personas()
        config = make_config()
        responses = SurveyRunner(MockAdapter()).run_survey(mini_survey, personas, config)

        assert len(responses) == len(personas) * len(mini_survey.questions)
        for resp in responses:
            assert isinstance(resp, ResponseRecord)
            assert resp.run_id == build_run_id(mini_survey, config)
            assert resp.prompt_hash
            assert resp.raw_text
            assert resp.parsed is not None

    def test_run_survey_is_reproducible(self, mini_survey):
        personas = get_test_personas()
        r1 = SurveyRunner(MockAdapter()).run_survey(mini_survey, personas, make_config())
        r2 = SurveyRunner(MockAdapter()).run_survey(mini_survey, personas, make_config())
        assert [x.raw_text for x in r1] == [x.raw_text for x in r2]
        assert [x.seed for x in r1] == [x.seed for x in r2]

    def test_repetitions(self, mini_survey):
        personas = get_test_personas()[:1]
        responses = SurveyRunner(MockAdapter()).run_survey(
            mini_survey, personas, make_config(repetitions=3)
        )
        q1 = sorted(
            (r for r in responses if r.question_id == "Q1"), key=lambda r: r.repetition
        )
        assert [r.repetition for r in q1] == [0, 1, 2]

    def test_jsonl_logging_and_resume(self, mini_survey, tmp_path):
        personas = get_test_personas()
        config = make_config()
        runner = SurveyRunner(MockAdapter(), log_dir=tmp_path)

        first = runner.run_survey(mini_survey, personas, config)
        log_file = tmp_path / f"{build_run_id(mini_survey, config)}.jsonl"
        assert log_file.exists()
        assert len(log_file.read_text().strip().splitlines()) == len(first)

        # 재실행: 완료분은 건너뛰고 로그가 불어나지 않아야 한다 (resume)
        second = runner.run_survey(mini_survey, personas, config)
        assert len(second) == len(first)
        assert len(log_file.read_text().strip().splitlines()) == len(first)

    def test_adapter_errors_propagate(self, mini_survey):
        runner = SurveyRunner(ClaudeAdapter(dry_run=True))
        with pytest.raises(RuntimeError):
            runner.run_survey(mini_survey, get_test_personas(), make_config(adapter="claude"))
