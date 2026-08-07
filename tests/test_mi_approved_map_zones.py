"""승인 MI 이벤트 지도 영향권(/api/mi/approved/map-zones) 테스트."""
from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from api_server import app
from backend.app.services import mi_approved_map as svc

_REAL_HTTPX_REQUEST = httpx.Client.request


@pytest.fixture(autouse=True)
def _allow_testclient_http(monkeypatch):
    monkeypatch.setattr(httpx.Client, "request", _REAL_HTTPX_REQUEST)


def _event(event_id: str, **overrides):
    event = {
        "event_id": event_id,
        "headline": f"헤드라인 {event_id}",
        "severity": "HIGH",
        "status": "ACTIVE",
        "valid_from": "2026-08-01",
        "valid_to": None,
        "affected_locations": [
            {
                "code": "RED_SEA",
                "name": "Red Sea",
                "location_type": "SEA_AREA",
                "lat": 20.5,
                "lon": 38.5,
                "radius_km": 500.0,
            }
        ],
    }
    event.update(overrides)
    return event


def _write_run(store: Path, analysis_id: str, payload: dict, mtime: int) -> None:
    path = store / f"{analysis_id}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.utime(path, (mtime, mtime))


def _canonical(events: list[dict]) -> dict:
    return {"schema_version": "1.0", "events": events}


@pytest.fixture()
def run_store(tmp_path, monkeypatch):
    store = tmp_path / "mi_runs"
    store.mkdir()
    monkeypatch.setenv("MI_RUN_STORE_DIR", str(store))
    return store


@pytest.fixture(autouse=True)
def _no_labels(monkeypatch):
    monkeypatch.setattr(svc, "load_map_labels", lambda: {})


def test_latest_canonical_run_only(run_store):
    _write_run(
        run_store, "old", {"canonical_payload": _canonical([_event("EV-OLD")])}, mtime=100
    )
    _write_run(
        run_store, "new", {"canonical_payload": _canonical([_event("EV-NEW")])}, mtime=200
    )
    zones = svc.approved_map_zones()
    assert [z["event_id"] for z in zones] == ["EV-NEW"]


def test_skips_runs_without_canonical(run_store):
    # response만 있는 run(미검토)은 건드너뛰고 canonical run 사용
    _write_run(
        run_store,
        "unreviewed",
        {"response": {"events": [_event("EV-RAW")]}},
        mtime=300,
    )
    _write_run(
        run_store, "reviewed", {"canonical_payload": _canonical([_event("EV-OK")])}, mtime=100
    )
    zones = svc.approved_map_zones()
    assert [z["event_id"] for z in zones] == ["EV-OK"]


def test_event_without_locations_excluded(run_store):
    _write_run(
        run_store,
        "run",
        {
            "canonical_payload": _canonical(
                [
                    _event("EV-NOLOC", affected_locations=[]),
                    _event("EV-LOC"),
                ]
            )
        },
        mtime=100,
    )
    zones = svc.approved_map_zones()
    assert [z["event_id"] for z in zones] == ["EV-LOC"]
    loc = zones[0]["locations"][0]
    assert loc["code"] == "RED_SEA"
    assert loc["lat"] == 20.5 and loc["radius_km"] == 500.0


def test_expired_valid_to_excluded(run_store):
    _write_run(
        run_store,
        "run",
        {
            "canonical_payload": _canonical(
                [
                    _event("EV-EXPIRED", valid_to="2020-01-01"),
                    _event("EV-FUTURE", valid_to="2999-12-31"),
                    _event("EV-OPEN"),
                ]
            )
        },
        mtime=100,
    )
    zones = svc.approved_map_zones()
    assert {z["event_id"] for z in zones} == {"EV-FUTURE", "EV-OPEN"}


def test_short_label_attached(run_store, monkeypatch):
    monkeypatch.setattr(
        svc, "load_map_labels", lambda: {"EV-LABELED": "홍해 통항 리스크"}
    )
    _write_run(
        run_store,
        "run",
        {
            "canonical_payload": _canonical(
                [_event("EV-LABELED"), _event("EV-UNLABELED")]
            )
        },
        mtime=100,
    )
    zones = svc.approved_map_zones()
    by_id = {z["event_id"]: z for z in zones}
    assert by_id["EV-LABELED"]["short_label"] == "홍해 통항 리스크"
    assert by_id["EV-UNLABELED"]["short_label"] == ""


def test_empty_store_returns_empty(run_store):
    assert svc.approved_map_zones() == []


def test_api_approved_map_zones(run_store):
    _write_run(
        run_store, "run", {"canonical_payload": _canonical([_event("EV-1")])}, mtime=100
    )
    client = TestClient(app)
    resp = client.get("/api/mi/approved/map-zones")
    assert resp.status_code == 200
    zones = resp.json()
    assert len(zones) == 1
    assert zones[0]["event_id"] == "EV-1"
    assert zones[0]["status"] == "ACTIVE"


def test_api_approved_map_zones_empty_store(run_store):
    client = TestClient(app)
    resp = client.get("/api/mi/approved/map-zones")
    assert resp.status_code == 200
    assert resp.json() == []
