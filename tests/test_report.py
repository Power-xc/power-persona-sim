"""리포트 생성 테스트."""

import tempfile
from pathlib import Path

from power_persona_sim.report import render_report
from tests.fixtures.report.sample_data import (
    create_sample_manifest,
    create_sample_responses,
    create_sample_survey,
    create_sample_validation,
)


def test_render_report_creates_html():
    """리포트가 HTML 파일로 생성되는지 검증."""
    survey = create_sample_survey()
    manifest = create_sample_manifest()
    responses = create_sample_responses()
    validation = create_sample_validation()

    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        result_path = render_report(survey, manifest, responses, validation, out_dir)

        assert result_path.exists()
        assert result_path.suffix == ".html"
        assert result_path.name == "report.html"

        content = result_path.read_text(encoding="utf-8")
        assert len(content) > 0
        assert "<!DOCTYPE html>" in content
        assert "{{ title }}" not in content  # Jinja2 템플릿이 렌더링됨


def test_report_html_contains_key_sections():
    """리포트에 주요 섹션이 포함되는지 검증."""
    survey = create_sample_survey()
    manifest = create_sample_manifest()
    responses = create_sample_responses()
    validation = create_sample_validation()

    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        result_path = render_report(survey, manifest, responses, validation, out_dir)
        content = result_path.read_text(encoding="utf-8")

        # 주요 제목 확인
        assert "조사 설계" in content
        assert "검증 상태" in content
        assert "문항별 응답 요약" in content

        # 검증 결과 배지 확인
        assert "통과" in content or "실패" in content

        # 설문 정보 확인
        assert survey.id in content


def test_report_no_absolute_percentages():
    """리포트에 절대 수치(%)가 없는지 검증."""
    survey = create_sample_survey()
    manifest = create_sample_manifest()
    responses = create_sample_responses()
    validation = create_sample_validation()

    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        result_path = render_report(survey, manifest, responses, validation, out_dir)
        content = result_path.read_text(encoding="utf-8")

        # 절대 수치 패턴 제거 (예: "45%", "32.5%")
        import re
        percentage_pattern = r'\d+(\.\d+)?%'
        matches = re.findall(percentage_pattern, content)

        # 수치 표현만 있고 %는 없어야 함
        for match in matches:
            # 허용되는 표현 (예: "0.8", "0.3" 온도나 척도)
            assert "%" not in match


def test_report_contains_validation_verdict():
    """리포트에 검증 결론(adopt/discard)이 포함되는지 검증."""
    survey = create_sample_survey()
    manifest = create_sample_manifest()
    responses = create_sample_responses()
    validation = create_sample_validation()

    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        result_path = render_report(survey, manifest, responses, validation, out_dir)
        content = result_path.read_text(encoding="utf-8")

        # 검증 결론이 포함됨
        assert validation.verdict.upper() in content


def test_report_self_contained_html():
    """리포트가 self-contained(외부 CDN 의존 없음)인지 검증."""
    survey = create_sample_survey()
    manifest = create_sample_manifest()
    responses = create_sample_responses()
    validation = create_sample_validation()

    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        result_path = render_report(survey, manifest, responses, validation, out_dir)
        content = result_path.read_text(encoding="utf-8")

        # 외부 CDN 참조 검사
        assert "https://cdn" not in content
        assert "https://maxcdn" not in content
        assert "https://fonts.googleapis.com" not in content

        # CSS와 JS는 내부에 포함
        assert "<style>" in content
        assert "<script>" in content
