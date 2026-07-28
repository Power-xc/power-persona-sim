"""설정 파일 자체를 검사한다.

프로덕션 설정(configs/)이 실측 데이터와 어긋나면 표본이 조용히 비뚤어진다.
그 어긋남을 코드가 아니라 여기서 잡는다.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
import yaml

from power_persona_sim.sampling import (
    assign_axes,
    build_cell_specs,
    load_cells,
    load_signals,
    passes_hard_filter,
)

#: 브리프가 가정했지만 실제 데이터에 없는 값 (DuckDB 원격 조회로 확인)
PHANTOM_FAMILY_TYPES = ("3세대 이상", "부모와 거주", "1인 가구")


def test_프로덕션_셀_설정이_12셀을_만든다(cells_path):
    assert len(build_cell_specs(load_cells(cells_path))) == 12


def test_프로덕션_쿼터는_브리프_규모다(cells_path):
    cfg = load_cells(cells_path)
    assert (cfg.quota_survey_min, cfg.quota_survey) == (25, 40)
    assert (cfg.quota_idi_min, cfg.quota_idi) == (1, 2)
    assert 12 * cfg.quota_survey_min == 300
    assert 12 * cfg.quota_survey == 480


@pytest.mark.parametrize("phantom", PHANTOM_FAMILY_TYPES)
def test_존재하지_않는_가구형태를_리터럴로_적지_않았다(cells_path, phantom):
    """이 값들을 다시 적으면 30~69세의 40% 이상이 조용히 사라진다."""
    text = cells_path.read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.split("#", 1)[0]
        assert phantom not in stripped, f"{phantom!r} 은 실제 데이터에 없는 값입니다."


def test_한글자_키워드를_쓰지_않는다(signals_path):
    """부분문자열 매칭이라 한 글자는 무관한 단어를 삼킨다 (`국` → 중국·태국·영국)."""
    cfg = load_signals(signals_path)
    everything = [*cfg.signals, *([cfg.price_axis] if cfg.price_axis else [])]
    short = [(s.key, kw) for s in everything for kw in s.keywords if len(kw) < 2]
    assert not short, f"한 글자 키워드: {short}"


def test_신호_가중치가_브리프_표와_일치한다(signals_path):
    cfg = load_signals(signals_path)
    weights = {s.key: s.weight for s in cfg.signals}
    assert weights == {
        "hansik_homefood": 2,
        "meat_preference": 2,
        "holiday_cooking": 3,
        "convenience_open": 2,
        "premium": 1,
    }
    assert cfg.price_axis is not None and cfg.price_axis.weight == 1


def test_테스트용_셀_설정은_쿼터만_다르다(cells_path, small_cells_path):
    """축·필터가 갈라지면 테스트가 프로덕션 동작을 증명하지 못한다."""
    prod = yaml.safe_load(cells_path.read_text(encoding="utf-8"))
    small = yaml.safe_load(small_cells_path.read_text(encoding="utf-8"))
    assert prod["hard_filter"] == small["hard_filter"]
    assert prod["axes"] == small["axes"]
    assert prod["quota"] != small["quota"]


def test_실측_가구형태_전수가_어느_한쪽으로_분류된다(cells_path, personas_rows):
    """통과하든 탈락하든 분류는 되어야 한다 — 예외로 죽으면 파이프라인이 멈춘다."""
    cfg = load_cells(cells_path)
    for row in personas_rows:
        if passes_hard_filter(row, cfg):
            assert assign_axes(row, cfg) is not None, row["family_type"]


def test_1인가구_설정을_끄면_표본에서_사라진다(cells_path, personas_rows):
    cfg = load_cells(cells_path)
    off = replace(cfg, keep_single_household_cell=False)
    singles = [r for r in personas_rows if "혼자 거주" in r["family_type"] and 30 <= r["age"] <= 69]
    assert singles, "fixture에 1인 가구가 없어 이 테스트가 무의미합니다."
    assert any(passes_hard_filter(r, cfg) for r in singles)
    assert not any(passes_hard_filter(r, off) for r in singles)
