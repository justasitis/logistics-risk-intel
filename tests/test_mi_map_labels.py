"""지도 라벨(간결 문구) 생성 + map-zones short_label 연동 테스트."""
from __future__ import annotations

import json

import pytest

from backend.app.core import marinesia_settings
from backend.app.services import mi_event_registry, mi_location_resolver
from backend.app.services import mi_map_labels as svc


@pytest.fixture
def sharepoint_root(tmp_path, monkeypatch):
    root = tmp_path / "LogisticsRisk"
    root.mkdir(parents=True)  # resolve_synced_path의 이름 치환 방지 (존재하면 그대로 사용)
    monkeypatch.setenv("MARINESIA_SHAREPOINT_ROOT", str(root))
    marinesia_settings.get_marinesia_settings.cache_clear()
    yield root
    marinesia_settings.get_marinesia_settings.cache_clear()


def _set_actify_env(monkeypatch):
    monkeypatch.setenv("ACTIFY_BASE_URL", "http://fake")
    monkeypatch.setenv("ACTIFY_API_KEY", "fake")
    monkeypatch.setenv("ACTIFY_USER", "tester")


EVENTS = [
    {
        "event_id": "EV-1",
        "headline": "홍해 회랑 긴장 지속",
        "summary": "요약",
        "severity": "HIGH",
        "status": "ACTIVE",
        "locations": ["RED_SEA"],
        "corridors": ["ASIA_EUROPE"],
    },
    {
        "event_id": "EV-2",
        "headline": "해소된 이벤트",
        "summary": "요약",
        "severity": "LOW",
        "status": "RESOLVED",
        "locations": [],
        "corridors": [],
    },
]


def test_load_map_labels_missing_file(sharepoint_root):
    assert svc.load_map_labels() == {}


def test_generate_map_labels_success(sharepoint_root, monkeypatch):
    _set_actify_env(monkeypatch)
    answer = json.dumps(
        {
            "labels": [
                {"event_id": "EV-1", "short_label": "홍해 통항 리스크"},
                {"event_id": "EV-GHOST", "short_label": "유령 이벤트"},  # 미등록 제외
                {"event_id": "EV-2", "short_label": "해소 건"},          # RESOLVED 제외
            ]
        },
        ensure_ascii=False,
    )
    monkeypatch.setattr(
        svc.ActifyClient,
        "call",
        lambda self, prompt, conversation_id="": type(
            "R", (), {"answer": answer, "conversation_id": ""}
        )(),
    )
    labels = svc.generate_map_labels(EVENTS)
    assert labels == {"EV-1": "홍해 통항 리스크"}
    # 파일 저장 확인
    saved = json.loads(
        (sharepoint_root / "MI" / "map_labels.json").read_text(encoding="utf-8")
    )
    assert saved["labels"] == {"EV-1": "홍해 통항 리스크"}
    assert svc.load_map_labels() == {"EV-1": "홍해 통항 리스크"}


def test_generate_map_labels_truncates_long_label(sharepoint_root, monkeypatch):
    _set_actify_env(monkeypatch)
    long_label = "가" * 40
    answer = json.dumps(
        {"labels": [{"event_id": "EV-1", "short_label": long_label}]},
        ensure_ascii=False,
    )
    monkeypatch.setattr(
        svc.ActifyClient,
        "call",
        lambda self, prompt, conversation_id="": type(
            "R", (), {"answer": answer, "conversation_id": ""}
        )(),
    )
    labels = svc.generate_map_labels(EVENTS)
    assert len(labels["EV-1"]) == svc.MAX_LABEL_LEN


def test_map_zones_include_short_label(sharepoint_root, tmp_path, monkeypatch):
    # 위치 마스터 + 레지스트리 + 라벨 파일 준비
    master = {
        "RED_SEA": {
            "name": "Red Sea",
            "location_type": "SEA_AREA",
            "lat": 20.5,
            "lon": 38.5,
            "default_radius_km": 500,
        }
    }
    master_path = tmp_path / "master.json"
    master_path.write_text(json.dumps(master, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(mi_location_resolver, "MASTER_PATH", master_path)

    registry_path = tmp_path / "mi_event_registry.json"
    registry_path.write_text(
        json.dumps(
            {"reference_date": "2026-08-04", "events": EVENTS},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "backend.app.services.mi_map_labels.load_map_labels",
        lambda: {"EV-1": "홍해 통항 리스크"},
    )

    zones = mi_event_registry.map_zones(registry_file=registry_path)
    assert len(zones) == 1
    assert zones[0]["short_label"] == "홍해 통항 리스크"
