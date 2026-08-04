"""항로별 리드타임 리포트 자동 집계 (B-LAP bl_info 기반).

L/T 정의 (사용자 검증 대상 — 변경 시 이 주석과 응답의 definitions를 함께 수정):
- 집계 대상: cargo_type3 == 'FCL' 인 행만 (컨테이너 전적 — LCL 등 제외)
  + 해상(sea) 그룹은 운송모드 해상(trpr_mode == '100')만 — 육상(200)·
    Rail+Truck(300) 등 제외. 모드 미기재는 FCL이므로 해상으로 간주해 포함.
    내륙(inland) 그룹은 row_groups의 trpr_mode 코드가 자체 판별한다.
- 월 그룹핑(해상): onboard_date의 월 (없으면 atd의 월)
- 실적(actual) 해상 L/T: ata - onboard_date (onboard_date 없으면 ata - atd), 일 단위
  * 완료 운송(ata 존재)만 집계. onboard 월 기준으로 귀속.
- 예상(forecast) 해상 L/T: 진행 중 운송(ata 없음)의 current_eta 기준
  * current_eta = eta_date 우선, 없으면 eta
  * L/T = current_eta - onboard_date (없으면 atd, 그래도 없으면 etd)
  * 도착 예정월(current_eta의 월) 열에 귀속
- 내륙 L/T (metric == 'inland' 그룹, "항만 출발 / 생산 거점 도착" 표):
  * 실적 = dlvy_ata - ata, ata(입항) 월 기준 귀속
  * 예상 = dlvy_eta - current_eta, dlvy_eta 월 기준 귀속
- 총 L/T = Cargo Cut-Off + 해상 L/T + 내륙 L/T.
- 아웃라이어 제외: 월별 버킷별로 IQR(사분위 범위) 방식 적용 — 머신러닝 전처리의
  표준 기법. [Q1 - 1.5×IQR, Q3 + 1.5×IQR] 범위를 벗어나는 극단값만 제거하므로
  미주 동안 55일처럼 정상적인 장기 L/T는 유지된다. 표본 4개 미만 버킷은 제거하지 않음.

항로 그룹핑은 backend/app/data/leadtime_route_groups.json 설정으로 정의한다.
그룹 스키마 v2:
- region: 권역 헤더 (유럽/미주/아시아 등) — 프런트 섹션 구분용
- metric: sea(기본) | inland
- countries / country_labels: 국가 행 구성과 라벨 재정의 (기본 KR/CN/JP)
- row_groups: 국가 대신 커스텀 행 구분 (예: 선적구분, 출발항만, 운송방식)
  [{"row_id", "label", "field": 임의 bl_info 컬럼(dprt/arvl/trpr_mode 등), "codes": [...]}]
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from services.datalake_schedule_client import fetch_bl_info

logger = logging.getLogger(__name__)

ROUTE_GROUPS_PATH = (
    Path(__file__).resolve().parents[1]
    / "backend" / "app" / "data" / "leadtime_route_groups.json"
)

# 실적 조회 범위 (완료 운송 포함, 넓은 기간)
ETD_LOOKBACK_DAYS = 400

# 리드타임 집계에 필요한 컬럼만 서버측 프로젝션 ($select) — 전체 88컬럼을
# 받으면 2만 행 × 88컬럼 JSON이 수백 MB가 되어 "집계중" 장기화의 원인이 된다.
LEADTIME_SELECT_COLUMNS = [
    "trpr_no",
    "dprt",
    "arvl",
    "stopby",
    "stopby_nm",
    "cargo_type3",
    "trpr_mode",
    "onboard_date",
    "etd",
    "atd",
    "eta",
    "eta_date",
    "ata",
    "dlvy_eta",
    "dlvy_ata",
]

# dprt 접두 → 국가 판별용 (행 구성은 그룹의 countries 설정이 결정)
KNOWN_COUNTRY_PREFIXES = ["KR", "CN", "JP", "ID", "PL"]
COUNTRY_ORDER = ["KR", "CN", "JP"]
COUNTRY_LABELS = {
    "KR": "한국",
    "CN": "중국",
    "JP": "일본",
    "ID": "인도네시아",
    "PL": "북유럽",
}
STAT_ORDER = ["Avg", "Min", "Max"]
MONTH_LABELS = [
    "Jan.", "Feb.", "Mar.", "Apr.", "May.", "Jun.",
    "Jul.", "Aug.", "Sep.", "Oct.", "Nov.", "Dec.",
]

DEFINITIONS = {
    "total_lt": "총 L/T = Cargo Cut-Off + 해상 L/T + 내륙 L/T",
    "scope": "집계 대상: cargo_type3 == 'FCL' (컨테이너 전적) 운송만",
    "sea_mode": "해상 표는 운송모드 해상(trpr_mode 100)만 집계 — 육상(200)·Rail+Truck(300) 등 제외 (모드 미기재는 FCL 기준 해상 간주)",
    "fixed_rows": "'고정값' 표시 행은 실데이터 집계가 아닌 사용자 제공 고정값 (훼리 등 spot성 구간)",
    "actual_lt": "실적 해상 L/T = ata - onboard_date (onboard_date 없으면 atd), 일 단위",
    "forecast_lt": "예상 해상 L/T = current_eta - onboard_date (없으면 atd, 그래도 없으면 etd)",
    "inland_lt": "내륙 L/T(항만 출발/생산 거점 도착 표): 실적 = dlvy_ata - ata, 예상 = dlvy_eta - current_eta",
    "month_basis": "월 그룹핑 = onboard_date 월 (없으면 atd 월), 내륙은 ata 월",
    "source": "각 월의 SK 화물 On-board 선사·모선의 운송 소요 시간(B-LAP bl_info)",
    "outlier": "아웃라이어 제외: 월별 항로 집계에서 IQR 방식(Q1-1.5×IQR ~ Q3+1.5×IQR)으로 극단값만 제거 (표본 4건 미만은 제거 안 함)",
}


def load_route_groups(path: Path | None = None) -> list[dict[str, Any]]:
    target = path or ROUTE_GROUPS_PATH
    with open(target, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("groups", [])


def _ts(value: Any) -> pd.Timestamp | None:
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return None
    return pd.Timestamp(ts)


def _month_key(ts: pd.Timestamp) -> str:
    return f"{ts.year:04d}-{ts.month:02d}"


def _country_of(dprt: str) -> str | None:
    code = (dprt or "").strip().upper()
    for country in KNOWN_COUNTRY_PREFIXES:
        if code.startswith(country):
            return country
    return None


def _code_match(code: str, patterns: list[str]) -> bool:
    """코드 매칭 — 패턴 끝의 '*'는 접두 와일드카드 (예: 'KR*')."""
    code = code.strip().upper()
    for pattern in patterns:
        p = str(pattern).strip().upper()
        if p.endswith("*"):
            if code.startswith(p[:-1]):
                return True
        elif code == p:
            return True
    return False


def _matches_group(row: dict[str, Any], group: dict[str, Any]) -> bool:
    arvl = str(row.get("arvl") or "")
    if not _code_match(arvl, group.get("arvl_codes", [])):
        return False
    dprt_codes = group.get("dprt_codes", [])
    if dprt_codes and not _code_match(str(row.get("dprt") or ""), dprt_codes):
        return False
    tokens = [t.upper() for t in group.get("stopby_match", [])]
    if not tokens:
        return True
    haystack = (
        str(row.get("stopby") or "") + "|" + str(row.get("stopby_nm") or "")
    ).upper()
    excluded = [t.upper() for t in group.get("stopby_exclude", [])]
    if any(t in haystack for t in excluded):
        return False
    return any(t in haystack for t in tokens)


def _percentile(sorted_values: list[float], p: float) -> float:
    """선형 보간 백분위 (numpy 기본 방식과 동일). sorted_values는 정렬된 상태."""
    n = len(sorted_values)
    pos = (n - 1) * p
    lo = int(pos)
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * frac


def _iqr_filter(values: list[float]) -> list[float]:
    """IQR(사분위 범위) 방식 아웃라이어 제거 — ML 전처리의 표준 기법.

    [Q1 - 1.5×IQR, Q3 + 1.5×IQR] 범위를 벗어나는 값만 제거한다.
    표본이 4개 미만이면 사분위가 불안정하므로 그대로 반환한다.
    """
    if len(values) < 4:
        return values
    s = sorted(values)
    q1 = _percentile(s, 0.25)
    q3 = _percentile(s, 0.75)
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    return [v for v in values if lower <= v <= upper]


def _lt_point(
    row: dict[str, Any],
    onboard: pd.Timestamp | None,
    ata: pd.Timestamp | None,
    metric: str,
    actual_window: list[str],
    forecast_window: list[str],
) -> tuple[str, float, str] | None:
    """(kind, lt, month) — metric별 기준일·월 귀속이 다르다."""
    if metric == "inland":
        dlvy_ata = _ts(row.get("dlvy_ata"))
        if ata is not None and dlvy_ata is not None:
            lt = (dlvy_ata - ata).days
            month = _month_key(ata)
            if lt < 0 or month not in actual_window:
                return None
            return ("actual", float(lt), month)
        eta = _ts(row.get("eta_date")) or _ts(row.get("eta"))
        dlvy_eta = _ts(row.get("dlvy_eta"))
        if eta is None or dlvy_eta is None:
            return None
        lt = (dlvy_eta - eta).days
        month = _month_key(dlvy_eta)
        if lt < 0 or month not in forecast_window:
            return None
        return ("forecast", float(lt), month)

    # metric == "sea" (기본)
    if ata is not None and onboard is not None:
        lt = (ata - onboard).days
        month = _month_key(onboard)
        if lt < 0 or month not in actual_window:
            return None
        return ("actual", float(lt), month)
    if ata is None:
        eta = _ts(row.get("eta_date")) or _ts(row.get("eta"))
        base = onboard or _ts(row.get("etd"))
        if eta is None or base is None:
            return None
        lt = (eta - base).days
        month = _month_key(eta)
        if lt < 0 or month not in forecast_window:
            return None
        return ("forecast", float(lt), month)
    return None


def compute_leadtime_report(
    info_df: pd.DataFrame,
    *,
    months: int = 12,
    forecast_months: int = 3,
    today: date | None = None,
    groups: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """bl_info DataFrame → 리포트 구조. 외부 호출 없음(테스트 가능)."""
    if today is None:
        today = date.today()
    if groups is None:
        groups = load_route_groups()

    current_month = today.replace(day=1)
    # 실적 월 창: 최근 `months`개월 (당월 포함)
    month_cursor = current_month
    actual_window: list[str] = []
    for _ in range(months):
        actual_window.insert(0, _month_key(pd.Timestamp(month_cursor)))
        month_cursor = (month_cursor - timedelta(days=1)).replace(day=1)
    # 예상 월 창: 다음 달부터 forecast_months개월
    forecast_window: list[str] = []
    cursor = current_month
    for _ in range(forecast_months):
        cursor = (
            (cursor.replace(day=28) + timedelta(days=7)).replace(day=1)
        )
        forecast_window.append(_month_key(pd.Timestamp(cursor)))

    # buckets[group_id][row_key][month_key] = [lt, ...]  (실적)
    # forecast_buckets[group_id][row_key][month_key] = [lt, ...]  (예상)
    # row_key: 국가 코드(KR 등) 또는 row_groups의 row_id
    buckets: dict[str, dict[str, dict[str, list[float]]]] = {}
    forecast_buckets: dict[str, dict[str, dict[str, list[float]]]] = {}

    if info_df is not None and not info_df.empty:
        for row in info_df.to_dict(orient="records"):
            # FCL(컨테이너 전적)만 집계 대상
            if str(row.get("cargo_type3") or "").strip().upper() != "FCL":
                continue
            matched = [g for g in groups if _matches_group(row, g)]
            if not matched:
                continue
            onboard = _ts(row.get("onboard_date")) or _ts(row.get("atd"))
            ata = _ts(row.get("ata"))
            dprt = str(row.get("dprt") or "")
            arvl = str(row.get("arvl") or "")
            mode = str(row.get("trpr_mode") or "").strip()
            country = _country_of(dprt)

            for group in matched:
                metric = str(group.get("metric") or "sea")
                # 해상 그룹은 해상모드(100)만 — 육상(200)·Rail+Truck(300) 등 제외.
                # 모드 미기재는 FCL(해상 컨테이너)이므로 해상으로 간주해 포함.
                # 내륙 그룹은 row_groups의 trpr_mode 코드가 자체 판별하므로 게이트 없음.
                if metric == "sea" and mode and mode != "100":
                    continue
                point = _lt_point(
                    row, onboard, ata, metric, actual_window, forecast_window,
                )
                if point is None:
                    continue
                kind, lt, month = point

                row_groups = group.get("row_groups") or []
                if row_groups:
                    # 커스텀 행 구분 (선적구분/출발항만/운송방식 등) —
                    # field는 임의 bl_info 컬럼 (dprt, arvl, trpr_mode 등)
                    row_keys = [
                        rg["row_id"]
                        for rg in row_groups
                        if _code_match(
                            str(row.get(rg.get("field", "dprt")) or ""),
                            rg.get("codes", []),
                        )
                    ]
                else:
                    if country is None:
                        continue
                    row_keys = [country]
                if not row_keys:
                    continue

                source = buckets if kind == "actual" else forecast_buckets
                for key in row_keys:
                    source.setdefault(group["group_id"], {}).setdefault(
                        key, {}
                    ).setdefault(month, []).append(lt)

    def _cells(source: dict[str, dict[str, list[float]]], group_id: str,
               row_key: str, stat: str) -> dict[str, float]:
        out: dict[str, float] = {}
        for month, values in source.get(group_id, {}).get(row_key, {}).items():
            values = _iqr_filter(values)
            if not values:
                continue
            if stat == "Avg":
                out[month] = round(sum(values) / len(values), 1)
            elif stat == "Min":
                out[month] = round(min(values), 1)
            else:
                out[month] = round(max(values), 1)
        return out

    # 월 열 확정 (실적/예상 데이터가 있는 월만)
    used_months: dict[str, str] = {}
    for source, kind in ((buckets, "actual"), (forecast_buckets, "forecast")):
        for row_keys in source.values():
            for months_map in row_keys.values():
                for key in months_map:
                    used_months[key] = kind

    def _sort_key(key: str) -> tuple[int, int]:
        year, month = key.split("-")
        return (int(year), int(month))

    month_columns = [
        {
            "key": key,
            "label": MONTH_LABELS[int(key.split("-")[1]) - 1],
            "kind": used_months[key],
        }
        for key in sorted(used_months, key=_sort_key)
    ]

    group_payloads = []
    for group in groups:
        rows = []
        group_id = group["group_id"]
        row_groups = group.get("row_groups") or []
        if row_groups:
            # 커스텀 행 구분 그룹 — 설정 순서대로 행 방출
            for rg in row_groups:
                for stat in STAT_ORDER:
                    cells = _cells(buckets, group_id, rg["row_id"], stat)
                    fcells = _cells(
                        forecast_buckets, group_id, rg["row_id"], stat,
                    )
                    rows.append(
                        {
                            "country": rg["row_id"],
                            "country_label": rg.get("label", rg["row_id"]),
                            "stat": stat,
                            "cells": {**cells, **fcells},
                        }
                    )
        else:
            countries = group.get("countries") or COUNTRY_ORDER
            labels = {**COUNTRY_LABELS, **(group.get("country_labels") or {})}
            for country in countries:
                for stat in STAT_ORDER:
                    cells = _cells(buckets, group_id, country, stat)
                    fcells = _cells(forecast_buckets, group_id, country, stat)
                    rows.append(
                        {
                            "country": country,
                            "country_label": labels.get(country, country),
                            "stat": stat,
                            "cells": {**cells, **fcells},
                        }
                    )
        # 고정 행 주입 (사용자 제공 고정값 — 실데이터 집계 없이 모든 월 열 동일 값)
        for fixed in group.get("fixed_rows", []):
            values = fixed.get("values", {})
            for stat in STAT_ORDER:
                rows.append(
                    {
                        "country": fixed.get("country", "FIXED"),
                        "country_label": fixed.get("country_label", "고정값"),
                        "stat": stat,
                        "cells": {
                            col["key"]: values.get(stat)
                            for col in month_columns
                            if values.get(stat) is not None
                        },
                        "fixed": True,
                        "fixed_note": fixed.get("note", ""),
                    }
                )
        group_payloads.append(
            {
                "group_id": group_id,
                "name": group["name"],
                "region": str(group.get("region") or ""),
                "metric": str(group.get("metric") or "sea"),
                "row_label": str(group.get("row_label") or "국가"),
                "rows": rows,
            }
        )

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": "B-LAP bl_info",
        "definitions": DEFINITIONS,
        "month_columns": month_columns,
        "groups": group_payloads,
    }


def fetch_leadtime_report(
    *,
    months: int = 12,
    forecast_months: int = 3,
) -> dict[str, Any]:
    """외부 호출 포함: bl_info 조회 → 집계.

    리드타임(실적 ata-onboard, 예상 current_eta-base)은 bl_info만으로
    계산 가능하므로 history 조회는 하지 않는다.
    """
    info_df = fetch_bl_info(
        etd_from=date.today() - timedelta(days=ETD_LOOKBACK_DAYS),
        select_columns=LEADTIME_SELECT_COLUMNS,
    )
    return compute_leadtime_report(
        info_df, months=months, forecast_months=forecast_months
    )
