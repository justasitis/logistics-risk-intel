"""services/schedule_history_service.py 테스트.

Snapshot 집계와 이력 정규화/지표 계산(최초등록 제외, 반복지연 카운트,
Lead Time 산출)을 작은 가짜 데이터로 검증한다.
"""
from __future__ import annotations

import pandas as pd
import pytest

from services.schedule_history_service import (
    build_schedule_metrics,
    build_transport_snapshot,
    normalize_schedule_history,
)


def _days_ago(n: int) -> str:
    return (pd.Timestamp.now().normalize() - pd.Timedelta(days=n)).strftime(
        "%Y-%m-%d"
    )


def _days_ahead(n: int) -> str:
    return (pd.Timestamp.now().normalize() + pd.Timedelta(days=n)).strftime(
        "%Y-%m-%d"
    )


def _info_row(**overrides):
    row = {
        "cmpy_cd": "SKBA",
        "cmpy_nm": "테스트법인",
        "plnt_cd": "P1",
        "plnt_nm": "플랜트1",
        "trpr_no": "TRPR001",
        "hbl_no": "HBL001",
        "mbl_no": "MBL001",
        "cntr_no": "CNTR001",
        "po_no": "PO001",
        "item_cd": "ITEM001",
        "dlvy_qty": 10,
        "dlvy_unit": "EA",
        "dprt": "KRPUS",
        "dprt_nm": "부산",
        "arvl": "SIKOP",
        "arvl_nm": "코페르",
        "vessel_nm": "TEST VESSEL",
        "voyage_no": "V001",
        # 기본값은 활성 운송: stale 제외(ACTIVE_STALE_DAYS)에 걸리지 않는
        # 미래 ETA. 과거 ETA가 필요한 테스트는 명시적으로 덮어쓴다.
        "etd": _days_ago(10),
        "eta": _days_ahead(30),
        "atd": None,
        "ata": None,
        "cmpl_yn": "N",
    }
    row.update(overrides)
    return row


def _history_row(
    his_type,
    fr_date,
    to_date,
    ins_datetime,
    *,
    trpr_no="TRPR001",
    cmpy_cd="SKBA",
    plnt_cd="P1",
    his_no=None,
):
    return {
        "cmpy_cd": cmpy_cd,
        "plnt_cd": plnt_cd,
        "trpr_no": trpr_no,
        "his_type": his_type,
        "his_no": his_no,
        "fr_date": fr_date,
        "to_date": to_date,
        "ins_datetime": ins_datetime,
    }


class TestBuildTransportSnapshot:
    def test_missing_trpr_no_column_raises(self):
        with pytest.raises(ValueError, match="trpr_no"):
            build_transport_snapshot(pd.DataFrame({"cmpy_cd": ["SKBA"]}))

    def test_groups_by_transport_key(self):
        snapshot = build_transport_snapshot(pd.DataFrame([
            _info_row(po_no="PO001", item_cd="ITEM001"),
            _info_row(po_no="PO002", item_cd="ITEM002", hbl_no="HBL002"),
        ]))
        assert len(snapshot) == 1
        record = snapshot.iloc[0]
        assert record["transport_key"] == "SKBA|P1|TRPR001"
        assert record["po_count"] == 2
        assert record["item_count"] == 2
        assert record["hbl_no"] == "HBL001, HBL002"
        assert record["source_row_count"] == 2
        assert record["completed"] is False or record["completed"] == False  # noqa: E712

    def test_blank_trpr_no_rows_dropped(self):
        snapshot = build_transport_snapshot(pd.DataFrame([
            _info_row(),
            _info_row(trpr_no="  "),
        ]))
        assert len(snapshot) == 1

    def test_active_only_filters_completed(self):
        df = pd.DataFrame([
            _info_row(trpr_no="T1", cmpl_yn="Y"),
            _info_row(trpr_no="T2", ata="2026-03-10"),
            _info_row(trpr_no="T3"),
        ])
        active = build_transport_snapshot(df, active_only=True)
        assert sorted(active["trpr_no"]) == ["T3"]

        all_rows = build_transport_snapshot(df, active_only=False)
        assert len(all_rows) == 3

    def test_eta_date_preferred_over_eta(self):
        snapshot = build_transport_snapshot(pd.DataFrame([
            _info_row(eta_date=_days_ahead(15), eta=_days_ahead(10)),
        ]))
        assert snapshot.iloc[0]["current_eta"] == pd.Timestamp(
            _days_ahead(15)
        )


class TestNormalizeScheduleHistory:
    def test_missing_required_columns_raises(self):
        with pytest.raises(ValueError, match="필수 컬럼 누락"):
            normalize_schedule_history(pd.DataFrame({"trpr_no": ["T1"]}))

    def test_only_etd_eta_types_kept(self):
        df = normalize_schedule_history(pd.DataFrame([
            _history_row("ETD", None, "2026-02-01", "2026-01-01"),
            _history_row("DLVY_ETA", None, "2026-03-01", "2026-01-01"),
            _history_row("eta", None, "2026-03-01", "2026-01-01"),
        ]))
        assert sorted(df["his_type"].unique()) == ["ETA", "ETD"]

    def test_initial_record_kept_and_flagged(self):
        # fr_date가 비어 있어도 최초 등록행은 삭제되지 않는다.
        df = normalize_schedule_history(pd.DataFrame([
            _history_row("ETA", None, "2026-03-01", "2026-01-01"),
        ]))
        assert len(df) == 1
        assert df.iloc[0]["is_initial_record"]
        assert not df.iloc[0]["is_actual_change"]
        assert df.iloc[0]["change_direction"] == "NO_CHANGE"

    def test_change_direction_and_actual_change(self):
        df = normalize_schedule_history(pd.DataFrame([
            _history_row("ETA", "2026-03-01", "2026-03-05", "2026-02-01", his_no="H1"),
            _history_row("ETA", "2026-03-05", "2026-03-03", "2026-02-02", his_no="H2"),
            _history_row("ETA", "2026-03-03", "2026-03-03", "2026-02-03", his_no="H3"),
        ]))
        directions = list(df.sort_values("ins_datetime")["change_direction"])
        assert directions == ["DELAYED", "ADVANCED", "NO_CHANGE"]
        actual = df[df["is_actual_change"]]
        assert len(actual) == 2  # NO_CHANGE 행은 실제 변경 아님

    def test_rows_without_his_no_deduped_to_last(self):
        # his_no가 모두 비어 있으면 (transport_key, his_type, his_no) 기준
        # 전부 중복으로 간주되어 마지막 행만 남는다. 현재 동작을 기록한다.
        df = normalize_schedule_history(pd.DataFrame([
            _history_row("ETA", "2026-03-01", "2026-03-05", "2026-02-01"),
            _history_row("ETA", "2026-03-05", "2026-03-09", "2026-02-02"),
        ]))
        assert len(df) == 1
        assert df.iloc[0]["to_date"] == pd.Timestamp("2026-03-09")

    def test_rows_without_to_date_or_ins_datetime_dropped(self):
        df = normalize_schedule_history(pd.DataFrame([
            _history_row("ETA", None, None, "2026-01-01"),
            _history_row("ETA", None, "2026-03-01", None),
            _history_row("ETA", None, "2026-03-01", "2026-01-01"),
        ]))
        assert len(df) == 1

    def test_duplicates_keep_last(self):
        df = normalize_schedule_history(pd.DataFrame([
            _history_row("ETA", "2026-03-01", "2026-03-05", "2026-02-01", his_no="H1"),
            _history_row("ETA", "2026-03-01", "2026-03-07", "2026-02-02", his_no="H1"),
        ]))
        assert len(df) == 1
        assert df.iloc[0]["to_date"] == pd.Timestamp("2026-03-07")

    def test_transport_key_built(self):
        df = normalize_schedule_history(pd.DataFrame([
            _history_row("ETA", None, "2026-03-01", "2026-01-01"),
        ]))
        assert df.iloc[0]["transport_key"] == "SKBA|P1|TRPR001"


class TestBuildScheduleMetrics:
    NOW = pd.Timestamp("2026-02-20")

    def _snapshot(self, **overrides):
        row = {
            "transport_key": "SKBA|P1|TRPR001",
            "trpr_no": "TRPR001",
            "current_etd": pd.NaT,
            "current_eta": pd.NaT,
            "actual_atd": pd.NaT,
            "actual_ata": pd.NaT,
        }
        row.update(overrides)
        return pd.DataFrame([row])

    def test_empty_snapshot_returns_empty(self):
        result = build_schedule_metrics(pd.DataFrame(), pd.DataFrame())
        assert result.empty

    def test_empty_history_produces_zero_stats(self):
        result = build_schedule_metrics(
            self._snapshot(), pd.DataFrame(), now=self.NOW,
        )
        record = result.iloc[0]
        assert record["etd_change_count"] == 0
        assert record["etd_delay_count_recent"] == 0
        assert record["etd_net_delay_days"] is None
        assert record["planned_lead_time_days"] is None

    def test_delay_counts_exclude_initial_and_no_change(self):
        history = pd.DataFrame([
            # 최초 등록행 (fr_date 없음) — 변경 카운트에서 제외
            _history_row("ETA", None, "2026-03-01", "2026-01-01", his_no="H1"),
            # 실제 지연 +4일, recent window 안
            _history_row("ETA", "2026-03-01", "2026-03-05", "2026-02-19", his_no="H2"),
            # NO_CHANGE — 실제 변경 아님
            _history_row("ETA", "2026-03-05", "2026-03-05", "2026-02-20", his_no="H3"),
        ])
        result = build_schedule_metrics(
            self._snapshot(), history, now=self.NOW,
        )
        record = result.iloc[0]
        assert record["eta_change_count"] == 1
        assert record["eta_delay_count"] == 1
        assert record["eta_delay_count_recent"] == 1
        assert record["eta_advance_count"] == 0
        assert record["eta_gross_delay_days"] == 4
        assert record["eta_initial"] == pd.Timestamp("2026-03-01")
        # snapshot current_eta가 없으면 최신 이력 to_date가 current
        assert record["eta_current"] == pd.Timestamp("2026-03-05")
        assert record["eta_net_delay_days"] == 4

    def test_recent_window_filters_old_delays(self):
        history = pd.DataFrame([
            _history_row("ETD", None, "2026-02-01", "2026-01-01", his_no="H1"),
            # 30일 전 지연 — recent window(14일) 밖
            _history_row("ETD", "2026-02-01", "2026-02-03", "2026-01-21", his_no="H2"),
            # 최근 지연
            _history_row("ETD", "2026-02-03", "2026-02-05", "2026-02-19", his_no="H3"),
        ])
        result = build_schedule_metrics(
            self._snapshot(), history, now=self.NOW, recent_window_days=14,
        )
        record = result.iloc[0]
        assert record["etd_delay_count"] == 2
        assert record["etd_delay_count_recent"] == 1

    def test_advance_counted_separately(self):
        history = pd.DataFrame([
            _history_row("ETA", None, "2026-03-10", "2026-01-01", his_no="H1"),
            _history_row("ETA", "2026-03-10", "2026-03-06", "2026-02-19", his_no="H2"),
        ])
        result = build_schedule_metrics(
            self._snapshot(), history, now=self.NOW,
        )
        record = result.iloc[0]
        assert record["eta_advance_count"] == 1
        assert record["eta_delay_count"] == 0
        assert record["eta_net_delay_days"] == -4

    def test_lead_time_calculation(self):
        snapshot = self._snapshot(
            current_etd=pd.Timestamp("2026-02-03"),
            current_eta=pd.Timestamp("2026-03-08"),
        )
        history = pd.DataFrame([
            _history_row("ETD", None, "2026-02-01", "2026-01-01", his_no="E1"),
            _history_row("ETA", None, "2026-03-01", "2026-01-01", his_no="A1"),
        ])
        result = build_schedule_metrics(snapshot, history, now=self.NOW)
        record = result.iloc[0]
        assert record["planned_lead_time_days"] == 28   # 03-01 - 02-01
        assert record["projected_lead_time_days"] == 33  # 03-08 - 02-03
        assert record["lead_time_variance_days"] == 5

    def test_actual_lead_time(self):
        snapshot = self._snapshot(
            actual_atd=pd.Timestamp("2026-02-02"),
            actual_ata=pd.Timestamp("2026-03-10"),
        )
        result = build_schedule_metrics(snapshot, pd.DataFrame(), now=self.NOW)
        assert result.iloc[0]["actual_lead_time_days"] == 36

    def test_metrics_only_for_matching_transport(self):
        snapshot = self._snapshot()
        history = pd.DataFrame([
            _history_row("ETA", "2026-03-01", "2026-03-09", "2026-02-19",
                         trpr_no="OTHER", his_no="H1"),
        ])
        result = build_schedule_metrics(snapshot, history, now=self.NOW)
        assert result.iloc[0]["eta_change_count"] == 0


class TestDeliveryRequestDateSnapshot:
    """dlvy_req_date는 운송 내 가장 이른 값(최소)이 대표 — 보수적 판정."""

    def test_min_request_date_used(self):
        snapshot = build_transport_snapshot(pd.DataFrame([
            _info_row(po_no="PO001", dlvy_req_date="2026-04-10T00:00:00"),
            _info_row(po_no="PO002", dlvy_req_date="2026-03-24T00:00:00"),
        ]))
        assert snapshot.iloc[0]["delivery_request_date"] == pd.Timestamp(
            "2026-03-24"
        )

    def test_request_date_with_missing_rows(self):
        snapshot = build_transport_snapshot(pd.DataFrame([
            _info_row(po_no="PO001", dlvy_req_date=None),
            _info_row(po_no="PO002", dlvy_req_date="2026-03-24T00:00:00"),
        ]))
        assert snapshot.iloc[0]["delivery_request_date"] == pd.Timestamp(
            "2026-03-24"
        )

    def test_all_missing_request_date_is_nat(self):
        snapshot = build_transport_snapshot(pd.DataFrame([
            _info_row(dlvy_req_date=None),
        ]))
        assert pd.isna(snapshot.iloc[0]["delivery_request_date"])

    def test_delivery_eta_first_non_null_kept(self):
        snapshot = build_transport_snapshot(pd.DataFrame([
            _info_row(po_no="PO001", dlvy_eta=None),
            _info_row(po_no="PO002", dlvy_eta="20260316000000"),
        ]))
        assert snapshot.iloc[0]["delivery_eta"] == pd.Timestamp("2026-03-16")


class TestDeliveryActualCompleted:
    """dlvy_ata(납품 실적)가 있으면 완료 운송으로 제외."""

    def test_dlvy_ata_excluded_from_active(self):
        snapshot = build_transport_snapshot(pd.DataFrame([
            _info_row(trpr_no="T1", dlvy_ata="20260310000000"),
            _info_row(trpr_no="T2"),
        ]))
        assert sorted(snapshot["trpr_no"]) == ["T2"]

    def test_dlvy_ata_kept_when_not_active_only(self):
        snapshot = build_transport_snapshot(
            pd.DataFrame([_info_row(trpr_no="T1", dlvy_ata="20260310000000")]),
            active_only=False,
        )
        assert len(snapshot) == 1
        assert snapshot.iloc[0]["completed"]
        assert snapshot.iloc[0]["delivery_actual_date"] == pd.Timestamp(
            "2026-03-10"
        )

    def test_cmpl_and_ata_still_excluded(self):
        snapshot = build_transport_snapshot(pd.DataFrame([
            _info_row(trpr_no="T1", cmpl_yn="Y"),
            _info_row(trpr_no="T2", ata="2026-03-10"),
            _info_row(trpr_no="T3"),
        ]))
        assert sorted(snapshot["trpr_no"]) == ["T3"]


class TestStaleTransportExclusion:
    """current_eta가 today-ACTIVE_STALE_DAYS(기본 30)보다 과거면 제외."""

    def test_boundary_29_30_31_days(self):
        snapshot = build_transport_snapshot(pd.DataFrame([
            _info_row(trpr_no="T29", eta=_days_ago(29)),
            _info_row(trpr_no="T30", eta=_days_ago(30)),
            _info_row(trpr_no="T31", eta=_days_ago(31)),
        ]))
        # cutoff(30일 전) 당일은 제외하지 않는다 (< 비교).
        assert sorted(snapshot["trpr_no"]) == ["T29", "T30"]

    def test_stale_not_applied_when_not_active_only(self):
        snapshot = build_transport_snapshot(
            pd.DataFrame([_info_row(trpr_no="T1", eta=_days_ago(90))]),
            active_only=False,
        )
        assert len(snapshot) == 1

    def test_missing_eta_kept(self):
        snapshot = build_transport_snapshot(pd.DataFrame([
            _info_row(trpr_no="T1", eta=None),
        ]))
        assert len(snapshot) == 1

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("ACTIVE_STALE_DAYS", "7")
        snapshot = build_transport_snapshot(pd.DataFrame([
            _info_row(trpr_no="T6", eta=_days_ago(6)),
            _info_row(trpr_no="T8", eta=_days_ago(8)),
        ]))
        assert sorted(snapshot["trpr_no"]) == ["T6"]

    def test_eta_date_preferred_for_stale_check(self):
        # eta_date가 있으면 eta보다 우선한다.
        snapshot = build_transport_snapshot(pd.DataFrame([
            _info_row(
                trpr_no="T1",
                eta=_days_ago(90),
                eta_date=_days_ago(5),
            ),
        ]))
        assert len(snapshot) == 1


class TestSearchFieldAggregation:
    """sppl_names/item_names(최대 3개+외 N), item_cds 집계."""

    def test_unique_and_sorted(self):
        snapshot = build_transport_snapshot(
            pd.DataFrame([
                _info_row(
                    po_no="PO1",
                    sppl_nm="공급B", item_nm="품목B", item_cd="IB",
                ),
                _info_row(
                    po_no="PO2",
                    sppl_nm="공급A", item_nm="품목A", item_cd="IA",
                ),
                _info_row(
                    po_no="PO3",
                    sppl_nm="공급A", item_nm="품목A", item_cd="IA",
                ),
            ]),
            active_only=False,
        )
        record = snapshot.iloc[0]
        assert record["sppl_names"] == "공급A, 공급B"
        assert record["item_names"] == "품목A, 품목B"
        assert record["item_cds"] == ["IA", "IB"]

    def test_cap_at_three_with_overflow_count(self):
        rows = [
            _info_row(
                po_no=f"PO{i}",
                sppl_nm=f"공급{i}", item_nm=f"품목{i}", item_cd=f"I{i}",
            )
            for i in range(5)
        ]
        snapshot = build_transport_snapshot(
            pd.DataFrame(rows), active_only=False,
        )
        record = snapshot.iloc[0]
        assert record["sppl_names"] == "공급0, 공급1, 공급2 외 2개"
        assert record["item_names"] == "품목0, 품목1, 품목2 외 2개"
        assert record["item_cds"] == ["I0", "I1", "I2", "I3", "I4"]

    def test_missing_columns_give_empty_values(self):
        snapshot = build_transport_snapshot(
            pd.DataFrame([_info_row()]), active_only=False,
        )
        record = snapshot.iloc[0]
        # sppl_nm/item_nm 컬럼은 없고 item_cd만 있는 입력
        assert record["sppl_names"] == ""
        assert record["item_names"] == ""
        assert record["item_cds"] == ["ITEM001"]

    def test_blank_values_ignored(self):
        snapshot = build_transport_snapshot(
            pd.DataFrame([
                _info_row(po_no="PO1", sppl_nm="  ", item_nm=None),
                _info_row(po_no="PO2", sppl_nm="공급A", item_nm="품목A"),
            ]),
            active_only=False,
        )
        record = snapshot.iloc[0]
        assert record["sppl_names"] == "공급A"
        assert record["item_names"] == "품목A"


class TestPoNosAggregation:
    def test_po_nos_unique_capped_at_five(self):
        rows = [
            _info_row(po_no=f"PO{i}") for i in range(7)
        ]
        snapshot = build_transport_snapshot(
            pd.DataFrame(rows), active_only=False,
        )
        assert snapshot.iloc[0]["po_nos"] == (
            "PO0, PO1, PO2, PO3, PO4 외 2개"
        )

    def test_po_nos_within_limit(self):
        snapshot = build_transport_snapshot(
            pd.DataFrame([
                _info_row(po_no="PO2"),
                _info_row(po_no="PO1"),
                _info_row(po_no="PO1"),
            ]),
            active_only=False,
        )
        assert snapshot.iloc[0]["po_nos"] == "PO1, PO2"

    def test_po_nos_missing_column_is_empty(self):
        df = pd.DataFrame([_info_row()]).drop(columns=["po_no"])
        snapshot = build_transport_snapshot(df, active_only=False)
        assert snapshot.iloc[0]["po_nos"] == ""
