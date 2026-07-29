"""HTML 리포트 생성 — Jinja2 기반 self-contained HTML."""

from pathlib import Path
from typing import Any

from jinja2 import Environment, PackageLoader, select_autoescape

from power_persona_sim.contracts import (
    ResponseRecord,
    SampleManifest,
    Survey,
    ValidationReport,
)


def render_report(
    survey: Survey,
    manifest: SampleManifest,
    responses: list[ResponseRecord],
    validation: ValidationReport,
    out_dir: Path,
) -> Path:
    """HTML 리포트 생성 및 저장.

    Args:
        survey: 설문 정의
        manifest: 표본 매니페스트
        responses: 응답 기록 리스트
        validation: 검증 리포트
        out_dir: 출력 디렉토리

    Returns:
        생성된 리포트 파일 경로
    """
    env = Environment(
        loader=PackageLoader("power_persona_sim.report", "templates"),
        autoescape=select_autoescape(["html", "xml"]),
    )

    template = env.get_template("report.html")

    # 응답을 세그먼트·문항별로 집계
    response_summary = _aggregate_responses(responses, survey)

    # 실행에 쓰인 모델 목록. 둘 이상이면 집계가 모델을 합친 값이라는 사실을
    # 리포트가 스스로 밝혀야 한다 — 교차검증 실행분을 단일 모델 결과로 읽으면
    # 모델 간 불일치가 통계에 묻힌다.
    models = sorted({r.model for r in responses})

    # 리포트 데이터 준비
    report_data = {
        "title": f"{survey.id} - 리포트",
        "survey": survey,
        "manifest": manifest,
        "validation": validation,
        "response_summary": response_summary,
        "total_responses": len(responses),
        "models": models,
        "persona_count": len({r.persona_uuid for r in responses}),
    }

    html_content = template.render(**report_data)

    # 출력 디렉토리 생성
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / "report.html"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    return output_path


def _aggregate_responses(
    responses: list[ResponseRecord],
    survey: Survey,
) -> dict[str, Any]:
    """응답을 문항별로 집계."""
    aggregated = {}

    for question in survey.questions:
        q_id = question.id
        q_responses = [r for r in responses if r.question_id == q_id]

        if not q_responses:
            continue

        parsed_values = [r.parsed for r in q_responses if r.parsed is not None]

        if not parsed_values:
            continue

        aggregated[q_id] = {
            "question": question,
            "total": len(q_responses),
            "responses": q_responses,
            "parsed_values": parsed_values,
        }

    return aggregated
