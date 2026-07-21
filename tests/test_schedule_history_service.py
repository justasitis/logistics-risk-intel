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
        "etd": "2026-02-01",
        "eta": "2026-03-01",
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
            _info_row(eta_date="2026-03-15", eta="2026-03-01"),
        ]))
        assert snapshot.iloc[0]["current_eta"] == pd.Timestamp("2026-03-15")


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
