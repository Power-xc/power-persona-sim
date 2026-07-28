"""YAML 원시 읽기와 타입 검사 도구.

로더는 관대하지 않다. 알 수 없는 키도 오류로 잡는다 — 오타 난 키를 조용히
무시하면 "썼는데 반영이 안 되는" 설계 파일이 생기고, 그건 조사에서 가장
비싼 종류의 버그다. 검사 함수는 예외를 던지지 않고 errors 리스트에 쌓기만
하며, 문서 단위로 `raise_if`가 한 번에 던진다. 한 번 고칠 때 다 고치라는 뜻이다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class DesignError(ValueError):
    """설계 문서의 구조 위반. 발견된 위반 전부를 한 메시지에 담는다."""


def read_mapping(path: Path) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DesignError(f"설계 파일을 찾을 수 없음: {path}") from exc
    except yaml.YAMLError as exc:
        raise DesignError(f"YAML 파싱 실패 {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise DesignError(f"최상위가 매핑이 아님: {path}")
    return raw


def raise_if(errors: list[str], path: Path) -> None:
    if errors:
        joined = "\n".join(f"  - {error}" for error in errors)
        raise DesignError(f"{path}\n{joined}")


def check_keys(
    data: Any, required: set[str], optional: set[str], where: str, errors: list[str]
) -> bool:
    """필수 키가 모두 있으면 True. 알 수 없는 키는 기록만 하고 통과시키지 않는다."""
    if not isinstance(data, dict):
        errors.append(f"{where}: 매핑이어야 함")
        return False
    missing = sorted(required - data.keys())
    unknown = sorted(data.keys() - required - optional)
    if missing:
        errors.append(f"{where}: 필수 키 누락 {missing}")
    if unknown:
        errors.append(f"{where}: 알 수 없는 키 {unknown}")
    return not missing


def text(data: dict[str, Any], key: str, where: str, errors: list[str]) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{where}: '{key}'는 비어 있지 않은 문자열이어야 함")
        return ""
    return value.strip()


def text_list(data: dict[str, Any], key: str, where: str, errors: list[str]) -> list[str]:
    value = data.get(key, [])
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        errors.append(f"{where}: '{key}'는 문자열 리스트여야 함")
        return []
    return list(value)


def integer(data: dict[str, Any], key: str, where: str, errors: list[str]) -> int:
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        errors.append(f"{where}: '{key}'는 정수여야 함")
        return 0
    return value


def item_list(data: dict[str, Any], key: str, where: str, errors: list[str]) -> list[Any]:
    value = data.get(key, [])
    if not isinstance(value, list) or not value:
        errors.append(f"{where}: '{key}'는 비어 있지 않은 리스트여야 함")
        return []
    return value


def check_unique(ids: list[str], where: str, errors: list[str]) -> None:
    duplicates = sorted({value for value in ids if ids.count(value) > 1 and value})
    if duplicates:
        errors.append(f"{where}: 중복된 id {duplicates}")
