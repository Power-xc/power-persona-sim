"""dataset — 스키마 검증, 레코드 변환, 캐시 위치, 쿼리 조립.

네트워크를 쓰는 테스트는 전부 skip 마커가 붙는다 (PPS_NETWORK_TESTS=1로 활성).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from power_persona_sim.contracts import ALL_COLUMNS, PersonaRecord
from power_persona_sim.dataset import (
    HF_PARQUET_GLOB,
    SHARD_COUNT,
    DuckDBRemoteSource,
    FixtureSource,
    SchemaError,
    build_remote_query,
    get_source,
    parse_list_field,
    resolve_hf_home,
    shard_uri,
    to_persona_record,
    to_persona_records,
    validate_schema,
    write_jsonl,
)

needs_network = pytest.mark.skipif(
    os.environ.get("PPS_NETWORK_TESTS") != "1",
    reason="네트워크 테스트는 PPS_NETWORK_TESTS=1 일 때만 실행합니다.",
)


# ── 스키마 ───────────────────────────────────────────────────────────


def test_계약_컬럼은_실측_26종이다():
    assert len(ALL_COLUMNS) == 26
    assert len(set(ALL_COLUMNS)) == 26


def test_fixture가_계약_스키마와_정확히_일치한다(personas_rows):
    for row in personas_rows:
        validate_schema(list(row))


def test_컬럼_누락은_에러다():
    with pytest.raises(SchemaError, match="필수 컬럼 누락"):
        validate_schema(["uuid", "age"])


def test_여분_컬럼은_strict에서만_에러다():
    cols = [*ALL_COLUMNS, "surprise"]
    validate_schema(cols, strict=False)
    with pytest.raises(SchemaError, match="계약에 없는 컬럼"):
        validate_schema(cols)


# ── _list 파싱 ───────────────────────────────────────────────────────


def test_list_필드는_파이썬_repr_문자열이다(personas_rows):
    """실측 포맷은 JSON이 아니라 홑따옴표 repr — json.loads 단독으로는 못 읽는다."""
    raw = personas_rows[0]["hobbies_and_interests_list"]
    assert isinstance(raw, str)
    assert raw.startswith("[") and "'" in raw
    assert len(parse_list_field(raw)) >= 1


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("['가', '나']", ["가", "나"]),
        ('["가", "나"]', ["가", "나"]),
        ("[]", []),
        ("", []),
        (None, []),
        (["이미", "리스트"], ["이미", "리스트"]),
    ],
)
def test_list_파싱_형식별(raw, expected):
    assert parse_list_field(raw) == expected


def test_파싱_불가면_원문을_보존한다():
    """빈 리스트를 돌려주면 데이터가 조용히 사라진다."""
    assert parse_list_field("망가진 [문자열") == ["망가진 [문자열"]


# ── PersonaRecord 변환 ───────────────────────────────────────────────


def test_레코드_변환은_uuid_기준이다(personas_rows):
    rec = to_persona_record(personas_rows[0])
    assert isinstance(rec, PersonaRecord)
    assert rec.uuid == personas_rows[0]["uuid"]
    assert isinstance(rec.age, int)


def test_raw에_26컬럼이_보존되고_list는_파싱된다(personas_rows):
    rec = to_persona_record(personas_rows[0])
    assert set(rec.raw) == set(ALL_COLUMNS)
    assert isinstance(rec.raw["hobbies_and_interests_list"], list)
    assert isinstance(rec.raw["skills_and_expertise_list"], list)


def test_uuid_없으면_거부한다(personas_rows):
    row = dict(personas_rows[0], uuid="")
    with pytest.raises(SchemaError, match="uuid"):
        to_persona_record(row)


def test_age가_정수가_아니면_거부한다(personas_rows):
    row = dict(personas_rows[0], age="서른")
    with pytest.raises(SchemaError, match="age"):
        to_persona_record(row)


def test_fixture_200건_전부_변환된다(personas_rows):
    records = to_persona_records(personas_rows)
    assert len(records) == 200
    assert len({r.uuid for r in records}) == 200


# ── 캐시 위치 ────────────────────────────────────────────────────────


def test_HF_HOME이_repo_안이면_거부한다(monkeypatch):
    inside = Path(__file__).resolve().parents[1] / ".hf-cache"
    monkeypatch.setenv("HF_HOME", str(inside))
    with pytest.raises(ValueError, match="repo 내부"):
        resolve_hf_home()


def test_HF_HOME_기본값은_repo_밖이다(monkeypatch, tmp_path):
    monkeypatch.setenv("HF_HOME", str(tmp_path / "hf"))
    assert resolve_hf_home() == (tmp_path / "hf").resolve()


# ── 쿼리 조립 ────────────────────────────────────────────────────────


def test_원격_쿼리는_브리프_예시_형태다():
    sql = build_remote_query(
        ["uuid", "age", "culinary_persona"],
        age_min=30,
        age_max=69,
        text_field="culinary_persona",
        text_any=["갈비", "명절"],
        limit=200,
    )
    assert "FROM 'hf://datasets/nvidia/Nemotron-Personas-Korea/**/*.parquet'" in sql
    assert "age BETWEEN 30 AND 69" in sql
    assert "culinary_persona LIKE '%갈비%'" in sql
    assert "ORDER BY uuid" in sql
    assert sql.rstrip().endswith("LIMIT 200")


def test_쿼리는_홑따옴표를_이스케이프한다():
    """키워드 사전은 설정 파일에서 온다 — 신뢰 입력이 아니다."""
    sql = build_remote_query(text_field="culinary_persona", text_any=["it's"])
    assert "''" in sql
    assert sql.count("LIKE") == 1


def test_쿼리에_ORDER_BY가_항상_붙는다():
    """LIMIT이 붙으면 순서가 곧 표본이라 정렬이 없으면 재현되지 않는다."""
    assert "ORDER BY uuid" in build_remote_query()


def test_샤드_URI와_범위():
    assert shard_uri(0).endswith("train-00000-of-00009.parquet")
    assert shard_uri(SHARD_COUNT - 1).endswith("train-00008-of-00009.parquet")
    with pytest.raises(ValueError):
        shard_uri(SHARD_COUNT)


def test_glob에_데이터셋_id가_박혀있다():
    assert "nvidia/Nemotron-Personas-Korea" in HF_PARQUET_GLOB


# ── 소스 레지스트리 ──────────────────────────────────────────────────


def test_source_문자열로_접근경로를_되살린다():
    assert isinstance(get_source("fixture"), FixtureSource)
    assert isinstance(get_source("remote-duckdb"), DuckDBRemoteSource)
    with pytest.raises(ValueError, match="알 수 없는 source"):
        get_source("없는경로")


def test_fixture_소스는_네트워크_없이_읽는다():
    rows = FixtureSource().fetch(limit=5)
    assert len(rows) == 5
    validate_schema(list(rows[0]))


def test_jsonl_왕복(tmp_path, personas_rows):
    path = tmp_path / "rt.jsonl"
    write_jsonl(path, personas_rows[:3], header="테스트 머리말")
    back = FixtureSource(path=path).fetch()
    assert back == personas_rows[:3]
    assert path.read_text(encoding="utf-8").startswith("# 테스트 머리말")


# ── 네트워크 (기본 skip) ─────────────────────────────────────────────


@needs_network
def test_원격_스키마가_계약과_일치한다():
    rows = DuckDBRemoteSource(query_kwargs={"shard": 0}).fetch(limit=3)
    assert len(rows) == 3
    validate_schema(list(rows[0]))
