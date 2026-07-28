"""configs/benchmarks/ YAML → 검증용 기대 분포 변환.

벤치마크 셀 키는 "age=30-44|region=수도권|family=자녀동거" 꼴이고,
sampling의 cell_id는 "30-44_수도권_자녀동거" 꼴이다. 여기서 잇는다.
proportion이 null인 셀(미확보 수치)은 조용히 채우지 않고 제외한다.
"""

from __future__ import annotations

from pathlib import Path

import yaml


def _cell_key_to_id(key: str) -> str:
    """'age=30-44|region=수도권|family=자녀동거' → '30-44_수도권_자녀동거'."""
    return "_".join(part.split("=", 1)[1] for part in key.split("|"))


def load_benchmark(path: Path | str) -> dict[str, float]:
    """벤치마크 YAML의 cells 섹션을 {cell_id: 기대 비율}로 변환.

    check_distribution / validate(benchmark=...)의 입력 형식이다.
    """
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    cells = data.get("cells")
    if not isinstance(cells, dict):
        raise TypeError(f"벤치마크에 cells 매핑이 없다: {path}")

    result: dict[str, float] = {}
    for key, spec in cells.items():
        proportion = spec.get("proportion") if isinstance(spec, dict) else spec
        if proportion is None:
            continue  # 미확보 수치 — 가짜 값으로 채우지 않는다
        result[_cell_key_to_id(str(key))] = float(proportion)

    if not result:
        raise ValueError(f"벤치마크에 사용 가능한 셀 비율이 없다: {path}")
    return result
