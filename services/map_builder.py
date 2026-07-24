
"""

services/map_builder.py

지도 시각화:

  - 배경: OpenStreetMap 타일 (VDI에서 타일 서버 접근 가능)

  - 해상 경로: searoute-py (실제 항로 기반 GeoJSON)

  - 항공 경로: 대원 곡선 (직선)

  - Leaflet JS/CSS 등은 folium 기본 CDN 사용 (VDI에서 CDN 접근 가능)

  - 서비스 종료된 죽은 CDN(netdna.bootstrapcdn.com)만 살아있는 미러로 치환


 

경량화: Natural Earth 배경/geopandas/오프라인 인라인 스택 제거.

"""


 

from __future__ import annotations


 

import math

from typing import Any


 

import folium

import pandas as pd


 

# searoute (오프라인 해상 경로)

try:

    import searoute as sr

    SEAROUTE_AVAILABLE = True

except ImportError:

    SEAROUTE_AVAILABLE = False


 

# ─────────────────────────────────────────────

# 죽은(서비스 종료) CDN → 살아있는 동등 리소스로 치환

# ─────────────────────────────────────────────

# 사내 VDI에서 외부 CDN 접근이 열려도 netdna.bootstrapcdn.com(구 MaxCDN)은

# 서비스가 종료되어 응답하지 않는다. folium은 leaflet.awesome-markers 의존성으로

# 이 도메인의 bootstrap-glyphicons.css를 기본 템플릿에 주입하는데, 이 앱은

# folium.Icon(glyphicon/font-awesome)을 쓰지 않고 DivIcon 이모지/CircleMarker만

# 사용하므로 실제로는 불필요하다. 다만 링크가 남아 있으면 브라우저가 죽은 도메인에

# 요청을 보내 콘솔 에러/로딩 지연이 발생하므로, 살아있는 CDN 미러로 치환한다.

_DEAD_CDN_REWRITE = {

    # folium 기본 템플릿이 주입하는 유일한 죽은 URL

    "https://netdna.bootstrapcdn.com/bootstrap/3.0.0/css/bootstrap-glyphicons.css":

        "https://cdn.jsdelivr.net/npm/bootstrap@3.4.1/dist/css/bootstrap.min.css",

    # 과거 folium 버전 대비 (혹시 다른 netdna 리소스를 참조할 경우)

    "https://netdna.bootstrapcdn.com/bootstrap/3.0.0/css/bootstrap.min.css":

        "https://cdn.jsdelivr.net/npm/bootstrap@3.4.1/dist/css/bootstrap.min.css",

    "https://netdna.bootstrapcdn.com/font-awesome/4.6.3/css/font-awesome.css":

        "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css",

}


 

def normalize_dead_cdn(html: str) -> str:

    """

    렌더링된 HTML에서 서비스 종료된 CDN URL을 살아있는 동등 URL로 치환한다.

    (folium이 주입하는 죽은 netdna URL → jsdelivr/cdnjs 미러)

    """

    for dead_url, live_url in _DEAD_CDN_REWRITE.items():

        if dead_url in html:

            html = html.replace(dead_url, live_url)

    return html


 

# ─────────────────────────────────────────────

# 주요 항만/공항 좌표

# ─────────────────────────────────────────────

PORT_COORDS: dict[str, tuple[float, float]] = {

    # ── Korea ──

    "KRPUS": (35.10, 129.03), "busan": (35.10, 129.03),

    "KRINC": (37.45, 126.60), "incheon": (37.45, 126.60),

    "KRPTK": (36.97, 126.83), "pyeongtaek": (36.97, 126.83),

    "KRKAN": (34.93, 127.70), "gwangyang": (34.93, 127.70),

    "KRICN": (37.45, 126.60),

    # Korea airports

    "ICN": (37.46, 126.44), "GMP": (37.56, 126.79),

    # ── China ──

    "CNSHA": (31.23, 121.47), "shanghai": (31.23, 121.47),

    "CNNGB": (29.87, 121.55), "ningbo": (29.87, 121.55),

    "CNTAO": (36.07, 120.38), "qingdao": (36.07, 120.38),

    "CNSZX": (22.47, 113.88), "shenzhen": (22.47, 113.88),

    "CNTSN": (39.08, 117.20), "tianjin": (39.08, 117.20),

    "CNDLC": (38.92, 121.64), "dalian": (38.92, 121.64),

    # China — 단거리 구간 추가 (2026-07)
    "CNZJG": (31.97, 120.40), "zhangjiagang": (31.97, 120.40),

    "CNLYG": (34.75, 119.43), "lianyungang": (34.75, 119.43),

    "CNDAF": (33.20, 120.46), "dafeng": (33.20, 120.46),

    "CNSHK": (31.23, 121.47),

    "CNXMN": (24.48, 118.09), "xiamen": (24.48, 118.09),

    # China airports

    "PVG": (31.14, 121.81), "PEK": (40.08, 116.58),

    "CAN": (23.39, 113.30), "SZX": (22.64, 113.81),

    "HKG": (22.31, 113.91),

    # ── Japan ──

    "JPYOK": (35.44, 139.64), "yokohama": (35.44, 139.64),

    "JPTYO": (35.65, 139.77), "tokyo": (35.65, 139.77),

    "JPOSA": (34.65, 135.43), "osaka": (34.65, 135.43),

    "JPNGO": (35.08, 136.88), "nagoya": (35.08, 136.88),

    "JPKOB": (34.69, 135.20), "kobe": (34.69, 135.20),

    # Japan airports

    "NRT": (35.76, 140.39), "KIX": (34.43, 135.23),

    "HND": (35.55, 139.78), "NGO": (34.86, 136.81),

    # ── Southeast Asia ──

    "SGSIN": (1.26, 103.84), "singapore": (1.26, 103.84),

    "SIN": (1.35, 103.99),

    "VNHPH": (20.86, 106.68), "haiphong": (20.86, 106.68),

    "VNSGN": (10.77, 106.70), "hochiminh": (10.77, 106.70),

    "VNHCM": (10.77, 106.70),

    "SGN": (10.82, 106.65), "HAN": (21.22, 105.81),

    "THLCH": (13.08, 100.89), "laemchabang": (13.08, 100.89),

    "BKK": (13.69, 100.75),

    "MYPKG": (3.00, 101.40), "klang": (3.00, 101.40),

    "KUL": (2.75, 101.71),

    "IDJKT": (-6.10, 106.88), "jakarta": (-6.10, 106.88),

    "CGK": (-6.13, 106.66),

    # ── Europe ──

    "HRRJK": (45.33, 14.44), "rijeka": (45.33, 14.44),

    "SIKOP": (45.55, 13.73), "koper": (45.55, 13.73),

    "DEHAM": (53.55, 9.99), "hamburg": (53.55, 9.99),

    "DEBRV": (53.54, 8.58), "bremerhaven": (53.54, 8.58),

    "NLRTM": (51.92, 4.48), "rotterdam": (51.92, 4.48),

    "BEANR": (51.26, 4.40), "antwerp": (51.26, 4.40),

    "ITGOA": (45.63, 13.76), "trieste": (45.63, 13.76),

    "GRPIR": (37.94, 23.64), "piraeus": (37.94, 23.64),

    # Europe airports

    "FRA": (50.03, 8.57), "AMS": (52.31, 4.77),

    "BUD": (47.44, 19.26), "VIE": (48.11, 16.57),

    # Hungary inland

    "komarom": (47.74, 18.12), "komárom": (47.74, 18.12),

    "ivancsa": (47.07, 18.82), "iváncsa": (47.07, 18.82),

    # ── USA ──

    "USSAV": (32.08, -81.09), "savannah": (32.08, -81.09),

    "USCHS": (32.78, -79.93), "charleston": (32.78, -79.93),

    "USORF": (36.85, -76.29), "norfolk": (36.85, -76.29),

    "USHOU": (29.76, -95.36), "houston": (29.76, -95.36),

    "USLAX": (33.74, -118.26), "losangeles": (33.74, -118.26),

    "USLGB": (33.75, -118.19), "longbeach": (33.75, -118.19),

    "USNYC": (40.68, -74.02), "newyork": (40.68, -74.02),

    "georgia": (33.25, -83.44),

    # USA airports

    "ATL": (33.64, -84.43), "JFK": (40.64, -73.78),

    "LAX": (33.94, -118.41), "ORD": (41.98, -87.90),

    # ── Middle East ──

    "AEJEA": (25.02, 56.34), "jebel ali": (25.02, 56.34),

    "OMSLL": (23.62, 58.57), "salalah": (23.62, 58.57),

    "DXB": (25.25, 55.36),

    # ── India ──

    "INNSA": (18.95, 72.95), "nhavasheva": (18.95, 72.95),

    "INMUN": (19.00, 72.87), "mumbai": (19.00, 72.87),

    "INCHE": (13.10, 80.29), "chennai": (13.10, 80.29),

    "BOM": (19.09, 72.87), "DEL": (28.56, 77.10),

}


 

# 공항 코드 (3자리 IATA) 집합 — 항공 판별용

AIRPORT_CODES: set[str] = {

    "ICN", "GMP", "PVG", "PEK", "CAN", "SZX", "HKG",

    "NRT", "KIX", "HND", "NGO", "SIN", "SGN", "HAN",

    "BKK", "KUL", "CGK", "FRA", "AMS", "BUD", "VIE",

    "ATL", "JFK", "LAX", "ORD", "DXB", "BOM", "DEL",

}


 

# 심각도/영향도별 색상

SEVERITY_COLORS = {

    "CRITICAL": "#dc3545",

    "HIGH":     "#fd7e14",

    "MEDIUM":   "#ffc107",

    "LOW":      "#28a745",

}


 

IMPACT_COLORS = {

    "DIRECT":     "#dc3545",

    "INDIRECT":   "#fd7e14",

    "MONITORING": "#17a2b8",

}


 

# ─────────────────────────────────────────────

# 리스크 이벤트 발생 지점 좌표

# affected_regions 키워드 → (lat, lon, 표시 반경 km)

# ─────────────────────────────────────────────

RISK_LOCATION_COORDS: dict[str, tuple[float, float, float]] = {

    # 해협/운하

    "suez": (30.46, 32.35, 150),

    "suez canal": (30.46, 32.35, 150),

    "panama": (9.08, -79.68, 120),

    "panama canal": (9.08, -79.68, 120),

    "hormuz": (26.57, 56.25, 200),

    "strait of hormuz": (26.57, 56.25, 200),

    "malacca": (2.50, 101.20, 200),

    "strait of malacca": (2.50, 101.20, 200),

    "bab el mandeb": (12.58, 43.33, 150),

    "bab-el-mandeb": (12.58, 43.33, 150),

    "taiwan strait": (24.00, 118.50, 200),

    "cape of good hope": (-34.36, 18.47, 200),

    "bering": (65.50, -169.00, 200),

    # 해역

    "red sea": (20.00, 38.50, 300),

    "south china sea": (15.00, 115.00, 400),

    "east china sea": (30.00, 125.00, 300),

    "persian gulf": (26.00, 52.00, 300),

    "gulf of aden": (12.50, 47.00, 250),

    "mediterranean": (35.50, 18.00, 400),

    "black sea": (43.50, 34.00, 300),

    "baltic sea": (58.00, 20.00, 300),

    "indian ocean": (0.00, 75.00, 500),

    # 지역

    "yemen": (15.55, 48.52, 250),

    "houthi": (15.55, 48.52, 250),

    "ukraine": (49.00, 31.00, 300),

    "russia": (60.00, 100.00, 500),

    # 항만 (PORT_COORDS와 겹치지만 리스크 이벤트 맥락용)

    "KRPUS": (35.10, 129.03, 80), "busan": (35.10, 129.03, 80),

    "CNSHA": (31.23, 121.47, 80), "shanghai": (31.23, 121.47, 80),

    "SGSIN": (1.26, 103.84, 80), "singapore": (1.26, 103.84, 80),

    "HRRJK": (45.33, 14.44, 80), "rijeka": (45.33, 14.44, 80),

    "SIKOP": (45.55, 13.73, 80), "koper": (45.55, 13.73, 80),

    "DEHAM": (53.55, 9.99, 80), "hamburg": (53.55, 9.99, 80),

    "NLRTM": (51.92, 4.48, 80), "rotterdam": (51.92, 4.48, 80),

    "USSAV": (32.08, -81.09, 80), "savannah": (32.08, -81.09, 80),

}


 

def _lookup_risk_location(region: str) -> tuple[float, float, float] | None:

    """리스크 지역명으로 좌표+반경 검색."""

    if not region:

        return None

    key = region.strip().lower()

    if key in RISK_LOCATION_COORDS:

        return RISK_LOCATION_COORDS[key]

    key_upper = region.strip().upper()

    if key_upper in RISK_LOCATION_COORDS:

        return RISK_LOCATION_COORDS[key_upper]

    # 부분 매치

    for k, v in RISK_LOCATION_COORDS.items():

        if key in k.lower() or k.lower() in key:

            return v

    return None


 

def _route_passes_near(

    route_coords: list[list[float]],

    event_lat: float,

    event_lon: float,

    radius_km: float,

) -> bool:

    """경로 좌표 중 하나라도 이벤트 지점 반경 내에 있으면 True."""

    import math

    for point in route_coords:

        lat, lon = point[0], point[1]

        # 간이 거리 계산 (도 단위, 1도 ≈ 111km)

        dlat = abs(lat - event_lat) * 111.0

        dlon = abs(lon - event_lon) * 111.0 * math.cos(math.radians(event_lat))

        dist = math.sqrt(dlat ** 2 + dlon ** 2)

        if dist <= radius_km:

            return True

    return False


 

# ─────────────────────────────────────────────

# 해상/항공 판별

# ─────────────────────────────────────────────

def detect_transport_mode(

    pol: str,

    pod: str,

    sheet_name: str = "",

    extra_columns: dict | None = None,

) -> str:

    """

    운송 모드 판별: 'sea' 또는 'air'.


 

    판별 우선순위:

      1. 시트명에 AIR/항공 키워드 → air

      2. 시트명에 OCEAN/SEA/해상/선적 키워드 → sea

      3. FLT 컬럼 존재 → air

      4. POL/POD가 IATA 공항 코드(3자리) → air

      5. POL/POD가 UN/LOCODE(5자리) → sea

      6. 기본값 → sea

    """

    # 1-2) 시트명 기반

    sn = sheet_name.upper().strip()

    air_keywords = {"AIR", "항공", "AIRFREIGHT", "AIR FREIGHT", "FLIGHT"}

    sea_keywords = {"OCEAN", "SEA", "해상", "선적", "SEAFREIGHT", "SEA FREIGHT", "VESSEL"}


 

    for kw in air_keywords:

        if kw in sn:

            return "air"

    for kw in sea_keywords:

        if kw in sn:

            return "sea"


 

    # 3) FLT 컬럼 존재

    if extra_columns and any(

        k.upper().strip() in ("FLT", "FLIGHT", "FLIGHT NO", "FLIGHT NO.")

        for k in extra_columns

    ):

        return "air"


 

    # 4-5) 코드 길이 및 공항 DB 기반

    pol_upper = pol.strip().upper()

    pod_upper = pod.strip().upper()


 

    if pol_upper in AIRPORT_CODES or pod_upper in AIRPORT_CODES:

        return "air"


 

    # 3자리 = 보통 공항, 5자리 = 보통 항만

    if len(pol_upper) == 3 and pol_upper.isalpha():

        return "air"

    if len(pod_upper) == 3 and pod_upper.isalpha():

        return "air"


 

    return "sea"


 

def _lookup_port(port_str: str) -> tuple[float, float] | None:

    """항만/공항 코드 또는 이름으로 좌표 검색."""

    if not port_str:

        return None

    key = port_str.strip().upper()

    if key in PORT_COORDS:

        return PORT_COORDS[key]

    key_lower = port_str.strip().lower()

    if key_lower in PORT_COORDS:

        return PORT_COORDS[key_lower]

    for k, v in PORT_COORDS.items():

        if key_lower in k.lower() or k.lower() in key_lower:

            return v

    return None


 

# ─────────────────────────────────────────────

# 경로 생성: 해상 (searoute) / 항공 (대원 곡선)

# ─────────────────────────────────────────────

def _get_sea_route(

    origin: tuple[float, float],

    destination: tuple[float, float],

) -> list[list[float]] | None:

    """

    searoute로 실제 해상 항로 좌표 생성.

    origin/destination: (lat, lon)

    반환: [[lat, lon], ...] folium 좌표 리스트

    """

    if not SEAROUTE_AVAILABLE:

        return None

    try:

        # searoute는 [lon, lat] 순서

        o = [origin[1], origin[0]]

        d = [destination[1], destination[0]]

        route = sr.searoute(o, d, units="km")


 

        # GeoJSON LineString → folium 좌표 ([lat, lon])

        coords = route["geometry"]["coordinates"]

        return [[c[1], c[0]] for c in coords]

    except Exception:

        return None


 

def _get_great_circle_points(

    origin: tuple[float, float],

    destination: tuple[float, float],

    num_points: int = 50,

) -> list[list[float]]:

    """

    대원(Great Circle) 경로 보간.

    항공 경로 시각화용.

    origin/destination: (lat, lon)

    """

    lat1, lon1 = math.radians(origin[0]), math.radians(origin[1])

    lat2, lon2 = math.radians(destination[0]), math.radians(destination[1])


 

    d = math.acos(

        math.sin(lat1) * math.sin(lat2)

        + math.cos(lat1) * math.cos(lat2) * math.cos(lon2 - lon1)

    )


 

    if d < 1e-10:

        return [list(origin), list(destination)]


 

    points = []

    for i in range(num_points + 1):

        f = i / num_points

        A = math.sin((1 - f) * d) / math.sin(d)

        B = math.sin(f * d) / math.sin(d)


 

        x = A * math.cos(lat1) * math.cos(lon1) + B * math.cos(lat2) * math.cos(lon2)

        y = A * math.cos(lat1) * math.sin(lon1) + B * math.cos(lat2) * math.sin(lon2)

        z = A * math.sin(lat1) + B * math.sin(lat2)


 

        lat = math.degrees(math.atan2(z, math.sqrt(x ** 2 + y ** 2)))

        lon = math.degrees(math.atan2(y, x))

        points.append([lat, lon])


 

    return points




# ─────────────────────────────────────────────

# 메인: 영향도 분류 결과 → 지도 생성

# ─────────────────────────────────────────────

def build_route_map(

    impact_df: pd.DataFrame,

    risk_events: list[dict[str, Any]],

    selected_site: str,

    sheet_name: str = "",

    extra_columns: list[str] | None = None,

    ais_data: dict | None = None,

    tiles: str = "OpenStreetMap",

) -> folium.Map | None:

    """

    영향도 분류 결과의 POL→POD 경로를 지도에 표시.

    - 배경: OpenStreetMap 타일 (VDI에서 타일 서버 접근 가능)

    - 해상: searoute (실제 항로), DIRECT는 심각도별 색상 실선

    - 항공: 대원 곡선 점선

    - INDIRECT: 주황 점선, MONITORING: 하늘 점선

    - ais_data: AISSTREAM JSON — 선박 실시간 위치 표시

    - tiles: folium 타일 이름 (기본 "OpenStreetMap")


 

    반환: 최종 지도 HTML 문자열

    """

    if impact_df.empty:

        return None


 

    m = folium.Map(

        location=[35, 105],       # 중국 중심

        zoom_start=3,

        tiles=tiles,              # OSM 타일 (VDI에서 접근 가능)

        control_scale=True,

        world_copy_jump=True,

        max_bounds=False,

    )


 

    # 이벤트 severity 매핑

    event_severity = {}

    for evt in risk_events:

        event_severity[evt.get("event_id", "")] = evt.get("severity", "MEDIUM")


 

    # extra_columns dict 변환 (항공 판별용)

    col_dict = {c: True for c in (extra_columns or [])}


 

    # ── 경로별 집계 ──

    route_data: dict[tuple[str, str], dict] = {}


 

    for _, row in impact_df.iterrows():

        pol = str(row.get("pol", "")).strip()

        pod = str(row.get("pod", "")).strip()

        impact = row.get("impact", "MONITORING")

        hbl = str(row.get("hbl_no", ""))

        matched = str(row.get("matched_events", ""))


 

        if not pol or not pod:

            continue


 

        key = (pol, pod)

        if key not in route_data:

            mode = detect_transport_mode(pol, pod, sheet_name, col_dict)

            route_data[key] = {

                "impact": impact,

                "count": 0,

                "hbl_list": [],

                "severity": "LOW",

                "mode": mode,

            }


 

        route_data[key]["count"] += 1

        route_data[key]["hbl_list"].append(hbl)


 

        # 가장 심각한 impact 유지

        imp_pri = {"DIRECT": 0, "INDIRECT": 1, "MONITORING": 2}

        if imp_pri.get(impact, 3) < imp_pri.get(route_data[key]["impact"], 3):

            route_data[key]["impact"] = impact


 

        # 가장 높은 severity 반영

        if matched:

            for eid in matched.split(","):

                sev = event_severity.get(eid.strip(), "LOW")

                sev_pri = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}

                if sev_pri.get(sev, 4) < sev_pri.get(route_data[key]["severity"], 4):

                    route_data[key]["severity"] = sev


 

    # ── 경로 그리기 ──

    drawn_ports: set[str] = set()

    sea_count = 0

    air_count = 0

    no_route_count = 0


 

    for (pol, pod), data in route_data.items():

        pol_coord = _lookup_port(pol)

        pod_coord = _lookup_port(pod)


 

        if not pol_coord or not pod_coord:

            no_route_count += 1

            continue


 

        impact = data["impact"]

        severity = data["severity"]

        count = data["count"]

        hbl_list = data["hbl_list"]

        mode = data["mode"]


 

        # 경로 좌표 생성

        if mode == "sea":

            route_coords = _get_sea_route(pol_coord, pod_coord)

            if not route_coords:

                # searoute 실패 시 직선 fallback

                route_coords = [list(pol_coord), list(pod_coord)]

            sea_count += 1

            mode_label = "🚢 해상"

        else:

            route_coords = _get_great_circle_points(pol_coord, pod_coord)

            air_count += 1

            mode_label = "✈️ 항공"


 

        # 경로 좌표 저장 (이벤트 근접 판정용)

        data["route_coords"] = route_coords


 

        # 선 스타일

        color = IMPACT_COLORS.get(impact, "#999999")

        if impact == "DIRECT":

            color = SEVERITY_COLORS.get(severity, color)

            weight = 3.5

            dash_array = None if mode == "sea" else "10 6"

            opacity = 0.9

        elif impact == "INDIRECT":

            weight = 2.5

            dash_array = "8 4"

            opacity = 0.7

        else:

            weight = 1.5

            dash_array = "4 6"

            opacity = 0.5


 

        # 항공은 항상 점선

        if mode == "air" and dash_array is None:

            dash_array = "10 6"


 

        # 팝업

        popup_html = (

            f"<div style='font-family:sans-serif;font-size:12px;min-width:220px'>"

            f"<b style='font-size:14px'>{pol} → {pod}</b><br>"

            f"<span style='color:gray'>{mode_label}</span>"

            f"<hr style='margin:4px 0'>"

            f"<b>Impact:</b> <span style='color:{color}'>{impact}</span><br>"

            f"<b>Severity:</b> {severity}<br>"

            f"<b>선적건수:</b> {count}<br>"

            f"<b>HBL:</b> {', '.join(hbl_list[:5])}"

            f"{'...' if len(hbl_list) > 5 else ''}"

            f"</div>"

        )


 

        folium.PolyLine(

            locations=route_coords,

            color=color,

            weight=weight,

            opacity=opacity,

            dash_array=dash_array,

            popup=folium.Popup(popup_html, max_width=300),

            tooltip=f"{mode_label} {pol}→{pod} ({impact})",

        ).add_to(m)


 

        # 복제 경로선 (+360) — 태평양 넘어가는 경로 표시용

        route_coords_shifted = [[lat, lon + 360] for lat, lon in route_coords]

        folium.PolyLine(

            locations=route_coords_shifted,

            color=color,

            weight=weight,

            opacity=opacity,

            dash_array=dash_array,

            popup=folium.Popup(popup_html, max_width=300),

            tooltip=f"{mode_label} {pol}→{pod} ({impact})",

        ).add_to(m)


 

        # 출발 마커

        if pol not in drawn_ports:

            icon_color = "#3388ff" if mode == "sea" else "#9b59b6"

            for lon_offset in [0, 360]:

                folium.CircleMarker(

                    location=[pol_coord[0], pol_coord[1] + lon_offset],

                    radius=6,

                    color="#333333",

                    fill=True,

                    fill_color=icon_color,

                    fill_opacity=0.8,

                    popup=f"<b>{pol}</b> (출발)",

                    tooltip=pol,

                ).add_to(m)

            drawn_ports.add(pol)


 

        # 도착 마커

        if pod not in drawn_ports:

            for lon_offset in [0, 360]:

                folium.CircleMarker(

                    location=[pod_coord[0], pod_coord[1] + lon_offset],

                    radius=6,

                    color="#333333",

                    fill=True,

                    fill_color="#ff5533",

                    fill_opacity=0.8,

                    popup=f"<b>{pod}</b> (도착)",

                    tooltip=pod,

                ).add_to(m)

            drawn_ports.add(pod)


 

    # ── 생산거점 마커 (DivIcon 이모지 — 원본 + 복제) ──

    site_coords = {

        "KOREA_SEOSAN": (36.78, 126.45, "한국 서산"),

        "HUNGARY_KOMAROM": (47.74, 18.12, "헝가리 코마롬"),

        "HUNGARY_IVANCSA": (47.07, 18.82, "헝가리 이반차"),

        "USA_GEORGIA": (33.25, -83.44, "미국 조지아"),

    }

    # GLOBAL_SCM이면 모든 거점 표시, 아니면 선택된 거점만

    sites_to_show = list(site_coords.keys()) if selected_site == "GLOBAL_SCM" else [selected_site]

    for site_key in sites_to_show:

        if site_key not in site_coords:

            continue

        lat, lon, label = site_coords[site_key]

        for lon_offset in [0, 360]:

            factory_icon = folium.DivIcon(

                html='<div style="font-size:24px; text-shadow:1px 1px 2px #333;">🏭</div>',

                icon_size=(30, 30),

                icon_anchor=(15, 15),

            )

            folium.Marker(

                location=[lat, lon + lon_offset],

                popup=f"<b>🏭 {label}</b><br>({site_key})",

                tooltip=f"🏭 {label}",

                icon=factory_icon,

            ).add_to(m)


 

    # ── 리스크 이벤트 마커 + 위험 반경 + 영향 경로 하이라이트 ──

    event_marker_count = 0

    for evt in risk_events:

        eid = evt.get("event_id", "")

        headline = evt.get("headline", "")

        severity = evt.get("severity", "MEDIUM")

        category = evt.get("risk_category", "")

        regions = evt.get("affected_regions", [])

        delay = evt.get("estimated_delay_days", None)


 

        sev_color = SEVERITY_COLORS.get(severity, "#ffc107")


 

        # 이벤트 severity별 이모지

        sev_emoji = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}.get(severity, "⚠️")


 

        for region in regions:

            loc = _lookup_risk_location(region)

            if not loc:

                continue


 

            evt_lat, evt_lon, radius_km = loc

            event_marker_count += 1


 

            # 위험 반경 원 (반투명)

            for lon_offset in [0, 360]:

                folium.Circle(

                    location=[evt_lat, evt_lon + lon_offset],

                    radius=radius_km * 1000,  # m 단위

                    color=sev_color,

                    weight=2,

                    fill=True,

                    fill_color=sev_color,

                    fill_opacity=0.12,

                    dash_array="6 4",

                ).add_to(m)


 

            # 경고 마커 (DivIcon 이모지)

            delay_text = f"<br><b>예상지연:</b> {delay}일" if delay else ""

            evt_popup = (

                f"<div style='font-family:sans-serif;font-size:12px;min-width:220px'>"

                f"<b style='font-size:14px'>{sev_emoji} {headline}</b>"

                f"<hr style='margin:4px 0'>"

                f"<b>ID:</b> {eid}<br>"

                f"<b>Category:</b> {category}<br>"

                f"<b>Severity:</b> <span style='color:{sev_color}'>{severity}</span><br>"

                f"<b>Region:</b> {region}"

                f"{delay_text}"

                f"</div>"

            )

            for lon_offset in [0, 360]:

                evt_icon = folium.DivIcon(

                    html=(

                        f'<div style="font-size:20px; text-align:center; '

                        f'text-shadow:1px 1px 2px #333; '

                        f'background:rgba(255,255,255,0.85); '

                        f'border:2px solid {sev_color}; '

                        f'border-radius:50%; width:32px; height:32px; '

                        f'line-height:30px;">⚠️</div>'

                    ),

                    icon_size=(32, 32),

                    icon_anchor=(16, 16),

                )

                folium.Marker(

                    location=[evt_lat, evt_lon + lon_offset],

                    popup=folium.Popup(evt_popup, max_width=320),

                    tooltip=f"⚠️ {headline} [{severity}]",

                    icon=evt_icon,

                ).add_to(m)


 

            # 이 이벤트 반경을 지나는 경로를 글로우 하이라이트

            for (pol, pod), rdata in route_data.items():

                rc = rdata.get("route_coords")

                if not rc:

                    continue

                if _route_passes_near(rc, evt_lat, evt_lon, radius_km):

                    # 기존 경로 위에 굵은 반투명 글로우 선 추가

                    for lon_offset in [0, 360]:

                        glow_coords = [[p[0], p[1] + lon_offset] for p in rc]

                        folium.PolyLine(

                            locations=glow_coords,

                            color=sev_color,

                            weight=10,

                            opacity=0.25,

                            dash_array=None,

                        ).add_to(m)


 

    # ── AIS 선박 위치 마커 ──

    vessel_count = 0

    if ais_data and isinstance(ais_data, dict):

        map_items = ais_data.get("map_items", [])


 

        # HBL 요약에서 vsl → (pol, pod) 매핑 구축

        vsl_to_route: dict[str, dict] = {}

        if not impact_df.empty:

            for _, row in impact_df.iterrows():

                vsl_raw = str(row.get("vsl", "")).strip()

                if vsl_raw:

                    vsl_key = vsl_raw.upper().strip()

                    if vsl_key not in vsl_to_route:

                        vsl_to_route[vsl_key] = {

                            "pol": str(row.get("pol", "")),

                            "pod": str(row.get("pod", "")),

                            "hbl_no": str(row.get("hbl_no", "")),

                            "impact": str(row.get("impact", "")),

                            "liner": str(row.get("liner", "")),

                            "voyage": str(row.get("voyage", "")),

                        }


 

        for item in map_items:

            pos_status = item.get("position_status", "")

            if pos_status not in ("LIVE", "MANUAL", "STALE"):

                continue

            lat = item.get("current_lat")

            lon = item.get("current_lon")

            if lat is None or lon is None:

                continue


 

            vessel_name = str(item.get("vessel_name", "")).strip()

            heading = item.get("heading") or 0

            speed = item.get("speed") or 0

            mmsi = item.get("mmsi_no", "")

            last_seen = item.get("last_seen_at", "")


 

            # HBL 매칭

            vsl_key = vessel_name.upper().strip()

            matched_info = vsl_to_route.get(vsl_key, {})


 

            # heading이 없거나 0이면 POL→POD 방향으로 계산

            if (heading == 0 or heading is None) and matched_info:

                pod_str = matched_info.get("pod", "")

                pod_coord = _lookup_port(pod_str)

                if pod_coord:

                    dlat = pod_coord[0] - lat

                    dlon = pod_coord[1] - lon

                    heading = math.degrees(math.atan2(dlon, dlat)) % 360


 

            # 선박 아이콘 (SVG 삼각형, heading으로 회전)

            impact_color = IMPACT_COLORS.get(matched_info.get("impact", ""), "#2196F3")

            icon_opacity = "0.5" if pos_status == "STALE" else "1.0"

            ship_svg = (

                f'<div style="transform:rotate({heading}deg); '

                f'font-size:22px; text-shadow:1px 1px 2px rgba(0,0,0,0.5); '

                f'color:{impact_color}; opacity:{icon_opacity}; line-height:1;">▲</div>'

            )

            ship_icon = folium.DivIcon(

                html=ship_svg,

                icon_size=(24, 24),

                icon_anchor=(12, 12),

            )


 

            # 팝업 정보

            source = item.get("source", "")

            status_badge = {

                "LIVE": "🟢 LIVE",

                "MANUAL": "🟡 수동입력",

                "STALE": "🔵 캐시(이전위치)",

            }.get(pos_status, pos_status)


 

            hbl_info = ""

            if matched_info:

                hbl_info = (

                    f"<hr style='margin:4px 0'>"

                    f"<b>HBL:</b> {matched_info.get('hbl_no', '-')}<br>"

                    f"<b>POL→POD:</b> {matched_info.get('pol', '?')} → {matched_info.get('pod', '?')}<br>"

                    f"<b>Impact:</b> <span style='color:{impact_color}'>{matched_info.get('impact', '-')}</span><br>"

                    f"<b>Liner:</b> {matched_info.get('liner', '-')}<br>"

                    f"<b>Voyage:</b> {matched_info.get('voyage', '-')}"

                )


 

            popup_html = (

                f"<div style='font-family:sans-serif;font-size:12px;min-width:220px'>"

                f"<b style='font-size:14px'>🚢 {vessel_name}</b>"

                f" <small>{status_badge}</small><br>"

                f"<hr style='margin:4px 0'>"

                f"<b>MMSI:</b> {mmsi}<br>"

                f"<b>위치:</b> {lat:.4f}, {lon:.4f}<br>"

                f"<b>속도:</b> {speed} kn<br>"

                f"<b>방위:</b> {heading:.0f}°<br>"

                f"<b>수신:</b> {last_seen}<br>"

                f"<b>출처:</b> {source}"

                f"{hbl_info}"

                f"</div>"

            )


 

            for lon_offset in [0, 360]:

                folium.Marker(

                    location=[lat, lon + lon_offset],

                    popup=folium.Popup(popup_html, max_width=320),

                    tooltip=f"🚢 {vessel_name} ({speed}kn, {heading:.0f}°)",

                    icon=ship_icon,

                ).add_to(m)


 

            vessel_count += 1


 

    # ── 범례 ──

    legend_html = f"""

    <div style="

        position:fixed; bottom:30px; left:30px; z-index:1000;

        background:white; padding:12px 16px; border-radius:8px;

        box-shadow:0 2px 8px rgba(0,0,0,0.3);

        font-family:sans-serif; font-size:12px; line-height:1.8;

    ">

        <b style="font-size:13px">범례</b><br>

        <span style="color:#dc3545">━━</span> DIRECT (CRITICAL)<br>

        <span style="color:#fd7e14">━━</span> DIRECT (HIGH) / INDIRECT<br>

        <span style="color:#ffc107">━━</span> DIRECT (MEDIUM)<br>

        <span style="color:#28a745">━━</span> DIRECT (LOW)<br>

        <span style="color:#17a2b8">╌╌</span> MONITORING<br>

        <hr style="margin:4px 0">

        ⚠️ 리스크 이벤트 ({event_marker_count}건)<br>

        <span style="color:#dc3545;font-size:14px">◌</span> 위험 반경 (글로우=영향 경로)<br>

        <hr style="margin:4px 0">

        <span style="color:#3388ff">●</span> 출발항 (해상)

        <span style="color:#9b59b6">●</span> 출발 (항공)<br>

        <span style="color:#ff5533">●</span> 도착항/공항

        <span style="color:green">▲</span> 생산거점<br>

        {"<b>🚢 선박 위치: " + str(vessel_count) + "척</b><br>" if vessel_count else ""}

        {"🟢LIVE 🔵STALE 🟡수동<br>" if vessel_count else ""}

        <hr style="margin:4px 0">

        <small>🚢 해상 {sea_count}건 ✈️ 항공 {air_count}건</small>

        {"<br><small>⚠️ 좌표 미매핑 " + str(no_route_count) + "건</small>" if no_route_count else ""}

    </div>

    """

    m.get_root().html.add_child(folium.Element(legend_html))


 

    folium.LayerControl(collapsed=False).add_to(m)


 

    # ── 최종 HTML 렌더링 ──

    html = m.get_root().render()

    # 죽은 CDN(netdna.bootstrapcdn.com 등)을 살아있는 CDN 미러로 치환

    # (folium이 기본 템플릿에 주입하는데, netdna는 서비스 종료되어 응답 없음)

    html = normalize_dead_cdn(html)


 

    # ── iframe 내부에서 지도 높이가 0이 되는 문제 수정 ──

    # folium은 지도 div에 width/height를 % 로 잡는데,

    # iframe 안에서 html/body 높이가 없으면 %가 0으로 계산됨.

    # 강제로 html, body, 지도 div 모두 고정 높이 부여.

    height_fix_css = """

    <style>

        html, body {

            width: 100%;

            height: 100%;

            margin: 0;

            padding: 0;

        }

        .folium-map {

            width: 100% !important;

            height: 100% !important;

            position: absolute !important;

            top: 0; left: 0;

        }

        /* 타일 로딩 전 잠깐 보이는 배경 (연한 회색) */

        .leaflet-container {

            background-color: #eaeaea !important;

        }

    </style>

    """

    # invalidateSize: Leaflet이 컨테이너 크기를 재계산하도록 강제 호출

    map_name = m.get_name()

    resize_js = f"""

    <script>

        document.addEventListener('DOMContentLoaded', function() {{

            setTimeout(function() {{

                if (typeof {map_name} !== 'undefined') {{

                    {map_name}.invalidateSize();

                }}

            }}, 200);

        }});

    </script>

    """

    html = html.replace("</head>", height_fix_css + "</head>")

    html = html.replace("</body>", resize_js + "</body>")


 

    return html


 