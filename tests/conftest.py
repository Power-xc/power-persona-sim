"""공용 fixture 로더.

repo가 `pip install -e` 로 설치되지 않은 상태(pyproject의 README.md 누락 결함)에서도
테스트가 돌도록 src를 경로에 넣는다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PERSONAS_JSONL = FIXTURES / "personas_sample.jsonl"
CONFIGS = ROOT / "configs"


@pytest.fixture(scope="session")
def personas_rows() -> list[dict]:
    """커밋된 실레코드 200건 (NVIDIA Nemotron-Personas-Korea, CC BY 4.0)."""
    from power_persona_sim.dataset import read_jsonl

    rows = list(read_jsonl(PERSONAS_JSONL))
    assert rows, f"fixture가 비었습니다: {PERSONAS_JSONL}"
    return rows


@pytest.fixture(scope="session")
def signals_path() -> Path:
    return CONFIGS / "signals" / "food.yaml"


@pytest.fixture(scope="session")
def cells_path() -> Path:
    return CONFIGS / "cells" / "default.yaml"


@pytest.fixture(scope="session")
def small_cells_path() -> Path:
    """쿼터를 줄인 테스트용 셀 설정 — 200건 fixture로 12셀을 채울 수 없다."""
    return FIXTURES / "cells_small.yaml"
