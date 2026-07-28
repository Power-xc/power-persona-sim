"""26컬럼 스키마 검증과 dict → PersonaRecord 변환.

실측 확인 (DuckDB httpfs로 원격 parquet DESCRIBE):
- 컬럼은 정확히 26개, contracts.ALL_COLUMNS와 집합이 일치한다.
- `age`만 BIGINT이고 나머지 25개는 전부 VARCHAR다.
- `*_list` 필드는 파이썬 repr 문자열이다: "['a', 'b']" — JSON이 아니라 홑따옴표.
"""

from __future__ import annotations

import ast
import json
from typing import Any

from ..contracts import ALL_COLUMNS, PersonaRecord

LIST_COLUMNS = ("skills_and_expertise_list", "hobbies_and_interests_list")

#: PersonaRecord가 raw 밖으로 끌어올려 쓰는 필드 (uuid·age 제외한 문자열 필드)
_TEXT_FIELDS = (
    "sex",
    "marital_status",
    "family_type",
    "housing_type",
    "education_level",
    "occupation",
    "district",
    "province",
    "persona",
    "culinary_persona",
    "family_persona",
    "hobbies_and_interests",
)


class SchemaError(ValueError):
    """데이터셋 스키마가 계약과 어긋날 때."""


def validate_schema(columns: list[str] | tuple[str, ...], *, strict: bool = True) -> None:
    """컬럼 집합이 contracts.ALL_COLUMNS와 일치하는지 검사한다.

    strict=False면 여분 컬럼은 허용하고 누락만 잡는다 (부분 SELECT 결과 검증용).
    """
    got, want = set(columns), set(ALL_COLUMNS)
    missing = sorted(want - got)
    if missing:
        raise SchemaError(f"필수 컬럼 누락 {len(missing)}개: {missing}")
    extra = sorted(got - want)
    if strict and extra:
        raise SchemaError(
            f"계약에 없는 컬럼 {len(extra)}개: {extra} — contracts.ALL_COLUMNS 갱신이 필요한지 확인하세요."
        )


def parse_list_field(value: Any) -> list[str]:
    """`*_list` 문자열을 리스트로. 이미 리스트면 그대로 통과시킨다.

    실측 포맷은 파이썬 repr("['a', 'b']")이라 literal_eval이 1순위,
    JSON으로 바뀔 가능성에 대비해 json.loads가 2순위다. 둘 다 실패하면
    빈 리스트가 아니라 원문 1개짜리 리스트를 돌려준다 — 조용한 데이터 손실 방지.
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    text = str(value).strip()
    if not text:
        return []
    for parser in (ast.literal_eval, json.loads):
        try:
            parsed = parser(text)
        except (ValueError, SyntaxError, TypeError):
            continue
        if isinstance(parsed, (list, tuple)):
            return [str(v) for v in parsed]
    return [text]


def to_persona_record(row: dict[str, Any]) -> PersonaRecord:
    """데이터셋 1행(dict) → PersonaRecord.

    raw에는 26컬럼 원본을 그대로 보존하되, `*_list` 두 필드는 파싱된 리스트로
    치환해 넣는다. 필터링은 `_list` 쪽이 유리하다 (브리프 §2.2).
    식별자는 언제나 uuid — 동명이인이 약 79%다.
    """
    uuid = row.get("uuid")
    if not uuid:
        raise SchemaError("uuid 없는 레코드 — 동명이인 79%라 이름은 식별자로 쓸 수 없습니다.")

    raw = dict(row)
    for col in LIST_COLUMNS:
        if col in raw:
            raw[col] = parse_list_field(raw[col])

    try:
        age = int(row["age"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SchemaError(
            f"age를 정수로 읽을 수 없습니다 (uuid={uuid}): {row.get('age')!r}"
        ) from exc

    fields = {name: str(row.get(name) or "") for name in _TEXT_FIELDS}
    return PersonaRecord(uuid=str(uuid), age=age, raw=raw, **fields)


def to_persona_records(rows: list[dict[str, Any]]) -> list[PersonaRecord]:
    return [to_persona_record(r) for r in rows]
