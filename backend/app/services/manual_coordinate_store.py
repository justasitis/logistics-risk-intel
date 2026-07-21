from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
import re
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4


_LOCK = RLock()


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _store_path() -> Path:
    configured = os.getenv(
        "MANUAL_COORDINATE_FILE",
        "",
    ).strip()

    if configured:
        # {username} 은 현재 로그인 사용자명으로 치환 (SharePoint 동기화 경로 대응)
        from backend.app.core.user_path import expand_username

        return Path(expand_username(configured)).expanduser().resolve()

    return (
        _project_root()
        / "data"
        / "manual_coordinates.json"
    )


def _now_iso() -> str:
    return datetime.now(
        timezone.utc,
    ).isoformat()


def normalize_location_code(
    value: Any,
) -> str:
    return re.sub(
        r"[^A-Z0-9]",
        "",
        str(value or "").strip().upper(),
    )


def normalize_company(
    value: Any,
) -> str:
    return (
        str(value or "")
        .strip()
        .upper()
    )


def _empty_document() -> dict[str, Any]:
    return {
        "version": 2,
        "scope": "GLOBAL",
        "updated_at": _now_iso(),
        "items": [],
    }


def _atomic_write(
    path: Path,
    document: dict[str, Any],
) -> None:
    temporary = path.with_name(
        f"{path.name}.{uuid4().hex}.tmp"
    )
    temporary.write_text(
        json.dumps(
            document,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    temporary.replace(path)


def _ensure_store() -> Path:
    path = _store_path()
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not path.exists():
        _atomic_write(
            path,
            _empty_document(),
        )

    return path


def _read_document() -> dict[str, Any]:
    path = _ensure_store()

    try:
        value = json.loads(
            path.read_text(
                encoding="utf-8",
            )
        )
    except (
        json.JSONDecodeError,
        OSError,
    ) as exc:
        raise RuntimeError(
            "수동 좌표 저장 파일을 읽지 못했습니다: "
            f"{path}"
        ) from exc

    if not isinstance(value, dict):
        return _empty_document()

    if not isinstance(
        value.get("items"),
        list,
    ):
        value["items"] = []

    return value


def _validate_coordinate(
    latitude: float,
    longitude: float,
) -> None:
    if not -90 <= latitude <= 90:
        raise ValueError(
            "위도는 -90~90 범위여야 합니다."
        )

    if not -180 <= longitude <= 180:
        raise ValueError(
            "경도는 -180~180 범위여야 합니다."
        )


def _entry_identity(
    item: dict[str, Any],
) -> tuple[str, str]:
    return (
        normalize_company(
            item.get("company"),
        ),
        normalize_location_code(
            item.get("location_code"),
        ),
    )


def list_manual_coordinates(
    company: str | None = None,
) -> list[dict[str, Any]]:
    # 좌표는 법인과 관계없는 공통 데이터다.
    del company

    with _LOCK:
        document = _read_document()
        raw_items = [
            deepcopy(item)
            for item in document["items"]
            if isinstance(item, dict)
        ]

    latest_by_code: dict[str, dict[str, Any]] = {}

    for item in raw_items:
        code = normalize_location_code(
            item.get("location_code"),
        )

        if not code:
            continue

        item["location_code"] = code
        item["company"] = ""
        item["scope"] = "GLOBAL"

        previous = latest_by_code.get(code)
        previous_time = str(
            (previous or {}).get("updated_at")
            or (previous or {}).get("created_at")
            or ""
        )
        item_time = str(
            item.get("updated_at")
            or item.get("created_at")
            or ""
        )

        if previous is None or item_time >= previous_time:
            latest_by_code[code] = item

    return sorted(
        latest_by_code.values(),
        key=lambda item: item["location_code"],
    )


def get_manual_coordinate(
    location_code: str,
    company: str | None = None,
) -> dict[str, Any] | None:
    del company

    code = normalize_location_code(
        location_code,
    )

    if not code:
        return None

    for item in list_manual_coordinates():
        if (
            normalize_location_code(
                item.get("location_code"),
            )
            == code
        ):
            return item

    return None


def upsert_manual_coordinate(
    *,
    location_code: str,
    latitude: float,
    longitude: float,
    location_name: str = "",
    country_code: str = "",
    company: str = "",
    note: str = "",
    updated_by: str = "",
) -> dict[str, Any]:
    del company

    code = normalize_location_code(
        location_code,
    )
    latitude = float(latitude)
    longitude = float(longitude)

    if not code:
        raise ValueError(
            "Location Code는 필수입니다."
        )

    _validate_coordinate(
        latitude,
        longitude,
    )

    now = _now_iso()

    with _LOCK:
        path = _ensure_store()
        document = _read_document()
        original_items = [
            item
            for item in document["items"]
            if isinstance(item, dict)
        ]

        previous_candidates = [
            item
            for item in original_items
            if normalize_location_code(
                item.get("location_code"),
            ) == code
        ]
        previous = max(
            previous_candidates,
            key=lambda item: str(
                item.get("updated_at")
                or item.get("created_at")
                or ""
            ),
            default={},
        )

        entry = {
            "location_code": code,
            "location_name": (
                str(location_name or "")
                .strip()
            ),
            "country_code": (
                str(country_code or "")
                .strip()
                .upper()
            ),
            "company": "",
            "scope": "GLOBAL",
            "latitude": latitude,
            "longitude": longitude,
            "note": str(note or "").strip(),
            "source": "MANUAL",
            "created_at": (
                previous.get("created_at")
                or now
            ),
            "updated_at": now,
            "updated_by": (
                str(updated_by or "")
                .strip()
            ),
        }

        items = [
            item
            for item in original_items
            if normalize_location_code(
                item.get("location_code"),
            ) != code
        ]
        items.append(entry)

        document["version"] = 2
        document["scope"] = "GLOBAL"
        document["items"] = sorted(
            items,
            key=lambda item: normalize_location_code(
                item.get("location_code"),
            ),
        )
        document["updated_at"] = now
        _atomic_write(
            path,
            document,
        )

    return deepcopy(entry)


def delete_manual_coordinate(
    location_code: str,
    company: str | None = None,
) -> bool:
    del company

    code = normalize_location_code(
        location_code,
    )

    with _LOCK:
        path = _ensure_store()
        document = _read_document()
        original_items = [
            item
            for item in document["items"]
            if isinstance(item, dict)
        ]

        filtered = [
            item
            for item in original_items
            if normalize_location_code(
                item.get("location_code"),
            ) != code
        ]

        deleted = (
            len(filtered)
            != len(original_items)
        )

        if deleted:
            document["version"] = 2
            document["scope"] = "GLOBAL"
            document["items"] = filtered
            document["updated_at"] = _now_iso()
            _atomic_write(
                path,
                document,
            )

    return deleted


def resolve_manual_coordinate(
    location_code: str,
    company: str | None = None,
) -> tuple[float, float] | None:
    entry = get_manual_coordinate(
        location_code,
        company,
    )

    if not entry:
        return None

    return (
        float(entry["longitude"]),
        float(entry["latitude"]),
    )


def manual_coordinate_health() -> dict[str, Any]:
    path = _ensure_store()
    items = list_manual_coordinates()

    return {
        "status": "ok",
        "scope": "GLOBAL",
        "store_path": str(path),
        "item_count": len(items),
    }
