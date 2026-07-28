"""데이터셋 접근 3경로 + 오프라인 fixture.

브리프 §3의 A/B/C를 그대로 구현한다. 어느 경로든 산출물은 26컬럼 dict의
리스트로 통일되고, 스키마 검증과 PersonaRecord 변환은 schema.py가 맡는다.

    A  HFDatasetsSource      datasets.load_dataset — 100만 행 전체
    B  DuckDBRemoteSource    hf:// parquet 원격 쿼리, 다운로드 없음 (탐색 단계 권장)
    C  ParquetShardSource    샤드 부분 로드 — 프로토타이핑용
    -  FixtureSource         커밋된 jsonl, 네트워크 없음 (테스트 기본값)

manifest의 source 문자열과 매핑:
    "remote-duckdb" → B · "local-parquet" → C · "hf-datasets" → A · "fixture" → FixtureSource
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from ..contracts import ALL_COLUMNS, HF_DATASET_ID
from .cache import apply_hf_home
from .schema import validate_schema

#: 원격 parquet glob — DuckDB httpfs가 hf:// 스킴을 직접 읽는다.
HF_PARQUET_GLOB = f"hf://datasets/{HF_DATASET_ID}/**/*.parquet"

#: 실측 샤드 수 (train-0000N-of-00009.parquet)
SHARD_COUNT = 9


class PersonaSource(Protocol):
    """모든 접근 경로의 공통 인터페이스."""

    #: SampleManifest.source 에 기록되는 식별자
    source_id: str

    def fetch(self, limit: int | None = None) -> list[dict[str, Any]]: ...


# ── 경로 B · DuckDB 원격 쿼리 ────────────────────────────────────────


def _sql_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def build_remote_query(
    columns: Sequence[str] = ALL_COLUMNS,
    *,
    age_min: int | None = None,
    age_max: int | None = None,
    family_type_in: Sequence[str] | None = None,
    province_in: Sequence[str] | None = None,
    text_field: str | None = None,
    text_any: Sequence[str] | None = None,
    limit: int | None = None,
    shard: int | None = None,
) -> str:
    """브리프 §3.3 쿼리를 안전하게 조립한다.

    문자열 리터럴은 전부 홑따옴표 이스케이프를 거친다 — 키워드 사전은 설정
    파일에서 오므로 신뢰 입력이 아니다.
    """
    cols = ", ".join(columns)
    target = _sql_quote(shard_uri(shard) if shard is not None else HF_PARQUET_GLOB)

    where: list[str] = []
    if age_min is not None and age_max is not None:
        where.append(f"age BETWEEN {int(age_min)} AND {int(age_max)}")
    elif age_min is not None:
        where.append(f"age >= {int(age_min)}")
    elif age_max is not None:
        where.append(f"age <= {int(age_max)}")

    if family_type_in:
        where.append("family_type IN (" + ", ".join(_sql_quote(v) for v in family_type_in) + ")")
    if province_in:
        where.append("province IN (" + ", ".join(_sql_quote(v) for v in province_in) + ")")
    if text_field and text_any:
        ors = " OR ".join(f"{text_field} LIKE {_sql_quote('%' + kw + '%')}" for kw in text_any)
        where.append(f"({ors})")

    sql = f"SELECT {cols}\nFROM {target}"
    if where:
        sql += "\nWHERE " + "\n  AND ".join(where)
    # uuid 정렬로 원격 결과 순서를 고정한다 — LIMIT이 붙으면 순서가 곧 표본이다.
    sql += "\nORDER BY uuid"
    if limit is not None:
        sql += f"\nLIMIT {int(limit)}"
    return sql


def shard_uri(index: int) -> str:
    if not 0 <= index < SHARD_COUNT:
        raise ValueError(f"샤드 인덱스는 0~{SHARD_COUNT - 1} 범위입니다: {index}")
    return f"hf://datasets/{HF_DATASET_ID}/data/train-{index:05d}-of-{SHARD_COUNT:05d}.parquet"


@dataclass
class DuckDBRemoteSource:
    """경로 B — 2 GB를 받지 않고 원격 parquet을 직접 쿼리한다.

    필터 조건 튜닝 단계에서 쓴다. 최종 표본이 수백 명이면 전체를 받을 이유가 없다.
    """

    query_kwargs: dict[str, Any] = field(default_factory=dict)
    source_id: str = "remote-duckdb"

    def fetch(self, limit: int | None = None) -> list[dict[str, Any]]:
        import duckdb  # 지연 임포트 — fixture 경로만 쓰는 테스트에 부담 주지 않는다.

        kwargs = dict(self.query_kwargs)
        if limit is not None:
            kwargs["limit"] = limit
        sql = build_remote_query(**kwargs)

        con = duckdb.connect()
        try:
            con.execute("INSTALL httpfs; LOAD httpfs;")
            cursor = con.execute(sql)
            columns = [d[0] for d in cursor.description]
            rows = [dict(zip(columns, r, strict=True)) for r in cursor.fetchall()]
        finally:
            con.close()
        validate_schema(columns, strict=False)
        return rows


# ── 경로 A · datasets 전체 로드 ──────────────────────────────────────


@dataclass
class HFDatasetsSource:
    """경로 A — datasets.load_dataset으로 100만 행 전체.

    캐시는 apply_hf_home()이 repo 밖으로 고정한다. 압축 해제 약 4 GB이므로
    최종 표본 확정 단계에서만 쓴다 (샤드는 셔플되어 있지만 전수 사용이 원칙).
    """

    split: str = "train"
    source_id: str = "hf-datasets"

    def fetch(self, limit: int | None = None) -> list[dict[str, Any]]:
        from datasets import load_dataset  # 지연 임포트 — hf extra가 없어도 모듈이 임포트되게

        apply_hf_home()
        split = f"{self.split}[:{int(limit)}]" if limit is not None else self.split
        ds = load_dataset(HF_DATASET_ID, split=split)
        validate_schema(ds.column_names)
        return [dict(row) for row in ds]


# ── 경로 C · parquet 샤드 부분 로드 ──────────────────────────────────


@dataclass
class ParquetShardSource:
    """경로 C — 샤드 일부만 읽는다. 프로토타이핑 전용.

    로컬 경로가 주어지면 그것을, 없으면 원격 샤드 URI를 읽는다.
    실측상 샤드는 셔플되어 있어(첫 50행에 15개 시도가 섞여 나옴) 지역 편향은
    관찰되지 않았지만, 브리프 §3.4대로 최종 표본 추출에는 전수를 쓴다.
    """

    shards: Sequence[int] = (0,)
    local_dir: Path | None = None
    source_id: str = "local-parquet"

    def _targets(self) -> list[str]:
        if self.local_dir is not None:
            base = Path(self.local_dir)
            return [str(base / f"train-{i:05d}-of-{SHARD_COUNT:05d}.parquet") for i in self.shards]
        return [shard_uri(i) for i in self.shards]

    def fetch(self, limit: int | None = None) -> list[dict[str, Any]]:
        import duckdb

        per_shard = None if limit is None else max(1, -(-int(limit) // len(self._targets())))
        con = duckdb.connect()
        rows: list[dict[str, Any]] = []
        try:
            con.execute("INSTALL httpfs; LOAD httpfs;")
            for target in self._targets():
                sql = f"SELECT {', '.join(ALL_COLUMNS)} FROM {_sql_quote(target)}"
                if per_shard is not None:
                    sql += f" LIMIT {per_shard}"
                cursor = con.execute(sql)
                columns = [d[0] for d in cursor.description]
                validate_schema(columns, strict=False)
                rows.extend(dict(zip(columns, r, strict=True)) for r in cursor.fetchall())
        finally:
            con.close()
        return rows if limit is None else rows[: int(limit)]


# ── fixture · 오프라인 ───────────────────────────────────────────────

DEFAULT_FIXTURE = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "personas_sample.jsonl"
)


@dataclass
class FixtureSource:
    """커밋된 jsonl을 읽는다. 네트워크 없음 — 테스트의 기본 경로."""

    path: Path = DEFAULT_FIXTURE
    source_id: str = "fixture"

    def fetch(self, limit: int | None = None) -> list[dict[str, Any]]:
        return list(read_jsonl(self.path, limit=limit))


def read_jsonl(path: Path | str, *, limit: int | None = None) -> Iterable[dict[str, Any]]:
    """`#`로 시작하는 머리말 주석을 건너뛰며 jsonl을 읽는다."""
    count = 0
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            yield json.loads(line)
            count += 1
            if limit is not None and count >= limit:
                return


def write_jsonl(path: Path | str, rows: Iterable[dict[str, Any]], *, header: str = "") -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with path.open("w", encoding="utf-8") as fh:
        for comment in filter(None, header.splitlines()):
            fh.write(f"# {comment}\n")
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            written += 1
    return written


_SOURCES: dict[str, type] = {
    "remote-duckdb": DuckDBRemoteSource,
    "local-parquet": ParquetShardSource,
    "hf-datasets": HFDatasetsSource,
    "fixture": FixtureSource,
}


def get_source(source_id: str, **kwargs: Any) -> PersonaSource:
    """manifest.source 문자열로 접근 경로를 되살린다."""
    try:
        cls = _SOURCES[source_id]
    except KeyError:
        raise ValueError(
            f"알 수 없는 source: {source_id!r} — {sorted(_SOURCES)} 중 하나여야 합니다."
        ) from None
    return cls(**kwargs)
