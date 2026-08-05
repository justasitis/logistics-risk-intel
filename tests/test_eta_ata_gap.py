"""ETA-ATA Gap 주차별 집계 테스트 (가짜 DataFrame, 외부 호출 없음)."""
from datetime import date

import pandas as pd

from services import eta_ata_gap_service as svc

TODAY = date(2026, 8, 5)  # 수요일 — ISO W32

GROUPS = [
    {
        "group_id": "ADRIA_SUEZ",
        "name": "아드리아해 / 수에즈",
        "region": "유럽",
        "arvl_codes": ["SIKOP"],
        "stopby_match": ["SUEZ"],
        "stopby_exclude": [],
    },
    {
        "group_id": "US_EAST",
        "name": "미주 동안",
        "region": "미주",
        "arvl_codes": ["USSAV"],
        "stopby_match": [],
        "stopby_exclude": [],
    },
]


def _row(**kw):
    base = {
        "dprt": "KRPUS", "arvl": "SIKOP", "stopby": "SUEZ", "stopby_nm": "",
        "eta": None, "eta_date": None, "ata": None,
    }
    base.update(kw)
    return base


def _report(df, **kw):
    return svc.compute_eta_ata_gap(df, today=TODAY, groups=GROUPS, **kw)


def _weekly(report, group_id):
    if group_id == "ALL":
        return report["overall"]["weekly"]
    group = next(g for g in report["groups"] if g["group_id"] == group_id)
    return group["weekly"]


def _avg(report, group_id, week):
    for w in _weekly(report, group_id):
        if w["week"] == week:
            return w.get("avg_gap")
    return None


def test_gap_calculation_and_week_bucket():
    # 2026-07-22(W30) 도착, ETA 07-20 → Gap +2일
    # 2026-07-23(W30) 도착, ETA 07-25 → Gap -2일 (조기 도착도 평균에 반영)
    df = pd.DataFrame([
        _row(eta_date="2026-07-20", ata="2026-07-22"),
        _row(eta_date="2026-07-25", ata="2026-07-23"),
    ])
    report = _report(df)
    assert _avg(report, "ADRIA_SUEZ", "2026-W30") == 0.0  # (2 + -2) / 2
    w30 = next(w for w in _weekly(report, "ADRIA_SUEZ") if w["week"] == "2026-W30")
    assert w30["count"] == 2
    assert w30["delayed_count"] == 1
    assert w30["delayed_ratio"] == 0.5


def test_eta_fallback_and_incomplete_excluded():
    df = pd.DataFrame([
        # eta_date 없으면 eta 사용 (7/29 W31 도착, ETA 7/27 → +2)
        _row(eta="2026-07-27", ata="2026-07-29"),
        # ata 없으면(진행 중) 제외
        _row(eta_date="2026-07-20", ata=None),
        # eta/ata 둘 다 없으면 제외
        _row(),
    ])
    report = _report(df)
    assert _avg(report, "ADRIA_SUEZ", "2026-W31") == 2.0


def test_group_isolation_and_overall():
    df = pd.DataFrame([
        _row(eta_date="2026-07-20", ata="2026-07-22"),                    # SUEZ +2
        _row(arvl="USSAV", stopby="", eta_date="2026-07-20", ata="2026-07-26"),  # US +6
    ])
    report = _report(df)
    assert _avg(report, "ADRIA_SUEZ", "2026-W30") == 2.0
    assert _avg(report, "US_EAST", "2026-W30") == 6.0
    assert _avg(report, "ALL", "2026-W30") == 4.0  # (2+6)/2


def test_watch_level_on_three_consecutive_increases():
    # W28: 1일, W29: 2일, W30: 3일, W31: 4일 → 3주 연속 증가 → WATCH
    df = pd.DataFrame([
        _row(eta_date="2026-07-06", ata="2026-07-07"),   # W28 +1
        _row(eta_date="2026-07-13", ata="2026-07-15"),   # W29 +2
        _row(eta_date="2026-07-20", ata="2026-07-23"),   # W30 +3
        _row(eta_date="2026-07-27", ata="2026-07-31"),   # W31 +4
    ])
    report = _report(df)
    group = next(g for g in report["groups"] if g["group_id"] == "ADRIA_SUEZ")
    assert group["consecutive_increases"] == 3
    assert group["level"] == "WATCH"
    assert any("연속 증가" in r for r in group["level_reasons"])


def test_warn_level_on_threshold_exceeded():
    # 최근 완료 주 평균 Gap 6일 > 기준 5일 → WARN (연속 증가 없어도)
    df = pd.DataFrame([
        _row(eta_date="2026-07-27", ata="2026-08-02"),   # W31 +6
        _row(eta_date="2026-07-20", ata="2026-07-21"),   # W30 +1 (감소 추세)
    ])
    report = _report(df)
    group = next(g for g in report["groups"] if g["group_id"] == "ADRIA_SUEZ")
    assert group["latest_avg_gap"] == 6.0
    assert group["level"] == "WARN"
    assert any("기준" in r for r in group["level_reasons"])


def test_current_week_excluded_from_trend():
    # 당주(W32) 데이터는 표시되지만 추세 판정에서는 제외
    df = pd.DataFrame([
        _row(eta_date="2026-07-27", ata="2026-07-28"),   # W31 +1
        _row(eta_date="2026-08-03", ata="2026-08-05"),   # W32(당주) +2
    ])
    report = _report(df)
    group = next(g for g in report["groups"] if g["group_id"] == "ADRIA_SUEZ")
    assert _avg(report, "ADRIA_SUEZ", "2026-W32") == 2.0  # 표시는 됨
    assert group["consecutive_increases"] == 0  # 당주 증가는 추세 미반영
    assert group["level"] == "OK"
    assert report["params"]["current_week"] == "2026-W32"


def test_empty_dataframe():
    report = _report(pd.DataFrame())
    assert report["overall"]["level"] == "OK"
    assert report["overall"]["latest_avg_gap"] is None
    assert all(w["count"] == 0 for w in report["overall"]["weekly"])
