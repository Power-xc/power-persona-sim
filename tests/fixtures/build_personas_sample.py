#!/usr/bin/env python
"""공용 fixture 생성기 — tests/fixtures/personas_sample.jsonl 을 만든다.

무과금 경로만 쓴다 (DuckDB httpfs 원격 parquet 조회, 2 GB 다운로드 없음).
9개 샤드에서 균등하게 머리 부분을 떠서 합친다. 실측상 샤드 내부가 이미
셔플되어 있어(첫 50행에 15개 시도가 섞여 나옴) 이 방식으로도 지역 편향이
관찰되지 않았다.

    python tests/fixtures/build_personas_sample.py [--rows 200]

네트워크가 없으면 스키마에 충실한 합성 레코드로 대체하고 파일 머리말에
synthetic 표기를 남긴다 — 조용히 가짜 데이터를 흘리지 않기 위해서다.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = Path(__file__).resolve().parent / "personas_sample.jsonl"

_SYNTH_FAMILY = ("배우자·자녀와 거주", "배우자와 거주", "혼자 거주", "부모와 동거", "기타3세대")
_SYNTH_PROVINCE = ("서울", "경기", "인천", "부산", "경상남", "충청북", "전라남", "제주")
_SYNTH_CULINARY = (
    "주말마다 가족과 삼겹살을 구워 먹고 명절에는 직접 갈비찜을 준비합니다.",
    "평일에는 밀키트와 배달로 간단히 해결하고 주말에만 집밥을 차립니다.",
    "전통시장에서 저렴한 제철 나물을 사다 반찬을 만들어 두고 먹습니다.",
    "한우와 좋은 재료를 백화점에서 사서 손님상을 차리는 편입니다.",
)


def _pkg():
    """repo가 설치되지 않은 상태로 직접 실행해도 돌게 한다."""
    src = str(ROOT / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from power_persona_sim import contracts, dataset

    return contracts, dataset


def fetch_remote(rows: int) -> list[dict]:
    """9개 샤드에서 균등 분할해 가져온다."""
    import duckdb

    contracts, dataset = _pkg()
    per_shard = -(-rows // dataset.SHARD_COUNT)
    cols = ", ".join(contracts.ALL_COLUMNS)
    union = "\nUNION ALL\n".join(
        f"(SELECT {cols} FROM '{dataset.shard_uri(i)}' LIMIT {per_shard})"
        for i in range(dataset.SHARD_COUNT)
    )
    con = duckdb.connect()
    try:
        con.execute("INSTALL httpfs; LOAD httpfs;")
        cursor = con.execute(f"{union}\nORDER BY uuid")
        columns = [d[0] for d in cursor.description]
        dataset.validate_schema(columns)
        out = [dict(zip(columns, r, strict=True)) for r in cursor.fetchall()]
    finally:
        con.close()
    return out[:rows]


def synth(rows: int) -> list[dict]:
    """네트워크 실패 시 폴백. 26컬럼 스키마를 그대로 채운다."""
    contracts, _ = _pkg()
    out = []
    for i in range(rows):
        uid = hashlib.blake2b(f"synthetic:{i}".encode(), digest_size=16).hexdigest()
        rec = {c: f"합성-{c}-{i}" for c in contracts.ALL_COLUMNS}
        rec.update(
            uuid=uid,
            age=19 + (i * 7) % 71,
            sex="남자" if i % 2 else "여자",
            country="대한민국",
            family_type=_SYNTH_FAMILY[i % len(_SYNTH_FAMILY)],
            province=_SYNTH_PROVINCE[i % len(_SYNTH_PROVINCE)],
            district=f"{_SYNTH_PROVINCE[i % len(_SYNTH_PROVINCE)]}-테스트구",
            culinary_persona=_SYNTH_CULINARY[i % len(_SYNTH_CULINARY)],
            skills_and_expertise_list=f"['합성 역량 {i}A', '합성 역량 {i}B']",
            hobbies_and_interests_list=f"['합성 취미 {i}A', '합성 취미 {i}B']",
        )
        out.append(rec)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=200)
    ap.add_argument("--out", type=Path, default=OUT_PATH)
    args = ap.parse_args()

    contracts, dataset = _pkg()
    try:
        records = fetch_remote(args.rows)
        origin = (
            f"출처: {contracts.HF_DATASET_ID} (CC BY 4.0, NVIDIA) — 실제 레코드",
            f"수집: DuckDB httpfs 원격 parquet 조회, {dataset.SHARD_COUNT}개 샤드 균등 추출, 무과금",
            "생성: python tests/fixtures/build_personas_sample.py",
        )
    except Exception as exc:  # noqa: BLE001 — 네트워크·드라이버 실패 전부 폴백 대상
        print(f"원격 조회 실패 → 합성 레코드로 대체합니다: {exc}", file=sys.stderr)
        records = synth(args.rows)
        origin = (
            "synthetic: 실제 데이터가 아닙니다 — 원격 조회 실패로 생성된 합성 레코드입니다.",
            "synthetic: 스키마(26컬럼)만 충실하며 분포·문장은 실측을 대표하지 않습니다.",
            "synthetic: 재생성 → python tests/fixtures/build_personas_sample.py",
        )

    n = dataset.write_jsonl(args.out, records, header="\n".join(origin))
    print(f"{n}건 기록 → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
