"""
services/dashboard_geo_service.py

일정 이상탐지 결과를 Vue/MapLibre가 직접 렌더링할 수 있는
GeoJSON FeatureCollection으로 변환한다.

현재 map_builder.py의 항만 좌표 및 searoute 계산 로직을 재사용한다.
Folium HTML은 생성하지 않는다.
"""

from __future__ import annotations

from functools import lru_cache
import json
from typing import Any

import pandas as pd

from services.map_builder import (
    _get_great_circle_points,
    _get_sea_route,
    _lookup_port,
    detect_transport_mode,
)


EMPTY_FEATURE_COLLECTION = {
    "type": "FeatureCollection",
    "features": [],
}


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _safe_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass
    try:
        return int(float(value))
    except (TypeError, ValueError, OverflowError):
        return default


@lru_cache(maxsize=512)
def _build_route_coordinates(
    pol: str,
    pod: str,
    mode: str,
) -> tuple[tuple[float, float], ...]:
    """
    MapLibre용 [lon, lat] 좌표 배열을 tuple로 캐시한다.
    같은 POL/POD Lane의 searoute 중복 계산을 방지한다.
    """
    origin = _lookup_port(pol)
    destination = _lookup_port(pod)

    if not origin or not destination:
        return tuple()

    if mode == "air":
        route_lat_lon = _get_great_circle_points(origin, destination)
    else:
        route_lat_lon = _get_sea_route(origin, destination)
        if not route_lat_lon:
            route_lat_lon = [list(origin), list(destination)]

    return tuple((float(lon), float(lat)) for lat, lon in route_lat_lon)


def build_schedule_map_geojson(
    enriched_df: pd.DataFrame,
    *,
    max_routes: int = 300,
) -> dict[str, Any]:
    """
    일정 이상탐지 운송건을 지도용 GeoJSON으로 변환.

    routes:
        운송번호별 LineString
    ports:
        표시된 Lane의 출발/도착 Point
    missing_ports:
        좌표 DB에서 찾지 못한 코드 목록
    """
    if enriched_df.empty:
        return {
            "routes": dict(EMPTY_FEATURE_COLLECTION),
            "ports": dict(EMPTY_FEATURE_COLLECTION),
            "missing_ports": [],
            "route_count": 0,
        }

    severity_rank = {
        "CRITICAL": 4,
        "HIGH": 3,
        "MEDIUM": 2,
        "LOW": 1,
        "NORMAL": 0,
    }

    work = enriched_df.copy()
    work["_severity_rank"] = (
        work.get("severity", pd.Series(index=work.index, dtype=object))
        .map(severity_rank)
        .fillna(0)
    )
    work["_risk_score"] = pd.to_numeric(
        work.get("risk_score", pd.Series(index=work.index, dtype=float)),
        errors="coerce",
    ).fillna(0)

    # 위험도가 높은 운송건을 우선 표시한다.
    work = work.sort_values(
        ["_severity_rank", "_risk_score"],
        ascending=False,
    ).head(max_routes)

    route_features: list[dict[str, Any]] = []
    port_features_by_key: dict[str, dict[str, Any]] = {}
    missing_ports: set[str] = set()

    for _, row in work.iterrows():
        pol = _safe_text(row.get("pol"))
        pod = _safe_text(row.get("pod"))

        if not pol or not pod:
            continue

        origin = _lookup_port(pol)
        destination = _lookup_port(pod)

        if not origin:
            missing_ports.add(pol)
        if not destination:
            missing_ports.add(pod)
        if not origin or not destination:
            continue

        mode = detect_transport_mode(pol, pod)
        coordinates = _build_route_coordinates(pol, pod, mode)
        if len(coordinates) < 2:
            continue

        signals = row.get("anomaly_signals")
        if not isinstance(signals, list):
            signals = []

        properties = {
            "transport_key": _safe_text(row.get("transport_key")),
            "trpr_no": _safe_text(row.get("trpr_no")),
            "hbl_no": _safe_text(row.get("hbl_no")),
            "pol": pol,
            "pol_name": _safe_text(row.get("pol_name")),
            "pod": pod,
            "pod_name": _safe_text(row.get("pod_name")),
            "vessel_name": _safe_text(row.get("vessel_name")),
            "voyage_no": _safe_text(row.get("voyage_no")),
            "severity": _safe_text(row.get("severity")) or "NORMAL",
            "risk_score": _safe_int(row.get("risk_score")),
            "etd_delay_count_recent": _safe_int(
                row.get("etd_delay_count_recent")
            ),
            "eta_delay_count_recent": _safe_int(
                row.get("eta_delay_count_recent")
            ),
            "etd_net_delay_days": _safe_int(
                row.get("etd_net_delay_days")
            ),
            "eta_net_delay_days": _safe_int(
                row.get("eta_net_delay_days")
            ),
            "lead_time_variance_days": _safe_int(
                row.get("lead_time_variance_days")
            ),
            "signals": signals,
            # GeoJSON property에서 배열 처리를 단순하게 하기 위한 팝업용 문자열
            "signals_label": ", ".join(signals) if signals else "정상",
            "mode": mode,
        }

        route_features.append(
            {
                "type": "Feature",
                "id": properties["transport_key"],
                "properties": properties,
                "geometry": {
                    "type": "LineString",
                    "coordinates": [list(point) for point in coordinates],
                },
            }
        )

        for code, name, coord, role in [
            (pol, properties["pol_name"], origin, "POL"),
            (pod, properties["pod_name"], destination, "POD"),
        ]:
            key = f"{role}|{code}"
            if key not in port_features_by_key:
                port_features_by_key[key] = {
                    "type": "Feature",
                    "id": key,
                    "properties": {
                        "code": code,
                        "name": name,
                        "role": role,
                    },
                    "geometry": {
                        "type": "Point",
                        "coordinates": [float(coord[1]), float(coord[0])],
                    },
                }

    return {
        "routes": {
            "type": "FeatureCollection",
            "features": route_features,
        },
        "ports": {
            "type": "FeatureCollection",
            "features": list(port_features_by_key.values()),
        },
        "missing_ports": sorted(missing_ports),
        "route_count": len(route_features),
    }
