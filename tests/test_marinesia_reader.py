"""Marinesia 신규 JSON 포맷(2026-08~, company 없음) 파싱 테스트."""
from __future__ import annotations

import json
from pathlib import Path

from backend.app.core.marinesia_settings import MarinesiaSettings
from backend.app.services.marinesia_sharepoint_reader import (
    read_marinesia_latest,
)

NEW_FORMAT_ROW = {
    "vessel_name": "AFIF",
    "imo_no": "9732345",
    "registered_mmsi_no": "211888820",
    "query_key": "9732345",
    "mmsi_changed": False,
    "record_index": 1,
    "mmsi": 211888820,
    "imo": "9732345",
    "status": 0,
    "lat": 2.8989601,
    "lng": 90.45121,
    "sog": 17.1,
    "cog": 233,
    "dest": "MAPTM",
    "ts": "2026-08-09T21:53:48",
    "fetched_at": "2026-08-10T07:15:22+00:00",
    "api_message": "Successfully fetched data",
    "api_error": False,
}

OLD_FORMAT_ROW = {
    "company": "SKBA",
    "vessel_name": "AL MANAMAH",
    "query_mmsi_no": "636093140",
    "record_index": 1,
    "mmsi": 636093140,
    "imo": 9349538,
    "status": 0,
    "lat": 49.728241,
    "lng": -8.3372936,
    "ts": "2026-08-10T02:55:54",
    "fetched_at": "2026-08-10T03:12:11+00:00",
    "api_message": "Successfully fetched data",
    "api_error": False,
}


def _settings(root: Path) -> MarinesiaSettings:
    return MarinesiaSettings(
        sharepoint_root=root,
        default_company="SKBA",
        live_hours=6.0,
        stale_warning_hours=24.0,
        max_file_size_mb=50,
    )


def _write_latest(root: Path, rows: list[dict]) -> None:
    target = root / "AIS" / "Marinesia" / "Current"
    target.mkdir(parents=True)
    (target / "marinesia_latest.json").write_text(
        json.dumps(rows), encoding="utf-8",
    )


def test_new_format_without_company(tmp_path):
    """신규 포맷: company 없이도 전체 항목이 조회되고 법인 폴� 경고가 없다."""
    _write_latest(tmp_path, [NEW_FORMAT_ROW])
    result = read_marinesia_latest(settings=_settings(tmp_path))

    assert len(result["items"]) == 1
    item = result["items"][0]
    assert item["company"] == ""
    # registered_mmsi_no가 조회 MMSI로 매핑된다
    assert item["query_mmsi_no"] == "211888820"
    assert item["mmsi_no"] == "211888820"
    assert item["imo_no"] == "9732345"
    assert item["vessel_name"] == "AFIF"
    # company 폴� 적용 경고가 사라졌다
    assert not any("기본 법인" in w for w in result["warnings"])


def test_old_format_company_preserved(tmp_path):
    """구 포맷 호환: company가 있으면 보존, query_mmsi_no 폴� 동작."""
    _write_latest(tmp_path, [OLD_FORMAT_ROW])
    result = read_marinesia_latest(settings=_settings(tmp_path))

    item = result["items"][0]
    assert item["company"] == "SKBA"
    assert item["query_mmsi_no"] == "636093140"
    assert item["imo_no"] == "9349538"


def test_company_argument_ignored(tmp_path):
    """companies 인자를 넘겨도 필터링하지 않는다 (하위호환)."""
    _write_latest(tmp_path, [NEW_FORMAT_ROW])
    result = read_marinesia_latest(
        companies=["SKO"], settings=_settings(tmp_path),
    )
    assert len(result["items"]) == 1
    assert result["filters"]["companies"] == []
