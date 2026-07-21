"""B-LAP 실데이터 기반 품목별 도착 물량 집계 (L2 수급 시뮬레이션 입력).

bl_info는 PO 품목 라인 단위(item_cd/item_nm/dlvy_qty/hbl_no)이고,
운송의 현재·최초 ETA는 스냅샷+이력 메트릭이 제공한다. 둘을 transport_key로
조인해 품목(item_cd)별 도착 물량을 집계한다.

주의: 이 모듈의 외부 호출(fetch_bl_info/fetch_bl_history_for_transports)은
읽기 전용이며, inventory_sim.simulate()의 입력 형식을 만들 뿐이다.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import pandas as pd

from services.datalake_schedule_client import (
    fetch_bl_history_for_transports,
    fetch_bl_info,
)
from services.schedule_history_service import (
    build_schedule_metrics,
    build_transport_snapshot,
)

logger = logging.getLogger(__name__)

# 조회 범위 (api_server 대시보드 기본값과 유사하게 보수적으로 설정)
ETD_LOOKBACK_DAYS = 45
HISTORY_LOOKBACK_DAYS = 90


def _iso_date(value: Any) -> str | None:
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return None
    return ts.date().isoformat()


def aggregate_item_arrivals(
    info_df: pd.DataFrame,
    metrics_df: pd.DataFrame,
) -> list[dict[str, Any]]:
    """bl_info 품목 라인 × 운송 메트릭 조인 → item_cd별 도착 물량 집계.

    - transport_key = cmpy_cd|plnt_cd|trpr_no (schedule_history_service 규칙)
    - metrics에 없는 운송(비활성/완료)과 ETA가 없는 운송은 제외
    - qty는 동일 선적(transport) 내 동일 품목 합산
    """
    if info_df is None or info_df.empty:
        return []

    df = info_df.copy()
    for col in ("cmpy_cd", "plnt_cd", "trpr_no", "item_cd", "item_nm", "dlvy_unit", "hbl_no"):
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str).str.strip()
    df["dlvy_qty"] = pd.to_numeric(df.get("dlvy_qty"), errors="coerce").fillna(0)
    df = df[(df["item_cd"] != "") & (df["trpr_no"] != "")].copy()
    if df.empty:
        return []
    df["transport_key"] = df["cmpy_cd"] + "|" + df["plnt_cd"] + "|" + df["trpr_no"]

    metrics_by_key: dict[str, dict[str, Any]] = {}
    if metrics_df is not None and not metrics_df.empty:
        for row in metrics_df.to_dict(orient="records"):
            metrics_by_key[str(row.get("transport_key") or "")] = row

    items: dict[str, dict[str, Any]] = {}
    for (item_cd, tkey), group in df.groupby(["item_cd", "transport_key"], sort=False):
        metrics = metrics_by_key.get(str(tkey))
        if metrics is None:
            continue  # 비활성 운송
        eta_current = _iso_date(metrics.get("eta_current")) or _iso_date(metrics.get("current_eta"))
        if not eta_current:
            continue  # ETA 미확정 운송은 곡선 계산 불가
        eta_plan = _iso_date(metrics.get("eta_initial")) or eta_current

        first = group.iloc[0]
        shipment_id = (
            str(metrics.get("hbl_no") or "").strip()
            or str(first["hbl_no"] or "").strip()
            or str(metrics.get("trpr_no") or "").strip()
            or str(tkey).split("|")[-1]
        )

        item = items.setdefault(
            str(item_cd),
            {
                "item_id": str(item_cd),
                "name": str(first["item_nm"] or item_cd),
                "unit": str(first["dlvy_unit"] or "units"),
                "shipments": [],
            },
        )
        if not item["name"] and first["item_nm"]:
            item["name"] = str(first["item_nm"])
        item["shipments"].append(
            {
                "shipment_id": shipment_id,
                "vessel_name": str(metrics.get("vessel_name") or ""),
                "qty": int(group["dlvy_qty"].sum()),
                "eta_plan": eta_plan,
                "eta_current": eta_current,
            }
        )
    return list(items.values())


def fetch_item_arrivals() -> list[dict[str, Any]]:
    """외부 호출 파이프라인: bl_info → 스냅샷 → 이력 → 메트릭 → 품목 집계."""
    info_df = fetch_bl_info(etd_from=date.today() - timedelta(days=ETD_LOOKBACK_DAYS))
    snapshot_df = build_transport_snapshot(info_df, active_only=True)
    if snapshot_df.empty:
        logger.info("B-LAP 활성 운송 없음 — 도착 물량 0건")
        return []

    transport_keys = [
        (
            str(row.get("cmpy_cd") or ""),
            str(row.get("plnt_cd") or ""),
            str(row.get("trpr_no") or ""),
        )
        for row in snapshot_df.to_dict(orient="records")
    ]
    history_df = fetch_bl_history_for_transports(
        transport_keys,
        changed_from=date.today() - timedelta(days=HISTORY_LOOKBACK_DAYS),
    )
    metrics_df = build_schedule_metrics(snapshot_df, history_df)

    items = aggregate_item_arrivals(info_df, metrics_df)
    logger.info("B-LAP 품목 도착 집계: %d품목", len(items))
    return items
