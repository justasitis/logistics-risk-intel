"""
특정 Transportation No.의 ETD/ETA 변경이력을 사용자용 Timeline JSON으로 변환한다.
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from services.schedule_history_service import (
    normalize_schedule_history,
)


def _clean_text(value: Any) -> str:
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass

    return str(value).strip()


def _to_timestamp(value: Any) -> pd.Timestamp:
    return pd.to_datetime(value, errors="coerce")


def _iso_or_none(value: Any) -> Optional[str]:
    parsed = _to_timestamp(value)
    if pd.isna(parsed):
        return None
    return parsed.isoformat()


def _safe_int(
    value: Any,
    default: int = 0,
) -> int:
    if value is None:
        return default

    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass

    try:
        return int(float(value))
    except (
        TypeError,
        ValueError,
        OverflowError,
    ):
        return default


def _first_schedule_date(
    subset: pd.DataFrame,
) -> pd.Timestamp:
    if subset.empty:
        return pd.NaT

    previous_dates = subset["fr_date"].dropna()
    if not previous_dates.empty:
        return _to_timestamp(previous_dates.iloc[0])

    revised_dates = subset["to_date"].dropna()
    if not revised_dates.empty:
        return _to_timestamp(revised_dates.iloc[0])

    return pd.NaT


def _last_schedule_date(
    subset: pd.DataFrame,
) -> pd.Timestamp:
    if subset.empty:
        return pd.NaT

    revised_dates = subset["to_date"].dropna()
    if revised_dates.empty:
        return pd.NaT

    return _to_timestamp(revised_dates.iloc[-1])


def _build_type_timeline(
    normalized_history: pd.DataFrame,
    *,
    schedule_type: str,
    current_date: Any,
    include_no_change: bool,
) -> dict[str, Any]:
    full_subset = normalized_history.loc[
        normalized_history["his_type"].eq(
            schedule_type
        )
    ].copy()

    full_subset = full_subset.sort_values(
        ["ins_datetime", "his_no"],
        kind="stable",
    )

    current_ts = _to_timestamp(current_date)

    if full_subset.empty:
        return {
            "schedule_type": schedule_type,
            "initial_date": None,
            "current_date": _iso_or_none(current_ts),
            "change_count": 0,
            "delay_count": 0,
            "advance_count": 0,
            "gross_delay_days": 0,
            "gross_advance_days": 0,
            "net_change_days": 0,
            "last_changed_at": None,
            "source_row_count": 0,
            "initial_record_count": 0,
            "events": [],
        }

    initial_date = _first_schedule_date(
        full_subset
    )
    history_current = _last_schedule_date(
        full_subset
    )
    effective_current = (
        current_ts
        if not pd.isna(current_ts)
        else history_current
    )

    actual_subset = full_subset.loc[
        full_subset["is_actual_change"]
        .fillna(False)
        .astype(bool)
    ].copy()

    event_subset = (
        full_subset
        if include_no_change
        else actual_subset
    )

    delayed = actual_subset.loc[
        actual_subset["change_days"]
        .fillna(0)
        .gt(0)
    ]
    advanced = actual_subset.loc[
        actual_subset["change_days"]
        .fillna(0)
        .lt(0)
    ]

    net_change_days = 0
    if (
        not pd.isna(initial_date)
        and not pd.isna(effective_current)
    ):
        net_change_days = int(
            (
                effective_current
                - initial_date
            ).days
        )

    events: list[dict[str, Any]] = []

    for row_index, row in event_subset.iterrows():
        change_days = _safe_int(
            row.get("change_days")
        )
        direction = (
            _clean_text(
                row.get("change_direction")
            )
            or "NO_CHANGE"
        )
        history_no = _clean_text(
            row.get("his_no")
        )

        if not history_no:
            history_no = (
                f"{schedule_type}-"
                f"{row_index}-"
                f"{_clean_text(row.get('ins_datetime'))}"
            )

        events.append(
            {
                "history_no": history_no,
                "schedule_type": schedule_type,
                "previous_date": _iso_or_none(
                    row.get("fr_date")
                ),
                "revised_date": _iso_or_none(
                    row.get("to_date")
                ),
                "change_days": change_days,
                "direction": direction,
                "changed_at": _iso_or_none(
                    row.get("ins_datetime")
                ),
                "changed_by": _clean_text(
                    row.get("ins_person_id")
                ),
                "is_actual_change": bool(
                    row.get(
                        "is_actual_change",
                        False,
                    )
                ),
            }
        )

    return {
        "schedule_type": schedule_type,
        "initial_date": _iso_or_none(
            initial_date
        ),
        "current_date": _iso_or_none(
            effective_current
        ),
        "change_count": int(
            len(actual_subset)
        ),
        "delay_count": int(len(delayed)),
        "advance_count": int(len(advanced)),
        "gross_delay_days": (
            int(delayed["change_days"].sum())
            if not delayed.empty
            else 0
        ),
        "gross_advance_days": (
            abs(
                int(
                    advanced[
                        "change_days"
                    ].sum()
                )
            )
            if not advanced.empty
            else 0
        ),
        "net_change_days": net_change_days,
        "last_changed_at": _iso_or_none(
            actual_subset[
                "ins_datetime"
            ].max()
            if not actual_subset.empty
            else full_subset[
                "ins_datetime"
            ].max()
        ),
        "source_row_count": int(
            len(full_subset)
        ),
        "initial_record_count": int(
            full_subset.get(
                "is_initial_record",
                pd.Series(
                    False,
                    index=full_subset.index,
                ),
            )
            .fillna(False)
            .astype(bool)
            .sum()
        ),
        "events": events,
    }


def build_transport_timeline(
    snapshot_row: Optional[pd.Series],
    history_df: pd.DataFrame,
    *,
    cmpy_cd: str,
    plnt_cd: str,
    trpr_no: str,
    include_no_change: bool = False,
) -> dict[str, Any]:
    normalized_history = (
        normalize_schedule_history(history_df)
        if not history_df.empty
        else pd.DataFrame(
            columns=[
                "cmpy_cd",
                "plnt_cd",
                "trpr_no",
                "his_type",
                "his_no",
                "fr_date",
                "to_date",
                "ins_datetime",
                "ins_person_id",
                "change_days",
                "is_actual_change",
                "is_initial_record",
                "change_direction",
                "transport_key",
            ]
        )
    )

    row = (
        snapshot_row
        if snapshot_row is not None
        else pd.Series(dtype=object)
    )

    row_cmpy_cd = (
        _clean_text(row.get("cmpy_cd"))
        or _clean_text(cmpy_cd)
    )
    row_plnt_cd = (
        _clean_text(row.get("plnt_cd"))
        or _clean_text(plnt_cd)
    )
    row_trpr_no = (
        _clean_text(row.get("trpr_no"))
        or _clean_text(trpr_no)
    )

    transport_key = "|".join(
        [
            row_cmpy_cd,
            row_plnt_cd,
            row_trpr_no,
        ]
    )

    current_etd = row.get("current_etd")
    current_eta = row.get("current_eta")

    etd_timeline = _build_type_timeline(
        normalized_history,
        schedule_type="ETD",
        current_date=current_etd,
        include_no_change=include_no_change,
    )
    eta_timeline = _build_type_timeline(
        normalized_history,
        schedule_type="ETA",
        current_date=current_eta,
        include_no_change=include_no_change,
    )

    return {
        "transport_key": transport_key,
        "header": {
            "cmpy_cd": row_cmpy_cd,
            "cmpy_nm": _clean_text(
                row.get("cmpy_nm")
            ),
            "plnt_cd": row_plnt_cd,
            "plnt_nm": _clean_text(
                row.get("plnt_nm")
            ),
            "trpr_no": row_trpr_no,
            "hbl_no": _clean_text(
                row.get("hbl_no")
            ),
            "mbl_no": _clean_text(
                row.get("mbl_no")
            ),
            "pol": _clean_text(
                row.get("pol")
            ),
            "pol_name": _clean_text(
                row.get("pol_name")
            ),
            "pod": _clean_text(
                row.get("pod")
            ),
            "pod_name": _clean_text(
                row.get("pod_name")
            ),
            "vessel_name": _clean_text(
                row.get("vessel_name")
            ),
            "voyage_no": _clean_text(
                row.get("voyage_no")
            ),
            "current_etd": _iso_or_none(
                current_etd
            ),
            "current_eta": _iso_or_none(
                current_eta
            ),
        },
        "etd": etd_timeline,
        "eta": eta_timeline,
        "history_source_row_count": int(
            len(history_df)
        ),
        "history_row_count": int(
            len(normalized_history)
        ),
        "include_no_change": (
            include_no_change
        ),
    }
