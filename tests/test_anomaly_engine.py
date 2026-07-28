"""services/anomaly_engine.py 회귀 테스트.

step2 시절 `_safe_int` 이슈(bool(float('nan')) is True → int(nan) ValueError)의
회귀 방지와 severity/risk_score 룰 분류를 검증한다.
"""
from __future__ import annotations

import math

import pandas as pd
import pytest

from services.anomaly_engine import (
    AnomalyThresholds,
    _event_id,
    _is_missing,
    _safe_int,
    _safe_optional_int,
    build_dashboard_summary,
    evaluate_schedule_anomalies,
)


def _metrics_row(**overrides):
    row = {
        "transport_key": "SKBA|P1|TRPR001",
        "cmpy_cd": "SKBA",
        "cmpy_nm": "테스트법인",
        "plnt_cd": "P1",
        "trpr_no": "TRPR001",
        "hbl_no": "HBL001",
        "etd_delay_count_recent": 0,
        "eta_delay_count_recent": 0,
        "etd_net_delay_days": None,
        "eta_net_delay_days": None,
        "lead_time_variance_days": None,
    }
    row.update(overrides)
    return row


def _evaluate(rows, **kwargs):
    return evaluate_schedule_anomalies(pd.DataFrame(rows), **kwargs)


class TestSafeInt:
    """NaN/NaT 처리 — step2 _safe_int 회귀 방지."""

    def test_nan_returns_default(self):
        # bool(float('nan'))은 True이므로 `int(value or 0)` 패턴은 깨진다.
        assert _safe_int(float("nan")) == 0
        assert _safe_int(float("nan"), default=7) == 7

    def test_none_and_nat_return_default(self):
        assert _safe_int(None) == 0
        assert _safe_int(pd.NaT) == 0
        assert _safe_int(pd.NA) == 0

    def test_inf_returns_default(self):
        assert _safe_int(math.inf) == 0
        assert _safe_int(-math.inf) == 0

    def test_valid_conversions(self):
        assert _safe_int(5) == 5
        assert _safe_int(3.9) == 3
        assert _safe_int("12") == 12
        assert _safe_int(-4) == -4

    def test_non_numeric_returns_default(self):
        assert _safe_int("abc") == 0
        assert _safe_int("abc", default=-1) == -1

    def test_optional_missing_returns_none(self):
        assert _safe_optional_int(None) is None
        assert _safe_optional_int(float("nan")) is None
        assert _safe_optional_int(pd.NaT) is None

    def test_optional_valid_returns_int(self):
        assert _safe_optional_int("8") == 8
        assert _safe_optional_int(2.7) == 2

    def test_is_missing_variants(self):
        assert _is_missing(None)
        assert _is_missing(float("nan"))
        assert _is_missing(pd.NaT)
        assert not _is_missing(0)
        assert not _is_missing("")


class TestEvaluateScheduleAnomalies:
    def test_empty_dataframe(self):
        enriched, events = evaluate_schedule_anomalies(pd.DataFrame())
        assert enriched.empty
        assert events == []

    def test_no_signals_for_normal_row(self):
        enriched, events = _evaluate([_metrics_row()])
        assert events == []
        record = enriched.iloc[0]
        assert record["severity"] == "NORMAL"
        assert record["anomaly_signals"] == []
        assert record["anomaly_count"] == 0
        assert record["risk_score"] == 0

    def test_nan_inputs_do_not_crash_and_stay_normal(self):
        # None이 숫자형 컬럼에서 NaN으로 변환된 DataFrame 행.
        enriched, events = _evaluate(
            [_metrics_row(
                etd_delay_count_recent=None,
                eta_delay_count_recent=None,
                etd_net_delay_days=None,
                eta_net_delay_days=None,
                lead_time_variance_days=None,
            )]
        )
        assert events == []
        record = enriched.iloc[0]
        assert record["severity"] == "NORMAL"
        assert record["risk_score"] == 0
        assert record["etd_net_delay_days"] is None

    def test_repeated_etd_delay_minimum_medium(self):
        # 반복 횟수가 기준(2회) 이상이면 net 지연이 없어도 MEDIUM.
        enriched, events = _evaluate(
            [_metrics_row(etd_delay_count_recent=2, etd_net_delay_days=0)]
        )
        record = enriched.iloc[0]
        assert "REPEATED_ETD_DELAY" in record["anomaly_signals"]
        assert record["severity"] == "MEDIUM"
        assert len(events) == 1
        assert events[0]["primary_signal"] == "REPEATED_ETD_DELAY"

    def test_severity_by_net_delay_days(self):
        cases = [
            (1, "MEDIUM"),   # 반복지연이면 하한 MEDIUM, days 1 → LOW보다 MEDIUM
            (3, "MEDIUM"),
            (6, "HIGH"),
            (10, "CRITICAL"),
        ]
        for days, expected in cases:
            enriched, _ = _evaluate(
                [_metrics_row(etd_delay_count_recent=2, etd_net_delay_days=days)]
            )
            assert enriched.iloc[0]["severity"] == expected, f"days={days}"

    def test_repeated_eta_delay_signal(self):
        enriched, events = _evaluate(
            [_metrics_row(eta_delay_count_recent=3, eta_net_delay_days=7)]
        )
        record = enriched.iloc[0]
        assert "REPEATED_ETA_DELAY" in record["anomaly_signals"]
        assert record["severity"] == "HIGH"

    def test_lead_time_anomaly_thresholds(self):
        # variance 3 미만이면 신호 없음
        enriched, _ = _evaluate([_metrics_row(lead_time_variance_days=2)])
        assert enriched.iloc[0]["anomaly_signals"] == []

        cases = [(3, "MEDIUM"), (6, "HIGH"), (10, "CRITICAL")]
        for variance, expected in cases:
            enriched, _ = _evaluate(
                [_metrics_row(lead_time_variance_days=variance)]
            )
            record = enriched.iloc[0]
            assert record["anomaly_signals"] == ["LEAD_TIME_ANOMALY"]
            assert record["severity"] == expected, f"variance={variance}"

    def test_large_schedule_delay_only_when_no_other_signals(self):
        # 반복 횟수는 기준 미만이지만 누적 지연이 high 기준(6일) 이상.
        enriched, _ = _evaluate([_metrics_row(etd_net_delay_days=8)])
        record = enriched.iloc[0]
        assert record["anomaly_signals"] == ["LARGE_SCHEDULE_DELAY"]
        assert record["severity"] == "HIGH"

        # 다른 신호가 있으면 LARGE_SCHEDULE_DELAY는 붙지 않는다.
        enriched, _ = _evaluate(
            [_metrics_row(etd_delay_count_recent=2, etd_net_delay_days=8)]
        )
        assert "LARGE_SCHEDULE_DELAY" not in enriched.iloc[0]["anomaly_signals"]

    def test_risk_score_formula(self):
        # (1+2)*12 + max(0,4)*3 + max(0,5)*3 + max(0,3)*4 = 36+12+15+12 = 75
        enriched, _ = _evaluate(
            [_metrics_row(
                etd_delay_count_recent=1,
                eta_delay_count_recent=2,
                etd_net_delay_days=4,
                eta_net_delay_days=5,
                lead_time_variance_days=3,
            )]
        )
        assert enriched.iloc[0]["risk_score"] == 75

    def test_risk_score_capped_at_100(self):
        enriched, _ = _evaluate(
            [_metrics_row(
                etd_delay_count_recent=9,
                eta_delay_count_recent=9,
                etd_net_delay_days=30,
                eta_net_delay_days=30,
                lead_time_variance_days=30,
            )]
        )
        assert enriched.iloc[0]["risk_score"] == 100

    def test_negative_delays_not_added_to_risk_score(self):
        enriched, _ = _evaluate([_metrics_row(etd_net_delay_days=-5)])
        assert enriched.iloc[0]["risk_score"] == 0

    def test_events_sorted_by_severity_desc(self):
        _, events = _evaluate([
            _metrics_row(trpr_no="LOW1", transport_key="SKBA|P1|LOW1",
                         etd_delay_count_recent=2, etd_net_delay_days=3),
            _metrics_row(trpr_no="CRI1", transport_key="SKBA|P1|CRI1",
                         lead_time_variance_days=12),
        ])
        assert [e["severity"] for e in events] == ["CRITICAL", "MEDIUM"]

    def test_event_payload_fields(self):
        _, events = _evaluate(
            [_metrics_row(etd_delay_count_recent=2, etd_net_delay_days=4)]
        )
        event = events[0]
        assert event["event_type"] == "SCHEDULE_ANOMALY"
        assert event["status"] == "OPEN"
        assert event["event_id"].startswith("SCH-")
        assert event["transport_key"] == "SKBA|P1|TRPR001"
        assert "ETD 반복 지연" in event["headline"]
        assert event["signal_details"][0]["signal"] == "REPEATED_ETD_DELAY"

    def test_custom_thresholds(self):
        rules = AnomalyThresholds(repeated_delay_count=3)
        enriched, _ = _evaluate(
            [_metrics_row(etd_delay_count_recent=2, etd_net_delay_days=1)],
            thresholds=rules,
        )
        assert "REPEATED_ETD_DELAY" not in enriched.iloc[0]["anomaly_signals"]

    def test_event_id_deterministic_and_signal_order_independent(self):
        first = _event_id("K", ["B", "A"])
        second = _event_id("K", ["A", "B"])
        assert first == second
        assert first != _event_id("OTHER", ["A", "B"])


class TestBuildDashboardSummary:
    def test_empty(self):
        summary = build_dashboard_summary(pd.DataFrame(), [])
        assert summary == {
            "active_transports": 0,
            "etd_repeated_delay": 0,
            "eta_repeated_delay": 0,
            "lead_time_anomaly": 0,
            "delivery_req_breach": 0,
            "high_critical": 0,
            "anomaly_transports": 0,
        }

    def test_counts(self):
        enriched, events = _evaluate([
            _metrics_row(trpr_no="T1", transport_key="SKBA|P1|T1",
                         etd_delay_count_recent=2, etd_net_delay_days=3),
            _metrics_row(trpr_no="T2", transport_key="SKBA|P1|T2",
                         eta_delay_count_recent=2, eta_net_delay_days=10),
            _metrics_row(trpr_no="T3", transport_key="SKBA|P1|T3"),
        ])
        summary = build_dashboard_summary(enriched, events)
        assert summary["active_transports"] == 3
        assert summary["etd_repeated_delay"] == 1
        assert summary["eta_repeated_delay"] == 1
        assert summary["lead_time_anomaly"] == 0
        assert summary["high_critical"] == 1  # T2 CRITICAL
        assert summary["anomaly_transports"] == 2

    def test_nan_columns_do_not_crash(self):
        df = pd.DataFrame([_metrics_row()])
        df["etd_delay_count_recent"] = None  # NaN 컬럼
        summary = build_dashboard_summary(df, [])
        assert summary["etd_repeated_delay"] == 0


class TestDeliveryReqBreach:
    """DELIVERY_REQ_BREACH — 오로지 dlvy_eta(최종 도착지 납품 예정일)와
    dlvy_req_date(납품 요청일)만 비교한다. current_eta는 사용하지 않는다."""

    def test_breach_by_delivery_eta(self):
        enriched, events = _evaluate(
            [_metrics_row(
                delivery_eta="2026-03-20T00:00:00",
                delivery_request_date="2026-03-16T00:00:00",
            )]
        )
        record = enriched.iloc[0]
        assert record["anomaly_signals"] == ["DELIVERY_REQ_BREACH"]
        assert record["delivery_req_breach_days"] == 4
        assert record["severity"] == "MEDIUM"  # 3일 이상
        assert events[0]["signal_details"][0]["breach_days"] == 4
        assert (
            events[0]["signal_details"][0]["delivery_request_date"]
            == "2026-03-16"
        )
        assert events[0]["signal_details"][0]["delivery_eta"] == "2026-03-20"
        assert "납기 초과" in events[0]["headline"]

    def test_delivery_eta_raw_format_parsed(self):
        # 데이터레이크 원본 형식(YYYYMMDDHHMMSS)도 파싱돼야 한다.
        enriched, _ = _evaluate(
            [_metrics_row(
                delivery_eta="20260320000000",
                delivery_request_date="2026-03-16T00:00:00",
            )]
        )
        assert enriched.iloc[0]["delivery_req_breach_days"] == 4

    def test_current_eta_is_ignored(self):
        # current_eta가 요청일 이전이어도 dlvy_eta가 넘으면 breach다.
        enriched, _ = _evaluate(
            [_metrics_row(
                current_eta="2026-03-10T00:00:00",
                delivery_eta="20260325000000",
                delivery_request_date="2026-03-16T00:00:00",
            )]
        )
        record = enriched.iloc[0]
        assert record["anomaly_signals"] == ["DELIVERY_REQ_BREACH"]
        assert record["delivery_req_breach_days"] == 9

    def test_no_breach_when_dlvy_eta_on_time_even_if_current_eta_late(self):
        # current_eta가 요청일을 넘어도 dlvy_eta가 지켜지면 breach가 아니다.
        enriched, _ = _evaluate(
            [_metrics_row(
                current_eta="2026-03-25T00:00:00",
                delivery_eta="2026-03-14T00:00:00",
                delivery_request_date="2026-03-16T00:00:00",
            )]
        )
        record = enriched.iloc[0]
        assert "DELIVERY_REQ_BREACH" not in record["anomaly_signals"]
        assert record["delivery_req_breach_days"] == -2

    def test_severity_mapping(self):
        cases = [
            ("2026-03-17", 1, "LOW"),
            ("2026-03-19", 3, "MEDIUM"),
            ("2026-03-23", 7, "HIGH"),
            ("2026-03-30", 14, "CRITICAL"),
        ]
        for eta, days, expected in cases:
            enriched, _ = _evaluate(
                [_metrics_row(
                    delivery_eta=f"{eta}T00:00:00",
                    delivery_request_date="2026-03-16T00:00:00",
                )]
            )
            record = enriched.iloc[0]
            assert record["delivery_req_breach_days"] == days
            assert record["severity"] == expected, f"days={days}"

    def test_no_breach_when_eta_on_or_before_request(self):
        for eta in ["2026-03-16T00:00:00", "2026-03-10T00:00:00"]:
            enriched, events = _evaluate(
                [_metrics_row(
                    delivery_eta=eta,
                    delivery_request_date="2026-03-16T00:00:00",
                )]
            )
            record = enriched.iloc[0]
            assert "DELIVERY_REQ_BREACH" not in record["anomaly_signals"], eta
            assert record["severity"] == "NORMAL"

    def test_skip_when_request_date_missing(self):
        # 납품 요청일이 없는 운송건은 오탐 방지를 위해 판정하지 않는다.
        enriched, _ = _evaluate(
            [_metrics_row(
                delivery_eta="2026-06-01T00:00:00",
                delivery_request_date=None,
            )]
        )
        record = enriched.iloc[0]
        assert record["anomaly_signals"] == []
        assert record["delivery_req_breach_days"] is None
        assert record["severity"] == "NORMAL"

    def test_skip_when_delivery_eta_missing(self):
        # dlvy_eta가 없으면 current_eta가 있어도 판정하지 않는다.
        enriched, _ = _evaluate(
            [_metrics_row(
                current_eta="2026-06-01T00:00:00",
                delivery_eta=None,
                delivery_request_date="2026-03-16T00:00:00",
            )]
        )
        record = enriched.iloc[0]
        assert record["anomaly_signals"] == []
        assert record["delivery_req_breach_days"] is None

    def test_unparseable_dates_skipped(self):
        enriched, _ = _evaluate(
            [_metrics_row(
                delivery_eta="not-a-date",
                delivery_request_date="2026-03-16T00:00:00",
            )]
        )
        assert enriched.iloc[0]["delivery_req_breach_days"] is None

    def test_risk_score_contribution(self):
        # 초과 4일 * 5 = 20 (다른 지표 0)
        enriched, _ = _evaluate(
            [_metrics_row(
                delivery_eta="2026-03-20T00:00:00",
                delivery_request_date="2026-03-16T00:00:00",
            )]
        )
        assert enriched.iloc[0]["risk_score"] == 20

    def test_negative_breach_days_not_added_to_risk_score(self):
        enriched, _ = _evaluate(
            [_metrics_row(
                delivery_eta="2026-03-10T00:00:00",
                delivery_request_date="2026-03-16T00:00:00",
            )]
        )
        assert enriched.iloc[0]["risk_score"] == 0

    def test_summary_counts_breach(self):
        enriched, events = _evaluate([
            _metrics_row(
                trpr_no="T1", transport_key="SKBA|P1|T1",
                delivery_eta="2026-03-20T00:00:00",
                delivery_request_date="2026-03-16T00:00:00",
            ),
            _metrics_row(trpr_no="T2", transport_key="SKBA|P1|T2"),
        ])
        summary = build_dashboard_summary(enriched, events)
        assert summary["delivery_req_breach"] == 1

    def test_summary_empty_has_breach_key(self):
        summary = build_dashboard_summary(pd.DataFrame(), [])
        assert summary["delivery_req_breach"] == 0

    def test_delivered_transport_skips_breach(self):
        # dlvy_ata(납품 실적)가 있으면 이미 납품됐으므로 판정하지 않는다.
        enriched, events = _evaluate(
            [_metrics_row(
                delivery_eta="20260320000000",
                delivery_request_date="2026-03-16T00:00:00",
                delivery_actual_date="2026-03-18T00:00:00",
            )]
        )
        record = enriched.iloc[0]
        assert "DELIVERY_REQ_BREACH" not in record["anomaly_signals"]
        assert record["delivery_req_breach_days"] is None
        assert record["risk_score"] == 0
