"""VDT_INB_BL_INFO Snapshot과 VDT_INB_BL_HIS 이력을 운송번호 단위 일정 지표로 변환."""
from __future__ import annotations

from typing import Any, Optional
import pandas as pd

TRANSPORT_KEY_COLUMNS = ["cmpy_cd", "plnt_cd", "trpr_no"]


def _first_non_null(series: pd.Series) -> Any:
    for value in series.dropna():
        if str(value).strip():
            return value
    return None


def _unique_join(series: pd.Series) -> str:
    values = {str(v).strip() for v in series.dropna() if str(v).strip()}
    return ", ".join(sorted(values))


def _safe_numeric_sum(series: pd.Series) -> float:
    numeric = pd.to_numeric(series, errors="coerce")
    return float(numeric.sum()) if not numeric.dropna().empty else 0.0


def _coalesce_datetime(*values: Any) -> pd.Timestamp:
    for value in values:
        parsed = pd.to_datetime(value, errors="coerce")
        if not pd.isna(parsed):
            return parsed
    return pd.NaT


def _min_datetime(series: pd.Series) -> pd.Timestamp:
    """그룹 내 파싱 가능한 일시 중 가장 이른 값 (없으면 NaT)."""
    parsed = pd.to_datetime(series, errors="coerce").dropna()
    if parsed.empty:
        return pd.NaT
    return parsed.min()


def _series(group: pd.DataFrame, column: str) -> pd.Series:
    return group[column] if column in group.columns else pd.Series(dtype=object)


def build_transport_snapshot(info_df: pd.DataFrame, *, active_only: bool = True) -> pd.DataFrame:
    if "trpr_no" not in info_df.columns:
        raise ValueError("선적 Snapshot 필수 컬럼 누락: trpr_no")

    df = info_df.copy()
    for column in TRANSPORT_KEY_COLUMNS:
        if column not in df.columns:
            df[column] = ""
        df[column] = df[column].fillna("").astype(str).str.strip()
    df = df[df["trpr_no"] != ""].copy()

    records: list[dict[str, Any]] = []
    for key, group in df.groupby(TRANSPORT_KEY_COLUMNS, dropna=False, sort=False):
        cmpy_cd, plnt_cd, trpr_no = [str(v).strip() for v in key]
        eta_date = _first_non_null(_series(group, "eta_date"))
        eta_raw = _first_non_null(_series(group, "eta"))
        ata_raw = _first_non_null(_series(group, "ata"))
        cmpl_yn = str(_first_non_null(_series(group, "cmpl_yn")) or "").strip().upper()
        current_eta = _coalesce_datetime(eta_date, eta_raw)
        actual_ata = _coalesce_datetime(ata_raw)
        completed = cmpl_yn == "Y" or not pd.isna(actual_ata)

        record = {
            "transport_key": f"{cmpy_cd}|{plnt_cd}|{trpr_no}",
            "cmpy_cd": cmpy_cd,
            "cmpy_nm": _first_non_null(_series(group, "cmpy_nm")),
            "plnt_cd": plnt_cd,
            "plnt_nm": _first_non_null(_series(group, "plnt_nm")),
            "trpr_no": trpr_no,
            "trpr_mode": _first_non_null(_series(group, "trpr_mode")),
            "hbl_no": _unique_join(_series(group, "hbl_no")),
            "mbl_no": _unique_join(_series(group, "mbl_no")),
            "container_no": _unique_join(_series(group, "cntr_no")),
            "po_list": _unique_join(_series(group, "po_no")),
            "item_list": _unique_join(_series(group, "item_cd")),
            "po_count": _series(group, "po_no").dropna().astype(str).nunique(),
            "item_count": _series(group, "item_cd").dropna().astype(str).nunique(),
            "quantity_sum": _safe_numeric_sum(_series(group, "dlvy_qty")),
            "quantity_unit": _first_non_null(_series(group, "dlvy_unit")),
            "pol": _first_non_null(_series(group, "dprt")),
            "pol_name": _first_non_null(_series(group, "dprt_nm")),
            "pod": _first_non_null(_series(group, "arvl")),
            "pod_name": _first_non_null(_series(group, "arvl_nm")),
            "final_pod": _first_non_null(_series(group, "final_pod")),
            "final_pod_name": _first_non_null(_series(group, "final_pod_nm")),
            "vessel_name": _first_non_null(_series(group, "vessel_nm")),
            "voyage_no": _first_non_null(_series(group, "voyage_no")),
            "carrier_name": _first_non_null(_series(group, "carrier_nm")),
            "lsp_name": _first_non_null(_series(group, "lsp_nm")),
            "stopby": _first_non_null(_series(group, "stopby")),
            "stopby_name": _first_non_null(_series(group, "stopby_nm")),
            "current_etd": _coalesce_datetime(_first_non_null(_series(group, "etd"))),
            "actual_atd": _coalesce_datetime(_first_non_null(_series(group, "atd"))),
            "current_eta": current_eta,
            "actual_ata": actual_ata,
            # 운송 내 PO 라인이 여러 개면 가장 이른 납품 요청일을 대표로
            # 사용한다 (보수적 판정 — 가장 빠른 납기를 먼저 넘는지 본다).
            "delivery_request_date": _min_datetime(_series(group, "dlvy_req_date")),
            "delivery_eta": _coalesce_datetime(_first_non_null(_series(group, "dlvy_eta"))),
            "completed": completed,
            "cmpl_yn": cmpl_yn,
            "source_row_count": len(group),
        }
        records.append(record)

    snapshot = pd.DataFrame(records)
    if active_only and not snapshot.empty:
        snapshot = snapshot[~snapshot["completed"]].copy()
    return snapshot.reset_index(drop=True)



def normalize_schedule_history(
    history_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    VDT_INB_BL_HIS를 ETD/ETA 변경행으로 정규화한다.

    fr_date가 비어 있고 to_date만 있는 행은 최초 일정 등록행으로
    유지한다. 기존 코드처럼 fr_date 누락행을 삭제하면 최초 일정과
    일부 법인의 Timeline이 모두 0으로 보일 수 있다.
    """
    required = {
        "cmpy_cd",
        "plnt_cd",
        "trpr_no",
        "his_type",
        "fr_date",
        "to_date",
        "ins_datetime",
    }
    missing = required - set(history_df.columns)

    if missing:
        raise ValueError(
            f"변경이력 필수 컬럼 누락: {sorted(missing)}"
        )

    df = history_df.copy()

    for column in TRANSPORT_KEY_COLUMNS:
        df[column] = (
            df[column]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    df["his_type"] = (
        df["his_type"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    # DLVY_ETA, ATD 등은 Timeline 대상이 아니다.
    df = df.loc[
        df["his_type"].isin(["ETD", "ETA"])
    ].copy()

    for column in [
        "fr_date",
        "to_date",
        "ins_datetime",
    ]:
        df[column] = pd.to_datetime(
            df[column],
            errors="coerce",
        )

    # to_date와 변경 입력시각이 있어야 Timeline 행으로 사용할 수 있다.
    # fr_date는 최초 등록행에서 비어 있을 수 있으므로 삭제하지 않는다.
    df = df.dropna(
        subset=["to_date", "ins_datetime"]
    ).copy()

    df["is_initial_record"] = df["fr_date"].isna()
    df["change_days"] = (
        df["to_date"] - df["fr_date"]
    ).dt.days

    df["is_actual_change"] = (
        df["fr_date"].notna()
        & df["change_days"].notna()
        & df["change_days"].ne(0)
    )

    df["change_direction"] = "NO_CHANGE"
    df.loc[
        df["change_days"].gt(0),
        "change_direction",
    ] = "DELAYED"
    df.loc[
        df["change_days"].lt(0),
        "change_direction",
    ] = "ADVANCED"

    df["transport_key"] = (
        df["cmpy_cd"]
        + "|"
        + df["plnt_cd"]
        + "|"
        + df["trpr_no"]
    )

    duplicate_columns = [
        "transport_key",
        "his_type",
        "his_no",
    ]
    duplicate_columns = [
        column
        for column in duplicate_columns
        if column in df.columns
    ]

    if duplicate_columns:
        df = df.drop_duplicates(
            subset=duplicate_columns,
            keep="last",
        )

    sort_columns = [
        "transport_key",
        "his_type",
        "ins_datetime",
    ]

    if "his_no" in df.columns:
        sort_columns.append("his_no")

    return df.sort_values(
        sort_columns,
        kind="stable",
    ).reset_index(drop=True)


def _first_schedule_date(
    subset: pd.DataFrame,
) -> pd.Timestamp:
    """
    최초 실제 변경의 fr_date를 우선 사용한다.
    실제 변경이 하나도 없으면 최초 등록행의 to_date를 사용한다.
    """
    if subset.empty:
        return pd.NaT

    previous_dates = subset["fr_date"].dropna()
    if not previous_dates.empty:
        return pd.to_datetime(
            previous_dates.iloc[0],
            errors="coerce",
        )

    revised_dates = subset["to_date"].dropna()
    if not revised_dates.empty:
        return pd.to_datetime(
            revised_dates.iloc[0],
            errors="coerce",
        )

    return pd.NaT


def _schedule_stats(
    history: pd.DataFrame,
    schedule_type: str,
    current_date: pd.Timestamp,
    recent_from: pd.Timestamp,
) -> dict[str, Any]:
    """
    ETD 또는 ETA 변경이력 통계를 계산한다.

    이력이 없는 운송건에서는 빈 object Series를 DataFrame 인덱서로 사용하면
    pandas가 boolean mask가 아닌 컬럼 선택으로 해석할 수 있다. 그 결과
    actual DataFrame의 컬럼이 사라져 change_days KeyError가 발생할 수 있으므로,
    빈 이력을 먼저 처리하고 명시적인 bool mask + .loc를 사용한다.
    """
    prefix = schedule_type.lower()

    empty_result = {
        f"{prefix}_initial": pd.NaT,
        f"{prefix}_current": current_date if not pd.isna(current_date) else pd.NaT,
        f"{prefix}_change_count": 0,
        f"{prefix}_delay_count": 0,
        f"{prefix}_delay_count_recent": 0,
        f"{prefix}_advance_count": 0,
        f"{prefix}_gross_delay_days": 0,
        f"{prefix}_net_delay_days": None,
        f"{prefix}_last_change_at": pd.NaT,
    }

    required_columns = {
        "his_type",
        "fr_date",
        "to_date",
        "ins_datetime",
        "change_days",
        "is_actual_change",
    }
    if history.empty or not required_columns.issubset(history.columns):
        return empty_result

    subset = history.loc[history["his_type"].eq(schedule_type)].copy()
    if subset.empty:
        return empty_result

    actual_mask = subset["is_actual_change"].fillna(False).astype(bool)
    actual = subset.loc[actual_mask].copy()

    initial_date = _first_schedule_date(subset)
    latest_history_date = subset.iloc[-1]["to_date"]
    effective_current = (
        current_date if not pd.isna(current_date) else latest_history_date
    )

    delayed_mask = actual["change_days"].fillna(0).gt(0)
    advanced_mask = actual["change_days"].fillna(0).lt(0)

    all_delays = actual.loc[delayed_mask].copy()
    all_advances = actual.loc[advanced_mask].copy()
    recent_delays = actual.loc[
        delayed_mask & actual["ins_datetime"].ge(recent_from)
    ].copy()

    net_delay_days: Optional[int] = None
    if not pd.isna(initial_date) and not pd.isna(effective_current):
        net_delay_days = int((effective_current - initial_date).days)

    return {
        f"{prefix}_initial": initial_date,
        f"{prefix}_current": effective_current,
        f"{prefix}_change_count": int(len(actual)),
        f"{prefix}_delay_count": int(len(all_delays)),
        f"{prefix}_delay_count_recent": int(len(recent_delays)),
        f"{prefix}_advance_count": int(len(all_advances)),
        f"{prefix}_gross_delay_days": (
            int(all_delays["change_days"].sum())
            if not all_delays.empty
            else 0
        ),
        f"{prefix}_net_delay_days": net_delay_days,
        f"{prefix}_last_change_at": (
            actual["ins_datetime"].max()
            if not actual.empty
            else pd.NaT
        ),
    }


def build_schedule_metrics(snapshot_df: pd.DataFrame, history_df: pd.DataFrame, *, recent_window_days: int = 14, now: Optional[pd.Timestamp] = None) -> pd.DataFrame:
    if snapshot_df.empty:
        return pd.DataFrame()
    normalized = normalize_schedule_history(history_df) if not history_df.empty else pd.DataFrame(
        columns=["transport_key", "his_type", "fr_date", "to_date", "ins_datetime", "change_days", "is_actual_change"]
    )
    current_time = pd.Timestamp(now) if now is not None else pd.Timestamp.now()
    recent_from = current_time - pd.Timedelta(days=recent_window_days)
    history_groups = {key: group for key, group in normalized.groupby("transport_key")}
    records: list[dict[str, Any]] = []

    for _, transport in snapshot_df.iterrows():
        record = transport.to_dict()
        history = history_groups.get(str(record["transport_key"]), pd.DataFrame(columns=normalized.columns))
        record.update(_schedule_stats(history, "ETD", pd.to_datetime(record.get("current_etd"), errors="coerce"), recent_from))
        record.update(_schedule_stats(history, "ETA", pd.to_datetime(record.get("current_eta"), errors="coerce"), recent_from))

        initial_etd, initial_eta = record.get("etd_initial"), record.get("eta_initial")
        current_etd, current_eta = record.get("etd_current"), record.get("eta_current")
        actual_atd = pd.to_datetime(record.get("actual_atd"), errors="coerce")
        actual_ata = pd.to_datetime(record.get("actual_ata"), errors="coerce")

        planned_lt = int((initial_eta - initial_etd).days) if not pd.isna(initial_etd) and not pd.isna(initial_eta) else None
        projected_lt = int((current_eta - current_etd).days) if not pd.isna(current_etd) and not pd.isna(current_eta) else None
        actual_lt = int((actual_ata - actual_atd).days) if not pd.isna(actual_atd) and not pd.isna(actual_ata) else None
        lt_variance = projected_lt - planned_lt if planned_lt is not None and projected_lt is not None else None
        record.update({
            "planned_lead_time_days": planned_lt,
            "projected_lead_time_days": projected_lt,
            "actual_lead_time_days": actual_lt,
            "lead_time_variance_days": lt_variance,
        })
        records.append(record)
    return pd.DataFrame(records)
