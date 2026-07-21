"""backend/app/core/stopby_settings.py + 유럽향 희망봉 기본 경유 회귀 테스트.

배경: `.env`에 `EUROPE_BLANK_STOPBY_DEFAULT=` 처럼 빈 값으로 설정되면
이전 구현은 빈 문자열을 "비활성화"로 해석해, 유럽향 stopby 공란 건의
희망봉 기본 경유가 아무 경고 없이 꺼졌다 (지도에 희망봉 경로 미표시).
"""
from __future__ import annotations

import pytest

from backend.app.core.stopby_settings import (
    StopbySettings,
    get_stopby_settings,
)
from backend.app.services.stopby_route_builder import (
    _effective_stopby,
    build_stopby_routes,
)


@pytest.fixture
def _settings_cache_clear():
    get_stopby_settings.cache_clear()
    yield
    get_stopby_settings.cache_clear()


def _settings_with(default: str) -> StopbySettings:
    return StopbySettings(
        europe_blank_default=default,
        route_algorithm="astar",
        route_cache_size=16,
        maximum_routes=100,
    )


class TestEuropeBlankDefaultParsing:
    def test_unset_defaults_to_south_africa(
        self, monkeypatch, _settings_cache_clear,
    ):
        monkeypatch.delenv("EUROPE_BLANK_STOPBY_DEFAULT", raising=False)
        assert get_stopby_settings().europe_blank_default == "south_africa"

    def test_empty_string_falls_back_to_south_africa(
        self, monkeypatch, _settings_cache_clear,
    ):
        # 회귀: 빈 문자열이 기본 경유를 조용히 비활성화하던 문제.
        monkeypatch.setenv("EUROPE_BLANK_STOPBY_DEFAULT", "")
        assert get_stopby_settings().europe_blank_default == "south_africa"

    def test_whitespace_falls_back_to_south_africa(
        self, monkeypatch, _settings_cache_clear,
    ):
        monkeypatch.setenv("EUROPE_BLANK_STOPBY_DEFAULT", "   ")
        assert get_stopby_settings().europe_blank_default == "south_africa"

    def test_explicit_values(
        self, monkeypatch, _settings_cache_clear,
    ):
        monkeypatch.setenv("EUROPE_BLANK_STOPBY_DEFAULT", "SUEZ")
        assert get_stopby_settings().europe_blank_default == "suez"

    def test_explicit_disable_with_none(
        self, monkeypatch, _settings_cache_clear,
    ):
        monkeypatch.setenv("EUROPE_BLANK_STOPBY_DEFAULT", "none")
        assert get_stopby_settings().europe_blank_default == ""

    def test_invalid_value_falls_back(
        self, monkeypatch, _settings_cache_clear,
    ):
        monkeypatch.setenv("EUROPE_BLANK_STOPBY_DEFAULT", "panama")
        assert get_stopby_settings().europe_blank_default == "south_africa"


class TestEffectiveStopby:
    def test_blank_europe_suez_gets_default(self):
        effective, source = _effective_stopby(
            "", True, True, _settings_with("south_africa"),
        )
        assert effective == "south_africa"
        assert source == "EUROPE_SUEZ_DEFAULT"

    def test_blank_europe_suez_disabled_stays_shortest(self):
        # 명시적 비활성화(none) 시에는 최단항로 유지가 의도된 동작이다.
        effective, source = _effective_stopby(
            "", True, True, _settings_with(""),
        )
        assert effective == ""
        assert source == "SHORTEST"

    def test_blank_europe_without_suez_stays_shortest(self):
        # step9_11 설계: 최단항로가 수에즈를 지나지 않으면 기본값 미적용.
        effective, source = _effective_stopby(
            "", True, False, _settings_with("south_africa"),
        )
        assert effective == ""
        assert source == "SHORTEST"

    def test_blank_non_europe_stays_shortest(self):
        effective, source = _effective_stopby(
            "", False, True, _settings_with("south_africa"),
        )
        assert effective == ""
        assert source == "SHORTEST"

    def test_explicit_stopby_always_wins(self):
        effective, source = _effective_stopby(
            "희망봉", False, False, _settings_with("south_africa"),
        )
        assert effective == "south_africa"
        assert source == "IF"


class TestBuildStopbyRoutesCapeRegression:
    """실제 searoute로 유럽향 공란 stopby → 희망봉 경로 생성을 검증."""

    def _payload(self):
        routes = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "transport_key": "SKBA|P1|TR1",
                        "trpr_no": "TR1",
                        "pol": "KRPUS",
                        "pod": "SIKOP",
                    },
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [
                            [129.03, 35.10],
                            [13.73, 45.55],
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
                "pod": "SIKOP",
                "stopby": "",
            }
        ]
        return routes, transports

    def test_blank_europe_generates_cape_route(self):
        routes, transports = self._payload()
        result = build_stopby_routes(
            routes, transports, settings=_settings_with("south_africa"),
        )
        feature = result["routes"]["features"][0]
        props = feature["properties"]

        assert props["stopby_effective"] == "south_africa"
        assert props["stopby_source"] == "EUROPE_SUEZ_DEFAULT"
        assert props["route_geometry_status"] == "GENERATED"
        assert props["suez_exposed"] is True

        latitudes = [
            point[1] for point in feature["geometry"]["coordinates"]
        ]
        assert len(latitudes) >= 2
        # 희망봉 우회 검증: 남위 30도 이하를 지나야 한다.
        assert min(latitudes) <= -30
        assert props["passes_cape_latitude"] is True
        assert result["summary"]["europe_default_stopby"] == 1

    def test_disabled_default_keeps_shortest(self):
        routes, transports = self._payload()
        result = build_stopby_routes(
            routes, transports, settings=_settings_with(""),
        )
        props = result["routes"]["features"][0]["properties"]
        assert props["stopby_effective"] == ""
        assert props["stopby_source"] == "SHORTEST"
        assert result["summary"]["europe_default_stopby"] == 0
