"""ETA-ATA Gap 주차별 집계 (협의체장 요구).

- Gap = ATA - current_eta (일). current_eta = eta_date 우선, 없으면 eta.
  * current_eta는 '최신 계획' 기준이다. 최초 계획 대비 정확도는 변경이력(his)
    연동이 필요하며 2단계 확장 포인트로 남긴다.
- 주차: ATA(완료) 주, ISO 주차(월요일 시작). 당주는 진행 중이라 표시만 하고
  추세·경고 판정에서는 제외한다.
- 추세: 완료 주 기준 평균 Gap의 연속 증가 횟수 + 최소자승 기울기(일/주).
- 경고 레벨:
  * WARN(경고): 최근 완료 주 평균 Gap > warn_days (기본 5일)
  * WATCH(주의): 평균 Gap이 watch_consecutive주(기본 3주) 연속 증가
  * WARN이 WATCH보다 우선한다.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

from services import config_store
from services.datalake_schedule_client import fetch_bl_info
from services.leadtime_report_service import (
    _matches_group,
    _ts,
    load_route_groups,
)

logger = logging.getLogger(__name__)

# Gap 집계에 필요한 컬럼만 서버측 프로젝션
GAP_SELECT_COLUMNS = [
    "trpr_no",
    "dprt",
    "arvl",
    "stopby",
    "stopby_nm",
    "eta",
    "eta_date",
    "ata",
]

# 완료 운송(ata) 대상이라 짧은 창으로 충분 (해상 L/T + 지연 여유)
# 아래 상수들은 gap_thresholds 설정을 읽지 못할 때만 쓰는 폴터 기본값이다.
# 실제 적용값은 backend/app/data/gap_thresholds.json (config_store의
# gap_thresholds 키)에서 읽는다.
ETD_LOOKBACK_DAYS = 180

DEFAULT_WEEKS = 8
DEFAULT_WARN_DAYS = 5.0
DEFAULT_WATCH_CONSECUTIVE = 3

_DEFAULT_GAP_THRESHOLDS = {
    "warn_days": DEFAULT_WARN_DAYS,
    "watch_consecutive": DEFAULT_WATCH_CONSECUTIVE,
    "weeks": DEFAULT_WEEKS,
    "etd_lookback_days": ETD_LOOKBACK_DAYS,
}


def load_gap_thresholds() -> dict[str, Any]:
    """Gap 임계값 로드 — config_store 경유, 누락/오류 필드는 폴터 기본값."""
    try:
        data = config_store.load_config("gap_thresholds")
    except (OSError, ValueError):
        data = None
    if not isinstance(data, dict):
        return dict(_DEFAULT_GAP_THRESHOLDS)
    merged = dict(_DEFAULT_GAP_THRESHOLDS)
    for key in merged:
        if key in data:
            merged[key] = data[key]
    return merged


def _iso_week_key(ts: pd.Timestamp) -> str:
    iso = ts.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _week_keys(today: date, weeks: int) -> tuple[list[str], str]:
    """최근 weeks개 완료 주 키 + 당주 키 반환 (완료 주 오름차순)."""
    current = _iso_week_key(pd.Timestamp(today))
    keys: list[str] = []
    cursor = pd.Timestamp(today)
    for _ in range(weeks):
        cursor = cursor - timedelta(days=7)
        keys.insert(0, _iso_week_key(cursor))
    return keys, current


def _consecutive_increases(values: list[float]) -> int:
    """최신 주부터 거슬러 올라가며 연속 증가 횟수 (증가가 끊기면 종료)."""
    count = 0
    for i in range(len(values) - 1, 0, -1):
        if values[i] > values[i - 1]:
            count += 1
        else:
            break
    return count


def _slope(values: list[float]) -> float:
    """최소자승 기울기 (일/주). 표본 2개 미만이면 0."""
    n = len(values)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(values) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom == 0:
        return 0.0
    return round(
        sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values)) / denom, 2,
    )


def _level_of(
    latest_avg: float | None,
    consecutive: int,
    warn_days: float,
    watch_consecutive: int,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    level = "OK"
    if consecutive >= watch_consecutive:
        level = "WATCH"
        reasons.append(f"평균 Gap {consecutive}주 연속 증가")
    if latest_avg is not None and latest_avg > warn_days:
        level = "WARN"
        reasons.append(f"최근 주 평균 Gap {latest_avg}일 > 기준 {warn_days}일")
    return level, reasons


def _weekly_stats(series: dict[str, list[float]], week_keys: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for key in week_keys:
        gaps = series.get(key)
        if not gaps:
            out.append({"week": key, "count": 0})
            continue
        delayed = sum(1 for g in gaps if g > 0)
        out.append(
            {
                "week": key,
                "avg_gap": round(sum(gaps) / len(gaps), 1),
                "count": len(gaps),
                "delayed_count": delayed,
                "delayed_ratio": round(delayed / len(gaps), 2),
            }
        )
    return out


def compute_eta_ata_gap(
    info_df: pd.DataFrame,
    *,
    weeks: int | None = None,
    today: date | None = None,
    groups: list[dict[str, Any]] | None = None,
    warn_days: float | None = None,
    watch_consecutive: int | None = None,
) -> dict[str, Any]:
    """bl_info DataFrame → 주차별 Gap 집계. 외부 호출 없음(테스트 가능).

    weeks/warn_days/watch_consecutive 미지정 시 gap_thresholds 설정값 사용.
    """
    thresholds = load_gap_thresholds()
    if weeks is None:
        weeks = int(thresholds["weeks"])
    if warn_days is None:
        warn_days = float(thresholds["warn_days"])
    if watch_consecutive is None:
        watch_consecutive = int(thresholds["watch_consecutive"])
    if today is None:
        today = date.today()
    if groups is None:
        groups = load_route_groups()

    completed_keys, current_key = _week_keys(today, weeks)
    all_week_keys = [*completed_keys, current_key]

    # series[group_id][week_key] = [gap, ...] — "ALL"은 그룹 매칭 전체 합산
    series: dict[str, dict[str, list[float]]] = {}

    if info_df is not None and not info_df.empty:
        for row in info_df.to_dict(orient="records"):
            ata = _ts(row.get("ata"))
            if ata is None:
                continue
            eta = _ts(row.get("eta_date")) or _ts(row.get("eta"))
            if eta is None:
                continue
            gap = (ata - eta).days
            week = _iso_week_key(ata)
            if week not in all_week_keys:
                continue
            matched = [g for g in groups if _matches_group(row, g)]
            if not matched:
                continue
            series.setdefault("ALL", {}).setdefault(week, []).append(float(gap))
            for g in matched:
                series.setdefault(g["group_id"], {}).setdefault(
                    week, [],
                ).append(float(gap))

    def _summary(group_id: str) -> dict[str, Any]:
        weekly = _weekly_stats(series.get(group_id, {}), all_week_keys)
        # 완료 주만 추세 판정 (데이터 있는 주만)
        completed_values = [
            w["avg_gap"]
            for w in weekly
            if w["week"] in completed_keys and w.get("count")
        ]
        consecutive = _consecutive_increases(completed_values)
        latest_avg = completed_values[-1] if completed_values else None
        level, reasons = _level_of(
            latest_avg, consecutive, warn_days, watch_consecutive,
        )
        return {
            "weekly": weekly,
            "latest_avg_gap": latest_avg,
            "consecutive_increases": consecutive,
            "slope_per_week": _slope(completed_values),
            "level": level,
            "level_reasons": reasons,
        }

    group_payloads = [
        {
            "group_id": g["group_id"],
            "name": g["name"],
            "region": str(g.get("region") or ""),
            **_summary(g["group_id"]),
        }
        for g in groups
    ]

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "params": {
            "weeks": weeks,
            "warn_days": warn_days,
            "watch_consecutive": watch_consecutive,
            "current_week": current_key,
        },
        "definitions": {
            "gap": "Gap = ATA - current_eta (일). current_eta = eta_date 우선, 없으면 eta (최신 계획 기준)",
            "week_basis": "주차 = ATA 완료 주 (ISO, 월요일 시작). 당주는 진행 중으로 추세 판정 제외",
            "level": "경고: 최근 완료 주 평균 Gap > 기준일수 / 주의: 평균 Gap N주 연속 증가",
        },
        "overall": _summary("ALL"),
        "groups": group_payloads,
    }


def fetch_eta_ata_gap(*, weeks: int | None = None) -> dict[str, Any]:
    """외부 호출 포함: bl_info 조회 → 집계.

    weeks 미지정 시 gap_thresholds 설정의 weeks/etd_lookback_days를 쓴다.
    """
    thresholds = load_gap_thresholds()
    if weeks is None:
        weeks = int(thresholds["weeks"])
    info_df = fetch_bl_info(
        etd_from=date.today() - timedelta(
            days=int(thresholds["etd_lookback_days"]),
        ),
        select_columns=GAP_SELECT_COLUMNS,
    )
    return compute_eta_ata_gap(info_df, weeks=weeks)
