"""승인 MI 이벤트(최신 reviewed run의 canonical_payload)의 지도 영향권.

레지스트리(미승인 후보 추적)와 달리, 정제 탭에서 Actify 정제·사용자 승인까지
마친 이벤트만 대상으로 한다. 승인 이벤트의 affected_locations에는 좌표가 이미
포함되어 있어 별도 resolve가 필요 없다. 로컬 run 저장소만 읽고 외부 호출은 없다.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from .mi_map_labels import load_map_labels
from .mi_repository import MiRunRepository

RUN_SCAN_LIMIT = 50


def _canonical_events(run: dict[str, Any]) -> list[dict[str, Any]] | None:
    """run payload에서 canonical(승인) 이벤트 목록. reviewed run이 아니면 None."""
    canonical = run.get("canonical_payload")
    if isinstance(canonical, dict) and isinstance(canonical.get("events"), list):
        return canonical["events"]
    return None


def _is_expired(event: dict[str, Any], today: date) -> bool:
    """valid_to가 오늘보다 과거면 만료. 파싱 불가 값은 만료로 보지 않는다."""
    valid_to = str(event.get("valid_to") or "")[:10]
    if not valid_to:
        return False
    try:
        return date.fromisoformat(valid_to) < today
    except ValueError:
        return False


def approved_map_zones() -> list[dict[str, Any]]:
    """최신 승인본(canonical) 이벤트의 지도 영향권.

    run 저장소에서 canonical_payload를 가진 첫 run(mtime 최신 순)이 최신 승인본.
    affected_locations가 비어있거나 valid_to가 지난 이벤트는 제외.
    run이 없거나 대상 이벤트가 없으면 빈 배열.
    """
    events: list[dict[str, Any]] | None = None
    for run in MiRunRepository().list_recent(RUN_SCAN_LIMIT):
        events = _canonical_events(run)
        if events is not None:
            break
    if not events:
        return []

    labels = load_map_labels()
    today = date.today()

    zones: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        locations = [
            loc
            for loc in event.get("affected_locations") or []
            if isinstance(loc, dict)
            and loc.get("lat") is not None
            and loc.get("lon") is not None
        ]
        if not locations:
            continue
        if _is_expired(event, today):
            continue
        event_id = str(event.get("event_id") or "")
        zones.append(
            {
                "event_id": event_id,
                "headline": str(event.get("headline") or ""),
                "severity": str(event.get("severity") or ""),
                "status": str(event.get("status") or ""),
                "valid_from": str(event.get("valid_from") or "")[:10],
                "valid_to": str(event.get("valid_to") or "")[:10] or None,
                # 지도 라벨(Actify 생성 간결 문구) — 없으면 프런트가 headline 폭 사용
                "short_label": labels.get(event_id, ""),
                "locations": [
                    {
                        "code": str(loc.get("code") or ""),
                        "name": str(loc.get("name") or ""),
                        "lat": float(loc["lat"]),
                        "lon": float(loc["lon"]),
                        "radius_km": float(loc.get("radius_km") or 0),
                    }
                    for loc in locations
                ],
            }
        )
    return zones
