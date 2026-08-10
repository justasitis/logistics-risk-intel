"""날짜변경선(±180°) 통과 경로 geometry 정규화 — 공용 헬퍼.

searoute 등은 날짜변경선 통과 경로를 180°를 넘는 연속 경도
(예: 129°E → 241.9° == 118.1°W)로 반환한다. MapLibre는 각 vertex의
경도를 독립적으로 ±180°로 래핑하므로, 그대로 그리면 지도를 가로지르는
일자 라인이 생기거나( SKBA 미국향 버그 ) 반대쪽 가장자리로 넘어가
경로가 중간에 끊긴 것처럼 보인다.

경도를 [-180, 180]으로 래핑하고 ±180° 점프 지점에서 MultiLineString으로
분할한다. stopby_route_builder와 dashboard_geo_service가 공용으로 사용.
"""
from __future__ import annotations

import math
from typing import Any, Iterable


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def normalize_longitude(longitude: float) -> float:
    """경도를 [-180, 180] 범위로 래핑한다."""
    if -180.0 <= longitude <= 180.0:
        return longitude
    return (longitude + 180.0) % 360.0 - 180.0


def split_antimeridian(
    points: Iterable[Any],
) -> list[list[list[float]]]:
    """래핑 후 ±180° 점프가 생기는 지점에서 Line을 분할한다."""
    parts: list[list[list[float]]] = []
    current: list[list[float]] = []
    previous_longitude: float | None = None

    for point in points:
        if not isinstance(point, (list, tuple)):
            continue
        if len(point) < 2:
            continue

        longitude = _number(point[0])
        latitude = _number(point[1])

        if (
            longitude is None
            or latitude is None
            or not -90 <= latitude <= 90
        ):
            continue

        longitude = normalize_longitude(longitude)

        if (
            previous_longitude is not None
            and abs(longitude - previous_longitude) > 180
        ):
            if len(current) >= 2:
                parts.append(current)
            current = []

        coordinate = [longitude, latitude]
        if not current or current[-1] != coordinate:
            current.append(coordinate)
        previous_longitude = longitude

    if len(current) >= 2:
        parts.append(current)

    return parts


def normalize_geometry_antimeridian(geometry: Any) -> Any:
    """날짜변경선 통과 Route geometry를 렌더링 가능하게 정규화한다.

    LineString/MultiLineString의 경도를 [-180, 180]으로 래핑하고
    ±180° 점프 지점에서 분할한다. 그 외 geometry는 그대로 반환.
    """
    if not isinstance(geometry, dict):
        return geometry

    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")

    if (
        geometry_type == "LineString"
        and isinstance(coordinates, list)
    ):
        parts = split_antimeridian(coordinates)
    elif (
        geometry_type == "MultiLineString"
        and isinstance(coordinates, list)
    ):
        parts = [
            part
            for line in coordinates
            if isinstance(line, list)
            for part in split_antimeridian(line)
        ]
    else:
        return geometry

    if not parts:
        return geometry

    normalized = dict(geometry)
    if len(parts) == 1:
        normalized["type"] = "LineString"
        normalized["coordinates"] = parts[0]
    else:
        normalized["type"] = "MultiLineString"
        normalized["coordinates"] = parts
    return normalized
