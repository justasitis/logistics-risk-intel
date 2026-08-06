"""도착지연 분해 & 선사 정시성 집계 서비스.

'지연 추이' 탭 개편 — 입항 누적지연을 출항지연 + 항해 증감으로 분해하고
선사별 정시성(중앙값/IQR/상단꼬리)을 집계한다.

지표 정의 (단위: 일, 소수 첫째 자리):
- 출항지연 = ATD - 최초ETD
- 항해 증감 = (ATA - ATD) - (최초ETA - 최초ETD)
- 입항 누적지연 = ATA - 최초ETA (수학적으로 출항지연 + 항해 증감과 항등)
- 헤드라인 집계: 출항지연·항해 증감의 중앙값을 먼저 구하고 누적지연은
  두 값의 합으로 도출한다 (독립 집계 금지).
- 조기 도착은 음수 그대로 유지(클램프 금지). ATA/ATD/최초ETA/최초ETD 중
  하나라도 없으면 그 항차는 제외한다 (0/평균 채움 금지). 이상치 제거 금지.

최초ETD/최초ETA 규칙:
- VDT_INB_BL_HIS에서 (cmpy_cd, plnt_cd, trpr_no, his_type)별
  ins_datetime 최소 행의 fr_date(있으면), 없으면 to_date.
  MIN(날짜값) 절대 금지 — 기록 시점 기준이다.
- 이력이 아예 없는 운송은 최초값 없음 → 해당 항차 제외(결측 처리).

집계 규칙:
- 집계 단위: 항로 그룹 × 선사. 기간은 ATA 월 기준 최근 N개월(기본 12).
- 선사 키: carrier_cd(SCAC) 대문자 정규화. 공란이면 carrier_nm 정규화
  (대문자·공백정리). 둘 다 없으면 UNMAPPED.
- 선사 통계: 항해 증감 분포의 P50/IQR(P75-P25)/상단꼬리(P90-P50), 선형보간
  분위수(leadtime_report_service._percentile 재사용). 평균·표준편차 금지.
- 최소 표본(min_sample) 미만이면 통계 산출 없이 판정 보류.
- 커버리지 = 유효 항차 ÷ 전체 매칭 행. coverage_warn 미만이면 경고.

판정문은 규칙 기반이며 임계값은
backend/app/data/delay_verdict_thresholds.json 에서 읽는다 (읽기 전용).
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from services.datalake_schedule_client import (
    fetch_bl_history_for_transports,
    fetch_bl_info,
)
from services.leadtime_report_service import (
    _matches_group,
    _percentile,
    load_route_groups,
)
from services.schedule_history_service import normalize_schedule_history

logger = logging.getLogger(__name__)

VERDICT_THRESHOLDS_PATH = (
    Path(__file__).resolve().parents[1]
    / "backend" / "app" / "data" / "delay_verdict_thresholds.json"
)

# 대상 항로 그룹 5개 (해상만) — 응답의 available_groups 순서이기도 하다.
TARGET_GROUP_IDS = [
    "ADRIA_SUEZ",
    "ADRIA_CAPE",
    "US_EAST",
    "US_WEST",
    "CHINA_TO_KOREA",
]

# 지연 분해에 필요한 컬럼만 서버측 프로젝션 ($select)
DELAY_SELECT_COLUMNS = [
    "cmpy_cd",
    "plnt_cd",
    "trpr_no",
    "hbl_no",
    "cntr_no",
    "dprt",
    "arvl",
    "stopby",
    "stopby_nm",
    "carrier_cd",
    "carrier_nm",
    "vessel_nm",
    "voyage_no",
    "trpr_mode",
    "etd",
    "atd",
    "eta",
    "eta_date",
    "ata",
]

DEFAULT_MONTHS = 12
# etd_from lookback 여유: ATA가 창 안에 있어도 장기 항해+지연이면 ETD는
# 더 과거일 수 있으므로 월 환산(31일)에 항해/지연 여유 62일을 더한다.
LOOKBACK_BUFFER_DAYS = 62

# 중복 제거 시 첫 비null 값으로 채울 컬럼 (날짜 + 표시/집계용)
_DEDUP_FILL_COLUMNS = [
    "etd",
    "atd",
    "eta",
    "eta_date",
    "ata",
    "carrier_cd",
    "carrier_nm",
    "vessel_nm",
    "voyage_no",
    "dprt",
    "arvl",
    "stopby",
    "stopby_nm",
    "trpr_mode",
    "cntr_no",
]

# bl_info의 날짜 컬럼 (YYYYMMDDHHMMSS 14자리 문자열 또는 ISO)
_DATE_COLUMNS = ["etd", "atd", "eta", "eta_date", "ata"]


def load_verdict_thresholds(path: Path | None = None) -> dict[str, Any]:
    target = path or VERDICT_THRESHOLDS_PATH
    with open(target, encoding="utf-8") as f:
        return json.load(f)


def _parse_dt(value: Any) -> pd.Timestamp | None:
    """bl_info 날짜 파싱 — 14자리(YYYYMMDDHHMMSS) 우선, ISO 등은 일반 파싱."""
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        return None if pd.isna(value) else value
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if not text:
        return None
    if len(text) >= 14 and text[:14].isdigit():
        ts = pd.to_datetime(text[:14], format="%Y%m%d%H%M%S", errors="coerce")
        if not pd.isna(ts):
            return pd.Timestamp(ts)
    ts = pd.to_datetime(text, errors="coerce")
    if pd.isna(ts):
        return None
    return pd.Timestamp(ts)


def _days(delta: pd.Timedelta) -> float:
    """Timedelta → 일 (시각부가 있으면 소수로 유지)."""
    return delta.total_seconds() / 86400.0


def _month_key(ts: pd.Timestamp) -> str:
    return f"{ts.year:04d}-{ts.month:02d}"


def _month_window(today: date, months: int) -> set[str]:
    """당월 포함 최근 months개월 키 집합 (ATA 월 귀속용)."""
    cursor = today.replace(day=1)
    keys: list[str] = []
    for _ in range(months):
        keys.insert(0, _month_key(pd.Timestamp(cursor)))
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    return set(keys)


def _norm_text(value: Any) -> str:
    return str(value or "").strip()


def _carrier_key(row: dict[str, Any]) -> tuple[str, str]:
    """(그룹 키, 표시명). carrier_cd → carrier_nm → UNMAPPED 순."""
    code = _norm_text(row.get("carrier_cd")).upper()
    name = _norm_text(row.get("carrier_nm"))
    if code:
        return code, name or code
    if name:
        normalized = " ".join(name.split()).upper()
        return normalized, name
    return "UNMAPPED", "미매핑"


def dedup_bl_info(info_df: pd.DataFrame) -> list[dict[str, Any]]:
    """(cmpy_cd, plnt_cd, trpr_no, hbl_no) 단위 중복 제거.

    bl_info는 PO/품목 분할로 같은 운송이 여러 행일 수 있다.
    첫 행을 기본으로 하고 날짜 등 지정 컬럼은 첫 비null 값으로 채운다.
    """
    if info_df is None or info_df.empty:
        return []
    dedup: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for row in info_df.to_dict(orient="records"):
        key = (
            _norm_text(row.get("cmpy_cd")),
            _norm_text(row.get("plnt_cd")),
            _norm_text(row.get("trpr_no")),
            _norm_text(row.get("hbl_no")),
        )
        if key not in dedup:
            dedup[key] = dict(row)
            continue
        existing = dedup[key]
        for column in _DEDUP_FILL_COLUMNS:
            if _norm_text(existing.get(column)):
                continue
            if _norm_text(row.get(column)):
                existing[column] = row.get(column)
    return list(dedup.values())


def compute_first_schedules(
    history_df: pd.DataFrame,
) -> dict[str, dict[str, dict[str, pd.Timestamp]]]:
    """운송별 최초ETD/최초ETA와 첫 기록 시각.

    반환: {transport_key: {"ETD": {"value": ts, "recorded_at": ts},
                              "ETA": {...}}}

    규칙: (cmpy_cd, plnt_cd, trpr_no, his_type)별 ins_datetime 최소 행의
    fr_date(있으면), 없으면 to_date. MIN(날짜값) 금지 — 기록 시점 기준.
    """
    out: dict[str, dict[str, dict[str, pd.Timestamp]]] = {}
    if history_df is None or history_df.empty:
        return out
    norm = normalize_schedule_history(history_df)
    if norm.empty:
        return out
    # normalize_schedule_history는 transport_key/his_type/ins_datetime
    # 오름차순 정렬을 보장하므로 그룹 첫 행이 ins_datetime 최소 행이다.
    for (tkey, htype), sub in norm.groupby(
        ["transport_key", "his_type"], sort=False,
    ):
        first = sub.iloc[0]
        value = first["fr_date"]
        if pd.isna(value):
            value = first["to_date"]
        if pd.isna(value):
            continue
        out.setdefault(str(tkey), {})[str(htype)] = {
            "value": pd.Timestamp(value),
            "recorded_at": pd.Timestamp(first["ins_datetime"]),
        }
    return out


def build_verdict(
    *,
    n: int,
    p50: float | None,
    iqr: float | None,
    tail: float | None,
    thresholds: dict[str, Any],
) -> tuple[str, str]:
    """규칙 기반 판정문. 우선순위 순 평가, 첫 매칭 적용."""
    if n < int(thresholds["min_sample"]):
        return f"표본 {n}항차. 판정 보류.", "hold"
    assert p50 is not None and iqr is not None and tail is not None
    if iqr < thresholds["iqr_tight"] and abs(p50) < thresholds["median_small_abs"]:
        return "약속을 지킵니다. 계획 그대로 써도 됩니다.", "ok"
    if iqr < thresholds["iqr_tight"] and p50 >= thresholds["median_late"]:
        return (
            f"늘 늦지만 꾸준히 늦습니다. {round(p50)}일 당겨 잡으면 해결됩니다.",
            "steady",
        )
    if iqr >= thresholds["iqr_volatile"]:
        return "중앙값은 좋은데 매번 다릅니다. 계획을 세울 수 없습니다.", "hot"
    if tail >= thresholds["tail_burst"]:
        return "평소엔 괜찮은데 가끔 크게 터집니다.", "warn"
    return "평범합니다. 상단 꼬리만 주시하세요.", "neutral"


def _carrier_payload(
    code: str,
    name: str,
    total_count: int,
    voyages: list[dict[str, Any]],
    thresholds: dict[str, Any],
) -> dict[str, Any]:
    n = len(voyages)
    coverage = round(n / total_count, 2) if total_count else None
    coverage_warn = (
        coverage is not None and coverage < float(thresholds["coverage_warn"])
    )
    voyage_items = [
        {
            "hbl_no": v["hbl_no"],
            "vessel_nm": v["vessel_nm"],
            "voyage_no": v["voyage_no"],
            "ata": v["ata"].strftime("%Y-%m-%d"),
            "dep_delay_days": round(v["dep_raw"], 1),
            "voyage_delta_days": round(v["voyage_raw"], 1),
            # 누적지연은 표시값 기준 출항+항해의 합으로 도출 (항등 보장)
            "cumulative_delay_days": round(
                round(v["dep_raw"], 1) + round(v["voyage_raw"], 1), 1,
            ),
        }
        for v in sorted(voyages, key=lambda x: x["ata"])
    ]
    payload: dict[str, Any] = {
        "carrier_code": code,
        "carrier_name": name,
        "voyage_count": n,
        "total_count": total_count,
        "coverage": coverage,
        "coverage_warn": coverage_warn,
        "voyages": voyage_items,
    }
    min_sample = int(thresholds["min_sample"])
    if n < min_sample:
        verdict, tone = build_verdict(
            n=n, p50=None, iqr=None, tail=None, thresholds=thresholds,
        )
        payload.update(
            {
                "p25": None,
                "p50": None,
                "p75": None,
                "p90": None,
                "iqr": None,
                "tail": None,
                "verdict": verdict,
                "verdict_tone": tone,
            }
        )
        return payload

    # 선사 정시성 통계는 항해 증감(voyage_raw) 분포 기준 — 탄착군 점과 같은
    # 지표여야 하며, 세 항 중 선사 귀책으로 비교 가능한 것은 항해 증감뿐이다.
    values = sorted(v["voyage_raw"] for v in voyages)
    p25 = round(_percentile(values, 0.25), 1)
    p50 = round(_percentile(values, 0.50), 1)
    p75 = round(_percentile(values, 0.75), 1)
    p90 = round(_percentile(values, 0.90), 1)
    # IQR/꼬리는 표시되는 분위수 값 기준으로 도출해 화면 숫자와 일치시킨다.
    iqr = round(p75 - p25, 1)
    tail = round(p90 - p50, 1)
    verdict, tone = build_verdict(
        n=n, p50=p50, iqr=iqr, tail=tail, thresholds=thresholds,
    )
    payload.update(
        {
            "p25": p25,
            "p50": p50,
            "p75": p75,
            "p90": p90,
            "iqr": iqr,
            "tail": tail,
            "verdict": verdict,
            "verdict_tone": tone,
        }
    )
    return payload


def compute_delay_decomposition(
    info_df: pd.DataFrame,
    history_df: pd.DataFrame,
    *,
    group_id: str,
    months: int = DEFAULT_MONTHS,
    today: date | None = None,
    groups: list[dict[str, Any]] | None = None,
    thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """bl_info + 이력 DataFrame → 지연 분해 집계. 외부 호출 없음(테스트 가능)."""
    if today is None:
        today = date.today()
    if groups is None:
        groups = load_route_groups()
    if thresholds is None:
        thresholds = load_verdict_thresholds()

    if group_id not in TARGET_GROUP_IDS:
        raise ValueError(f"지원하지 않는 항로 그룹: {group_id}")
    target = next(
        (g for g in groups if g.get("group_id") == group_id), None,
    )
    if target is None:
        raise ValueError(f"항로 그룹 설정 없음: {group_id}")

    available_groups = [
        {"group_id": g["group_id"], "name": g.get("name", g["group_id"])}
        for g in groups
        if g.get("group_id") in TARGET_GROUP_IDS
    ]
    available_groups.sort(
        key=lambda g: TARGET_GROUP_IDS.index(g["group_id"]),
    )

    window = _month_window(today, months)
    first = compute_first_schedules(history_df)

    # 중복 제거 → 해상(100)만 → 그룹 매칭 → ATA 월 기간 필터
    period_rows: list[dict[str, Any]] = []
    for row in dedup_bl_info(info_df):
        if _norm_text(row.get("trpr_mode")) != "100":
            continue
        if not _matches_group(row, target):
            continue
        ata = _parse_dt(row.get("ata"))
        if ata is None or _month_key(ata) not in window:
            continue
        row = dict(row)
        row["_ata"] = ata
        period_rows.append(row)

    # 유효 항차: ATD + 최초ETD + 최초ETA 모두 있는 것 (결측은 0 채움 금지)
    voyages: list[dict[str, Any]] = []
    carrier_total: dict[str, int] = {}
    carrier_name: dict[str, str] = {}
    for row in period_rows:
        code, name = _carrier_key(row)
        carrier_total[code] = carrier_total.get(code, 0) + 1
        carrier_name.setdefault(code, name)

        atd = _parse_dt(row.get("atd"))
        if atd is None:
            continue
        tkey = "|".join(
            [
                _norm_text(row.get("cmpy_cd")),
                _norm_text(row.get("plnt_cd")),
                _norm_text(row.get("trpr_no")),
            ]
        )
        schedule = first.get(tkey) or {}
        etd_rec = schedule.get("ETD")
        eta_rec = schedule.get("ETA")
        if etd_rec is None or eta_rec is None:
            continue
        ata = row["_ata"]
        first_etd = etd_rec["value"]
        first_eta = eta_rec["value"]
        dep_raw = _days(atd - first_etd)
        voyage_raw = _days((ata - atd) - (first_eta - first_etd))
        cum_raw = _days(ata - first_eta)
        voyages.append(
            {
                "carrier_code": code,
                "hbl_no": _norm_text(row.get("hbl_no")),
                "vessel_nm": _norm_text(row.get("vessel_nm")),
                "voyage_no": _norm_text(row.get("voyage_no")),
                "ata": ata,
                "atd": atd,
                "dep_raw": dep_raw,
                "voyage_raw": voyage_raw,
                "cum_raw": cum_raw,
                # ETD/ETA 첫 기록 시각 차이 (시간)
                "record_gap_hours": abs(
                    (eta_rec["recorded_at"] - etd_rec["recorded_at"]).total_seconds()
                )
                / 3600.0,
            }
        )

    total_count = len(period_rows)
    voyage_count = len(voyages)
    coverage = round(voyage_count / total_count, 2) if total_count else None
    coverage_warn = (
        coverage is not None and coverage < float(thresholds["coverage_warn"])
    )

    # 헤드라인: 출항지연·항해 증감의 중앙값을 먼저 구하고 누적지연은 합으로 도출
    if voyages:
        dep_median = round(
            _percentile(sorted(v["dep_raw"] for v in voyages), 0.5), 1,
        )
        voyage_median = round(
            _percentile(sorted(v["voyage_raw"] for v in voyages), 0.5), 1,
        )
        cumulative = round(dep_median + voyage_median, 1)
        record_gap_median: float | None = round(
            _percentile(sorted(v["record_gap_hours"] for v in voyages), 0.5),
            1,
        )
        # 모든 ATA/ATD의 시각부가 00:00:00이면 날짜 단위 원본으로 판정
        timestamps = [v["ata"] for v in voyages] + [v["atd"] for v in voyages]
        date_only = all(
            (ts.hour, ts.minute, ts.second, ts.microsecond) == (0, 0, 0, 0)
            for ts in timestamps
        )
    else:
        dep_median = None
        voyage_median = None
        cumulative = None
        record_gap_median = None
        date_only = False

    headline = {
        "dep_delay_days": dep_median,
        "voyage_delta_days": voyage_median,
        "cumulative_delay_days": cumulative,
        "voyage_count": voyage_count,
        "total_count": total_count,
        "coverage": coverage,
        "coverage_warn": coverage_warn,
        "first_record_gap_hours": record_gap_median,
        "date_only": date_only,
    }

    # 선사별 집계 — 표본 충분(중앙값 오름차순) → 표본 부족(표본 내림차순)
    by_carrier: dict[str, list[dict[str, Any]]] = {}
    for v in voyages:
        by_carrier.setdefault(v["carrier_code"], []).append(v)
    # 유효 항차가 0인 선사도 표본 부족으로 노출한다.
    for code in carrier_total:
        by_carrier.setdefault(code, [])

    carriers = [
        _carrier_payload(
            code,
            carrier_name.get(code, code),
            carrier_total.get(code, 0),
            by_carrier[code],
            thresholds,
        )
        for code in by_carrier
    ]
    min_sample = int(thresholds["min_sample"])
    carriers.sort(
        key=lambda c: (
            0 if c["voyage_count"] >= min_sample else 1,
            c["p50"] if c["p50"] is not None else 0.0,
            -c["voyage_count"],
            c["carrier_code"],
        )
    )

    notes = [
        "ATA/ATD는 항구 현지 시각일 가능성이 있어 UTC 정규화 없이 원본 그대로 집계했습니다.",
    ]
    if record_gap_median is not None:
        notes.append(
            "최초ETD/최초ETA의 첫 기록 시각 차이 중앙값 "
            f"{record_gap_median}시간"
        )
    if date_only:
        notes.append(
            "원본이 날짜 단위라 지연값이 정수로 양자화되며 "
            "IQR 0은 측정 해상도의 한계입니다."
        )
    unmapped = by_carrier.get("UNMAPPED")
    if unmapped:
        notes.append(
            f"선사 코드/명이 모두 비어 UNMAPPED로 집계된 항차 "
            f"{len(unmapped)}건이 있습니다."
        )

    return {
        "group_id": group_id,
        "group_name": target.get("name", group_id),
        "months": months,
        "available_groups": available_groups,
        "headline": headline,
        "carriers": carriers,
        "notes": notes,
    }


def _matched_transport_keys(
    info_df: pd.DataFrame,
    target: dict[str, Any],
) -> list[tuple[str, str, str]]:
    """이력 조회 대상 운송 키 — 해상 + 그룹 매칭 행의 (cmpy, plnt, trpr)."""
    keys = set()
    for row in dedup_bl_info(info_df):
        if _norm_text(row.get("trpr_mode")) != "100":
            continue
        if not _matches_group(row, target):
            continue
        trpr_no = _norm_text(row.get("trpr_no"))
        if not trpr_no:
            continue
        keys.add(
            (
                _norm_text(row.get("cmpy_cd")),
                _norm_text(row.get("plnt_cd")),
                trpr_no,
            )
        )
    return sorted(keys)


def fetch_delay_decomposition(
    *,
    group_id: str,
    months: int = DEFAULT_MONTHS,
    today: date | None = None,
) -> dict[str, Any]:
    """외부 호출 포함: bl_info + 전체 이력 조회 → 집계.

    이력은 changed_from 없이 전체를 조회한다 — 첫 기록이 조회 창보다
    과거일 수 있으므로 기간 제한을 걸면 최초값이 오염된다.
    """
    if today is None:
        today = date.today()
    if group_id not in TARGET_GROUP_IDS:
        raise ValueError(f"지원하지 않는 항로 그룹: {group_id}")
    groups = load_route_groups()
    target = next(
        (g for g in groups if g.get("group_id") == group_id), None,
    )
    if target is None:
        raise ValueError(f"항로 그룹 설정 없음: {group_id}")

    lookback_days = months * 31 + LOOKBACK_BUFFER_DAYS
    info_df = fetch_bl_info(
        etd_from=today - timedelta(days=lookback_days),
        select_columns=DELAY_SELECT_COLUMNS,
    )
    keys = _matched_transport_keys(info_df, target)
    history_df = fetch_bl_history_for_transports(keys)
    return compute_delay_decomposition(
        info_df,
        history_df,
        group_id=group_id,
        months=months,
        today=today,
        groups=groups,
    )
