"""backend/app/services/mi_location_resolver.py 테스트.

코드/alias 해석, 미등록 코드 처리, radius 클램프(기본값의 0.5~2배),
중복 제거를 검증한다. 마스터 파일은 tmp JSON으로 주입한다.
"""
from __future__ import annotations

import json

import pytest

from backend.app.schemas.mi_ai import LocationRef
from backend.app.services import mi_location_resolver
from backend.app.services.mi_location_resolver import (
    load_location_master,
    resolve_locations,
)


MASTER = {
    "KRPUS": {
        "name": "Busan",
        "location_type": "PORT",
        "lat": 35.1,
        "lon": 129.03,
        "default_radius_km": 100,
        "aliases": ["Pusan", "부산"],
    },
    "EGSUZ": {
        "name": "Suez Canal",
        "location_type": "CANAL",
        "lat": 30.46,
        "lon": 32.35,
        "default_radius_km": 50,
    },
}


@pytest.fixture
def master_file(tmp_path, monkeypatch):
    path = tmp_path / "mi_location_master.json"
    path.write_text(
        json.dumps(MASTER, ensure_ascii=False), encoding="utf-8",
    )
    monkeypatch.setattr(mi_location_resolver, "MASTER_PATH", path)
    return path


class TestLoadLocationMaster:
    def test_missing_file_returns_empty_dict(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            mi_location_resolver,
            "MASTER_PATH",
            tmp_path / "nonexistent.json",
        )
        assert load_location_master() == {}

    def test_codes_uppercased(self, tmp_path, monkeypatch):
        path = tmp_path / "master.json"
        path.write_text(
            json.dumps({"krpus": MASTER["KRPUS"]}), encoding="utf-8",
        )
        monkeypatch.setattr(mi_location_resolver, "MASTER_PATH", path)
        assert list(load_location_master()) == ["KRPUS"]

    def test_non_object_payload_raises(self, tmp_path, monkeypatch):
        path = tmp_path / "master.json"
        path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        monkeypatch.setattr(mi_location_resolver, "MASTER_PATH", path)
        with pytest.raises(RuntimeError, match="must be an object"):
            load_location_master()


class TestResolveLocations:
    def test_resolve_by_code_case_insensitive(self, master_file):
        resolved, unresolved = resolve_locations(
            [LocationRef(code="krpus")]
        )
        assert unresolved == []
        assert len(resolved) == 1
        location = resolved[0]
        assert location.code == "KRPUS"
        assert location.name == "Busan"
        assert location.location_type == "PORT"
        assert location.lat == 35.1
        assert location.lon == 129.03
        assert location.radius_km == 100.0  # 기본 반경

    def test_resolve_by_name_and_alias(self, master_file):
        by_name, _ = resolve_locations([LocationRef(name="suez canal")])
        assert [loc.code for loc in by_name] == ["EGSUZ"]

        by_alias, _ = resolve_locations([LocationRef(name="부산")])
        assert [loc.code for loc in by_alias] == ["KRPUS"]

        by_english_alias, _ = resolve_locations([LocationRef(name="PUSAN")])
        # alias 매칭은 소문자 변환 후 비교한다.
        assert [loc.code for loc in by_english_alias] == ["KRPUS"]

    def test_unregistered_code_goes_unresolved(self, master_file):
        resolved, unresolved = resolve_locations(
            [LocationRef(code="XXXXX", name="Nowhere")]
        )
        assert resolved == []
        assert len(unresolved) == 1
        assert unresolved[0].code == "XXXXX"

    def test_radius_clamped_to_half_of_default(self, master_file):
        resolved, _ = resolve_locations(
            [LocationRef(code="KRPUS", radius_km=10)]
        )
        assert resolved[0].radius_km == 50.0  # 100 * 0.5

    def test_radius_clamped_to_double_of_default(self, master_file):
        resolved, _ = resolve_locations(
            [LocationRef(code="KRPUS", radius_km=1000)]
        )
        assert resolved[0].radius_km == 200.0  # 100 * 2.0

    def test_radius_within_range_kept(self, master_file):
        resolved, _ = resolve_locations(
            [LocationRef(code="EGSUZ", radius_km=75)]
        )
        assert resolved[0].radius_km == 75.0

    def test_duplicate_code_resolved_once(self, master_file):
        resolved, unresolved = resolve_locations([
            LocationRef(code="KRPUS"),
            LocationRef(name="부산"),  # 같은 코드로 해석됨
        ])
        assert len(resolved) == 1
        assert unresolved == []

    def test_mixed_resolved_and_unresolved(self, master_file):
        resolved, unresolved = resolve_locations([
            LocationRef(code="KRPUS"),
            LocationRef(code="UNKNOWN1"),
            LocationRef(code="EGSUZ"),
        ])
        assert [loc.code for loc in resolved] == ["KRPUS", "EGSUZ"]
        assert [ref.code for ref in unresolved] == ["UNKNOWN1"]

    def test_empty_input(self, master_file):
        resolved, unresolved = resolve_locations([])
        assert resolved == []
        assert unresolved == []
