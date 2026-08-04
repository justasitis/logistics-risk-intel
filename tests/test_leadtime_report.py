"""항로별 리드타임 리포트 집계 테스트 (가짜 DataFrame, 외부 호출 없음)."""
from datetime import date

import httpx
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api_server import app
from services import leadtime_report_service as svc

# TestClient는 앱 낸부(ASGI) 호출 — conftest의 httpx 차단 복원
_REAL_HTTPX_REQUEST = httpx.Client.request


@pytest.fixture(autouse=True)
def _allow_testclient_http(monkeypatch):
    monkeypatch.setattr(httpx.Client, "request", _REAL_HTTPX_REQUEST)


TODAY = date(2026, 7, 19)

GROUPS = [
    {
        "group_id": "ADRIA_SUEZ",
        "name": "아드리아해 / 수에즈",
        "arvl_codes": ["SIKOP"],
        "stopby_match": ["SUEZ"],
        "stopby_exclude": [],
    },
    {
        "group_id": "ADRIA_CAPE",
        "name": "아드리아해 / 희망봉",
        "arvl_codes": ["SIKOP"],
        "stopby_match": ["CAPE"],
        "stopby_exclude": [],
    },
]


def _row(**kw):
    base = {
        "dprt": "KRPUS", "arvl": "SIKOP", "stopby": "SUEZ", "stopby_nm": "",
        "cargo_type3": "FCL",
        "onboard_date": None, "atd": None, "ata": None,
        "eta": None, "eta_date": None, "etd": None,
    }
    base.update(kw)
    return base


def _report(df, **kw):
    return svc.compute_leadtime_report(df, today=TODAY, groups=GROUPS, **kw)


def _cell(report, group_id, country, stat, month):
    group = next(g for g in report["groups"] if g["group_id"] == group_id)
    row = next(
        r for r in group["rows"] if r["country"] == country and r["stat"] == stat
    )
    return row["cells"].get(month)


def test_actual_month_grouping_onboard_priority():
    df = pd.DataFrame([
        # onboard 5월 → 5월 열 (atd가 4월이어도 onboard 우선)
        _row(onboard_date="2026-05-10", atd="2026-04-28", ata="2026-06-09"),
    ])
    report = _report(df)
    assert _cell(report, "ADRIA_SUEZ", "KR", "Avg", "2026-05") == 30.0
    assert _cell(report, "ADRIA_SUEZ", "KR", "Avg", "2026-04") is None


def test_actual_fallback_to_atd_and_avg_min_max():
    df = pd.DataFrame([
        _row(atd="2026-05-01", ata="2026-05-31"),   # 30일 (onboard 없음 → atd)
        _row(onboard_date="2026-05-05", ata="2026-06-14"),  # 40일
        _row(onboard_date="2026-05-20", ata="2026-06-09"),  # 20일
    ])
    report = _report(df)
    assert _cell(report, "ADRIA_SUEZ", "KR", "Avg", "2026-05") == 30.0
    assert _cell(report, "ADRIA_SUEZ", "KR", "Min", "2026-05") == 20.0
    assert _cell(report, "ADRIA_SUEZ", "KR", "Max", "2026-05") == 40.0


def test_country_mapping_and_stopby_split():
    df = pd.DataFrame([
        _row(dprt="CNSHA", stopby="SUEZ", onboard_date="2026-05-01", ata="2026-06-01"),  # CN 수에즈
        _row(dprt="JPYOK", stopby="CAPE", onboard_date="2026-05-01", ata="2026-06-11"),  # JP 희망봉
        _row(dprt="KRPUS", stopby="CAPE", onboard_date="2026-05-01", ata="2026-06-21"),  # KR 희망봉
        _row(dprt="DEHAM", stopby="SUEZ", onboard_date="2026-05-01", ata="2026-06-01"),  # 국가 외 제외
    ])
    report = _report(df)
    assert _cell(report, "ADRIA_SUEZ", "CN", "Avg", "2026-05") == 31.0
    assert _cell(report, "ADRIA_SUEZ", "KR", "Avg", "2026-05") is None  # KR은 희망봉만
    assert _cell(report, "ADRIA_CAPE", "KR", "Avg", "2026-05") == 51.0
    assert _cell(report, "ADRIA_CAPE", "JP", "Avg", "2026-05") == 41.0


def test_forecast_columns():
    df = pd.DataFrame([
        # 진행 중: eta 8월 → forecast 열, L/T = eta - onboard
        _row(onboard_date="2026-07-01", ata=None, eta_date="2026-08-10"),
        # onboard 없으면 atd, 그래도 없으면 etd
        _row(atd=None, etd="2026-07-05", ata=None, eta="2026-08-15"),
        # 완료 건은 forecast에 들어가지 않음
        _row(onboard_date="2026-07-01", ata="2026-08-01"),
    ])
    report = _report(df)
    assert _cell(report, "ADRIA_SUEZ", "KR", "Avg", "2026-08") == 40.5  # (40+41)/2
    kinds = {c["key"]: c["kind"] for c in report["month_columns"]}
    assert kinds["2026-08"] == "forecast"


def test_window_excludes_old_months():
    df = pd.DataFrame([
        _row(onboard_date="2024-01-10", ata="2024-02-10"),  # 창 밖
    ])
    report = _report(df, months=12)
    assert report["month_columns"] == []


def test_empty_dataframe():
    report = _report(pd.DataFrame())
    assert report["groups"] and report["month_columns"] == []
    assert all(row["cells"] == {} for g in report["groups"] for row in g["rows"])
    assert "actual_lt" in report["definitions"]


def test_fcl_only_scope():
    df = pd.DataFrame([
        _row(cargo_type3="FCL", onboard_date="2026-05-10", ata="2026-06-09"),   # 포함
        _row(cargo_type3="LCL", onboard_date="2026-05-10", ata="2026-06-19"),   # 제외
        _row(cargo_type3=None, onboard_date="2026-05-10", ata="2026-06-19"),    # 미기재 제외
    ])
    report = _report(df)
    assert _cell(report, "ADRIA_SUEZ", "KR", "Avg", "2026-05") == 30.0
    assert _cell(report, "ADRIA_SUEZ", "KR", "Max", "2026-05") == 30.0  # LCL 40일 미반영
    assert report["definitions"]["scope"].startswith("집계 대상: cargo_type3 == 'FCL'")


def test_outlier_excluded_by_iqr():
    """IQR 방식: 극단값만 제거하고 정상 장기 L/T(미주 동안 55일 등)는 유지."""
    # 정상 분포 5건(28~32일) + 극단값 1건(150일)
    rows = [
        _row(onboard_date="2026-05-01", ata="2026-05-29"),  # 28일
        _row(onboard_date="2026-05-02", ata="2026-05-31"),  # 29일
        _row(onboard_date="2026-05-03", ata="2026-06-02"),  # 30일
        _row(onboard_date="2026-05-04", ata="2026-06-04"),  # 31일
        _row(onboard_date="2026-05-05", ata="2026-06-06"),  # 32일
        _row(onboard_date="2026-05-06", ata="2026-10-03"),  # 150일 극단값
    ]
    report = _report(pd.DataFrame(rows))
    assert _cell(report, "ADRIA_SUEZ", "KR", "Avg", "2026-05") == 30.0  # 극단값 미반영
    assert _cell(report, "ADRIA_SUEZ", "KR", "Max", "2026-05") == 32.0

    # 정상적인 장기 L/T(55일 안팎)는 아웃라이어가 아니므로 유지
    long_rows = [
        _row(onboard_date="2026-05-01", ata="2026-06-23"),  # 53일
        _row(onboard_date="2026-05-02", ata="2026-06-25"),  # 54일
        _row(onboard_date="2026-05-03", ata="2026-06-27"),  # 55일
        _row(onboard_date="2026-05-04", ata="2026-06-28"),  # 55일
        _row(onboard_date="2026-05-05", ata="2026-06-30"),  # 56일
    ]
    long_report = _report(pd.DataFrame(long_rows))
    assert _cell(long_report, "ADRIA_SUEZ", "KR", "Avg", "2026-05") == 54.6
    assert _cell(long_report, "ADRIA_SUEZ", "KR", "Max", "2026-05") == 56.0

    # 표본 4건 미만이면 제거하지 않음 (극단값 포함 그대로 집계)
    few = [
        _row(onboard_date="2026-05-01", ata="2026-05-31"),   # 30일
        _row(onboard_date="2026-05-02", ata="2026-06-01"),   # 30일
        _row(onboard_date="2026-05-03", ata="2026-09-30"),   # 150일
    ]
    few_report = _report(pd.DataFrame(few))
    assert _cell(few_report, "ADRIA_SUEZ", "KR", "Max", "2026-05") == 150.0

    # 예상(forecast) 버킷에도 동일하게 적용
    fc_rows = [
        _row(onboard_date="2026-07-01", ata=None, eta_date="2026-08-08"),   # 38일
        _row(onboard_date="2026-07-02", ata=None, eta_date="2026-08-10"),   # 39일
        _row(onboard_date="2026-07-03", ata=None, eta_date="2026-08-12"),   # 40일
        _row(onboard_date="2026-07-04", ata=None, eta_date="2026-08-14"),   # 41일
        _row(onboard_date="2026-07-05", ata=None, eta_date="2026-08-16"),   # 42일
        _row(onboard_date="2026-07-06", ata=None, eta_date="2026-10-14"),   # 100일 극단값
    ]
    fc_report = _report(pd.DataFrame(fc_rows))
    assert _cell(fc_report, "ADRIA_SUEZ", "KR", "Avg", "2026-08") == 40.0
    assert "outlier" in fc_report["definitions"]


def test_sea_mode_only():
    """운송모드 해상(100)만 집계 — 200/300 제외, 미기재는 해상 간주."""
    df = pd.DataFrame([
        _row(trpr_mode="100", onboard_date="2026-05-10", ata="2026-06-09"),  # 해상 포함
        _row(trpr_mode="300", onboard_date="2026-05-10", ata="2026-06-19"),  # 항공 제외
        _row(trpr_mode="200", onboard_date="2026-05-10", ata="2026-06-19"),  # 육상 제외
        _row(trpr_mode=None, onboard_date="2026-05-10", ata="2026-06-09"),   # 미기재 포함
    ])
    report = _report(df)
    assert _cell(report, "ADRIA_SUEZ", "KR", "Avg", "2026-05") == 30.0
    assert _cell(report, "ADRIA_SUEZ", "KR", "Max", "2026-05") == 30.0  # 항공 40일 미반영
    assert "sea_mode" in report["definitions"]


# ---------- 그룹 스키마 v2: 권역/커스텀 행/내륙 L/T ----------

def test_row_groups_custom_dimension():
    """row_groups: 국가 대신 선적구분 등 커스텀 행으로 버킷."""
    groups = [{
        "group_id": "CN_KR", "name": "중국→한국", "arvl_codes": ["KR*"],
        "row_groups": [
            {"row_id": "NORTH", "label": "북중국(컨테이너)", "field": "dprt", "codes": ["CNTSN"]},
            {"row_id": "SOUTH", "label": "남중국(컨테이너)", "field": "dprt", "codes": ["CNSZX"]},
        ],
    }]
    df = pd.DataFrame([
        _row(dprt="CNTSN", arvl="KRPUS", onboard_date="2026-05-01", ata="2026-05-03"),
        _row(dprt="CNSZX", arvl="KRPUS", onboard_date="2026-05-01", ata="2026-05-08"),
        _row(dprt="CNSHA", arvl="KRPUS", onboard_date="2026-05-01", ata="2026-05-04"),  # 미해당 제외
    ])
    report = svc.compute_leadtime_report(df, today=TODAY, groups=groups)
    rows = report["groups"][0]["rows"]
    north = next(r for r in rows if r["country"] == "NORTH" and r["stat"] == "Avg")
    south = next(r for r in rows if r["country"] == "SOUTH" and r["stat"] == "Avg")
    assert north["country_label"] == "북중국(컨테이너)"
    assert north["cells"] == {"2026-05": 2.0}
    assert south["cells"] == {"2026-05": 7.0}


def test_inland_metric_actual_and_forecast():
    """inland: 실적 dlvy_ata-ata(ata 월), 예상 dlvy_eta-eta(dlvy_eta 월)."""
    groups = [{
        "group_id": "US_INLAND", "name": "미주 내륙", "metric": "inland",
        "arvl_codes": ["USNYC"],
        "row_groups": [
            {"row_id": "EAST", "label": "미주동부항만", "field": "arvl", "codes": ["USNYC"]},
        ],
    }]
    df = pd.DataFrame([
        _row(dprt="KRPUS", arvl="USNYC", onboard_date="2026-04-10",
             ata="2026-05-20", dlvy_ata="2026-05-23"),   # 실적 3일 (5월)
        _row(dprt="KRPUS", arvl="USNYC", onboard_date="2026-07-01",
             ata=None, eta_date="2026-08-05", dlvy_eta="2026-08-07"),  # 예상 2일 (8월)
    ])
    report = svc.compute_leadtime_report(df, today=TODAY, groups=groups)
    avg = next(
        r for r in report["groups"][0]["rows"]
        if r["country"] == "EAST" and r["stat"] == "Avg"
    )
    assert avg["cells"] == {"2026-05": 3.0, "2026-08": 2.0}
    kinds = {c["key"]: c["kind"] for c in report["month_columns"]}
    assert kinds["2026-05"] == "actual" and kinds["2026-08"] == "forecast"


def test_countries_override_and_labels():
    """countries/country_labels: 그룹별 국가 행 구성과 라벨 재정의."""
    groups = [{
        "group_id": "US_EAST", "name": "미주 동안", "arvl_codes": ["USNYC"],
        "countries": ["KR", "ID", "PL"], "country_labels": {"PL": "북유럽"},
    }]
    df = pd.DataFrame([
        _row(dprt="IDJKT", arvl="USNYC", onboard_date="2026-05-01", ata="2026-06-01"),
        _row(dprt="PLGDN", arvl="USNYC", onboard_date="2026-05-01", ata="2026-06-11"),
        _row(dprt="CNSHA", arvl="USNYC", onboard_date="2026-05-01", ata="2026-06-21"),
    ])
    report = svc.compute_leadtime_report(df, today=TODAY, groups=groups)
    rows = report["groups"][0]["rows"]
    assert {r["country"] for r in rows} == {"KR", "ID", "PL"}  # CN 행 없음
    pl = next(r for r in rows if r["country"] == "PL" and r["stat"] == "Avg")
    assert pl["country_label"] == "북유럽"
    assert pl["cells"] == {"2026-05": 41.0}
    assert _cell(report, "US_EAST", "ID", "Avg", "2026-05") == 31.0


def test_real_config_loads_and_has_regions():
    groups = svc.load_route_groups()
    ids = [g["group_id"] for g in groups]
    assert len(ids) == len(set(ids))
    regions = {g.get("region") for g in groups}
    assert {"유럽", "미주", "아시아"} <= regions


def test_inland_row_groups_by_trpr_mode():
    """유럽 내륙: trpr_mode별 운송방식 행 분리 — 해상(100) 게이트는 sea 그룹에만."""
    groups = [{
        "group_id": "EU_INLAND", "name": "유럽 내륙", "metric": "inland",
        "arvl_codes": ["SIKOP"],
        "row_groups": [
            {"row_id": "DT", "label": "Direct Truck", "field": "trpr_mode", "codes": ["200"]},
            {"row_id": "RT", "label": "Rail+Truck", "field": "trpr_mode", "codes": ["300"]},
        ],
    }]
    df = pd.DataFrame([
        _row(arvl="SIKOP", trpr_mode="300", onboard_date="2026-04-10",
             ata="2026-05-10", dlvy_ata="2026-05-17"),   # Rail+Truck 7일
        _row(arvl="SIKOP", trpr_mode="200", onboard_date="2026-04-10",
             ata="2026-05-10", dlvy_ata="2026-05-12"),   # Direct Truck 2일
        _row(arvl="SIKOP", trpr_mode="100", onboard_date="2026-04-10",
             ata="2026-05-10", dlvy_ata="2026-05-30"),   # 해상모드 — 어느 행에도 미해당
    ])
    report = svc.compute_leadtime_report(df, today=TODAY, groups=groups)
    rows = report["groups"][0]["rows"]
    rt = next(r for r in rows if r["country"] == "RT" and r["stat"] == "Avg")
    dt = next(r for r in rows if r["country"] == "DT" and r["stat"] == "Avg")
    assert rt["cells"] == {"2026-05": 7.0}
    assert dt["cells"] == {"2026-05": 2.0}


# ---------- 고정 행(fixed rows) + dprt 매칭 ----------

FERRY_GROUPS = GROUPS + [
    {
        "group_id": "CHINA_TO_KOREA",
        "name": "중국 항만 선적 / 한국 항만 도착",
        "arvl_codes": ["KR*"],
        "dprt_codes": ["CNTSN", "CNSHA"],
        "stopby_match": [],
        "stopby_exclude": [],
        "fixed_rows": [
            {
                "country": "FERRY_NORTH_CN",
                "country_label": "북중국(훼리)",
                "values": {"Avg": 1, "Min": 1, "Max": 1},
                "note": "사용자 제공 고정값",
            }
        ],
    }
]


def test_fixed_rows_all_months_same_value():
    df = pd.DataFrame([
        _row(dprt="CNTSN", arvl="KRPUS", onboard_date="2026-05-01", ata="2026-05-03"),
        _row(dprt="CNSHA", arvl="KRBNP", onboard_date="2026-06-01", ata="2026-06-04"),
    ])
    report = svc.compute_leadtime_report(df, today=TODAY, groups=FERRY_GROUPS)
    group = next(g for g in report["groups"] if g["group_id"] == "CHINA_TO_KOREA")

    # dprt 매칭 + arvl 와일드카드: CN 행에 실적 집계
    assert _cell(report, "CHINA_TO_KOREA", "CN", "Avg", "2026-05") == 2.0
    assert _cell(report, "CHINA_TO_KOREA", "CN", "Avg", "2026-06") == 3.0
    # 한국 선적이 아니므로 KR 행은 비어 있음
    assert _cell(report, "CHINA_TO_KOREA", "KR", "Avg", "2026-05") is None

    # 고정 행: 모든 월 열 동일 값 + fixed 플래그
    fixed_avg = next(
        r for r in group["rows"] if r["country"] == "FERRY_NORTH_CN" and r["stat"] == "Avg"
    )
    assert fixed_avg["fixed"] is True
    assert fixed_avg["country_label"] == "북중국(훼리)"
    assert fixed_avg["cells"] == {"2026-05": 1, "2026-06": 1}
    fixed_max = next(
        r for r in group["rows"] if r["country"] == "FERRY_NORTH_CN" and r["stat"] == "Max"
    )
    assert fixed_max["cells"] == {"2026-05": 1, "2026-06": 1}
    assert "고정값" in report["definitions"]["fixed_rows"]


def test_dprt_codes_filter_excludes_other_ports():
    df = pd.DataFrame([
        _row(dprt="CNSZX", arvl="KRPUS", onboard_date="2026-05-01", ata="2026-05-03"),  # dprt_codes 외
    ])
    report = svc.compute_leadtime_report(df, today=TODAY, groups=FERRY_GROUPS)
    assert _cell(report, "CHINA_TO_KOREA", "CN", "Avg", "2026-05") is None


# ---------- API ----------

def test_api_leadtime(monkeypatch):
    monkeypatch.setattr(
        svc,
        "fetch_bl_info",
        lambda **kwargs: pd.DataFrame(
            [_row(onboard_date="2026-05-10", ata="2026-06-09")]
        ),
    )
    client = TestClient(app)
    resp = client.get("/api/report/leadtime?months=12")
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "B-LAP bl_info"
    assert body["month_columns"]
    assert _cell(body, "ADRIA_SUEZ", "KR", "Avg", "2026-05") == 30.0
    # months 검증
    assert client.get("/api/report/leadtime?months=2").status_code == 422


# ---------- 성능: history 미호출 + 컬럼 프로젝션 ----------

def test_fetch_leadtime_report_does_not_call_history(monkeypatch):
    """리드타임은 bl_info만으로 계산 — history chunk 호출이 없어야 한다."""
    called = {"info": 0}

    def _fake_info(**kwargs):
        called["info"] += 1
        called["select_columns"] = kwargs.get("select_columns")
        return pd.DataFrame([_row(onboard_date="2026-05-10", ata="2026-06-09")])

    def _forbidden_history(*args, **kwargs):
        raise AssertionError("리드타임 집계에서 history를 조회하면 안 됩니다")

    monkeypatch.setattr(svc, "fetch_bl_info", _fake_info)
    monkeypatch.setattr(
        "services.datalake_schedule_client.fetch_bl_history_for_transports",
        _forbidden_history,
    )
    monkeypatch.setattr(
        "services.datalake_schedule_client.fetch_bl_history",
        _forbidden_history,
    )
    report = svc.fetch_leadtime_report(months=12, forecast_months=3)
    assert called["info"] == 1
    assert called["select_columns"] == svc.LEADTIME_SELECT_COLUMNS
    assert report["month_columns"]
