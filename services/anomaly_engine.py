"""
services/anomaly_engine.py

ETD/ETA 반복지연 및 Lead Time 이상을 설명 가능한 Rule로 판정한다.

NaN 처리 원칙:
- pandas DataFrame에 None이 들어가면 숫자형 컬럼에서 NaN으로 변환될 수 있다.
- Python에서 bool(float("nan"))은 True이므로 `int(value or 0)`은 안전하지 않다.
- 모든 숫자 변환은 `_safe_int()`를 통해 수행한다.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime
import hashlib
import math
from typing import Any, Optional

import pandas as pd

from services import config_store


SEVERITY_RANK = {
    "NORMAL": 0,
    "LOW": 1,
    "MEDIUM": 2,
    "HIGH": 3,
    "CRITICAL": 4,
}


@dataclass(frozen=True)
class AnomalyThresholds:
    repeated_delay_count: int = 2
    medium_delay_days: int = 3
    high_delay_days: int = 6
    critical_delay_days: int = 10
    lead_time_warning_days: int = 3
    lead_time_high_days: int = 6
    lead_time_critical_days: int = 10
    # 납기 초과(생산 영향)는 일정 지연보다 한 단계 빠르게 격상한다.
    delivery_breach_medium_days: int = 3
    delivery_breach_high_days: int = 7
    delivery_breach_critical_days: int = 14


def load_anomaly_thresholds() -> AnomalyThresholds:
    """anomaly_thresholds 설정에서 기본 임계값 로드.

    config_store 경유(커스텀 파일 우선, repo 기본
    backend/app/data/anomaly_thresholds.json 폴터). 읽기 실패나
    누락/비정상 필드는 dataclass 기본값으로 채운다.
    """
    defaults = AnomalyThresholds()
    try:
        data = config_store.load_config("anomaly_thresholds")
    except (OSError, ValueError):
        data = None
    if not isinstance(data, dict):
        return defaults
    values: dict[str, int] = {}
    for field in fields(AnomalyThresholds):
        raw = data.get(field.name)
        try:
            values[field.name] = int(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            values[field.name] = getattr(defaults, field.name)
    return AnomalyThresholds(**values)


def _is_missing(value: Any) -> bool:
    """None, pandas.NA, NaN, NaT를 안전하게 판별."""
    if value is None:
        return True

    try:
        missing = pd.isna(value)
        # list/array가 들어오는 비정상 케이스는 missing으로 취급하지 않고
        # 이후 숫자 변환 단계에서 기본값으로 떨어뜨린다.
        if isinstance(missing, bool):
            return missing
    except (TypeError, ValueError):
        pass

    return False


def _safe_int(value: Any, default: int = 0) -> int:
    """
    숫자, 숫자 문자열, numpy scalar를 int로 안전하게 변환한다.

    `int(value or 0)`을 사용하지 않는 이유:
    float('nan')은 truthy이므로 `nan or 0`이 nan이 되어
    `int(nan)`에서 ValueError가 발생한다.
    """
    if _is_missing(value):
        return default

    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError):
        return default

    if math.isnan(numeric) or math.isinf(numeric):
        return default

    return int(numeric)


def _safe_optional_int(value: Any) -> Optional[int]:
    """결측값은 None, 유효 숫자는 int로 반환."""
    if _is_missing(value):
        return None

    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError):
        return None

    if math.isnan(numeric) or math.isinf(numeric):
        return None

    return int(numeric)


def _severity_for_days(
    days: Optional[int],
    thresholds: AnomalyThresholds,
) -> str:
    value = _safe_int(days)

    if value >= thresholds.critical_delay_days:
        return "CRITICAL"
    if value >= thresholds.high_delay_days:
        return "HIGH"
    if value >= thresholds.medium_delay_days:
        return "MEDIUM"
    if value > 0:
        return "LOW"
    return "NORMAL"


def _severity_for_lt(
    days: Optional[int],
    thresholds: AnomalyThresholds,
) -> str:
    value = _safe_int(days)

    if value >= thresholds.lead_time_critical_days:
        return "CRITICAL"
    if value >= thresholds.lead_time_high_days:
        return "HIGH"
    if value >= thresholds.lead_time_warning_days:
        return "MEDIUM"
    return "NORMAL"


def _severity_for_delivery_breach(
    days: Optional[int],
    thresholds: AnomalyThresholds,
) -> str:
    value = _safe_int(days)

    if value >= thresholds.delivery_breach_critical_days:
        return "CRITICAL"
    if value >= thresholds.delivery_breach_high_days:
        return "HIGH"
    if value >= thresholds.delivery_breach_medium_days:
        return "MEDIUM"
    if value > 0:
        return "LOW"
    return "NORMAL"


def _coerce_timestamp(value: Any) -> Optional[pd.Timestamp]:
    """NaN/NaT/파싱 불가 값은 None으로, 유효 값은 Timestamp로."""
    if _is_missing(value):
        return None

    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None

    return parsed


def _max_severity(*levels: str) -> str:
    return max(levels, key=lambda value: SEVERITY_RANK.get(value, 0))


def _event_id(transport_key: str, signals: list[str]) -> str:
    digest = hashlib.sha1(
        f"{transport_key}|{'|'.join(sorted(signals))}".encode("utf-8")
    ).hexdigest()[:10].upper()
    return f"SCH-{digest}"


def evaluate_schedule_anomalies(
    metrics_df: pd.DataFrame,
    *,
    thresholds: Optional[AnomalyThresholds] = None,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    rules = thresholds or load_anomaly_thresholds()

    if metrics_df.empty:
        return metrics_df.copy(), []

    enriched_records: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []

    for _, row in metrics_df.iterrows():
        record = row.to_dict()
        signals: list[str] = []
        signal_details: list[dict[str, Any]] = []
        severity = "NORMAL"

        etd_recent = _safe_int(record.get("etd_delay_count_recent"))
        eta_recent = _safe_int(record.get("eta_delay_count_recent"))
        etd_net = _safe_optional_int(record.get("etd_net_delay_days"))
        eta_net = _safe_optional_int(record.get("eta_net_delay_days"))
        lt_variance = _safe_optional_int(
            record.get("lead_time_variance_days")
        )

        if etd_recent >= rules.repeated_delay_count:
            signal_severity = _severity_for_days(etd_net, rules)
            signal_severity = _max_severity(signal_severity, "MEDIUM")

            signals.append("REPEATED_ETD_DELAY")
            signal_details.append(
                {
                    "signal": "REPEATED_ETD_DELAY",
                    "count_recent": etd_recent,
                    "net_delay_days": etd_net,
                    "severity": signal_severity,
                }
            )
            severity = _max_severity(severity, signal_severity)

        if eta_recent >= rules.repeated_delay_count:
            signal_severity = _severity_for_days(eta_net, rules)
            signal_severity = _max_severity(signal_severity, "MEDIUM")

            signals.append("REPEATED_ETA_DELAY")
            signal_details.append(
                {
                    "signal": "REPEATED_ETA_DELAY",
                    "count_recent": eta_recent,
                    "net_delay_days": eta_net,
                    "severity": signal_severity,
                }
            )
            severity = _max_severity(severity, signal_severity)

        if (
            lt_variance is not None
            and lt_variance >= rules.lead_time_warning_days
        ):
            signal_severity = _severity_for_lt(lt_variance, rules)

            signals.append("LEAD_TIME_ANOMALY")
            signal_details.append(
                {
                    "signal": "LEAD_TIME_ANOMALY",
                    "variance_days": lt_variance,
                    "severity": signal_severity,
                }
            )
            severity = _max_severity(severity, signal_severity)

        # 반복 횟수는 적지만 누적 지연이 큰 건도 놓치지 않는다.
        max_net_delay = max(
            _safe_int(etd_net),
            _safe_int(eta_net),
        )

        if not signals and max_net_delay >= rules.high_delay_days:
            signal_severity = _severity_for_days(max_net_delay, rules)

            signals.append("LARGE_SCHEDULE_DELAY")
            signal_details.append(
                {
                    "signal": "LARGE_SCHEDULE_DELAY",
                    "net_delay_days": max_net_delay,
                    "severity": signal_severity,
                }
            )
            severity = _max_severity(severity, signal_severity)

        # 납기 초과: 오로지 최종 도착지 납품 예정일(dlvy_eta)과 납품 요청일
        # (dlvy_req_date)만 비교한다. 항구 ETA(current_eta)는 사용하지 않으며,
        # 둘 중 하나라도 없으면 판정하지 않는다.
        # 납품 실적(dlvy_ata)이 찍힌 운송은 이미 납품됐으므로 판정하지 않는다.
        delivery_req_date = _coerce_timestamp(
            record.get("delivery_request_date")
        )
        delivery_eta = _coerce_timestamp(record.get("delivery_eta"))
        delivery_actual = _coerce_timestamp(
            record.get("delivery_actual_date")
        )

        delivery_breach_days: Optional[int] = None
        if (
            delivery_actual is None
            and delivery_req_date is not None
            and delivery_eta is not None
        ):
            delivery_breach_days = int(
                (delivery_eta - delivery_req_date).days
            )

        if (
            delivery_breach_days is not None
            and delivery_breach_days > 0
        ):
            signal_severity = _severity_for_delivery_breach(
                delivery_breach_days, rules,
            )

            signals.append("DELIVERY_REQ_BREACH")
            signal_details.append(
                {
                    "signal": "DELIVERY_REQ_BREACH",
                    "breach_days": delivery_breach_days,
                    "delivery_request_date": (
                        delivery_req_date.date().isoformat()
                    ),
                    "delivery_eta": delivery_eta.date().isoformat(),
                    "severity": signal_severity,
                }
            )
            severity = _max_severity(severity, signal_severity)

        risk_score = min(
            100,
            (etd_recent + eta_recent) * 12
            + max(0, _safe_int(etd_net)) * 3
            + max(0, _safe_int(eta_net)) * 3
            + max(0, _safe_int(lt_variance)) * 4
            + max(0, _safe_int(delivery_breach_days)) * 5,
        )

        record.update(
            {
                # API 직렬화 전에 DataFrame에서 다시 NaN으로 바뀔 수 있지만,
                # api_server._clean_value가 최종적으로 null 처리한다.
                "etd_net_delay_days": etd_net,
                "eta_net_delay_days": eta_net,
                "lead_time_variance_days": lt_variance,
                "delivery_req_breach_days": delivery_breach_days,
                "anomaly_signals": signals,
                "anomaly_count": len(signals),
                "severity": severity,
                "risk_score": risk_score,
            }
        )
        enriched_records.append(record)

        if not signals:
            continue

        labels = {
            "REPEATED_ETD_DELAY": "ETD 반복 지연",
            "REPEATED_ETA_DELAY": "ETA 반복 지연",
            "LEAD_TIME_ANOMALY": "Lead Time 증가",
            "LARGE_SCHEDULE_DELAY": "대규모 일정 지연",
            "DELIVERY_REQ_BREACH": "납기 초과",
        }

        events.append(
            {
                "event_id": _event_id(
                    str(record.get("transport_key", "")),
                    signals,
                ),
                "event_type": "SCHEDULE_ANOMALY",
                "primary_signal": signals[0],
                "signals": signals,
                "signal_details": signal_details,
                "severity": severity,
                "risk_score": risk_score,
                "transport_key": record.get("transport_key"),
                "cmpy_cd": record.get("cmpy_cd"),
                "cmpy_nm": record.get("cmpy_nm"),
                "plnt_cd": record.get("plnt_cd"),
                "trpr_no": record.get("trpr_no"),
                "hbl_no": record.get("hbl_no"),
                "pol": record.get("pol"),
                "pol_name": record.get("pol_name"),
                "pod": record.get("pod"),
                "pod_name": record.get("pod_name"),
                "vessel_name": record.get("vessel_name"),
                "voyage_no": record.get("voyage_no"),
                "etd_delay_count_recent": etd_recent,
                "eta_delay_count_recent": eta_recent,
                "etd_net_delay_days": etd_net,
                "eta_net_delay_days": eta_net,
                "planned_lead_time_days": _safe_optional_int(
                    record.get("planned_lead_time_days")
                ),
                "projected_lead_time_days": _safe_optional_int(
                    record.get("projected_lead_time_days")
                ),
                "lead_time_variance_days": lt_variance,
                "delivery_req_breach_days": delivery_breach_days,
                "po_count": _safe_int(record.get("po_count")),
                "item_count": _safe_int(record.get("item_count")),
                "quantity_sum": record.get("quantity_sum"),
                "quantity_unit": record.get("quantity_unit"),
                "headline": (
                    f"{record.get('trpr_no')} — "
                    f"{', '.join(labels.get(signal, signal) for signal in signals)}"
                ),
                "status": "OPEN",
                "detected_at": datetime.now().isoformat(timespec="seconds"),
            }
        )

    events.sort(
        key=lambda item: (
            SEVERITY_RANK.get(str(item.get("severity")), 0),
            _safe_int(item.get("risk_score")),
        ),
        reverse=True,
    )

    return pd.DataFrame(enriched_records), events


def build_dashboard_summary(
    enriched_df: pd.DataFrame,
    events: list[dict[str, Any]],
) -> dict[str, int]:
    if enriched_df.empty:
        return {
            "active_transports": 0,
            "etd_repeated_delay": 0,
            "eta_repeated_delay": 0,
            "lead_time_anomaly": 0,
            "delivery_req_breach": 0,
            "high_critical": 0,
            "anomaly_transports": 0,
        }

    etd_delay_count = pd.to_numeric(
        enriched_df.get(
            "etd_delay_count_recent",
            pd.Series(index=enriched_df.index, dtype=float),
        ),
        errors="coerce",
    ).fillna(0)

    eta_delay_count = pd.to_numeric(
        enriched_df.get(
            "eta_delay_count_recent",
            pd.Series(index=enriched_df.index, dtype=float),
        ),
        errors="coerce",
    ).fillna(0)

    lead_time_variance = pd.to_numeric(
        enriched_df.get(
            "lead_time_variance_days",
            pd.Series(index=enriched_df.index, dtype=float),
        ),
        errors="coerce",
    ).fillna(0)

    delivery_breach_days = pd.to_numeric(
        enriched_df.get(
            "delivery_req_breach_days",
            pd.Series(index=enriched_df.index, dtype=float),
        ),
        errors="coerce",
    ).fillna(0)

    return {
        "active_transports": int(len(enriched_df)),
        "etd_repeated_delay": int(
            (etd_delay_count >= 2).sum()
        ),
        "eta_repeated_delay": int(
            (eta_delay_count >= 2).sum()
        ),
        "lead_time_anomaly": int(
            (lead_time_variance >= 3).sum()
        ),
        "delivery_req_breach": int(
            (delivery_breach_days > 0).sum()
        ),
        "high_critical": int(
            sum(
                1
                for event in events
                if event.get("severity") in {"HIGH", "CRITICAL"}
            )
        ),
        "anomaly_transports": int(len(events)),
    }
