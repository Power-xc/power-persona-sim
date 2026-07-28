"""CLI 진입점 — 서브커맨드 기반 인터페이스."""

import argparse
import sys
from pathlib import Path


def run_sample_cmd(args: argparse.Namespace) -> int:
    """표본 추출 서브커맨드."""
    try:
        from power_persona_sim.sampling import build_sample, load_personas
    except ImportError:
        print("오류: sampling 모듈 미구현", file=sys.stderr)
        return 1

    signals_path = Path(args.signals) if args.signals else Path("configs/signals/food.yaml")
    cells_path = Path(args.cells) if args.cells else Path("configs/cells/default.yaml")

    manifest = build_sample(signals_path, cells_path, seed=args.seed, source=args.source)
    personas = load_personas(manifest)

    print(f"표본 추출 완료: {len(personas)}명")
    print(f"  Seed: {args.seed}")
    print(f"  Source: {args.source}")
    print(f"  Signals: {signals_path}")
    print(f"  Cells: {cells_path}")

    return 0


def run_design_check_cmd(args: argparse.Namespace) -> int:
    """설계 검증 서브커맨드."""
    try:
        from power_persona_sim.design import check_coverage, load_survey
    except ImportError:
        print("오류: design 모듈 미구현", file=sys.stderr)
        return 1

    survey_path = Path(args.survey)
    survey = load_survey(survey_path)

    coverage_violations = check_coverage(survey)
    if coverage_violations:
        print("커버리지 규율 위반:")
        for violation in coverage_violations:
            print(f"  - {violation}")
        return 1

    print("설계 검증: 통과")
    return 0


def run_run_cmd(args: argparse.Namespace) -> int:
    """시뮬레이션 실행 서브커맨드.

    기본은 dry-run — 표본·설문을 로드해 예상 요청 수와 비용만 보여준다.
    실제 실행은 --no-dry-run이며, 응답 jsonl과 manifest를 out-dir에 남긴다.
    """
    from power_persona_sim.contracts import RunConfig
    from power_persona_sim.design import load_survey
    from power_persona_sim.runners import build_run_id, estimate_cost, run_survey
    from power_persona_sim.sampling import build_sample, load_personas
    from power_persona_sim.sampling.manifest import save_manifest

    signals_path = Path(args.signals) if args.signals else Path("configs/signals/food.yaml")
    cells_path = Path(args.cells) if args.cells else Path("configs/cells/default.yaml")

    manifest = build_sample(signals_path, cells_path, seed=args.seed, source=args.source)
    personas = load_personas(manifest)
    survey = load_survey(Path(args.survey))

    config = RunConfig(
        adapter=args.adapter,
        model=args.model,
        temperature=args.temperature,
        seed=args.seed,
        repetitions=args.repetitions,
        prompt_version=args.prompt_version,
        awareness_condition=args.awareness_condition,
        dry_run=not args.no_dry_run,
    )
    estimate = estimate_cost(survey, personas, config)

    if config.dry_run:
        print("[DRY RUN] 실행하지 않았습니다.")
        print(f"  Adapter/Model: {config.adapter}/{config.model}")
        print(f"  페르소나 {len(personas)}명 × 문항 {len(survey.questions)}개 × 반복 {config.repetitions}회")
        print(f"  {estimate.summary()}")
        print("\n실행하려면 --no-dry-run 플래그를 사용하세요.")
        return 0

    print(estimate.summary())
    out_dir = Path(args.out_dir)
    responses = run_survey(survey, personas, config, log_dir=out_dir / "raw")
    run_id = build_run_id(survey, config)
    manifest_path = save_manifest(manifest, out_dir / f"{run_id}.manifest.json")
    print(f"실행 완료: 응답 {len(responses)}건")
    print(f"  응답 로그: {out_dir / 'raw' / (run_id + '.jsonl')}")
    print(f"  표본 manifest: {manifest_path}")
    return 0


def _load_validation_inputs(args: argparse.Namespace):
    from power_persona_sim.design import load_survey
    from power_persona_sim.runners import load_responses
    from power_persona_sim.sampling.manifest import load_manifest

    responses = load_responses(Path(args.responses))
    if not responses:
        raise SystemExit(f"오류: 응답 파일이 비어 있거나 없습니다 — {args.responses}")
    survey = load_survey(Path(args.survey))
    manifest = load_manifest(Path(args.manifest))
    return responses, manifest, survey


def _run_validation(args: argparse.Namespace):
    from power_persona_sim.validation import load_benchmark, validate

    responses, manifest, survey = _load_validation_inputs(args)
    benchmark = None
    if getattr(args, "benchmark", None):
        benchmark = load_benchmark(Path(args.benchmark))
    return responses, manifest, survey, validate(responses, manifest, survey, benchmark=benchmark)


def run_validate_cmd(args: argparse.Namespace) -> int:
    """타당성 검증 서브커맨드 — 응답 jsonl + manifest + 설문으로 4종 체크."""
    _, _, _, report = _run_validation(args)

    print(f"판정: {report.verdict.upper()}")
    for check in report.checks:
        mark = "✓" if check.passed else "✗"
        print(f"  {mark} {check.name}: {check.details}")
    if report.excluded_question_ids:
        print(f"  제외 문항: {report.excluded_question_ids}")
    return 0 if report.verdict == "adopt" else 1


def run_report_cmd(args: argparse.Namespace) -> int:
    """HTML 리포트 생성 — 검증을 먼저 수행하고 그 결과를 리포트에 박는다."""
    from power_persona_sim.report import render_report

    responses, manifest, survey, validation = _run_validation(args)
    output_path = render_report(survey, manifest, responses, validation, Path(args.out))
    print(f"리포트 생성: {output_path} (검증 판정: {validation.verdict})")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="power-persona-sim",
        description="NVIDIA Nemotron Personas Korea 기반 소비자 조사 시뮬레이터",
    )

    subparsers = parser.add_subparsers(dest="command", help="서브커맨드")

    # sample
    sample_parser = subparsers.add_parser("sample", help="표본 추출")
    sample_parser.add_argument("--signals", help="키워드 신호 설정 파일 경로")
    sample_parser.add_argument("--cells", help="셀 설계 파일 경로")
    sample_parser.add_argument("--seed", type=int, default=42, help="난수 시드 (기본: 42)")
    sample_parser.add_argument(
        "--source",
        choices=["remote-duckdb", "local-parquet", "fixture"],
        default="remote-duckdb",
        help="데이터 소스 (기본: remote-duckdb)",
    )
    sample_parser.set_defaults(func=run_sample_cmd)

    # design-check
    design_parser = subparsers.add_parser("design-check", help="설계 검증")
    design_parser.add_argument("survey", help="설문 YAML 파일 경로")
    design_parser.set_defaults(func=run_design_check_cmd)

    # run
    run_parser = subparsers.add_parser("run", help="시뮬레이션 실행")
    run_parser.add_argument("survey", help="설문 YAML 파일 경로")
    run_parser.add_argument("--signals", help="키워드 신호 설정 파일 경로")
    run_parser.add_argument("--cells", help="셀 설계 파일 경로")
    run_parser.add_argument("--seed", type=int, default=42, help="난수 시드 (기본: 42)")
    run_parser.add_argument(
        "--source",
        choices=["remote-duckdb", "local-parquet", "fixture"],
        default="fixture",
        help="데이터 소스 (기본: fixture)",
    )
    run_parser.add_argument(
        "--adapter",
        choices=["mock", "ollama", "claude", "gemini"],
        default="mock",
        help="모델 어댑터 (기본: mock)",
    )
    run_parser.add_argument(
        "--model",
        default="mock-model",
        help="모델명 (기본: mock-model)",
    )
    run_parser.add_argument(
        "--temperature",
        type=float,
        default=0.8,
        help="온도 파라미터 (기본: 0.8)",
    )
    run_parser.add_argument(
        "--repetitions",
        type=int,
        default=3,
        help="자기일관성 검증용 반복 횟수 (기본: 3)",
    )
    run_parser.add_argument(
        "--prompt-version",
        default="0.1.0",
        help="프롬프트 버전 (PREREG용, 기본: 0.1.0)",
    )
    run_parser.add_argument(
        "--awareness-condition",
        choices=["natural", "forced_unaware"],
        default="natural",
        help="미인지 조건 (기본: natural)",
    )
    run_parser.add_argument(
        "--no-dry-run",
        action="store_true",
        help="실제 실행 (기본은 dry-run)",
    )
    run_parser.add_argument(
        "--out-dir",
        default="results",
        help="응답 jsonl·manifest 출력 디렉터리 (기본: results)",
    )
    run_parser.set_defaults(func=run_run_cmd)

    # validate
    validate_parser = subparsers.add_parser("validate", help="타당성 검증")
    validate_parser.add_argument("responses", help="응답 jsonl 경로 (run이 남긴 results/raw/*.jsonl)")
    validate_parser.add_argument("--survey", required=True, help="설문 YAML 경로")
    validate_parser.add_argument("--manifest", required=True, help="표본 manifest JSON 경로")
    validate_parser.add_argument("--benchmark", help="셀별 기대 비율 YAML (configs/benchmarks/)")
    validate_parser.set_defaults(func=run_validate_cmd)

    # report
    report_parser = subparsers.add_parser("report", help="HTML 리포트 생성 (검증 포함)")
    report_parser.add_argument("responses", help="응답 jsonl 경로")
    report_parser.add_argument("--survey", required=True, help="설문 YAML 경로")
    report_parser.add_argument("--manifest", required=True, help="표본 manifest JSON 경로")
    report_parser.add_argument("--benchmark", help="셀별 기대 비율 YAML (configs/benchmarks/)")
    report_parser.add_argument("--out", default="results/report", help="출력 디렉터리 (기본: results/report)")
    report_parser.set_defaults(func=run_report_cmd)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    sys.exit(args.func(args))
