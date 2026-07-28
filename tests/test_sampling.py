"""sampling — 3단계 필터, 셀 할당, 쿼터, 재현성.

이 파일의 핵심은 `test_같은_seed는_바이트까지_동일한_manifest를_만든다` 다.
재현성이 이 도구의 존재 이유(브리프 §6.1 '분석 자유도')라 나머지 테스트가 다
통과해도 그 하나가 깨지면 결과를 못 쓴다.
"""

from __future__ import annotations

import pytest

from power_persona_sim.contracts import CellAssignment, SampleManifest
from power_persona_sim.sampling import (
    ValueMatcher,
    apply_weights,
    assign_axes,
    build_cell_specs,
    build_sample,
    compute_weights,
    dumps,
    is_single_household,
    load_cells,
    load_manifest,
    load_personas,
    load_signals,
    loads,
    passes_hard_filter,
    sample_diagnostics,
    save_manifest,
    score_text,
    select_idi,
)

FIXED_TIME = "2026-07-28T00:00:00+09:00"


@pytest.fixture
def cells(small_cells_path):
    return load_cells(small_cells_path)


@pytest.fixture
def signals(signals_path):
    return load_signals(signals_path)


def make(signals_path, cells_path, rows, seed=42, **kw):
    return build_sample(
        signals_path,
        cells_path,
        seed=seed,
        source="fixture",
        rows=rows,
        created_at=FIXED_TIME,
        **kw,
    )


# ── 재현성: 이 절이 이 모듈의 계약이다 ───────────────────────────────


def test_같은_seed는_바이트까지_동일한_manifest를_만든다(
    signals_path, small_cells_path, personas_rows
):
    a = make(signals_path, small_cells_path, personas_rows)
    b = make(signals_path, small_cells_path, personas_rows)
    assert dumps(a) == dumps(b)
    assert dumps(a).encode("utf-8") == dumps(b).encode("utf-8")


def test_입력_순서가_바뀌어도_manifest는_동일하다(signals_path, small_cells_path, personas_rows):
    """정렬이 아니라 입력 순서가 표본을 정하고 있으면 여기서 깨진다."""
    a = make(signals_path, small_cells_path, personas_rows)
    b = make(signals_path, small_cells_path, list(reversed(personas_rows)))
    assert dumps(a) == dumps(b)


def test_seed가_다르면_표본이_달라진다(signals_path, small_cells_path, personas_rows):
    a = make(signals_path, small_cells_path, personas_rows, seed=1)
    b = make(signals_path, small_cells_path, personas_rows, seed=2)
    assert {x.uuid for x in a.assignments} != {x.uuid for x in b.assignments}


def test_seed가_달라도_셀_구조와_규모는_유지된다(signals_path, small_cells_path, personas_rows):
    a = make(signals_path, small_cells_path, personas_rows, seed=1)
    b = make(signals_path, small_cells_path, personas_rows, seed=7)
    assert [c.cell_id for c in a.cells] == [c.cell_id for c in b.cells]
    assert len(a.assignments) == len(b.assignments)


def test_manifest_저장_로드_왕복이_바이트를_보존한다(
    tmp_path, signals_path, small_cells_path, personas_rows
):
    m = make(signals_path, small_cells_path, personas_rows)
    path = save_manifest(m, tmp_path / "manifest.json")
    assert dumps(load_manifest(path)) == dumps(m)


def test_manifest는_한글을_이스케이프하지_않는다(signals_path, small_cells_path, personas_rows):
    text = dumps(make(signals_path, small_cells_path, personas_rows))
    assert "수도권" in text
    assert "\\u" not in text


def test_created_at은_호출자가_주입한다(signals_path, small_cells_path, personas_rows):
    """모듈이 시각을 읽으면 같은 seed로도 manifest가 매번 달라진다."""
    m = make(signals_path, small_cells_path, personas_rows)
    assert m.created_at == FIXED_TIME
    other = build_sample(
        signals_path,
        small_cells_path,
        seed=42,
        source="fixture",
        rows=personas_rows,
        created_at="1999-01-01T00:00:00+09:00",
    )
    assert dumps(m) != dumps(other)  # created_at만 다르다
    assert [a.uuid for a in m.assignments] == [a.uuid for a in other.assignments]


# ── 1단계 하드 필터 ──────────────────────────────────────────────────


def test_연령_범위_밖은_탈락한다(cells, personas_rows):
    row = dict(personas_rows[0], age=25, family_type="배우자·자녀와 거주")
    assert not passes_hard_filter(row, cells)
    assert passes_hard_filter(dict(row, age=30), cells)
    assert passes_hard_filter(dict(row, age=69), cells)
    assert not passes_hard_filter(dict(row, age=70), cells)


@pytest.mark.parametrize(
    "family_type",
    ["배우자·자녀와 거주", "배우자와 거주", "부모와 동거", "기타3세대", "어머니와 동거"],
)
def test_실측_가구형태가_통과한다(cells, personas_rows, family_type):
    """브리프의 리터럴 4종으로는 뒤 세 개가 조용히 탈락했다."""
    row = dict(personas_rows[0], age=45, family_type=family_type)
    assert passes_hard_filter(row, cells)


def test_비친족_동거는_제외된다(cells, personas_rows):
    row = dict(personas_rows[0], age=45, family_type="비친족 동거")
    assert not passes_hard_filter(row, cells)


def test_비친족이_친인척_패턴에_걸리지_않는다(cells):
    """'비친족'은 '친인척'을 부분문자열로 갖지 않지만 exclude가 이중 안전장치다."""
    assert not cells.family_filter.matches("비친족 동거")
    assert cells.family_filter.matches("친인척과 거주")


def test_1인가구는_설정에_따라_통과여부가_갈린다(cells, personas_rows):
    row = dict(personas_rows[0], age=45, family_type="혼자 거주")
    assert cells.keep_single_household_cell
    assert passes_hard_filter(row, cells)
    assert is_single_household("혼자 거주 (배우자 별거)", cells)


def test_1인가구_유지가_꺼지면_탈락한다(cells, personas_rows):
    from dataclasses import replace

    cfg = replace(cells, keep_single_household_cell=False)
    row = dict(personas_rows[0], age=45, family_type="혼자 거주")
    assert not passes_hard_filter(row, cfg)


def test_실측_기준_하드필터_통과율이_리터럴_방식을_넘는다(cells, personas_rows):
    literal = {"배우자·자녀와 거주", "배우자와 거주", "3세대 이상", "부모와 거주"}
    in_band = [r for r in personas_rows if 30 <= r["age"] <= 69]
    old = sum(1 for r in in_band if r["family_type"] in literal)
    new = sum(1 for r in in_band if passes_hard_filter(r, cells))
    assert new > old


# ── 2단계 신호 스코어링 ──────────────────────────────────────────────


def test_신호는_한번만_가산된다(signals):
    """출현 횟수로 곱하면 서사 길이가 점수를 지배한다."""
    once = score_text("갈비 좋아요", signals)
    many = score_text("갈비 갈비 갈비 고기 고기", signals)
    assert once.total == many.total


def test_가격민감은_총점에_합산되지_않는다(signals):
    plain = score_text("명절에 갈비찜을 합니다", signals)
    thrifty = score_text("명절에 갈비찜을 합니다. 전통시장에서 저렴하게 삽니다", signals)
    assert thrifty.total == plain.total
    assert thrifty.price_sensitivity > plain.price_sensitivity == 0


def test_발화한_신호를_설명할_수_있다(signals):
    r = score_text("명절에 한식 반찬과 갈비를 준비합니다", signals)
    assert set(r.fired) >= {"holiday_cooking", "hansik_homefood", "meat_preference"}
    assert r.total == 7  # 3 + 2 + 2


def test_한글자_국_오탐이_제거되었다(signals):
    """`국` 한 글자는 fixture에서 중국·태국·영국까지 삼켰다."""
    for noise in ["중국집 음식을 좋아합니다", "태국 여행에서 먹은 음식", "영국식 아침"]:
        assert "hansik_homefood" not in score_text(noise, signals).fired
    for real in ["된장국을 끓입니다", "국밥 한 그릇", "청국장을 즐깁니다"]:
        assert "hansik_homefood" in score_text(real, signals).fired


def test_신호_없는_텍스트는_0점(signals):
    r = score_text("특별히 언급할 것이 없습니다", signals)
    assert r.total == 0 and r.fired == ()


# ── 3단계 셀 할당 ────────────────────────────────────────────────────


def test_12셀이_생성된다(cells):
    specs = build_cell_specs(cells)
    assert len(specs) == 12
    assert len({s.cell_id for s in specs}) == 12


def test_와일드카드_수준은_항상_마지막이다(cells):
    """'나머지 전부'가 먼저 매칭되면 구체 수준이 영원히 안 걸린다."""
    assert cells.regions[-1][0] == "비수도권"
    assert cells.households[-1][0] == "자녀비동거"


@pytest.mark.parametrize(
    ("province", "expected"),
    [
        ("서울", "수도권"),
        ("경기", "수도권"),
        ("인천", "수도권"),
        ("부산", "비수도권"),
        ("제주", "비수도권"),
    ],
)
def test_지역_축(cells, personas_rows, province, expected):
    row = dict(personas_rows[0], age=40, province=province, family_type="배우자와 거주")
    assert assign_axes(row, cells)["region"] == expected


@pytest.mark.parametrize(
    ("family_type", "expected"),
    [
        ("배우자·자녀와 거주", "자녀동거"),
        ("자녀와 거주 (한부모)", "자녀동거"),
        ("기타3세대", "자녀동거"),
        ("4세대이상", "자녀동거"),
        ("배우자와 거주", "자녀비동거"),
        ("혼자 거주", "자녀비동거"),
        ("부모와 동거", "자녀비동거"),
    ],
)
def test_가구_축(cells, personas_rows, family_type, expected):
    row = dict(personas_rows[0], age=40, province="서울", family_type=family_type)
    assert assign_axes(row, cells)["household"] == expected


@pytest.mark.parametrize(
    ("age", "band"), [(30, "30-44"), (44, "30-44"), (45, "45-59"), (69, "60-69")]
)
def test_연령_축(cells, personas_rows, age, band):
    row = dict(personas_rows[0], age=age, province="서울", family_type="배우자와 거주")
    assert assign_axes(row, cells)["age"] == band


def test_셀id는_세_축의_조합이다(cells, personas_rows):
    row = dict(personas_rows[0], age=35, province="서울", family_type="배우자·자녀와 거주")
    assert assign_axes(row, cells) == {"age": "30-44", "region": "수도권", "household": "자녀동거"}


# ── 쿼터 ─────────────────────────────────────────────────────────────


def test_셀당_쿼터_상한을_넘지_않는다(signals_path, small_cells_path, personas_rows, cells):
    m = make(signals_path, small_cells_path, personas_rows)
    per_cell: dict[str, int] = {}
    for a in m.assignments:
        per_cell[a.cell_id] = per_cell.get(a.cell_id, 0) + 1
    assert per_cell
    assert max(per_cell.values()) <= cells.quota_survey


def test_점수가_높은_사람이_먼저_뽑힌다(signals_path, small_cells_path, personas_rows):
    m = make(signals_path, small_cells_path, personas_rows)
    by_cell: dict[str, list[float]] = {}
    for a in m.assignments:
        by_cell.setdefault(a.cell_id, []).append(a.signal_score)
    for scores in by_cell.values():
        assert scores == sorted(scores, reverse=True)


def test_쿼터_미달_셀을_숨기지_않는다(signals_path, small_cells_path, personas_rows):
    diag = sample_diagnostics(make(signals_path, small_cells_path, personas_rows))
    assert diag["total"] == sum(diag["per_cell"].values())
    assert set(diag["per_cell"]) == {
        c.cell_id for c in build_cell_specs(load_cells(small_cells_path))
    }
    assert isinstance(diag["cells_below_floor"], dict)


def test_IDI는_셀별_상위에서_뽑힌다(signals_path, small_cells_path, personas_rows):
    m = make(signals_path, small_cells_path, personas_rows)
    idi = select_idi(m)
    quotas = {c.cell_id: c.quota_idi for c in m.cells}
    counts: dict[str, int] = {}
    for a in idi:
        counts[a.cell_id] = counts.get(a.cell_id, 0) + 1
    for cell_id, n in counts.items():
        assert n <= quotas[cell_id]
    assert {a.uuid for a in idi} <= {a.uuid for a in m.assignments}


def test_IDI_선정도_결정적이다(signals_path, small_cells_path, personas_rows):
    a = select_idi(make(signals_path, small_cells_path, personas_rows))
    b = select_idi(make(signals_path, small_cells_path, personas_rows))
    assert [x.uuid for x in a] == [x.uuid for x in b]


# ── 가중치 훅 ────────────────────────────────────────────────────────


def test_기준분포가_없으면_가중치는_1이고_그_사실을_숨기지_않는다(
    signals_path, small_cells_path, personas_rows
):
    m = make(signals_path, small_cells_path, personas_rows)
    assert all(a.weight == 1.0 for a in m.assignments)


def test_기준분포가_있으면_가중치가_반영된다():
    assignments = [
        CellAssignment(uuid=f"u{i}", cell_id="A", signal_score=0, price_sensitivity_score=0)
        for i in range(3)
    ] + [CellAssignment(uuid="u9", cell_id="B", signal_score=0, price_sensitivity_score=0)]
    weights = compute_weights(assignments, {"A": 0.5, "B": 0.5})
    assert weights["A"] < 1.0 < weights["B"]  # 과대표집 A는 축소, 과소표집 B는 확대
    applied = apply_weights(assignments, {"A": 0.5, "B": 0.5})
    assert applied[0].weight == pytest.approx(weights["A"], abs=1e-6)


def test_가중치_적용은_원본을_바꾸지_않는다():
    orig = [CellAssignment(uuid="u", cell_id="A", signal_score=1, price_sensitivity_score=0)]
    apply_weights(orig, {"A": 1.0})
    assert orig[0].weight == 1.0


# ── 파사드 ───────────────────────────────────────────────────────────


def test_파사드가_계약_시그니처를_export한다():
    from power_persona_sim import sampling
    from power_persona_sim.contracts import SamplingFacade

    assert callable(sampling.build_sample)
    assert callable(sampling.load_personas)
    assert hasattr(SamplingFacade, "build_sample")


def test_build_sample은_SampleManifest를_돌려준다(signals_path, small_cells_path, personas_rows):
    m = make(signals_path, small_cells_path, personas_rows)
    assert isinstance(m, SampleManifest)
    assert m.seed == 42 and m.source == "fixture"
    assert m.signals_config["category"] == "food-galbijjim"
    assert m.cells_config["hard_filter"]["age"]["max"] == 69


def test_load_personas는_manifest_순서를_지킨다(signals_path, small_cells_path, personas_rows):
    m = make(signals_path, small_cells_path, personas_rows)
    people = load_personas(m, rows=personas_rows)
    assert [p.uuid for p in people] == [a.uuid for a in m.assignments]
    assert all(30 <= p.age <= 69 for p in people)


def test_load_personas는_어긋난_원본을_알려준다(signals_path, small_cells_path, personas_rows):
    m = make(signals_path, small_cells_path, personas_rows)
    with pytest.raises(KeyError, match="원본에 없는 uuid"):
        load_personas(m, rows=personas_rows[:1])


def test_load_personas는_fixture를_기본_경로로_찾는다(
    signals_path, small_cells_path, personas_rows
):
    m = make(signals_path, small_cells_path, personas_rows)
    assert len(load_personas(m)) == len(m.assignments)


# ── 매처 단위 ────────────────────────────────────────────────────────


def test_매처_표기별_동작():
    assert ValueMatcher.parse(["서울", "경기"]).matches("서울")
    assert not ValueMatcher.parse(["서울"]).matches("부산")
    assert ValueMatcher.parse("*").matches("무엇이든")
    assert ValueMatcher.parse({"match_any": ["자녀"]}).matches("배우자·자녀와 거주")
    m = ValueMatcher.parse({"match_any": ["거주"], "exclude_any": ["비친족"]})
    assert m.matches("배우자와 거주") and not m.matches("비친족 동거 거주")


def test_알수없는_표기는_거부한다():
    with pytest.raises(ValueError, match="알 수 없는 매처"):
        ValueMatcher.parse(42)


# ── 직렬화 단위 ──────────────────────────────────────────────────────


def test_manifest_문자열_왕복(signals_path, small_cells_path, personas_rows):
    m = make(signals_path, small_cells_path, personas_rows)
    assert dumps(loads(dumps(m))) == dumps(m)
