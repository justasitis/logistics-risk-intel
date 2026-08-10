"""대시보드 overview 경로의 날짜변경선 정규화 테스트 (SKBA 미국향 끊김 버그)."""
from __future__ import annotations

import pandas as pd

from services import dashboard_geo_service as svc
from services.geo_antimeridian import normalize_geometry_antimeridian


def test_normalize_geometry_splits_beyond_180():
    """180° 초과 연속 경도 LineString → MultiLineString 분할 + 래핑."""
    geometry = {
        "type": "LineString",
        "coordinates": [
            [129.0, 35.0],
            [170.0, 38.0],
            [185.0, 40.0],
            [241.9, 35.0],
        ],
    }
    normalized = normalize_geometry_antimeridian(geometry)
    assert normalized["type"] == "MultiLineString"
    assert len(normalized["coordinates"]) == 2
    for part in normalized["coordinates"]:
        lons = [p[0] for p in part]
        assert all(-180 <= lon <= 180 for lon in lons)
        jumps = [abs(b - a) for a, b in zip(lons, lons[1:])]
        assert all(j <= 180 for j in jumps)


def test_normalize_geometry_untouched_within_range():
    """±180° 이내 경로는 LineString 그대로."""
    geometry = {
        "type": "LineString",
        "coordinates": [[129.0, 35.0], [13.0, 45.0]],
    }
    normalized = normalize_geometry_antimeridian(geometry)
    assert normalized["type"] == "LineString"
    assert normalized["coordinates"] == geometry["coordinates"]


def test_overview_route_normalized(monkeypatch):
    """build_schedule_map_geojson의 경로도 ±180° 정규화를 거친다."""
    monkeypatch.setattr(
        svc,
        "_lookup_port",
        lambda code: (35.1, 129.0) if code == "KRPUS" else (33.7, -118.2),
    )
    monkeypatch.setattr(svc, "detect_transport_mode", lambda pol, pod: "sea")
    # searoute 스타일 [lat, lon] — 180° 초과 연속 경도
    monkeypatch.setattr(
        svc,
        "_get_sea_route",
        lambda origin, destination: [
            [35.0, 129.0],
            [38.0, 170.0],
            [40.0, 185.0],
            [35.0, 241.9],
        ],
    )
    df = pd.DataFrame(
        [
            {
                "pol": "KRPUS",
                "pod": "USLGB",
                "transport_key": "S330|PL01|T1",
                "severity": "NORMAL",
            }
        ]
    )
    result = svc.build_schedule_map_geojson(df)
    geometry = result["routes"]["features"][0]["geometry"]
    assert geometry["type"] == "MultiLineString"
    assert len(geometry["coordinates"]) == 2
    for part in geometry["coordinates"]:
        assert all(-180 <= p[0] <= 180 for p in part)
