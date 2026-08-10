from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
from typing import Any, Iterable

from ..core.marinesia_settings import (
    MarinesiaSettings,
    get_marinesia_settings,
)


_SECRET_PATTERNS = (
    re.compile(r"([?&]key=)[^&\s\"']+", re.IGNORECASE),
    re.compile(r"\b(api[_-]?key\s*[=:]\s*)[^&\s\"']+", re.IGNORECASE),
)

# 허용 법인 폴터 상수 — companies 설정을 읽지 못할 때만 사용.
# 실제 허용 집합은 companies 설정(기본 backend/app/data/companies.json)이 우선.
_ALLOWED_COMPANIES = {
    "SKO",
    "SKOH",
    "SKBM",
    "SKBA",
    "SKOJ",
    "SKOY",
}


def _allowed_companies() -> set[str]:
    """허용 법인 코드 집합 — companies 설정 우선, 실패 시 상수 폴터.

    참고: AIS latest 파이프라인은 신규 포맷에 company가 없어 법인 구분을
    하지 않는다. 이 헬퍼는 companies 설정 로딩 검증 등 공용 용도로 유지.
    """
    try:
        from services.config_store import load_companies

        companies = load_companies()
    except Exception:  # 설정 로드 실패는 폴터로 흡수
        companies = None
    if companies:
        return {
            str(c.get("code") or "").strip().upper()
            for c in companies
            if c.get("code")
        }
    return set(_ALLOWED_COMPANIES)


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _optional_text(value: Any) -> str | None:
    result = _text(value)
    return result or None


def _digits(value: Any) -> str | None:
    result = re.sub(r"\D", "", _text(value))
    return result or None


def _finite_number(value: Any) -> float | None:
    if value is None or value == "":
        return None

    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    return result if math.isfinite(result) else None


def _valid_coordinate(
    latitude: float | None,
    longitude: float | None,
) -> bool:
    return (
        latitude is not None
        and longitude is not None
        and -90 <= latitude <= 90
        and -180 <= longitude <= 180
    )


def _parse_datetime(value: Any) -> datetime | None:
    raw = _text(value)
    if not raw:
        return None

    normalized = raw.replace("Z", "+00:00")

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def _iso_from_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(
        timestamp,
        tz=timezone.utc,
    ).isoformat()


def sanitize_api_message(value: Any) -> str | None:
    message = _optional_text(value)
    if not message:
        return None

    sanitized = message
    for pattern in _SECRET_PATTERNS:
        sanitized = pattern.sub(r"\1***", sanitized)

    return sanitized


def _candidate_rank(path: Path, root: Path) -> tuple[int, float]:
    try:
        relative = path.relative_to(root)
    except ValueError:
        relative = path

    parts = [part.lower() for part in relative.parts]
    exact_name = path.name.lower() == "marinesia_latest.json"

    if path.parent == root and exact_name:
        priority = 0
    elif exact_name and "current" in parts:
        priority = 1
    elif exact_name:
        priority = 2
    else:
        priority = 3

    return priority, -path.stat().st_mtime


def find_marinesia_file(
    root: Path,
    kind: str,
) -> Path | None:
    if not root.exists() or not root.is_dir():
        return None

    exact_name = f"marinesia_{kind}.json"
    patterns = [exact_name, f"marinesia_{kind}*.json"]

    if kind == "table":
        exact_name = "marinesia_table.csv"
        patterns = [exact_name, "marinesia_table*.csv"]

    candidates: dict[str, Path] = {}

    for pattern in patterns:
        for path in root.rglob(pattern):
            if not path.is_file():
                continue
            candidates[str(path).lower()] = path

    if not candidates:
        return None

    return sorted(
        candidates.values(),
        key=lambda path: _candidate_rank(path, root),
    )[0]


def discover_marinesia_files(
    settings: MarinesiaSettings | None = None,
) -> dict[str, Any]:
    resolved = settings or get_marinesia_settings()
    root = resolved.sharepoint_root

    result: dict[str, Any] = {
        "root": str(root),
        "root_exists": root.exists() and root.is_dir(),
        "files": {},
    }

    for kind in ("latest", "raw", "table"):
        path = find_marinesia_file(root, kind)
        result["files"][kind] = (
            {
                "path": str(path),
                "name": path.name,
                "size_bytes": path.stat().st_size,
                "modified_at": _iso_from_timestamp(
                    path.stat().st_mtime
                ),
            }
            if path
            else None
        )

    return result


def _load_json_array(
    path: Path,
    max_file_size_mb: int,
) -> list[dict[str, Any]]:
    max_bytes = max_file_size_mb * 1024 * 1024
    size = path.stat().st_size

    if size > max_bytes:
        raise ValueError(
            f"{path.name} 크기가 {max_file_size_mb}MB를 초과합니다."
        )

    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except UnicodeDecodeError as exc:
        raise ValueError(
            f"{path.name}을 UTF-8로 읽을 수 없습니다."
        ) from exc
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{path.name} JSON 형식이 올바르지 않습니다: "
            f"line {exc.lineno}, column {exc.colno}"
        ) from exc

    if not isinstance(value, list):
        raise ValueError(
            f"{path.name} 최상위 구조는 배열이어야 합니다."
        )

    rows: list[dict[str, Any]] = []
    for index, row in enumerate(value):
        if not isinstance(row, dict):
            raise ValueError(
                f"{path.name}의 {index + 1}번째 항목이 객체가 아닙니다."
            )
        rows.append(row)

    return rows


def _freshness(
    api_error: bool,
    latitude: float | None,
    longitude: float | None,
    observed_at: datetime | None,
    settings: MarinesiaSettings,
) -> tuple[str, float | None]:
    if api_error:
        return "ERROR", None

    if (
        not _valid_coordinate(latitude, longitude)
        or observed_at is None
    ):
        return "NO_SIGNAL", None

    now = datetime.now(timezone.utc)
    age_hours = max(
        0.0,
        (now - observed_at).total_seconds() / 3600,
    )

    if age_hours <= settings.live_hours:
        return "LIVE", round(age_hours, 2)

    return "STALE", round(age_hours, 2)


def _latest_fetched_at(rows: Iterable[dict[str, Any]]) -> str | None:
    values = [
        parsed
        for parsed in (
            _parse_datetime(row.get("fetched_at"))
            for row in rows
        )
        if parsed is not None
    ]

    return max(values).isoformat() if values else None


def _row_to_ais_item(
    row: dict[str, Any],
    index: int,
    settings: MarinesiaSettings,
) -> tuple[dict[str, Any], bool]:
    # 2026-08 신규 포맷에는 company가 없다 (관리자 1인이 전 법인 선박을
    # 한 파일로 관리). 구 포맷의 company가 있으면 그대로 보존한다.
    company = _text(row.get("company")).upper()
    vessel_name = _text(row.get("vessel_name"))
    # 신규 포맷은 registered_mmsi_no(마스터 등록 MMSI)가 조회 기준
    query_mmsi = _digits(row.get("registered_mmsi_no")) or _digits(
        row.get("query_mmsi_no")
    )
    response_mmsi = _digits(row.get("mmsi"))
    imo = _digits(row.get("imo_no")) or _digits(row.get("imo"))
    latitude = _finite_number(row.get("lat"))
    longitude = _finite_number(row.get("lng"))
    observed_at = _parse_datetime(row.get("ts"))
    fetched_at = _parse_datetime(row.get("fetched_at"))
    api_error = bool(row.get("api_error"))

    position_status, freshness_hours = _freshness(
        api_error,
        latitude,
        longitude,
        observed_at,
        settings,
    )

    coordinate_valid = _valid_coordinate(latitude, longitude)
    sanitized_message = sanitize_api_message(
        row.get("api_message")
    )
    secret_redacted = (
        sanitized_message
        != _optional_text(row.get("api_message"))
    )

    fallback_id = (
        query_mmsi
        or response_mmsi
        or vessel_name
        or f"ROW-{index + 1}"
    )

    heading = _finite_number(row.get("hdt"))
    course = _finite_number(row.get("cog"))

    ais_id_parts = ["MARINESIA"]
    if company:
        ais_id_parts.append(company)
    ais_id_parts.extend([vessel_name, fallback_id])

    item = {
        "ais_id": ":".join(ais_id_parts),
        "shipment_id": "",
        "company": company,
        "trpr_no": None,
        "hbl_no": None,
        "mbl_no": None,
        "vessel_name": vessel_name or "(선명 없음)",
        "query_mmsi_no": query_mmsi,
        "mmsi_no": response_mmsi,
        "imo_no": imo,
        "call_sign": None,
        "position_status": position_status,
        "current_lat": latitude if coordinate_valid else None,
        "current_lon": longitude if coordinate_valid else None,
        "speed": _finite_number(row.get("sog")),
        "heading": heading if heading is not None else course,
        "course": course,
        "nav_status": row.get("status"),
        "position_accuracy": row.get("pos_acc"),
        "rate_of_turn": _finite_number(row.get("rot")),
        "draught": _finite_number(row.get("draught")),
        "last_seen_at": (
            observed_at.isoformat()
            if observed_at
            else None
        ),
        "next_port": _optional_text(row.get("dest")),
        "eta_ais": _optional_text(row.get("eta")),
        "source": "MARINESIA_SHAREPOINT",
        "collected_at": (
            fetched_at.isoformat()
            if fetched_at
            else None
        ),
        "freshness_hours": freshness_hours,
        "api_error": api_error,
        "api_message": sanitized_message,
        "error": sanitized_message if api_error else None,
        "matched_transport_key": None,
        "matched_trpr_no": None,
        "match_method": None,
    }

    return item, secret_redacted


def _summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    mappable = sum(
        1
        for item in items
        if item["current_lat"] is not None
        and item["current_lon"] is not None
    )
    companies = Counter(item["company"] for item in items)

    return {
        "total": len(items),
        "live": sum(
            item["position_status"] == "LIVE"
            for item in items
        ),
        "stale": sum(
            item["position_status"] == "STALE"
            for item in items
        ),
        "no_signal": sum(
            item["position_status"] == "NO_SIGNAL"
            for item in items
        ),
        "error": sum(
            item["position_status"] == "ERROR"
            for item in items
        ),
        "mappable": mappable,
        "linked": 0,
        "unlinked": len(items),
        "companies": dict(sorted(companies.items())),
    }


def read_marinesia_latest(
    companies: list[str] | None = None,
    settings: MarinesiaSettings | None = None,
) -> dict[str, Any]:
    resolved = settings or get_marinesia_settings()
    root = resolved.sharepoint_root
    path = find_marinesia_file(root, "latest")

    if path is None:
        raise FileNotFoundError(
            "SharePoint 폴더에서 marinesia_latest.json을 "
            "찾지 못했습니다."
        )

    rows = _load_json_array(path, resolved.max_file_size_mb)

    # 신규 포맷(2026-08~)에는 company가 없다 — AIS는 법인 구분 없이
    # 전 법인 선박을 하나의 파일로 관리하므로 법인 필터를 적용하지 않는다.
    items: list[dict[str, Any]] = []
    redacted_count = 0

    for index, row in enumerate(rows):
        item, secret_redacted = (
            _row_to_ais_item(row, index, resolved)
        )

        items.append(item)
        redacted_count += int(secret_redacted)

    duplicate_pairs = Counter(
        (
            item["company"],
            item["vessel_name"],
            item["query_mmsi_no"],
        )
        for item in items
    )
    duplicate_count = sum(
        count - 1
        for count in duplicate_pairs.values()
        if count > 1
    )

    vessel_mmsi_candidates: dict[
        tuple[str, str],
        set[str],
    ] = defaultdict(set)

    for item in items:
        candidate = (
            item["query_mmsi_no"]
            or item["mmsi_no"]
        )
        if candidate:
            vessel_mmsi_candidates[
                (item["company"], item["vessel_name"])
            ].add(candidate)

    ambiguous_vessels = [
        {
            "company": key[0],
            "vessel_name": key[1],
            "mmsi_candidates": sorted(values),
        }
        for key, values in vessel_mmsi_candidates.items()
        if len(values) > 1
    ]

    warnings: list[str] = []
    if redacted_count:
        warnings.append(
            f"API 오류 메시지 {redacted_count}건에서 "
            "API Key를 마스킹했습니다."
        )
    if duplicate_count:
        warnings.append(
            f"동일 company·선박명·조회 MMSI 중복 "
            f"{duplicate_count}건이 있습니다."
        )
    if ambiguous_vessels:
        warnings.append(
            f"복수 MMSI 후보를 가진 선박 "
            f"{len(ambiguous_vessels)}척은 MMSI Master로 "
            "선택해야 합니다."
        )

    summary = _summary(items)

    return {
        "source_type": "MARINESIA_SHAREPOINT",
        "source_root": str(root),
        "source_file": str(path),
        "source_file_name": path.name,
        "source_modified_at": _iso_from_timestamp(
            path.stat().st_mtime
        ),
        "generated_at": _latest_fetched_at(rows),
        "filters": {
            "companies": [],
        },
        "items": items,
        "summary": summary,
        "warnings": warnings,
        "ambiguous_vessels": ambiguous_vessels,
    }
