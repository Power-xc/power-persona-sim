"""2단계 — 텍스트 신호 스코어링 (브리프 §5.1).

카테고리가 바뀌면 configs/signals/*.yaml 만 교체한다. 이 모듈은 카테고리를 모른다.

가격 민감도는 **총점에 합산하지 않는다.** 가격에 민감한 사람이 카테고리
관여도가 높은 것도 낮은 것도 아니기 때문이다 — 세그먼트 분석용 독립 축이다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class Signal:
    key: str
    label: str
    keywords: tuple[str, ...]
    weight: float


@dataclass(frozen=True)
class SignalConfig:
    category: str
    text_field: str
    signals: tuple[Signal, ...]
    price_axis: Signal | None
    raw: dict[str, Any]

    @property
    def max_score(self) -> float:
        return sum(s.weight for s in self.signals)


def _signal(key: str, spec: dict[str, Any]) -> Signal:
    keywords = spec.get("keywords") or []
    if not keywords:
        raise ValueError(f"신호 {key!r}에 keywords가 없습니다.")
    return Signal(
        key=key,
        label=str(spec.get("label", key)),
        keywords=tuple(str(k) for k in keywords),
        weight=float(spec.get("weight", 1)),
    )


def load_signals(path: Path | str) -> SignalConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TypeError(f"신호 설정이 매핑이 아닙니다: {path}")

    signals = tuple(_signal(k, v) for k, v in (raw.get("signals") or {}).items())
    if not signals:
        raise ValueError(f"신호가 하나도 정의되지 않았습니다: {path}")

    price_raw = raw.get("price_sensitivity_axis")
    price = _signal("price_sensitivity", price_raw) if price_raw else None

    return SignalConfig(
        category=str(raw.get("category", "unknown")),
        text_field=str(raw.get("text_field", "culinary_persona")),
        signals=signals,
        price_axis=price,
        raw=raw,
    )


@dataclass(frozen=True)
class ScoreResult:
    total: float
    price_sensitivity: float
    fired: tuple[str, ...]  # 발화한 신호 key — 왜 뽑혔는지 설명 가능해야 한다


def score_text(text: str, config: SignalConfig) -> ScoreResult:
    """신호별로 키워드가 **하나라도** 걸리면 가중치를 1회 더한다.

    출현 횟수로 곱하지 않는 이유: 서사 길이가 점수를 지배해 버린다.
    """
    haystack = text or ""
    total = 0.0
    fired: list[str] = []
    for sig in config.signals:
        if any(kw in haystack for kw in sig.keywords):
            total += sig.weight
            fired.append(sig.key)

    price = 0.0
    if config.price_axis and any(kw in haystack for kw in config.price_axis.keywords):
        price = config.price_axis.weight

    return ScoreResult(total=total, price_sensitivity=price, fired=tuple(fired))
