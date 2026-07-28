"""CLI 인터페이스 테스트 — 실제 파이프라인 배선(e2e) 포함."""

import sys
from pathlib import Path

import pytest

from power_persona_sim.cli import main

SURVEY = Path("cases/cheongwayeon/design/survey.yaml")


def run_cli(*argv: str) -> int:
    sys.argv = ["power-persona-sim", *argv]
    with pytest.raises(SystemExit) as exc_info:
        main()
    return exc_info.value.code or 0


def test_cli_shows_help_without_args(capsys):
    assert run_cli() == 0
    captured = capsys.readouterr()
    assert "서브커맨드" in captured.out or "usage" in captured.out.lower()


def test_cli_sample_fixture_source(capsys):
    assert run_cli("sample", "--source", "fixture") == 0
    assert "표본 추출 완료" in capsys.readouterr().out


def test_cli_design_check_cheongwayeon(capsys):
    assert run_cli("design-check", str(SURVEY)) == 0
    assert "통과" in capsys.readouterr().out


def test_cli_run_default_is_dry_run(capsys):
    """run 기본값은 dry-run — 실행 없이 비용 추정만 출력."""
    assert run_cli("run", str(SURVEY), "--source", "fixture") == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out
    assert "비용 추정" in out


def test_cli_full_pipeline_offline(tmp_path, capsys):
    """run(mock) → validate → report 전 구간을 fixture로 오프라인 완주."""
    out_dir = tmp_path / "results"
    assert (
        run_cli(
            "run", str(SURVEY),
            "--source", "fixture",
            "--adapter", "mock",
            "--model", "mock",
            "--repetitions", "2",
            "--no-dry-run",
            "--out-dir", str(out_dir),
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "실행 완료" in out

    responses = list((out_dir / "raw").glob("*.jsonl"))
    manifests = list(out_dir.glob("*.manifest.json"))
    assert len(responses) == 1
    assert len(manifests) == 1

    # validate — mock 응답이라 known-truth 재현은 못 해도 커맨드는 완주해야 한다
    code = run_cli(
        "validate", str(responses[0]),
        "--survey", str(SURVEY),
        "--manifest", str(manifests[0]),
    )
    assert code in (0, 1)
    assert "판정" in capsys.readouterr().out

    # report — 검증 결과를 품은 self-contained HTML이 실제로 생성돼야 한다
    report_dir = tmp_path / "report"
    assert (
        run_cli(
            "report", str(responses[0]),
            "--survey", str(SURVEY),
            "--manifest", str(manifests[0]),
            "--out", str(report_dir),
        )
        == 0
    )
    html = report_dir / "report.html"
    assert html.exists()
    content = html.read_text(encoding="utf-8")
    assert "cheongwayeon" in content
    assert "http" not in content.split("</head>")[0].lower().replace("http-equiv", "")  # 외부 리소스 없음


def test_cli_validate_missing_responses_fails(tmp_path):
    with pytest.raises(SystemExit) as exc_info:
        sys.argv = [
            "power-persona-sim", "validate", str(tmp_path / "none.jsonl"),
            "--survey", str(SURVEY), "--manifest", str(tmp_path / "none.json"),
        ]
        main()
    assert exc_info.value.code != 0
