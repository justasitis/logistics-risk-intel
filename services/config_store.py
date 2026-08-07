"""사용자 편집 가능 설정 저장소 (config_store).

하드코딩됐던 업무 기준정보(항로 그룹, 위치 마스터, 각종 임계값, 법인 매핑,
선사·경유항로 추론 규칙)를 JSON 설정으로 이관해, 관리자가
PUT /api/config/{key} 로 수정하고 POST /api/config/{key}/reset 으로
기본값으로 되돌릴 수 있게 한다.

[파일 해석 규칙]
- 읽기: 커스텀 파일(설정 디렉터리/{key}.json)이 있으면 커스텀, 없으면
  repo 기본 파일(backend/app/data/...)을 읽는다.
- 쓰기: 커스텀 파일에 atomic 저장 (tmp → os.replace).
- reset: 커스텀 파일 삭제 → repo 기본 파일로 복귀.

[설정 디렉터리 결정 순서]
1. LRI_CONFIG_DIR 환경변수 (명시 오버라이드)
2. SharePoint 루트 하위 config\\ — 기본 경로를 resolve_synced_path로 해석하고
   루트(부모 폴터)가 실재할 때만 사용
3. repo 폴터: backend/data/config
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from backend.app.core.user_path import resolve_synced_path

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DATA_DIR = PROJECT_ROOT / "backend" / "app" / "data"
FALLBACK_CONFIG_DIR = PROJECT_ROOT / "backend" / "data" / "config"

# SharePoint 루트 하위 config 폴터 — {username}은 resolve_synced_path가 치환.
DEFAULT_CONFIG_DIR = (
    r"C:\Users\{username}\SK on\M365_TtNUJmLE - 데이터_접근금지\config"
)


@dataclass(frozen=True)
class ConfigSpec:
    """설정 섹션 메타 — key는 URL/파일명({key}.json)에 그대로 쓴다."""

    key: str
    title: str
    kind: str
    default_filename: str  # backend/app/data 하위 repo 기본 파일명


CONFIG_SPECS: dict[str, ConfigSpec] = {
    spec.key: spec
    for spec in [
        ConfigSpec(
            "route_groups", "항로 그룹", "route_groups",
            "leadtime_route_groups.json",
        ),
        ConfigSpec(
            "location_master", "위치 마스터", "location_master",
            "mi_location_master.json",
        ),
        ConfigSpec(
            "delay_thresholds", "지연 판정 임계값", "thresholds",
            "delay_verdict_thresholds.json",
        ),
        ConfigSpec(
            "gap_thresholds", "ETA-ATA Gap 임계값", "thresholds",
            "gap_thresholds.json",
        ),
        ConfigSpec(
            "anomaly_thresholds", "일정 이상 임계값", "thresholds",
            "anomaly_thresholds.json",
        ),
        ConfigSpec(
            "companies", "법인 매핑", "companies",
            "companies.json",
        ),
        ConfigSpec(
            "carrier_inference", "선사·경유항로 추론 규칙", "carrier_inference",
            "carrier_inference.json",
        ),
    ]
}


def _spec(key: str) -> ConfigSpec:
    spec = CONFIG_SPECS.get(key)
    if spec is None:
        raise KeyError(key)
    return spec


def config_dir() -> Path:
    """커스텀 설정 디렉터리 (LRI_CONFIG_DIR > SharePoint config > repo 폴터)."""
    override = os.environ.get("LRI_CONFIG_DIR", "").strip()
    if override:
        return Path(resolve_synced_path(override))
    resolved = Path(resolve_synced_path(DEFAULT_CONFIG_DIR))
    if resolved.parent.exists():
        return resolved
    return FALLBACK_CONFIG_DIR


def _repo_default_path(key: str) -> Path:
    """repo 기본 파일 경로."""
    return APP_DATA_DIR / _spec(key).default_filename


def custom_path(key: str) -> Path:
    """커스텀 파일 경로 (설정 디렉터리/{key}.json)."""
    return config_dir() / f"{_spec(key).key}.json"


def load_config(key: str, *, default_path: Path | None = None) -> Any | None:
    """설정 JSON 로드 — 커스텀 우선, 없으면 repo 기본. 둘 다 없으면 None.

    default_path를 넘기면 repo 기본 파일 위치를 호출처가 재지정할 수 있다
    (테스트에서 모듈 상수 경로를 monkeypatch하는 기존 패턴 지원).
    """
    spec = _spec(key)
    custom = custom_path(key)
    target = (
        custom if custom.exists()
        else (default_path or _repo_default_path(spec.key))
    )
    if not target.exists():
        return None
    return json.loads(target.read_text(encoding="utf-8"))


def save_config(key: str, data: Any) -> None:
    """커스텀 파일에 atomic 저장 (tmp → os.replace)."""
    path = custom_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp, path)


def reset_config(key: str) -> bool:
    """커스텀 파일 삭제 → repo 기본으로 복귀. 삭제 여부 반환."""
    path = custom_path(key)
    if not path.exists():
        return False
    path.unlink()
    return True


def source_of(key: str) -> str:
    """현재 적용 출처 — "custom" | "default"."""
    return "custom" if custom_path(key).exists() else "default"


def updated_at(key: str) -> str | None:
    """커스텀 파일 수정 시각 (ISO). 커스텀이 없으면 None."""
    path = custom_path(key)
    if not path.exists():
        return None
    return datetime.fromtimestamp(
        path.stat().st_mtime,
    ).isoformat(timespec="seconds")


def describe(key: str, *, include_data: bool = False) -> dict[str, Any]:
    """섹션 메타 (+ 선택적으로 현재 적용 데이터)."""
    spec = _spec(key)
    payload: dict[str, Any] = {
        "key": spec.key,
        "title": spec.title,
        "kind": spec.kind,
        "source": source_of(key),
        "updated_at": updated_at(key),
    }
    if include_data:
        payload["data"] = load_config(key)
    return payload


def catalog() -> list[dict[str, Any]]:
    """전체 섹션 메타 목록 (GET /api/config/catalog 응답용)."""
    return [describe(key) for key in CONFIG_SPECS]


def load_companies() -> list[dict[str, Any]] | None:
    """companies 설정의 법인 목록. 파일 없음/형식 오류 시 None (호출처 폴터용)."""
    try:
        data = load_config("companies")
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    companies = data.get("companies")
    if not isinstance(companies, list) or not companies:
        return None
    valid = [
        c
        for c in companies
        if isinstance(c, dict) and c.get("code") and c.get("lap_code")
    ]
    return valid or None


# ---------- 검증 (PUT /api/config/{key}) ----------
# 실패 시 ValueError(한국어 메시지) — API 계층에서 400으로 변환한다.


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_int_like(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    return isinstance(value, float) and value.is_integer()


def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_route_groups(data: Any) -> None:
    if not isinstance(data, dict) or not isinstance(data.get("groups"), list):
        raise ValueError("route_groups 설정은 groups 리스트를 포함한 객체여야 합니다.")
    seen: set[str] = set()
    for idx, group in enumerate(data["groups"]):
        where = f"groups[{idx}]"
        if not isinstance(group, dict):
            raise ValueError(f"{where}: 그룹은 객체여야 합니다.")
        for field in ("group_id", "name", "region"):
            if not _nonempty_str(group.get(field)):
                raise ValueError(f"{where}: {field} 필드가 필요합니다.")
        group_id = group["group_id"]
        if group_id in seen:
            raise ValueError(f"group_id가 중복됩니다: {group_id}")
        seen.add(group_id)
        codes = group.get("arvl_codes")
        if not isinstance(codes, list) or not all(
            isinstance(c, str) for c in codes
        ):
            raise ValueError(
                f"{where}: arvl_codes는 문자열 리스트여야 합니다."
            )
        if "delay_target" in group and not isinstance(
            group["delay_target"], bool
        ):
            raise ValueError(f"{where}: delay_target은 true/false여야 합니다.")


def _validate_location_master(data: Any) -> None:
    if not isinstance(data, dict):
        raise ValueError(
            "location_master 설정은 코드 → 위치 객체의 맵이어야 합니다."
        )
    for code, item in data.items():
        if not isinstance(item, dict):
            raise ValueError(f"{code}: 위치는 객체여야 합니다.")
        for field in ("name", "location_type"):
            if not _nonempty_str(item.get(field)):
                raise ValueError(f"{code}: {field} 필드가 필요합니다.")
        lat = item.get("lat")
        if not _is_number(lat) or not -90 <= lat <= 90:
            raise ValueError(f"{code}: lat는 -90~90 숫자여야 합니다.")
        lon = item.get("lon")
        if not _is_number(lon) or not -180 <= lon <= 180:
            raise ValueError(f"{code}: lon는 -180~180 숫자여야 합니다.")
        radius = item.get("default_radius_km")
        if not _is_number(radius) or radius <= 0:
            raise ValueError(f"{code}: default_radius_km는 양수여야 합니다.")
        aliases = item.get("aliases", [])
        if not isinstance(aliases, list):
            raise ValueError(f"{code}: aliases는 리스트여야 합니다.")


def _validate_delay_thresholds(data: Any) -> None:
    if not isinstance(data, dict):
        raise ValueError("delay_thresholds 설정은 객체여야 합니다.")
    for field in (
        "iqr_tight",
        "median_small_abs",
        "median_late",
        "iqr_volatile",
        "tail_burst",
    ):
        value = data.get(field)
        if not _is_number(value) or value <= 0:
            raise ValueError(f"{field}는 양수 숫자여야 합니다.")
    min_sample = data.get("min_sample")
    if not _is_int_like(min_sample) or min_sample < 1:
        raise ValueError("min_sample는 1 이상의 정수여야 합니다.")
    coverage_warn = data.get("coverage_warn")
    if not _is_number(coverage_warn) or not 0 <= coverage_warn <= 1:
        raise ValueError("coverage_warn는 0~1 숫자여야 합니다.")


def _validate_gap_thresholds(data: Any) -> None:
    if not isinstance(data, dict):
        raise ValueError("gap_thresholds 설정은 객체여야 합니다.")
    warn_days = data.get("warn_days")
    if not _is_number(warn_days) or warn_days <= 0:
        raise ValueError("warn_days는 양수여야 합니다.")
    watch_consecutive = data.get("watch_consecutive")
    if not _is_int_like(watch_consecutive) or watch_consecutive < 2:
        raise ValueError("watch_consecutive는 2 이상의 정수여야 합니다.")
    weeks = data.get("weeks")
    if not _is_int_like(weeks) or not 4 <= weeks <= 16:
        raise ValueError("weeks는 4~16 정수여야 합니다.")
    etd_lookback_days = data.get("etd_lookback_days")
    if not _is_number(etd_lookback_days) or etd_lookback_days <= 0:
        raise ValueError("etd_lookback_days는 양수여야 합니다.")


def _anomaly_field_names() -> list[str]:
    """AnomalyThresholds dataclass 필드명 (지연 import — 순환 참조 방지)."""
    from dataclasses import fields

    from services.anomaly_engine import AnomalyThresholds

    return [f.name for f in fields(AnomalyThresholds)]


def _validate_anomaly_thresholds(data: Any) -> None:
    if not isinstance(data, dict):
        raise ValueError("anomaly_thresholds 설정은 객체여야 합니다.")
    names = _anomaly_field_names()
    unknown = sorted(set(data) - set(names))
    if unknown:
        raise ValueError("알 수 없는 필드: " + ", ".join(unknown))
    for name in names:
        value = data.get(name)
        if not _is_int_like(value) or value <= 0:
            raise ValueError(f"{name}는 양의 정수여야 합니다.")


def _validate_companies(data: Any) -> None:
    if (
        not isinstance(data, dict)
        or not isinstance(data.get("companies"), list)
        or not data["companies"]
    ):
        raise ValueError(
            "companies 설정은 companies 리스트를 포함한 객체여야 합니다."
        )
    seen: set[str] = set()
    for idx, company in enumerate(data["companies"]):
        where = f"companies[{idx}]"
        if not isinstance(company, dict):
            raise ValueError(f"{where}: 법인은 객체여야 합니다.")
        for field in ("code", "label", "lap_code"):
            if not _nonempty_str(company.get(field)):
                raise ValueError(f"{where}: {field} 필드가 필요합니다.")
        code = company["code"].strip().upper()
        if code in seen:
            raise ValueError(f"법인 코드가 중복됩니다: {code}")
        seen.add(code)


def _validate_carrier_inference(data: Any) -> None:
    if not isinstance(data, dict):
        raise ValueError("carrier_inference 설정은 객체여야 합니다.")
    ports = data.get("adria_arrival_ports")
    if (
        not isinstance(ports, list)
        or not ports
        or not all(_nonempty_str(p) for p in ports)
    ):
        raise ValueError("adria_arrival_ports는 비어 있지 않은 문자열 리스트여야 합니다.")
    vessel_rules = data.get("vessel_carrier_rules")
    if not isinstance(vessel_rules, list):
        raise ValueError("vessel_carrier_rules는 리스트여야 합니다.")
    for idx, rule in enumerate(vessel_rules):
        where = f"vessel_carrier_rules[{idx}]"
        if not isinstance(rule, dict):
            raise ValueError(f"{where}: 규칙은 객체여야 합니다.")
        for field in ("keyword", "carrier_cd", "carrier_nm"):
            if not _nonempty_str(rule.get(field)):
                raise ValueError(f"{where}: {field} 필드가 필요합니다.")
    via_rules = data.get("carrier_via_rules")
    if not isinstance(via_rules, list):
        raise ValueError("carrier_via_rules는 리스트여야 합니다.")
    for idx, rule in enumerate(via_rules):
        where = f"carrier_via_rules[{idx}]"
        if not isinstance(rule, dict):
            raise ValueError(f"{where}: 규칙은 객체여야 합니다.")
        if not _nonempty_str(rule.get("carrier_cd")):
            raise ValueError(f"{where}: carrier_cd 필드가 필요합니다.")
        if not isinstance(rule.get("carrier_nm_contains"), str):
            raise ValueError(
                f"{where}: carrier_nm_contains는 문자열이어야 합니다."
            )
        if str(rule.get("via") or "").upper() not in ("SUEZ", "CAPE"):
            raise ValueError(f"{where}: via는 SUEZ 또는 CAPE만 가능합니다.")


_VALIDATORS: dict[str, Callable[[Any], None]] = {
    "route_groups": _validate_route_groups,
    "location_master": _validate_location_master,
    "delay_thresholds": _validate_delay_thresholds,
    "gap_thresholds": _validate_gap_thresholds,
    "anomaly_thresholds": _validate_anomaly_thresholds,
    "companies": _validate_companies,
    "carrier_inference": _validate_carrier_inference,
}


def validate_config(key: str, data: Any) -> None:
    """설정 데이터 검증. 실패 시 ValueError(한국어 메시지)."""
    _spec(key)
    _VALIDATORS[key](data)
