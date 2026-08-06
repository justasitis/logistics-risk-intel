"""날짜변경선 통과 Route geometry 정규화 회귀 테스트.

배경: SKBA(미국향) 선택 시 한국→미국 Route가 북태평양에서
날짜변경선을 통과하는데, searoute는 180°를 넘는 연속 경도
(예: 129°E → 241.9° == 118.1°W)를 반환했다. 이를 그대로
프런트에 본 날짜변경선 통과 Route는 MapLibre가 vertex별로
경도를 래핑하면서 지도 상단을 가로지르는 일자 라인으로
그려졌다.
"""
from __future__ import annotations

import pytest

from backend.app.services.stopby_route_builder import (
    _normalize_geometry_antimeridian,
    _normalize_longitude,
    build_stopby_routes,
)


class TestNormalizeLongitude:
    def test_wraps_beyond_180(self):
        assert _normalize_longitude(241.8785) == pytest.approx(
            -118.1215,
        )

    def test_keeps_in_range(self):
        assert _normalize_longitude(129.04) == pytest.approx(129.04)
        assert _normalize_longitude(-118.26) == pytest.approx(
            -118.26,
        )


class TestNormalizeGeometryAntimeridian:
    def test_linestring_split_at_antimeridian(self):
        geometry = {
            "type": "LineString",
            "coordinates": [
                [129.04, 35.10],
                [170.0, 50.0],
                [185.0, 51.0],
                [241.8785, 33.73],
            ],
        }

        normalized = _normalize_geometry_antimeridian(geometry)

        assert normalized["type"] == "MultiLineString"
        parts = normalized["coordinates"]
        assert len(parts) == 2

        for part in parts:
            for longitude, _ in part:
                assert -180 <= longitude <= 180
            for first, second in zip(part, part[1:]):
                assert abs(first[0] - second[0]) <= 180

    def test_linestring_without_crossing_unchanged(self):
        geometry = {
            "type": "LineString",
            "coordinates": [
                [129.03, 35.10],
                [13.73, 45.55],
            ],
        }

        normalized = _normalize_geometry_antimeridian(geometry)

        assert normalized["type"] == "LineString"
        assert normalized["coordinates"] == [
            [129.03, 35.10],
            [13.73, 45.55],
        ]

    def test_non_line_geometry_passthrough(self):
        geometry = {
            "type": "Point",
            "coordinates": [129.03, 35.10],
        }

        assert (
            _normalize_geometry_antimeridian(geometry)
            is geometry
        )


class TestBuildStopbyRoutesAntimeridianRegression:
    """실제 searoute로 한국→미국 Route 생성 시 날짜변경선 분할 검증."""

    def test_korea_to_us_route_splits_at_antimeridian(self):
        routes = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "transport_key": "SKBA|P1|TR1",
                        "trpr_no": "TR1",
                        "pol": "KRPUS",
                        "pod": "USLAX",
                    },
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [
                            [129.03, 35.10],
                            [-118.26, 33.73],
                        ],
                    },
                }
            ],
        }
        transports = [
            {
                "transport_key": "SKBA|P1|TR1",
                "trpr_no": "TR1",
                "pol": "KRPUS",
                "pod": "USLAX",
                "stopby": "",
            }
        ]

        result = build_stopby_routes(routes, transports)
        feature = result["routes"]["features"][0]

        assert (
            feature["properties"]["route_geometry_status"]
            == "GENERATED"
        )

        geometry = feature["geometry"]
        parts = (
            geometry["coordinates"]
            if geometry["type"] == "MultiLineString"
            else [geometry["coordinates"]]
        )

        for part in parts:
            for longitude, latitude in part:
                assert -180 <= longitude <= 180
                assert -90 <= latitude <= 90
            for first, second in zip(part, part[1:]):
                assert abs(first[0] - second[0]) <= 180
