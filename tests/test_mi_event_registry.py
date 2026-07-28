"""MI 이벤트 레지스트리: 날짜 파싱, 시그니처 매칭, 생명주기, 멱등 리빌드."""
import json
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from api_server import app
from backend.app.services import mi_event_registry as reg

# TestClient는 앱 낸부(ASGI) 호출 — conftest의 httpx 차단 복원
_REAL_HTTPX_REQUEST = httpx.Client.request


@pytest.fixture(autouse=True)
def _allow_testclient_http(monkeypatch):
    monkeypatch.setattr(httpx.Client, "request", _REAL_HTTPX_REQUEST)


def _candidate(cid, headline, locs, hint="", keywords=None, severity="HIGH"):
    return {
        "candidate_id": cid,
        "headline": headline,
        "short_summary": f"{headline} 요약",
        "cluster_hint": hint,
        "location_mentions": locs,
        "corridor_mentions": ["ASIA_EUROPE"],
        "risk_keyword_hints": keywords or [],
        "severity": severity,
        "evidence": [{"article_id": f"A-{cid}", "url": f"https://x/{cid}", "title": cid}],
    }


def _write_day(directory, name, candidates, generated_at=None):
    payload = {"schema_version": "1.0", "candidates": candidates}
    if generated_at:
        payload["generated_at"] = generated_at
    (directory / name).write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


@pytest.fixture()
def series(tmp_path, monkeypatch):
    current = tmp_path / "current"
    current.mkdir()
    registry_file = tmp_path / "mi_event_registry.json"
    monkeypatch.setenv("MI_EVENT_REGISTRY_FILE", str(registry_file))
    return current, registry_file


# ---------- 날짜 파싱 ----------

def test_parse_file_date(tmp_path):
    path = tmp_path / "external_mi_candidates_260713.json"
    assert reg.parse_file_date(path, {}) == date(2026, 7, 13)
    plain = tmp_path / "external_mi_candidates.json"
    assert reg.parse_file_date(plain, {"generated_at": "2026-07-19T04:00:00Z"}) == date(2026, 7, 19)
    assert reg.parse_file_date(plain, {}) is None


# ---------- 시그니처 매칭 ----------

def test_match_same_locations_strong():
    a = _candidate("C1", "홍해 선박 공격", ["Red Sea"], hint="red-sea-attack")
    b = _candidate("C2", "홍해 공격 확대", ["Red Sea"], hint="hormuz-tension")
    matched, _ = reg._is_match(
        reg._location_set(a), reg._token_set(a),
        reg._location_set(b), reg._token_set(b),
    )
    assert matched  # 위치 집합 동일 → 강한 신호


def test_match_shared_location_and_similar_tokens():
    a = _candidate("C1", "홍해 선박 공격 재개", ["Red Sea", "Yemen"], hint="red-sea-attack")
    b = _candidate("C2", "홍해 선박 공격 확대", ["Red Sea"], hint="red-sea-attack")
    matched, _ = reg._is_match(
        reg._location_set(a), reg._token_set(a),
        reg._location_set(b), reg._token_set(b),
    )
    assert matched  # 공유 위치 1개 + 유사도 충족


def test_no_match_different_locations():
    a = _candidate("C1", "홍해 선박 공격", ["Red Sea"], hint="red-sea-attack")
    b = _candidate("C2", "홍해 선박 공격", ["Strait of Hormuz"], hint="red-sea-attack")
    matched, _ = reg._is_match(
        reg._location_set(a), reg._token_set(a),
        reg._location_set(b), reg._token_set(b),
    )
    assert not matched  # 위치가 완전히 다름


def test_no_location_requires_higher_similarity():
    a = _candidate("C1", "글로벌 해운 운임 급등", [], hint="freight-rate-surge")
    same = _candidate("C2", "글로벌 해운 운임 급등", [], hint="freight-rate-surge")
    other = _candidate("C3", "파나마 운하 통행 제한", [], hint="panama-canal")
    assert reg._is_match(
        reg._location_set(a), reg._token_set(a),
        reg._location_set(same), reg._token_set(same),
    )[0]
    assert not reg._is_match(
        reg._location_set(a), reg._token_set(a),
        reg._location_set(other), reg._token_set(other),
    )[0]


# ---------- 리빌드 + 생명주기 + 멱등 ----------

def test_rebuild_lifecycle_and_idempotent(series):
    current, registry_file = series
    # 7/13: 홍해 사건 첫 목격
    _write_day(current, "external_mi_candidates_260713.json",
               [_candidate("C1", "홍해 선박 공격", ["Red Sea"], hint="red-sea-attack")])
    # 7/14: 동일 사건 재목격 (매칭) + 신규 사건
    _write_day(current, "external_mi_candidates_260714.json", [
        _candidate("C2", "홍해 선박 공격", ["Red Sea"], hint="red-sea-attack", severity="CRITICAL"),
        _candidate("C3", "수에즈 운하 혼잡", ["Suez Canal"], hint="suez-congestion"),
    ])
    # 7/19(기준일): 수에즈만 재목격 → 홍해는 5일 미목격 ACTIVE, 오래된 건은 아래 케이스에서
    _write_day(current, "external_mi_candidates_260719.json",
               [_candidate("C4", "수에즈 운하 혼잡", ["Suez Canal"], hint="suez-congestion")])

    result = reg.rebuild_registry(current_dir=current, registry_file=registry_file)
    assert result["files_processed"] == 3
    assert result["reference_date"] == "2026-07-19"
    data = json.loads(registry_file.read_text(encoding="utf-8"))
    events = {e["headline"]: e for e in data["events"]}
    redsea = events["홍해 선박 공격"]
    assert redsea["first_seen"] == "2026-07-13"
    assert redsea["last_seen"] == "2026-07-14"
    assert redsea["sighting_count"] == 2
    assert redsea["severity"] == "CRITICAL"  # 상승분 갱신
    assert redsea["status"] == "ACTIVE"  # 5일 미목격
    assert set(redsea["source_candidate_ids"]) == {"C1", "C2"}
    assert len(redsea["evidence"]) == 2
    suez = events["수에즈 운하 혼잡"]
    assert suez["sighting_dates"] == ["2026-07-14", "2026-07-19"]

    # 멱등: 재실행 결과 동일
    reg.rebuild_registry(current_dir=current, registry_file=registry_file)
    again = json.loads(registry_file.read_text(encoding="utf-8"))
    assert again == data


@pytest.mark.parametrize(
    "silent_days,expected",
    [(6, "ACTIVE"), (7, "IMPROVING"), (13, "IMPROVING"), (14, "RESOLVED")],
)
def test_lifecycle_boundaries(series, silent_days, expected):
    current, registry_file = series
    from datetime import timedelta

    first = date(2026, 7, 1)
    name = f"external_mi_candidates_{str(first)[2:].replace('-', '')}.json"
    _write_day(current, name, [_candidate("C1", "테스트 사건", ["Red Sea"], hint="red-sea-attack")])
    ref = first + timedelta(days=silent_days)
    name2 = f"external_mi_candidates_{str(ref)[2:].replace('-', '')}.json"
    _write_day(current, name2, [_candidate("C2", "다른 사건", ["Suez Canal"], hint="suez")])
    reg.rebuild_registry(current_dir=current, registry_file=registry_file)
    data = json.loads(registry_file.read_text(encoding="utf-8"))
    event = next(e for e in data["events"] if e["headline"] == "테스트 사건")
    assert event["status"] == expected


def test_reactivation(series):
    current, registry_file = series
    _write_day(current, "external_mi_candidates_260701.json",
               [_candidate("C1", "재활성 사건", ["Red Sea"], hint="red-sea-attack")])
    _write_day(current, "external_mi_candidates_260719.json",
               [_candidate("C2", "다른 사건", ["Suez Canal"], hint="suez")])
    reg.rebuild_registry(current_dir=current, registry_file=registry_file)
    data = json.loads(registry_file.read_text(encoding="utf-8"))
    event = next(e for e in data["events"] if e["headline"] == "재활성 사건")
    assert event["status"] == "RESOLVED"

    # 14일 이후 재목격 → ACTIVE 재활성화
    _write_day(current, "external_mi_candidates_260720.json",
               [_candidate("C3", "재활성 사건", ["Red Sea"], hint="red-sea-attack")])
    reg.rebuild_registry(current_dir=current, registry_file=registry_file)
    data = json.loads(registry_file.read_text(encoding="utf-8"))
    event = next(e for e in data["events"] if e["headline"] == "재활성 사건")
    assert event["status"] == "ACTIVE"
    assert event["reactivated"] is True


def test_evidence_cap(series, monkeypatch):
    current, registry_file = series
    monkeypatch.setenv("MI_REGISTRY_MAX_EVIDENCE", "3")
    candidates = []
    for i in range(5):
        cand = _candidate(f"C{i}", "같은 사건", ["Red Sea"], hint="red-sea-attack")
        cand["evidence"] = [{"article_id": f"A{i}", "url": f"https://x/{i}", "title": str(i)}]
        candidates.append(cand)
    _write_day(current, "external_mi_candidates_260719.json", candidates)
    reg.rebuild_registry(current_dir=current, registry_file=registry_file)
    data = json.loads(registry_file.read_text(encoding="utf-8"))
    assert len(data["events"][0]["evidence"]) == 3


# ---------- API ----------

def test_api_registry(series):
    current, _ = series
    import backend.app.api  # noqa: F401

    # api_server의 엔드포인트는 서비스 기본 경로를 쓰므로 MI_CURRENT_DIR도 설정
    import os
    os.environ["MI_CURRENT_DIR"] = str(current)
    try:
        _write_day(current, "external_mi_candidates_260719.json",
                   [_candidate("C1", "홍해 선박 공격", ["Red Sea"], hint="red-sea-attack")])
        client = TestClient(app)
        resp = client.post("/api/mi/registry/rebuild")
        assert resp.status_code == 200
        assert resp.json()["event_count"] == 1

        body = client.get("/api/mi/registry").json()
        assert body["events"][0]["status"] == "ACTIVE"
        event_id = body["events"][0]["event_id"]

        assert client.get("/api/mi/registry?status=RESOLVED").json()["events"] == []
        assert client.get(f"/api/mi/registry/{event_id}").status_code == 200
        assert client.get("/api/mi/registry/MIREG-NOPE").status_code == 404
    finally:
        os.environ.pop("MI_CURRENT_DIR", None)
