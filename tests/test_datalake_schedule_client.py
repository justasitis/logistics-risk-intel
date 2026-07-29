"""services/datalake_schedule_client.py 테스트.

회귀 배경: 법인 "SKO — 한국"(cmpy_nm='SKO' ↔ cmpy_cd='S000') 선택 시
`변경이력 필수 컬럼 누락: ['fr_date','his_type','ins_datetime','to_date']`
오류가 발생했다. 원인은 `_parse_payload_to_rows`가 Denodo의 빈 결과
페이지({"elements": []})를 falsy로 걸러 봉투 dict 자체를 1행으로
반환한 것. SKO는 운송 수가 많아 History 조회 chunk 중 0건 매칭이
발생하는데, 그때마다 가짜 행이 끼어들어 normalize가 깨졌다.

외부 HTTP는 모두 monkeypatch로 대체한다 (conftest의 차단 fixture와 무관).
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from services import datalake_schedule_client
from services.datalake_schedule_client import (
    HISTORY_SELECT_COLUMNS,
    _parse_payload_to_rows,
    fetch_bl_history_for_transports,
    fetch_bl_info,
)
from services.schedule_history_service import (
    build_schedule_metrics,
    build_transport_snapshot,
)


@pytest.fixture(autouse=True)
def _credentials(monkeypatch):
    # 모듈 상수는 import 시점에 env를 읽으므로 상수를 직접 교체한다.
    monkeypatch.setattr(
        datalake_schedule_client, "DEFAULT_USERNAME", "test",
    )
    monkeypatch.setattr(
        datalake_schedule_client, "DEFAULT_PASSWORD", "test",
    )


class _FakeResponse:
    status_code = 200
    text = "{}"

    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _mock_get(monkeypatch, handler):
    monkeypatch.setattr(
        datalake_schedule_client.requests,
        "get",
        lambda url, **kwargs: _FakeResponse(
            handler(kwargs.get("params", {}))
        ),
    )


def _history_row(trpr_no: str, his_no: str) -> dict:
    return {
        "cmpy_cd": "S000",
        "plnt_cd": "P1",
        "trpr_no": trpr_no,
        "his_type": "ETA",
        "his_no": his_no,
        "fr_date": "2026-03-01",
        "to_date": "2026-03-05",
        "ins_datetime": "2026-02-20",
        "ins_person_id": "tester",
    }


class TestParsePayloadToRows:
    def test_bare_list_passthrough(self):
        rows = [{"a": 1}, {"a": 2}]
        assert _parse_payload_to_rows(rows) == rows

    def test_envelope_with_rows(self):
        payload = {"elements": [{"a": 1}]}
        assert _parse_payload_to_rows(payload) == [{"a": 1}]

    def test_empty_elements_returns_empty_list(self):
        # 회귀: 이전에는 봉투 자체([{"elements": []}])를 반환했다.
        assert _parse_payload_to_rows({"elements": []}) == []

    def test_null_elements_returns_empty_list(self):
        assert _parse_payload_to_rows({"elements": None}) == []

    def test_other_envelope_keys(self):
        assert _parse_payload_to_rows({"data": [{"a": 1}]}) == [{"a": 1}]
        assert _parse_payload_to_rows({"rows": []}) == []
        assert _parse_payload_to_rows({"result": [{"a": 1}]}) == [{"a": 1}]

    def test_single_record_dict_without_envelope(self):
        record = {"trpr_no": "TR1", "cmpy_cd": "S000"}
        assert _parse_payload_to_rows(record) == [record]

    def test_unexpected_type_raises(self):
        with pytest.raises(RuntimeError, match="예상치 못한"):
            _parse_payload_to_rows("plain string")


class TestFetchBlInfoEmptyTrailingPage:
    def test_empty_trailing_page_not_appended(self, monkeypatch):
        # 1페이지가 page_size와 정확히 같으면 2페이지를 요청하고,
        # Denodo는 {"elements": []}를 반환한다. 이 빈 페이지가
        # 가짜 행으로 추가되지 않아야 한다.
        first_page = [
            {"trpr_no": f"TR{i:05d}", "cmpy_cd": "S000", "cmpy_nm": "SKO"}
            for i in range(1000)
        ]
        calls = {"n": 0}

        def handler(params):
            calls["n"] += 1
            if params["$start_index"] == 0:
                return {"elements": first_page}
            return {"elements": []}

        _mock_get(monkeypatch, handler)
        df = fetch_bl_info(companies=["SKO"], max_rows=5_000)

        assert calls["n"] == 2
        assert len(df) == 1000
        assert set(df["trpr_no"]) == {r["trpr_no"] for r in first_page}

    def test_company_filter_uses_cmpy_nm(self, monkeypatch):
        captured = {}

        def handler(params):
            captured.update(params)
            return {"elements": []}

        _mock_get(monkeypatch, handler)
        fetch_bl_info(companies=["SKO", "SKBA"], max_rows=1_000)
        assert "cmpy_nm = 'SKO'" in captured["$filter"]
        assert "cmpy_nm = 'SKBA'" in captured["$filter"]


class TestFetchBlHistoryEmptyChunk:
    def test_zero_match_chunk_returns_empty_with_columns(
        self, monkeypatch,
    ):
        # SKO 시나리오: 어떤 chunk의 운송들이 조회 기간 내 History가
        # 없으면 Denodo는 {"elements": []}를 반환한다.
        _mock_get(monkeypatch, lambda params: {"elements": []})

        df = fetch_bl_history_for_transports(
            [("S000", "P1", "TR260001001")],
            changed_from=date(2026, 1, 1),
        )
        assert df.empty
        assert list(df.columns) == HISTORY_SELECT_COLUMNS

    def test_sko_scenario_does_not_raise_column_error(
        self, monkeypatch,
    ):
        # 회귀: 빈 History chunk가 가짜 행을 만들어
        # "변경이력 필수 컬럼 누락" ValueError가 발생했던 경로.
        info_rows = [
            {
                "cmpy_cd": "S000", "cmpy_nm": "SKO",
                "plnt_cd": "P1", "trpr_no": "TR260001001",
                "dprt": "KRPUS", "arvl": "SIKOP",
                "etd": "2026-02-01",
                # 활성 운송이어야 하므로 ETA는 미래로 둔다.
                "eta": (
                    pd.Timestamp.now().normalize()
                    + pd.Timedelta(days=30)
                ).strftime("%Y-%m-%d"),
            }
        ]
        snapshot = build_transport_snapshot(pd.DataFrame(info_rows))

        _mock_get(monkeypatch, lambda params: {"elements": []})
        history_df = fetch_bl_history_for_transports(
            [
                (
                    str(row["cmpy_cd"]),
                    str(row["plnt_cd"]),
                    str(row["trpr_no"]),
                )
                for row in snapshot.to_dict("records")
            ],
            changed_from=date(2026, 1, 1),
        )

        metrics = build_schedule_metrics(snapshot, history_df)
        assert len(metrics) == 1
        assert metrics.iloc[0]["eta_change_count"] == 0

    def test_mixed_empty_and_nonempty_chunks(self, monkeypatch):
        keys = [
            ("S000", "P1", f"TR{i:07d}")
            for i in range(25)  # chunk_size=20 → chunk 2개
        ]

        def handler(params):
            if "TR0000000'" in params["$filter"]:
                return {"elements": [
                    _history_row("TR0000000", "H1"),
                ]}
            return {"elements": []}

        _mock_get(monkeypatch, handler)
        df = fetch_bl_history_for_transports(
            keys, changed_from=date(2026, 1, 1),
        )
        assert len(df) == 1
        assert df.iloc[0]["trpr_no"] == "TR0000000"
        assert "fr_date" in df.columns


class TestEmptyCompanyResult:
    """미존재 법인 등으로 bl_info가 0건이면 에러가 아니라 빈 결과."""

    def test_empty_info_gives_empty_snapshot_not_error(
        self, monkeypatch,
    ):
        _mock_get(monkeypatch, lambda params: {"elements": []})
        info_df = fetch_bl_info(companies=["NO_SUCH_COMPANY"])
        assert info_df.empty

        snapshot = build_transport_snapshot(info_df)
        assert snapshot.empty

    def test_non_empty_frame_still_validates_columns(self):
        with pytest.raises(ValueError, match="trpr_no"):
            build_transport_snapshot(
                pd.DataFrame([{"cmpy_cd": "S000"}])
            )


class TestCompanyMapping:
    """법인 이름↔코드 단일 정의처(COMPANY_NAME_TO_CODE)와 정규화."""

    def test_mapping_table_covers_six_companies(self):
        assert datalake_schedule_client.COMPANY_NAME_TO_CODE == {
            "SKO": "S000",
            "SKOH": "S210",
            "SKBM": "S220",
            "SKBA": "S330",
            "SKOJ": "S930",
            "SKOY": "S950",
        }

    def test_normalize_name_to_code_and_back(self):
        assert datalake_schedule_client.normalize_company_code("SKO") == "S000"
        assert datalake_schedule_client.normalize_company_code("sko") == "S000"
        assert datalake_schedule_client.normalize_company_name("S000") == "SKO"
        assert datalake_schedule_client.normalize_company_name("s000") == "SKO"

    def test_unknown_values_pass_through(self):
        assert datalake_schedule_client.normalize_company_code("NEWCO") == "NEWCO"
        assert datalake_schedule_client.normalize_company_name("S999") == "S999"
        assert datalake_schedule_client.normalize_company_name("") == ""

    def test_fetch_bl_info_accepts_company_code(self, monkeypatch):
        # 코드(S000)로 조회필터를 건 넣어도 cmpy_nm='SKO'로 정규화된다.
        captured = {}

        def handler(params):
            captured.update(params)
            return {"elements": []}

        _mock_get(monkeypatch, handler)
        fetch_bl_info(companies=["S000"], max_rows=1_000)
        assert "cmpy_nm = 'SKO'" in captured["$filter"]

    def test_fetch_bl_history_accepts_company_name(self, monkeypatch):
        captured = {}

        def handler(params):
            captured.update(params)
            return {"elements": []}

        _mock_get(monkeypatch, handler)
        datalake_schedule_client.fetch_bl_history(
            company_codes=["SKO"], max_rows=1_000,
        )
        assert "cmpy_cd = 'S000'" in captured["$filter"]


class TestHistoryChunkSizing:
    def test_default_chunk_size_is_100(self, monkeypatch):
        monkeypatch.delenv("HISTORY_CHUNK_SIZE", raising=False)
        calls = []
        _mock_get(monkeypatch, lambda params: calls.append(1) or {"elements": []})
        fetch_bl_history_for_transports(
            [("S000", "P1", f"TR{i:07d}") for i in range(150)],
        )
        assert len(calls) == 2  # 100 + 50

    def test_env_override_chunk_size(self, monkeypatch):
        monkeypatch.setenv("HISTORY_CHUNK_SIZE", "10")
        calls = []
        _mock_get(monkeypatch, lambda params: calls.append(1) or {"elements": []})
        fetch_bl_history_for_transports(
            [("S000", "P1", f"TR{i:07d}") for i in range(25)],
        )
        assert len(calls) == 3  # 10 + 10 + 5

    def test_explicit_chunk_size_still_honored(self, monkeypatch):
        calls = []
        _mock_get(monkeypatch, lambda params: calls.append(1) or {"elements": []})
        fetch_bl_history_for_transports(
            [("S000", "P1", f"TR{i:07d}") for i in range(25)],
            chunk_size=20,
        )
        assert len(calls) == 2  # 20 + 5

    def test_invalid_env_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("HISTORY_CHUNK_SIZE", "abc")
        calls = []
        _mock_get(monkeypatch, lambda params: calls.append(1) or {"elements": []})
        fetch_bl_history_for_transports(
            [("S000", "P1", f"TR{i:07d}") for i in range(150)],
        )
        assert len(calls) == 2

    def test_etd_to_filter_uses_next_day_exclusive(self, monkeypatch):
        captured = {}
        _mock_get(monkeypatch, lambda params: captured.update(params) or {"elements": []})
        fetch_bl_info(etd_to=date(2026, 7, 15))
        assert "etd < '2026-07-16'" in captured["$filter"]

    def test_etd_from_and_to_together(self, monkeypatch):
        captured = {}
        _mock_get(monkeypatch, lambda params: captured.update(params) or {"elements": []})
        fetch_bl_info(
            etd_from=date(2026, 7, 1), etd_to=date(2026, 7, 15),
        )
        assert "etd >= '2026-07-01'" in captured["$filter"]
        assert "etd < '2026-07-16'" in captured["$filter"]
