"""도착지연 분해 & 선사 정시성 집계 테스트 (가짜 DataFrame, 외부 호출 없음)."""
from datetime import date, timedelta

import httpx
import pandas as pd
import pytest

from services import delay_decomposition_service as svc

# TestClient는 앱 내부(ASGI) 호출 — conftest의 httpx 차단 복원용 원본
_REAL_HTTPX_REQUEST = httpx.Client.request
from services.leadtime_report_service import _percentile

TODAY = date(2026, 8, 5)

THRESHOLDS = {
    "iqr_tight": 2.0,
    "median_small_abs": 1.0,
    "median_late": 3.0,
    "iqr_volatile": 4.0,
    "tail_burst": 6.0,
    "min_sample": 10,
    "coverage_warn": 0.7,
}

GROUPS = [
    {
        "group_id": "ADRIA_SUEZ",
        "name": "아드리아해 / 수에즈",
        "arvl_codes": ["SIKOP"],
        "stopby_match": ["SUEZ", "수에즈", "EGSCN"],
        "stopby_exclude": [],
    },
    {
        "group_id": "ADRIA_CAPE",
        "name": "아드리아해 / 희망봉",
        "arvl_codes": ["SIKOP"],
        "stopby_match": ["CAPE", "희망봉", "GOOD HOPE", "ZACPT"],
        "stopby_exclude": [],
    },
]

# 최초ETD 기준 계획 항해일수 (테스트 고정값)
PLANNED_DAYS = 30
FIRST_ETD = pd.Timestamp("2026-06-01")
ETD_RECORDED_AT = "2026-05-20T09:00:00"
ETA_RECORDED_AT = "2026-05-20T10:30:00"  # ETD 첫 기록보다 1.5시간 뒤


def _fmt(ts: pd.Timestamp) -> str:
    return ts.strftime("%Y%m%d%H%M%S")


def _info_row(trpr_no, **kw):
    base = {
        "cmpy_cd": "S000",
        "plnt_cd": "P1",
        "trpr_no": trpr_no,
        "hbl_no": f"HBL-{trpr_no}",
        "cntr_no": "CNTR1",
        "dprt": "KRPUS",
        "arvl": "SIKOP",
        "stopby": "EGSCN",
        "stopby_nm": "SUEZ CANAL",
        "carrier_cd": "MAEU",
        "carrier_nm": "MAERSK",
        "vessel_nm": "VSL A",
        "voyage_no": "V001",
        "trpr_mode": "100",
        "etd": "",
        "atd": "",
        "eta": "",
        "eta_date": "",
        "ata": "",
    }
    base.update(kw)
    return base


def _his_row(trpr_no, his_type, fr_date, to_date, ins_datetime, his_no="1"):
    return {
        "cmpy_cd": "S000",
        "plnt_cd": "P1",
        "trpr_no": trpr_no,
        "his_type": his_type,
        "his_no": his_no,
        "fr_date": fr_date,
        "to_date": to_date,
        "ins_datetime": ins_datetime,
    }


def _voyage(trpr_no, *, dep, voy, **info_kw):
    """dep/voy(일)가 정확히 성립하는 bl_info 1행 + 최초 이력 2행 생성.

    최초ETD/최초ETA는 fr_date 공란(최초 등록행)의 to_date로 기록한다.
    """
    atd = FIRST_ETD + timedelta(days=dep)
    first_eta = FIRST_ETD + timedelta(days=PLANNED_DAYS)
    ata = atd + timedelta(days=PLANNED_DAYS + voy)
    info = _info_row(
        trpr_no,
        etd=_fmt(FIRST_ETD),
        atd=_fmt(atd),
        ata=_fmt(ata),
        **info_kw,
    )
    history = [
        _his_row(trpr_no, "ETD", "", _fmt(FIRST_ETD), ETD_RECORDED_AT),
        _his_row(trpr_no, "ETA", "", _fmt(first_eta), ETA_RECORDED_AT),
    ]
    return info, history


def _build(voyages, *, extra_info=(), extra_history=()):
    infos, histories = [], []
    for v in voyages:
        info, history = v
        infos.append(info)
        histories.extend(history)
    infos.extend(extra_info)
    histories.extend(extra_history)
    return pd.DataFrame(infos), pd.DataFrame(histories)


def _compute(info_df, history_df, *, group_id="ADRIA_SUEZ", months=12):
    return svc.compute_delay_decomposition(
        info_df,
        history_df,
        group_id=group_id,
        months=months,
        today=TODAY,
        groups=GROUPS,
        thresholds=THRESHOLDS,
    )


def _carrier(report, code):
    return next(c for c in report["carriers"] if c["carrier_code"] == code)


# 1. 항등식: 누적 = 출항 + 항해 (헤드라인 + 항차 단위)
def test_identity_headline_and_voyage_level():
    deps = [-2, -1, 0, 1, 1, 2, 2, 3, 3, 4, 5, 8]
    voys = [1, -1, 2, 0, 1, -2, 0, 3, 1, 0, 2, -1]
    voyages = [
        _voyage(f"T{i:03d}", dep=d, voy=v) for i, (d, v) in enumerate(zip(deps, voys))
    ]
    info_df, history_df = _build(voyages)
    report = _compute(info_df, history_df)

    headline = report["headline"]
    assert headline["voyage_count"] == 12
    assert headline["total_count"] == 12
    assert abs(
        headline["cumulative_delay_days"]
        - (headline["dep_delay_days"] + headline["voyage_delta_days"])
    ) < 0.05

    carrier = _carrier(report, "MAEU")
    assert len(carrier["voyages"]) == 12
    for item in carrier["voyages"]:
        assert abs(
            item["cumulative_delay_days"]
            - (item["dep_delay_days"] + item["voyage_delta_days"])
        ) < 0.05


# 2. 최초값 규칙: ins_datetime 최소 행, fr_date 우선/없으면 to_date, MIN(날짜) 금지
def test_first_schedule_rule():
    history_df = pd.DataFrame(
        [
            # T1: 첫 기록행 fr_date 사용 — 이후 앞당김(01-12 → 01-05) 이력이
            # 있어도 MIN(날짜)인 01-05가 아니라 첫 기록의 fr_date 01-10이 최초ETD
            _his_row("T1", "ETD", "20260110000000", "20260112000000",
                     "2026-01-05T09:00:00", his_no="1"),
            _his_row("T1", "ETD", "20260112000000", "20260105000000",
                     "2026-01-20T09:00:00", his_no="2"),
            # T2: 첫 기록행 fr_date 공란(최초 등록행) → to_date 사용
            _his_row("T2", "ETA", "", "20260201000000",
                     "2026-01-05T09:00:00", his_no="1"),
            _his_row("T2", "ETA", "20260201000000", "20260210000000",
                     "2026-01-15T09:00:00", his_no="2"),
            # T3: 등록 시각이 더 이른 행이 우선 (to_date가 더 늦어도 무관)
            _his_row("T3", "ETD", "20260101000000", "20260103000000",
                     "2026-01-02T09:00:00", his_no="1"),
            _his_row("T3", "ETD", "20260103000000", "20260115000000",
                     "2026-01-10T09:00:00", his_no="2"),
        ]
    )
    first = svc.compute_first_schedules(history_df)

    assert first["S000|P1|T1"]["ETD"]["value"] == pd.Timestamp("2026-01-10")
    assert first["S000|P1|T2"]["ETA"]["value"] == pd.Timestamp("2026-02-01")
    assert first["S000|P1|T3"]["ETD"]["value"] == pd.Timestamp("2026-01-01")


# 3. 표본 10 미만 → 판정 보류 + 통계 null (표본 수 노출, voyages는 반환)
def test_small_sample_hold():
    voyages = [_voyage(f"T{i:03d}", dep=i % 3, voy=0) for i in range(9)]
    info_df, history_df = _build(voyages)
    report = _compute(info_df, history_df)

    carrier = _carrier(report, "MAEU")
    assert carrier["voyage_count"] == 9
    assert carrier["verdict"] == "표본 9항차. 판정 보류."
    assert carrier["verdict_tone"] == "hold"
    for field in ("p25", "p50", "p75", "p90", "iqr", "tail"):
        assert carrier[field] is None
    assert len(carrier["voyages"]) == 9  # 표본 부족이어도 voyages는 반환


# 4. UNMAPPED 집계 + 음수 유지 + 결측 제외 + 커버리지 계산·경고
def test_unmapped_negative_missing_and_coverage():
    # 12개 모두 선사 코드/명 공란, 전부 조기 도착(음수 지연)
    voyages = [
        _voyage(f"T{i:03d}", dep=-2, voy=-1, carrier_cd="", carrier_nm="")
        for i in range(12)
    ]
    # atd 결측 1건 추가 — 유효 항차에서 제외되지만 전체 매칭 행에는 포함
    missing = _info_row("T900", ata="20260710000000", atd="")
    missing_history = [
        _his_row("T900", "ETD", "", "20260601000000", ETD_RECORDED_AT),
        _his_row("T900", "ETA", "", "20260701000000", ETA_RECORDED_AT),
    ]
    info_df, history_df = _build(
        voyages, extra_info=[missing], extra_history=missing_history,
    )
    report = _compute(info_df, history_df)

    headline = report["headline"]
    assert headline["voyage_count"] == 12
    assert headline["total_count"] == 13
    assert headline["coverage"] == round(12 / 13, 2)
    assert headline["coverage_warn"] is False
    # 조기 도착 음수 유지 (클clamp 금지)
    assert headline["dep_delay_days"] == -2.0
    assert headline["cumulative_delay_days"] == -3.0

    unmapped = _carrier(report, "UNMAPPED")
    assert unmapped["carrier_name"] == "미매핑"
    assert unmapped["voyage_count"] == 12
    assert unmapped["p50"] == -1.0  # 선사 통계는 항해 증감(voy=-1) 기준
    assert all(v["cumulative_delay_days"] < 0 for v in unmapped["voyages"])
    assert any("UNMAPPED" in note for note in report["notes"])

    # 커버리지 경고: 유효 5 / 전체 10 = 0.5 < 0.7
    voyages2 = [_voyage(f"U{i:03d}", dep=1, voy=1) for i in range(5)]
    missing2 = [
        _info_row(f"U9{i:02d}", ata="20260710000000", atd="")
        for i in range(5)
    ]
    info_df2, history_df2 = _build(voyages2, extra_info=missing2)
    report2 = _compute(info_df2, history_df2)
    headline2 = report2["headline"]
    assert headline2["coverage"] == 0.5
    assert headline2["coverage_warn"] is True


# 5. stopby 수에즈/희망봉 그룹 분리 매칭
def test_stopby_group_separation():
    suez_info, suez_his = _voyage("TS01", dep=2, voy=1)
    cape_info, cape_his = _voyage(
        "TC01", dep=5, voy=2, stopby="ZACPT", stopby_nm="CAPE OF GOOD HOPE",
    )
    info_df, history_df = _build([(suez_info, suez_his), (cape_info, cape_his)])

    suez_report = _compute(info_df, history_df, group_id="ADRIA_SUEZ")
    assert suez_report["headline"]["total_count"] == 1
    assert suez_report["headline"]["voyage_count"] == 1
    suez_voyage = suez_report["carriers"][0]["voyages"][0]
    assert suez_voyage["hbl_no"] == "HBL-TS01"
    assert suez_voyage["dep_delay_days"] == 2.0

    cape_report = _compute(info_df, history_df, group_id="ADRIA_CAPE")
    assert cape_report["headline"]["total_count"] == 1
    cape_voyage = cape_report["carriers"][0]["voyages"][0]
    assert cape_voyage["hbl_no"] == "HBL-TC01"
    assert cape_voyage["dep_delay_days"] == 5.0


# 6. 판정문 5룰 + 우선순위 (첫 매칭 적용)
def test_verdict_rules_and_priority():
    def verdict(**kw):
        return svc.build_verdict(thresholds=THRESHOLDS, **kw)

    # 룰 1: 표본 부족
    assert verdict(n=9, p50=None, iqr=None, tail=None) == (
        "표본 9항차. 판정 보류.", "hold",
    )
    # 룰 2: IQR 타이트 + 중앙값 절대값 작음
    assert verdict(n=20, p50=0.5, iqr=1.0, tail=1.0) == (
        "약속을 지킵니다. 계획 그대로 써도 됩니다.", "ok",
    )
    # 룰 3: IQR 타이트 + 중앙값 지연 — tail이 커도 steady가 우선
    text, tone = verdict(n=20, p50=3.5, iqr=1.0, tail=9.0)
    assert tone == "steady"
    assert "4일 당겨 잡으면" in text
    # 룰 3은 양수 지연에만 적용 — 조기 도착(음수)은 steady가 아님
    text, tone = verdict(n=20, p50=-3.5, iqr=1.0, tail=7.0)
    assert tone == "warn"
    # 룰 4: IQR 변동성 — tail 조건과 동시 충족 시 hot이 우선
    assert verdict(n=20, p50=0.5, iqr=5.0, tail=10.0) == (
        "중앙값은 좋은데 매번 다릅니다. 계획을 세울 수 없습니다.", "hot",
    )
    # 룰 5: 상단 꼬리 버스트
    assert verdict(n=20, p50=2.0, iqr=3.0, tail=6.5) == (
        "평소엔 괜찮은데 가끔 크게 터집니다.", "warn",
    )
    # 기본
    assert verdict(n=20, p50=2.0, iqr=3.0, tail=2.0) == (
        "평범합니다. 상단 꼬리만 주시하세요.", "neutral",
    )


# 7. 선형보간 분위수 고정값 검증
def test_percentile_linear_interpolation():
    values = [1.0, 2.0, 3.0, 4.0]
    assert _percentile(values, 0.25) == pytest.approx(1.75)
    assert _percentile(values, 0.50) == pytest.approx(2.5)
    assert _percentile(values, 0.75) == pytest.approx(3.25)
    assert _percentile(values, 0.90) == pytest.approx(3.7)
    assert _percentile([5.0], 0.5) == pytest.approx(5.0)
    assert _percentile([1.0, 2.0], 0.9) == pytest.approx(1.9)


# 8. date_only 판정 + notes (첫 기록 시각 차이 중앙값 포함)
def test_date_only_and_notes():
    voyages = [_voyage(f"T{i:03d}", dep=1, voy=1) for i in range(12)]
    info_df, history_df = _build(voyages)
    report = _compute(info_df, history_df)

    headline = report["headline"]
    assert headline["date_only"] is True
    # ETD 09:00 / ETA 10:30 등록 → 첫 기록 시각 차이 중앙값 1.5시간
    assert headline["first_record_gap_hours"] == 1.5
    assert any("첫 기록 시각 차이 중앙값 1.5시간" in n for n in report["notes"])
    assert any("측정 해상도" in n for n in report["notes"])
    assert any("UTC 정규화 없이" in n for n in report["notes"])

    # 시각부가 있는 ATA가 하나라도 있으면 date_only False
    info2, history2 = _voyage("TX01", dep=1, voy=1)
    info2["ata"] = "20260702143000"
    info_df2 = pd.concat([info_df, pd.DataFrame([info2])], ignore_index=True)
    history_df2 = pd.concat(
        [history_df, pd.DataFrame(history2)], ignore_index=True,
    )
    report2 = _compute(info_df2, history_df2)
    assert report2["headline"]["date_only"] is False
    assert not any("측정 해상도" in n for n in report2["notes"])


# 9. fetch 래퍼 — 외부 호출 monkeypatch (조회 범위/컬럼/이력 키 검증)
def test_fetch_wrapper_monkeypatched(monkeypatch):
    voyages = [_voyage(f"T{i:03d}", dep=1, voy=1) for i in range(12)]
    info_df, history_df = _build(voyages)
    # 그룹 불일치 행은 이력 조회 대상에서 빠져야 한다.
    other = _info_row("T800", arvl="USSAV", stopby="", stopby_nm="")
    info_df = pd.concat([info_df, pd.DataFrame([other])], ignore_index=True)

    calls = {}

    def fake_fetch_bl_info(**kw):
        calls["info"] = kw
        return info_df

    def fake_fetch_history(keys):
        calls["keys"] = keys
        return history_df

    monkeypatch.setattr(svc, "fetch_bl_info", fake_fetch_bl_info)
    monkeypatch.setattr(svc, "fetch_bl_history_for_transports", fake_fetch_history)

    report = svc.fetch_delay_decomposition(
        group_id="ADRIA_SUEZ", months=12, today=TODAY,
    )

    assert report["group_id"] == "ADRIA_SUEZ"
    assert report["headline"]["voyage_count"] == 12
    assert calls["info"]["select_columns"] == svc.DELAY_SELECT_COLUMNS
    assert calls["info"]["etd_from"] == TODAY - timedelta(
        days=12 * 31 + svc.LOOKBACK_BUFFER_DAYS,
    )
    # 해상+그룹 매칭된 운송만 이력 조회 (T800 제외)
    assert len(calls["keys"]) == 12
    assert all(key[2] != "T800" for key in calls["keys"])

    with pytest.raises(ValueError):
        svc.fetch_delay_decomposition(group_id="EU_INLAND", today=TODAY)


# 10. 그룹 목록 경량 조회 — 외부 호출 없음
def test_list_delay_groups_order_and_fields():
    groups = svc.list_delay_groups(GROUPS)
    # GROUPS 픽스처는 2개만 포함 — TARGET 순서 유지, id+name만 반환
    assert groups == [
        {"group_id": "ADRIA_SUEZ", "name": "아드리아해 / 수에즈"},
        {"group_id": "ADRIA_CAPE", "name": "아드리아해 / 희망봉"},
    ]
    # name이 없으면 group_id로 대체
    fallback = svc.list_delay_groups([{"group_id": "US_EAST"}])
    assert fallback == [{"group_id": "US_EAST", "name": "US_EAST"}]
    # 집계 결과의 available_groups와 동일 함수를 쓴다.
    voyages = [_voyage(f"T{i:03d}", dep=1, voy=1) for i in range(3)]
    info_df, history_df = _build(voyages)
    report = svc.compute_delay_decomposition(
        info_df,
        history_df,
        group_id="ADRIA_SUEZ",
        months=12,
        today=TODAY,
        groups=GROUPS,
        thresholds=THRESHOLDS,
    )
    assert report["available_groups"] == svc.list_delay_groups(GROUPS)


def test_delay_decomposition_groups_endpoint():
    from fastapi.testclient import TestClient

    from api_server import app

    # TestClient는 앱 내부(ASGI) 호출 — conftest의 httpx 차단 복원
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(httpx.Client, "request", _REAL_HTTPX_REQUEST)
        client = TestClient(app)
        res = client.get("/api/anomaly/delay-decomposition/groups")
    assert res.status_code == 200
    groups = res.json()["groups"]
    ids = [g["group_id"] for g in groups]
    assert ids == svc.TARGET_GROUP_IDS
    assert all(g["name"] for g in groups)


# 11. 유럽향 선사·경유항로 추론 — 지연 분해에도 동일 적용
def test_europe_inference_unico_cma_vessel():
    """유니코 + 선명 CMA + stopby 공란 → 수에즈 경유 부여 → ADRIA_SUEZ 집계."""
    info, history = _voyage(
        "TI01", dep=2, voy=1,
        stopby="", stopby_nm="", carrier_cd="", carrier_nm="",
        lsp_nm="유니코로지스", vessel_nm="CMA CGM LIBERTY",
    )
    info_df, history_df = _build([(info, history)])
    report = _compute(info_df, history_df)
    assert report["headline"]["total_count"] == 1
    assert report["headline"]["voyage_count"] == 1
    # 추론으로 보정된 선사 코드로 집계된다.
    assert _carrier(report, "CMAU")["voyage_count"] == 1


def test_europe_inference_unico_unknown_vessel_excluded():
    """유니코인데 선명이 CMA/MAERSK 둘 다 아니면 집계 제외."""
    info, history = _voyage(
        "TI02", dep=2, voy=1,
        stopby="", stopby_nm="", carrier_cd="", carrier_nm="",
        lsp_nm="유니코로지스", vessel_nm="HYUNDAI MERCURY",
    )
    info_df, history_df = _build([(info, history)])
    report = _compute(info_df, history_df)
    assert report["headline"]["total_count"] == 0
    assert report["headline"]["voyage_count"] == 0


def test_eu_north_in_target_group_ids():
    """EU_NORTH는 ADRIA_CAPE 다음 위치의 집계 대상 그룹."""
    ids = svc.TARGET_GROUP_IDS
    assert ids.index("EU_NORTH") == ids.index("ADRIA_CAPE") + 1
