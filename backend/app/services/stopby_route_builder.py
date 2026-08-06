from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import math
import re
from typing import Any, Iterable

from ..core.stopby_settings import (
    StopbySettings,
    get_stopby_settings,
)


EUROPE_COUNTRY_CODES = {
    "AL", "AD", "AT", "BY", "BE", "BA", "BG", "HR",
    "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR",
    "HU", "IS", "IE", "IT", "LV", "LI", "LT", "LU",
    "MT", "MD", "MC", "ME", "NL", "MK", "NO", "PL",
    "PT", "RO", "SM", "RS", "SK", "SI", "ES", "SE",
    "CH", "TR", "UA", "GB", "UK", "VA",
}

STOPBY_ALIASES = {
    "희망봉": "south_africa",
    "CAPE": "south_africa",
    "CAPE OF GOOD HOPE": "south_africa",
    "GOOD HOPE": "south_africa",
    "SOUTH AFRICA": "south_africa",
    "SOUTH_AFRICA": "south_africa",
    "CGH": "south_africa",
    "수에즈": "suez",
    "수에즈운하": "suez",
    "SUEZ": "suez",
    "SUEZ CANAL": "suez",
}

STOPBY_LABELS = {
    "south_africa": "희망봉",
    "suez": "수에즈",
    "": "최단항로",
}


# GeoJSON / searoute 좌표 순서: (longitude, latitude)
# 희망봉 경유를 확실히 보장하기 위한 해상 Waypoint다.
SOUTH_AFRICA_WAYPOINTS_EAST_TO_WEST = (
    (48.0, -27.0),
    (18.0, -35.6),
    (5.0, -31.0),
)


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    return result if math.isfinite(result) else None


def _properties(feature: dict[str, Any]) -> dict[str, Any]:
    value = feature.get("properties")
    return dict(value) if isinstance(value, dict) else {}


def _passage_name(value: Any) -> str:
    if value is None:
        return ""

    enum_value = getattr(
        value,
        "value",
        value,
    )
    normalized = _text(enum_value).lower()

    if "." in normalized:
        normalized = normalized.rsplit(".", 1)[-1]

    return normalized.replace("-", "_").replace(" ", "_")


def _feature_traversed_passages(
    feature: dict[str, Any],
) -> list[str]:
    raw = _properties(feature).get(
        "traversed_passages",
        [],
    )

    if raw is None:
        return []

    if isinstance(raw, str):
        raw = [raw]
    elif not isinstance(
        raw,
        (list, tuple, set),
    ):
        raw = [raw]

    result: list[str] = []

    for value in raw:
        name = _passage_name(value)

        if name and name not in result:
            result.append(name)

    return result


def _route_uses_passage(
    feature: dict[str, Any],
    passage: str,
) -> bool:
    expected = _passage_name(passage)
    return expected in _feature_traversed_passages(feature)


def _line_coordinates(
    feature: dict[str, Any],
) -> list[list[float]]:
    geometry = feature.get("geometry")
    if not isinstance(geometry, dict):
        return []

    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")

    if geometry_type == "LineString" and isinstance(
        coordinates,
        list,
    ):
        source = coordinates
    elif geometry_type == "MultiLineString" and isinstance(
        coordinates,
        list,
    ):
        source = [
            point
            for line in coordinates
            if isinstance(line, list)
            for point in line
        ]
    else:
        return []

    result: list[list[float]] = []
    for point in source:
        if not isinstance(point, (list, tuple)):
            continue
        if len(point) < 2:
            continue

        longitude = _number(point[0])
        latitude = _number(point[1])

        if (
            longitude is None
            or latitude is None
            or not -180 <= longitude <= 180
            or not -90 <= latitude <= 90
        ):
            continue

        coordinate = [longitude, latitude]
        if not result or result[-1] != coordinate:
            result.append(coordinate)

    return result


def _normalize_longitude(longitude: float) -> float:
    """경도를 [-180, 180] 범위로 래핑한다.

    searoute는 날짜변경선 통과 Route를 180°를 넘는 연속 경도
    (예: 129°E → 241.9° == 118.1°W)로 반환한다.
    """
    if -180.0 <= longitude <= 180.0:
        return longitude

    return (longitude + 180.0) % 360.0 - 180.0


def _split_antimeridian(
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

        longitude = _normalize_longitude(longitude)

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


def _normalize_geometry_antimeridian(
    geometry: Any,
) -> Any:
    """날짜변경선 통과 Route geometry를 렌더링 가능하게 정규화한다.

    MapLibre는 각 vertex의 경도를 독립적으로 ±180°으로 래핑하므로,
    180°를 넘는 연속 경도를 그대로 본 날짜변경선 통과 Route는
    지도 상단을 가로지르는 일자 라인으로 그려진다 (SKBA 미국향 버그).
    경도를 [-180, 180]으로 래핑하고, 날짜변경선 교차 지점에서
    MultiLineString으로 분할한다.
    """
    if not isinstance(geometry, dict):
        return geometry

    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")

    if (
        geometry_type == "LineString"
        and isinstance(coordinates, list)
    ):
        parts = _split_antimeridian(coordinates)
    elif (
        geometry_type == "MultiLineString"
        and isinstance(coordinates, list)
    ):
        parts = [
            part
            for line in coordinates
            if isinstance(line, list)
            for part in _split_antimeridian(line)
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


def _unlocode_country(value: Any) -> str:
    normalized = re.sub(
        r"[^A-Z]",
        "",
        _text(value).upper(),
    )
    return normalized[:2] if len(normalized) >= 2 else ""


def _point_in_europe(point: list[float]) -> bool:
    longitude, latitude = point
    return (
        -25 <= longitude <= 45
        and 34 <= latitude <= 72
    )


def _is_europe_bound(
    properties: dict[str, Any],
    transport: dict[str, Any],
    destination: list[float],
) -> bool:
    pod = (
        transport.get("pod")
        or properties.get("pod")
        or transport.get("pod_code")
        or properties.get("pod_code")
    )
    country = _unlocode_country(pod)

    if country in EUROPE_COUNTRY_CODES:
        return True

    destination_country = _text(
        transport.get("pod_country")
        or properties.get("pod_country")
        or transport.get("destination_country")
        or properties.get("destination_country")
    ).upper()

    if destination_country[:2] in EUROPE_COUNTRY_CODES:
        return True

    return _point_in_europe(destination)


def _normalize_stopby(value: Any) -> str:
    raw = _text(value)
    if not raw:
        return ""

    normalized = re.sub(
        r"\s+",
        " ",
        raw.upper().replace("-", " ").replace("_", " "),
    ).strip()

    for alias, passage in STOPBY_ALIASES.items():
        alias_normalized = re.sub(
            r"\s+",
            " ",
            alias.upper().replace("-", " ").replace("_", " "),
        ).strip()
        if (
            normalized == alias_normalized
            or alias_normalized in normalized
        ):
            return passage

    return ""


def _effective_stopby(
    raw_stopby: Any,
    europe_bound: bool,
    baseline_uses_suez: bool,
    settings: StopbySettings,
) -> tuple[str, str]:
    """
    1. IF stopby 명시값은 항상 우선한다.
    2. stopby 공란 + 유럽향 + 최단항로가 실제 수에즈 통과:
       유럽 기본 우회정책을 적용한다.
    3. 그 외는 최단항로를 유지한다.
    """
    explicit = _normalize_stopby(raw_stopby)

    if explicit:
        return explicit, "IF"

    if (
        europe_bound
        and baseline_uses_suez
        and settings.europe_blank_default
    ):
        return (
            settings.europe_blank_default,
            "EUROPE_SUEZ_DEFAULT",
        )

    return "", "SHORTEST"



def _transport_number_from_key(
    value: Any,
) -> str:
    raw = _text(value)
    if not raw:
        return ""

    for separator in ("|", "/", ":"):
        if separator not in raw:
            continue

        parts = [
            part.strip()
            for part in raw.split(separator)
            if part.strip()
        ]

        for part in reversed(parts):
            if part.upper().startswith("TR"):
                return part

    return ""


def _append_index(
    index: dict[str, list[dict[str, Any]]],
    key: str,
    transport: dict[str, Any],
) -> None:
    normalized = _text(key)
    if not normalized:
        return

    index.setdefault(normalized, []).append(
        transport
    )


def _unique_index_value(
    index: dict[str, list[dict[str, Any]]],
    key: Any,
) -> dict[str, Any]:
    normalized = _text(key)
    if not normalized:
        return {}

    candidates = index.get(normalized, [])
    return (
        candidates[0]
        if len(candidates) == 1
        else {}
    )


def _transport_indices(
    transports: list[dict[str, Any]],
) -> dict[str, Any]:
    by_key: dict[str, dict[str, Any]] = {}
    by_trpr: dict[
        str,
        list[dict[str, Any]],
    ] = {}
    by_hbl: dict[
        str,
        list[dict[str, Any]],
    ] = {}

    for transport in transports:
        if not isinstance(transport, dict):
            continue

        transport_key = _text(
            transport.get("transport_key")
        )
        trpr_no = _text(
            transport.get("trpr_no")
        )
        hbl_no = _text(
            transport.get("hbl_no")
        )

        if transport_key:
            by_key[transport_key] = transport

        _append_index(
            by_trpr,
            trpr_no,
            transport,
        )
        _append_index(
            by_hbl,
            hbl_no,
            transport,
        )

    return {
        "by_key": by_key,
        "by_trpr": by_trpr,
        "by_hbl": by_hbl,
    }


def _feature_mapping(
    feature: dict[str, Any],
    indices: dict[str, Any],
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    str,
]:
    properties = _properties(feature)

    by_key = indices["by_key"]
    by_trpr = indices["by_trpr"]
    by_hbl = indices["by_hbl"]

    transport_key = _text(
        properties.get("transport_key")
    )

    transport = by_key.get(
        transport_key,
        {},
    )
    if transport:
        return (
            properties,
            transport,
            "TRANSPORT_KEY",
        )

    trpr_no = _text(
        properties.get("trpr_no")
        or properties.get("system_trpr_no")
    )

    transport = _unique_index_value(
        by_trpr,
        trpr_no,
    )
    if transport:
        return (
            properties,
            transport,
            "TRPR_NO",
        )

    hbl_no = _text(
        properties.get("hbl_no")
        or properties.get("display_id")
    )

    transport = _unique_index_value(
        by_hbl,
        hbl_no,
    )
    if transport:
        return (
            properties,
            transport,
            "HBL_NO",
        )

    # SKBM처럼 법인/Plant Prefix가 달라도
    # transport_key 마지막의 TR No.는 동일할 수 있다.
    key_trpr_no = _transport_number_from_key(
        transport_key
    )

    transport = _unique_index_value(
        by_trpr,
        key_trpr_no,
    )
    if transport:
        return (
            properties,
            transport,
            "TRANSPORT_KEY_TRPR_SUFFIX",
        )

    return properties, {}, "UNMATCHED"


@lru_cache(maxsize=512)
def _passage_midpoint(
    passage: str,
) -> tuple[float, float] | None:
    import searoute as sr

    network = sr.setup_M()
    passage_edges = [
        (u, v)
        for u, v, attributes in network.edges(data=True)
        if attributes.get("passage") == passage
    ]

    if not passage_edges:
        return None

    _, node = passage_edges[len(passage_edges) // 2]

    if (
        not isinstance(node, (tuple, list))
        or len(node) < 2
    ):
        return None

    longitude = _number(node[0])
    latitude = _number(node[1])

    if longitude is None or latitude is None:
        return None

    return longitude, latitude


def _feature_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)

    if hasattr(value, "__geo_interface__"):
        interface = value.__geo_interface__
        if isinstance(interface, dict):
            return deepcopy(interface)

    try:
        converted = dict(value)
    except (TypeError, ValueError):
        return {}

    return deepcopy(converted)


def _route_segment(
    origin: tuple[float, float],
    destination: tuple[float, float],
    algorithm: str | None = None,
) -> dict[str, Any]:
    """
    searoute 1.4.3 호환 구간 Route 생성.

    algorithm은 기존 상위 호출 구조와 설정 호환을 위해
    인자로 받지만, searoute 1.4.3에는 전달하지 않는다.
    """
    import searoute as sr

    value = sr.searoute(
        list(origin),
        list(destination),
        append_orig_dest=True,
        return_passages=True,
    )

    if isinstance(value, list):
        value = value[0] if value else {}

    feature = _feature_dict(value)

    if not feature:
        raise RuntimeError(
            "searoute가 빈 Route를 반환했습니다."
        )

    if len(_line_coordinates(feature)) < 2:
        raise RuntimeError(
            "searoute Route 좌표가 2개 미만입니다."
        )

    return feature


def _segment_coordinates(
    feature: dict[str, Any],
) -> list[list[float]]:
    return _line_coordinates(feature)


def _merge_passages(
    values: Iterable[Any],
) -> list[str]:
    result: list[str] = []

    for value in values:
        if not isinstance(value, list):
            continue
        for passage in value:
            name = _text(passage)
            if name and name not in result:
                result.append(name)

    return result



def _generate_via_waypoints(
    origin: tuple[float, float],
    destination: tuple[float, float],
    waypoints: Iterable[
        tuple[float, float]
    ],
    passage: str,
    algorithm: str,
) -> dict[str, Any]:
    sequence = [
        origin,
        *list(waypoints),
        destination,
    ]

    segments = [
        _route_segment(
            segment_origin,
            segment_destination,
            algorithm,
        )
        for (
            segment_origin,
            segment_destination,
        ) in zip(sequence, sequence[1:])
    ]

    coordinates: list[list[float]] = []
    lengths: list[float] = []
    durations: list[float] = []
    passages: list[Any] = []

    for segment in segments:
        segment_coordinates = (
            _segment_coordinates(segment)
        )

        if (
            coordinates
            and segment_coordinates
            and coordinates[-1]
            == segment_coordinates[0]
        ):
            segment_coordinates = (
                segment_coordinates[1:]
            )

        coordinates.extend(
            segment_coordinates
        )

        segment_properties = _properties(
            segment
        )
        length = _number(
            segment_properties.get("length")
        )
        duration = _number(
            segment_properties.get(
                "duration_hours"
            )
        )

        if length is not None:
            lengths.append(length)
        if duration is not None:
            durations.append(duration)

        passages.append(
            segment_properties.get(
                "traversed_passages"
            )
        )

    traversed = _merge_passages(passages)

    if passage not in traversed:
        traversed.append(passage)

    return {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": coordinates,
        },
        "properties": {
            "length": round(
                sum(lengths),
                3,
            ),
            "units": "km",
            "duration_hours": (
                round(sum(durations), 3)
                if durations
                else None
            ),
            "traversed_passages": traversed,
            "mandatory_passage": passage,
            "segment_count": len(segments),
            "waypoint_count": (
                len(sequence) - 2
            ),
        },
    }


def _south_africa_waypoints(
    origin: tuple[float, float],
    destination: tuple[float, float],
) -> tuple[tuple[float, float], ...]:
    # 동쪽(아시아) → 서쪽(유럽/대서양)이면
    # 인도양 → 희망봉 남쪽 → 남대서양 순서.
    if origin[0] >= destination[0]:
        return (
            SOUTH_AFRICA_WAYPOINTS_EAST_TO_WEST
        )

    return tuple(
        reversed(
            SOUTH_AFRICA_WAYPOINTS_EAST_TO_WEST
        )
    )


def _generate_via_passage(
    origin: tuple[float, float],
    destination: tuple[float, float],
    passage: str,
    algorithm: str,
) -> dict[str, Any]:
    if passage == "south_africa":
        return _generate_via_waypoints(
            origin,
            destination,
            _south_africa_waypoints(
                origin,
                destination,
            ),
            passage,
            algorithm,
        )

    midpoint = _passage_midpoint(passage)
    if midpoint is None:
        raise RuntimeError(
            f"Searoute graph에서 {passage} passage를 "
            "찾지 못했습니다."
        )

    segments = [
        _route_segment(origin, midpoint, algorithm),
        _route_segment(midpoint, destination, algorithm),
    ]

    coordinates: list[list[float]] = []
    lengths: list[float] = []
    durations: list[float] = []
    passages: list[Any] = []

    for segment in segments:
        segment_coordinates = _segment_coordinates(segment)

        if (
            coordinates
            and segment_coordinates
            and coordinates[-1] == segment_coordinates[0]
        ):
            segment_coordinates = segment_coordinates[1:]

        coordinates.extend(segment_coordinates)

        segment_properties = _properties(segment)
        length = _number(segment_properties.get("length"))
        duration = _number(
            segment_properties.get("duration_hours")
        )

        if length is not None:
            lengths.append(length)
        if duration is not None:
            durations.append(duration)

        passages.append(
            segment_properties.get("traversed_passages")
        )

    traversed = _merge_passages(passages)

    if passage not in traversed:
        traversed.append(passage)

    return {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": coordinates,
        },
        "properties": {
            "length": round(sum(lengths), 3),
            "units": "km",
            "duration_hours": round(
                sum(durations),
                3,
            ) if durations else None,
            "traversed_passages": traversed,
            "mandatory_passage": passage,
            "segment_count": len(segments),
        },
    }


@lru_cache(maxsize=512)
def _cached_route(
    origin_lon: float,
    origin_lat: float,
    destination_lon: float,
    destination_lat: float,
    passage: str,
    algorithm: str,
) -> dict[str, Any]:
    origin = (origin_lon, origin_lat)
    destination = (
        destination_lon,
        destination_lat,
    )

    if passage:
        return _generate_via_passage(
            origin,
            destination,
            passage,
            algorithm,
        )

    return _route_segment(
        origin,
        destination,
        algorithm,
    )




def _display_id(
    properties: dict[str, Any],
    transport: dict[str, Any],
) -> tuple[str, str]:
    hbl_no = _text(
        transport.get("hbl_no")
        or properties.get("hbl_no")
    )
    trpr_no = _text(
        transport.get("trpr_no")
        or properties.get("trpr_no")
    )
    transport_key = _text(
        transport.get("transport_key")
        or properties.get("transport_key")
    )

    if hbl_no:
        return hbl_no, "HBL"
    if trpr_no:
        return trpr_no, "TR"
    return transport_key, "TRANSPORT_KEY"


def build_stopby_routes(
    routes: dict[str, Any],
    transports: list[dict[str, Any]],
    settings: StopbySettings | None = None,
) -> dict[str, Any]:
    resolved = settings or get_stopby_settings()
    features = routes.get("features")

    if not isinstance(features, list):
        raise ValueError(
            "routes.features 배열이 필요합니다."
        )

    if len(features) > resolved.maximum_routes:
        raise ValueError(
            f"Route 수가 최대 {resolved.maximum_routes}건을 "
            "초과했습니다."
        )

    transport_indices = _transport_indices(transports)
    output_features: list[dict[str, Any]] = []
    warnings: list[str] = []

    generated_count = 0
    preserved_count = 0
    europe_default_count = 0
    explicit_count = 0
    error_count = 0

    for index, source_feature in enumerate(features):
        if not isinstance(source_feature, dict):
            continue

        original = deepcopy(source_feature)
        (
            properties,
            transport,
            transport_match_method,
        ) = _feature_mapping(
            source_feature,
            transport_indices,
        )
        coordinates = _line_coordinates(source_feature)

        display_id, display_type = _display_id(
            properties,
            transport,
        )
        hbl_no = _text(
            transport.get("hbl_no")
            or properties.get("hbl_no")
        )
        trpr_no = _text(
            transport.get("trpr_no")
            or properties.get("trpr_no")
        )
        transport_key = _text(
            transport.get("transport_key")
            or properties.get("transport_key")
        )
        stopby_raw = _text(
            transport.get("stopby")
            or properties.get("stopby")
        )

        enriched_properties = {
            **properties,
            "transport_key": transport_key,
            "trpr_no": trpr_no,
            "system_trpr_no": trpr_no,
            "hbl_no": hbl_no,
            "display_id": display_id,
            "display_id_type": display_type,
            "stopby_raw": stopby_raw,
            "transport_match_method": (
                transport_match_method
            ),
        }

        if len(coordinates) < 2:
            enriched_properties.update({
                "stopby_effective": "",
                "stopby_label": "좌표 없음",
                "stopby_source": "NONE",
                "route_geometry_status": (
                    "PRESERVED_NO_COORDINATES"
                ),
            })
            original["properties"] = enriched_properties
            output_features.append(original)
            preserved_count += 1
            continue

        origin = coordinates[0]
        destination = coordinates[-1]
        europe_bound = _is_europe_bound(
            properties,
            transport,
            destination,
        )

        mode = _text(
            transport.get("transport_mode")
            or transport.get("mode")
            or properties.get("transport_mode")
            or properties.get("mode")
        ).upper()

        explicit = _normalize_stopby(stopby_raw)
        effective = explicit
        source = "IF" if explicit else "SHORTEST"
        baseline_passages: list[str] = []
        baseline_uses_suez = False

        if mode in {"AIR", "FLT", "항공"}:
            if explicit:
                explicit_count += 1

            enriched_properties.update({
                "stopby_effective": explicit,
                "stopby_label": STOPBY_LABELS.get(
                    explicit,
                    explicit or "최단항로",
                ),
                "stopby_source": source,
                "europe_bound": europe_bound,
                "baseline_traversed_passages": [],
                "suez_exposed": False,
                "route_geometry_status": (
                    "PRESERVED_NON_SEA"
                ),
            })
            original["properties"] = enriched_properties
            output_features.append(original)
            preserved_count += 1
            continue

        try:
            if explicit:
                explicit_count += 1
                generated = _cached_route(
                    round(origin[0], 6),
                    round(origin[1], 6),
                    round(destination[0], 6),
                    round(destination[1], 6),
                    explicit,
                    resolved.route_algorithm,
                )
            else:
                baseline = _cached_route(
                    round(origin[0], 6),
                    round(origin[1], 6),
                    round(destination[0], 6),
                    round(destination[1], 6),
                    "",
                    resolved.route_algorithm,
                )
                baseline_passages = (
                    _feature_traversed_passages(
                        baseline
                    )
                )
                baseline_uses_suez = (
                    _route_uses_passage(
                        baseline,
                        "suez",
                    )
                )

                effective, source = _effective_stopby(
                    stopby_raw,
                    europe_bound,
                    baseline_uses_suez,
                    resolved,
                )

                if source == "EUROPE_SUEZ_DEFAULT":
                    europe_default_count += 1
                    generated = _cached_route(
                        round(origin[0], 6),
                        round(origin[1], 6),
                        round(destination[0], 6),
                        round(destination[1], 6),
                        effective,
                        resolved.route_algorithm,
                    )
                else:
                    generated = baseline

            geometry = generated.get("geometry")
            generated_properties = _properties(generated)

            if (
                not isinstance(geometry, dict)
                or len(_line_coordinates(generated)) < 2
            ):
                raise RuntimeError(
                    "Searoute 결과 좌표가 비어 있습니다."
                )

            generated_coordinates = (
                _line_coordinates(generated)
            )
            generated_latitudes = [
                point[1]
                for point in generated_coordinates
            ]
            route_min_latitude = (
                min(generated_latitudes)
                if generated_latitudes
                else None
            )

            if (
                effective == "south_africa"
                and (
                    route_min_latitude is None
                    or route_min_latitude > -30
                )
            ):
                raise RuntimeError(
                    "희망봉 Route가 남위 30도 이하를 "
                    "통과하지 않습니다."
                )

            traversed = generated_properties.get(
                "traversed_passages",
                [],
            )
            if not isinstance(traversed, list):
                traversed = []

            enriched_properties.update({
                "stopby_effective": effective,
                "stopby_label": STOPBY_LABELS.get(
                    effective,
                    effective or "최단항로",
                ),
                "stopby_source": source,
                "europe_bound": europe_bound,
                "baseline_traversed_passages": (
                    baseline_passages
                ),
                "suez_exposed": baseline_uses_suez,
                "mandatory_passage": (
                    effective or None
                ),
                "traversed_passages": traversed,
                "route_length_km": _number(
                    generated_properties.get("length")
                ),
                "route_duration_hours": _number(
                    generated_properties.get(
                        "duration_hours"
                    )
                ),
                "route_segment_count": (
                    generated_properties.get(
                        "segment_count",
                        1,
                    )
                ),
                "route_geometry_status": "GENERATED",
                "route_mode": (
                    effective or "shortest"
                ),
                "route_min_latitude": (
                    route_min_latitude
                ),
                "passes_cape_latitude": (
                    route_min_latitude is not None
                    and route_min_latitude <= -30
                ),
            })

            output_features.append({
                **original,
                "geometry": (
                    _normalize_geometry_antimeridian(
                        geometry,
                    )
                ),
                "properties": enriched_properties,
            })
            generated_count += 1
        except Exception as exc:
            error_count += 1
            enriched_properties.update({
                "stopby_effective": effective,
                "stopby_label": STOPBY_LABELS.get(
                    effective,
                    effective or "최단항로",
                ),
                "stopby_source": source,
                "europe_bound": europe_bound,
                "baseline_traversed_passages": (
                    baseline_passages
                ),
                "suez_exposed": baseline_uses_suez,
                "route_geometry_status": (
                    "FALLBACK_ORIGINAL"
                ),
                "route_geometry_error": (
                    f"{type(exc).__name__}: {exc}"
                ),
            })
            original["properties"] = enriched_properties
            output_features.append(original)
            warnings.append(
                f"{display_id or index + 1}: "
                f"경유항로 생성 실패, 기존 Route 유지 — {exc}"
            )

    return {
        "routes": {
            "type": "FeatureCollection",
            "features": output_features,
        },
        "summary": {
            "total": len(output_features),
            "generated": generated_count,
            "preserved": preserved_count,
            "errors": error_count,
            "explicit_stopby": explicit_count,
            "europe_default_stopby": (
                europe_default_count
            ),
            "europe_suez_default_stopby": (
                europe_default_count
            ),
            "default_europe_passage": (
                resolved.europe_blank_default
            ),
            "cache": {
                "hits": _cached_route.cache_info().hits,
                "misses": _cached_route.cache_info().misses,
                "current_size": (
                    _cached_route.cache_info().currsize
                ),
            },
        },
        "warnings": warnings,
    }
