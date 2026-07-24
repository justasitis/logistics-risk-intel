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
