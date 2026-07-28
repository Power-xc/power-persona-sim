"""HF 캐시 위치 고정.

데이터셋은 압축 해제 시 약 4 GB다. 캐시가 repo 안에 생기면 git status가
망가지고 실수로 커밋될 수 있으므로 항상 repo 밖으로 강제한다.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_HF_HOME = Path.home() / ".cache" / "huggingface"


def repo_root() -> Path:
    """이 패키지를 담고 있는 repo 루트 (src/ 의 부모)."""
    return Path(__file__).resolve().parents[3]


def resolve_hf_home() -> Path:
    """HF_HOME을 결정하고 repo 안이면 거부한다.

    환경변수 HF_HOME이 있으면 그것을, 없으면 ~/.cache/huggingface를 쓴다.
    어느 쪽이든 repo 내부를 가리키면 ValueError — 조용히 고쳐주면 다음 사람이
    같은 실수를 반복한다.
    """
    raw = os.environ.get("HF_HOME")
    home = Path(raw).expanduser().resolve() if raw else DEFAULT_HF_HOME.resolve()
    root = repo_root()
    if home == root or root in home.parents:
        raise ValueError(
            f"HF_HOME이 repo 내부를 가리킵니다: {home}\n"
            f"약 4 GB 캐시가 repo 안에 쌓입니다. repo 밖 경로로 지정하세요 "
            f"(예: export HF_HOME=$HOME/.cache/huggingface)."
        )
    return home


def apply_hf_home() -> Path:
    """resolve_hf_home() 결과를 프로세스 환경에 반영한다. HF 로더 호출 전에 부른다."""
    home = resolve_hf_home()
    home.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HOME"] = str(home)
    return home
