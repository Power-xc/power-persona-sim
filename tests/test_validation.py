"""validation 모듈 테스트."""

from typing import ClassVar

import pytest

from power_persona_sim.contracts import (
    CellAssignment,
    CellSpec,
    Goal,
    Knowledge,
    Lever,
    Question,
    QuestionType,
    ResponseRecord,
    SampleManifest,
    Survey,
)
from power_persona_sim.validation import validate
from power_persona_sim.validation.checks import (
    check_cross_model,
    check_distribution,
    check_known_truth,
    check_self_consistency,
)


def make_manifest(cell_counts: dict[str, int]) -> SampleManifest:
    assignments = []
    i = 0
    for cell_id, n in cell_counts.items():
        for _ in range(n):
            assignments.append(
                CellAssignment(
                    uuid=f"uuid-{i}", cell_id=cell_id, signal_score=1.0,
                    price_sensitivity_score=0.0,
                )
            )
            i += 1
    return SampleManifest(
        seed=42,
        source="fixture",
        signals_config={},
        cells_config={},
        cells=[
            CellSpec(cell_id=c, axes={}, quota_survey=n, quota_idi=0)
            for c, n in cell_counts.items()
        ],
        assignments=assignments,
        created_at="2026-07-28T00:00:00+00:00",
    )


def make_survey(questions: list[Question]) -> Survey:
    return Survey(
        id="test",
        goal=Goal(
            business_goal="g", decision="d",
            levers=[Lever(id="L1", name="l")],
            success_criteria="s", one_sentence="o",
        ),
        knowledge=[Knowledge(id="K1", statement="s", lever_ids=["L1"], judgement_rule="j")],
        questions=questions,
    )


def make_response(
    question_id: str,
    parsed,
    persona_uuid: str = "u1",
    repetition: int = 0,
    model: str = "mock",
) -> ResponseRecord:
    return ResponseRecord(
        run_id="r",
        persona_uuid=persona_uuid,
        question_id=question_id,
        repetition=repetition,
        seed=1,
        model=model,
        prompt_hash="h",
        raw_text=str(parsed),
        parsed=parsed,
    )


SCALE_Q = Question(
    id="Q1", section="A", text="점수?", qtype=QuestionType.SCALE,
    knowledge_ids=["K1"], scale_points=10,
)
RANK_Q = Question(
    id="Q2", section="B", text="순위?", qtype=QuestionType.RANK,
    knowledge_ids=["K1"], options=["a", "b", "c"],
)


class TestDistribution:
    def test_empty_manifest_fails(self):
        check = check_distribution(make_manifest({}))
        assert check.passed is False

    def test_no_benchmark_skips_as_pass(self):
        check = check_distribution(make_manifest({"C1": 10}))
        assert check.passed is True
        assert check.metrics["skipped"] == 1.0
        assert "스킵" in check.details

    def test_matching_benchmark_passes(self):
        manifest = make_manifest({"C1": 50, "C2": 50})
        check = check_distribution(manifest, benchmark={"C1": 0.5, "C2": 0.5})
        assert check.passed is True
        assert check.metrics["p_value"] > 0.05

    def test_skewed_benchmark_fails(self):
        manifest = make_manifest({"C1": 95, "C2": 5})
        check = check_distribution(manifest, benchmark={"C1": 0.5, "C2": 0.5})
        assert check.passed is False

    def test_metrics_are_numeric(self):
        manifest = make_manifest({"C1": 50, "C2": 50})
        check = check_distribution(manifest, benchmark={"C1": 0.5, "C2": 0.5})
        assert all(isinstance(v, float) for v in check.metrics.values())


class TestKnownTruth:
    def test_no_kt_questions_passes(self):
        survey = make_survey([SCALE_Q])
        assert check_known_truth([], survey).passed is True

    def test_low_reproduction_rate_fails(self):
        q = Question(
            id="Q1", section="A", text="점수?", qtype=QuestionType.SCALE,
            knowledge_ids=["K1"], scale_points=10, known_truth={"range": [8, 10]},
        )
        survey = make_survey([q])
        # 10건 중 1건만 정답 범위 — 옛 구현(매치>0이면 통과)이라면 통과했을 케이스
        responses = [make_response("Q1", 9, persona_uuid="u0")] + [
            make_response("Q1", 2, persona_uuid=f"u{i}") for i in range(1, 10)
        ]
        check = check_known_truth(responses, survey)
        assert check.passed is False
        assert "Q1" in check.details

    def test_high_reproduction_rate_passes(self):
        q = Question(
            id="Q1", section="A", text="점수?", qtype=QuestionType.SCALE,
            knowledge_ids=["K1"], scale_points=10, known_truth={"range": [1, 10]},
        )
        survey = make_survey([q])
        responses = [make_response("Q1", 5, persona_uuid=f"u{i}") for i in range(10)]
        assert check_known_truth(responses, survey).passed is True

    def test_missing_responses_fail(self):
        q = Question(
            id="Q1", section="A", text="점수?", qtype=QuestionType.SCALE,
            knowledge_ids=["K1"], scale_points=10, known_truth={"range": [1, 10]},
        )
        assert check_known_truth([], make_survey([q])).passed is False


def _kt_question(expect: dict, options: list[str]) -> Question:
    """설계 YAML이 싣는 known_truth 형식 그대로의 문항."""
    return Question(
        id="Q1", section="A", text="도구?", qtype=QuestionType.SINGLE,
        knowledge_ids=["K1"], options=options,
        known_truth={"source": "s", "claim": "c", "expect": expect},
    )


class TestKnownTruthExpectSchema:
    """설계 YAML의 known_truth.expect 스키마 채점.

    이 형식을 검증기가 몰라서 어떤 응답이든 재현율 0%로 떨어지던 결함의 회귀 방지.
    """

    OPTIONS: ClassVar[list[str]] = ["엑셀", "BI 도구", "SQL"]

    def test_top_option_reproduced_passes(self):
        q = _kt_question({"kind": "top_option", "value": "엑셀"}, self.OPTIONS)
        responses = [make_response("Q1", "엑셀") for _ in range(6)]
        responses += [make_response("Q1", "SQL") for _ in range(2)]
        check = check_known_truth(responses, make_survey([q]))
        assert check.passed is True
        assert check.metrics["rate_Q1"] == 1.0

    def test_top_option_not_reproduced_fails(self):
        q = _kt_question({"kind": "top_option", "value": "엑셀"}, self.OPTIONS)
        responses = [make_response("Q1", "SQL") for _ in range(5)]
        check = check_known_truth(responses, make_survey([q]))
        assert check.passed is False
        assert check.metrics["rate_Q1"] == 0.0

    def test_rank_order_prefix_match(self):
        q = Question(
            id="Q1", section="A", text="순위?", qtype=QuestionType.RANK,
            knowledge_ids=["K1"], options=["a", "b", "c"],
            known_truth={
                "source": "s", "claim": "c",
                "expect": {"kind": "rank_order", "order": ["a", "b"]},
            },
        )
        responses = [make_response("Q1", ["a", "b", "c"]) for _ in range(3)]
        responses.append(make_response("Q1", ["c", "b", "a"]))
        check = check_known_truth(responses, make_survey([q]))
        assert check.metrics["rate_Q1"] == pytest.approx(0.75)

    def test_segment_gap_direction_holds(self):
        q = _kt_question(
            {
                "kind": "segment_gap", "segment_by": "age_band",
                "option": "SQL", "higher": "25-34", "lower": "45-59",
            },
            self.OPTIONS,
        )
        manifest = make_manifest({"25-34_수도권_전체": 2, "45-59_수도권_전체": 2})
        young = [a.uuid for a in manifest.assignments if a.cell_id.startswith("25-34")]
        old = [a.uuid for a in manifest.assignments if a.cell_id.startswith("45-59")]
        responses = [make_response("Q1", "SQL", persona_uuid=u) for u in young]
        responses += [make_response("Q1", "엑셀", persona_uuid=u) for u in old]
        check = check_known_truth(responses, make_survey([q]), manifest=manifest)
        assert check.passed is True

    def test_segment_gap_direction_reversed_fails(self):
        q = _kt_question(
            {
                "kind": "segment_gap", "segment_by": "age_band",
                "option": "SQL", "higher": "25-34", "lower": "45-59",
            },
            self.OPTIONS,
        )
        manifest = make_manifest({"25-34_수도권_전체": 2, "45-59_수도권_전체": 2})
        young = [a.uuid for a in manifest.assignments if a.cell_id.startswith("25-34")]
        old = [a.uuid for a in manifest.assignments if a.cell_id.startswith("45-59")]
        responses = [make_response("Q1", "엑셀", persona_uuid=u) for u in young]
        responses += [make_response("Q1", "SQL", persona_uuid=u) for u in old]
        check = check_known_truth(responses, make_survey([q]), manifest=manifest)
        assert check.passed is False

    def test_segment_gap_without_manifest_is_unscorable_not_silent_pass(self):
        q = _kt_question(
            {
                "kind": "segment_gap", "segment_by": "age_band",
                "option": "SQL", "higher": "25-34", "lower": "45-59",
            },
            self.OPTIONS,
        )
        check = check_known_truth([make_response("Q1", "SQL")], make_survey([q]))
        assert check.passed is False
        assert check.metrics["unscorable"] == 1.0
        assert "채점 불가" in check.details


class TestSelfConsistency:
    def test_consistent_ranks_pass(self):
        survey = make_survey([RANK_Q])
        responses = [
            make_response("Q2", ["a", "b", "c"], repetition=rep) for rep in range(3)
        ]
        check, excluded = check_self_consistency(responses, survey)
        assert check.passed is True
        assert excluded == []

    def test_contradictory_ranks_excluded(self):
        survey = make_survey([RANK_Q])
        responses = [
            make_response("Q2", ["a", "b", "c"], repetition=0),
            make_response("Q2", ["c", "b", "a"], repetition=1),
            make_response("Q2", ["a", "b", "c"], repetition=2),
        ]
        check, excluded = check_self_consistency(responses, survey)
        assert check.passed is False
        assert excluded == ["Q2"]

    def test_unstable_scale_excluded(self):
        survey = make_survey([SCALE_Q])
        responses = [
            make_response("Q1", v, repetition=rep) for rep, v in enumerate([1, 9, 2])
        ]
        _check, excluded = check_self_consistency(responses, survey)
        assert excluded == ["Q1"]

    def test_stable_scale_passes(self):
        survey = make_survey([SCALE_Q])
        responses = [
            make_response("Q1", v, repetition=rep) for rep, v in enumerate([7, 7, 8])
        ]
        _, excluded = check_self_consistency(responses, survey)
        assert excluded == []


class TestCrossModel:
    def test_single_model_skips(self):
        check = check_cross_model([make_response("Q1", 5)], make_survey([SCALE_Q]))
        assert check.passed is True
        assert check.metrics["skipped"] == 1.0

    def test_agreeing_models_pass(self):
        survey = make_survey([SCALE_Q])
        responses = [
            make_response("Q1", 7, model="m1"),
            make_response("Q1", 7, model="m2"),
        ]
        check = check_cross_model(responses, survey)
        assert check.passed is True
        assert check.metrics["agreement_rate"] == 1.0

    def test_disagreeing_models_fail(self):
        survey = make_survey([SCALE_Q])
        responses = [
            make_response("Q1", 2, model="m1"),
            make_response("Q1", 9, model="m2"),
        ]
        check = check_cross_model(responses, survey)
        assert check.passed is False


class TestValidate:
    def test_contract_signature_and_adopt(self):
        survey = make_survey([SCALE_Q])
        responses = [make_response("Q1", 5, persona_uuid=f"u{i}") for i in range(5)]
        report = validate(responses, make_manifest({"C1": 5}), survey)
        assert report.verdict == "adopt"
        assert len(report.checks) == 4

    def test_known_truth_failure_forces_discard(self):
        q = Question(
            id="Q1", section="A", text="점수?", qtype=QuestionType.SCALE,
            knowledge_ids=["K1"], scale_points=10, known_truth={"range": [9, 10]},
        )
        survey = make_survey([q])
        responses = [make_response("Q1", 1, persona_uuid=f"u{i}") for i in range(5)]
        report = validate(responses, make_manifest({"C1": 5}), survey)
        assert report.verdict == "discard"

    def test_distribution_failure_forces_discard(self):
        survey = make_survey([SCALE_Q])
        responses = [make_response("Q1", 5, persona_uuid=f"u{i}") for i in range(100)]
        report = validate(
            responses,
            make_manifest({"C1": 95, "C2": 5}),
            survey,
            benchmark={"C1": 0.5, "C2": 0.5},
        )
        assert report.verdict == "discard"

    def test_excluded_questions_flow_through(self):
        survey = make_survey([RANK_Q])
        responses = [
            make_response("Q2", ["a", "b", "c"], repetition=0),
            make_response("Q2", ["c", "b", "a"], repetition=1),
        ]
        report = validate(responses, make_manifest({"C1": 1}), survey)
        assert report.excluded_question_ids == ["Q2"]


class TestE2E:
    def test_mock_e2e_flow(self):
        """fixtures → MockAdapter 실행 → 검증까지 오프라인 완주."""
        pytest.importorskip("scipy")
        from power_persona_sim.runners import MockAdapter, SurveyRunner
        from tests.fixtures.runner.runner_persona_fixture import get_test_personas
        from tests.test_runners import make_config, mini_survey  # noqa: F401

        survey = make_survey(
            [
                Question(
                    id="Q1", section="A", text="최근 구매 만족도를 1~10점으로?",
                    qtype=QuestionType.SCALE, knowledge_ids=["K1"], scale_points=10,
                    known_truth={"range": [1, 10]},
                )
            ]
        )
        personas = get_test_personas()
        responses = SurveyRunner(MockAdapter()).run_survey(
            survey, personas, make_config(repetitions=2)
        )
        manifest = make_manifest({"C1": len(personas)})
        report = validate(responses, manifest, survey)
        assert report.verdict in ("adopt", "discard")
        assert len(report.checks) == 4


class TestBenchmarkLoader:
    def test_load_fixture_converts_cell_keys(self):
        from power_persona_sim.validation import load_benchmark

        bench = load_benchmark("tests/fixtures/benchmarks/population_small.yaml")
        assert "30-44_수도권" in bench
        assert abs(sum(bench.values()) - 0.6098) < 1e-6

    def test_load_full_benchmark_matches_sampling_cell_ids(self):
        from power_persona_sim.validation import load_benchmark

        bench = load_benchmark("configs/benchmarks/population-kr.yaml")
        assert "30-44_수도권_자녀동거" in bench
        assert len(bench) == 12
        assert abs(sum(bench.values()) - 1.0) < 0.02  # 반올림 오차 허용

    def test_null_proportions_are_skipped_not_faked(self, tmp_path):
        from power_persona_sim.validation import load_benchmark

        p = tmp_path / "b.yaml"
        p.write_text(
            "cells:\n"
            '  "age=30-44|region=수도권":\n    proportion: 0.5\n'
            '  "age=60-69|region=수도권":\n    proportion: null\n',
            encoding="utf-8",
        )
        bench = load_benchmark(p)
        assert bench == {"30-44_수도권": 0.5}
