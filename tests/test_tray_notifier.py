"""트레이 알림박스 핵심 로직 테스트 (UI 없이 순수 로직만)."""
import json

import pytest

from tray import notifier_core as core


class _FakeResponse:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload or {}

    def json(self):
        return self._payload


def _feed(items, computed_at="2026-07-19T09:00:00"):
    return {"computed_at": computed_at, "cache_hit": False, "items": items}


def _item(hbl, alerts):
    return {"hbl_no": hbl, "label": "", "alerts": alerts}


def _alert(atype="DELIVERY_REQ_BREACH", severity="HIGH", message="납기 초과 +9일", value=9):
    return {"type": atype, "severity": severity, "message": message, "value": value}


# ---------- fetch ----------

def test_fetch_alerts_ok(monkeypatch):
    monkeypatch.setattr(
        core.requests, "get",
        lambda url, timeout: _FakeResponse(200, _feed([_item("H1", [_alert()])])),
    )
    result = core.fetch_alerts("http://x")
    assert result is not None
    computed_at, items = result
    assert computed_at == "2026-07-19T09:00:00"
    assert items[0]["hbl_no"] == "H1"


def test_fetch_alerts_backend_down(monkeypatch):
    import requests as real_requests

    def _boom(url, timeout):
        raise real_requests.ConnectionError("down")

    monkeypatch.setattr(core.requests, "get", _boom)
    assert core.fetch_alerts("http://x") is None
    monkeypatch.setattr(core.requests, "get", lambda url, timeout: _FakeResponse(502))
    assert core.fetch_alerts("http://x") is None


# ---------- 서명 ----------

def test_signature_stable_and_distinct():
    a1 = core.alert_signature("H1", _alert())
    a2 = core.alert_signature("H1", _alert())
    assert a1 == a2
    assert a1 != core.alert_signature("H1", _alert(message="납기 초과 +10일", value=10))
    assert a1 != core.alert_signature("H2", _alert())


# ---------- diff ----------

def test_diff_first_run_silent():
    items = [_item("H1", [_alert()])]
    new, state = core.diff_new(
        {"initialized": False, "signatures": []}, items, "t1"
    )
    assert new == []  # 최초 실행은 무음 (상태만 저장)
    assert state["initialized"] is True
    assert len(state["signatures"]) == 1

    # 두 번째 실행에 같은 알림이면 신규 없음
    new2, _ = core.diff_new(state, items, "t2")
    assert new2 == []


def test_diff_only_new_alerts():
    items = [_item("H1", [_alert()])]
    _, state = core.diff_new({"initialized": False, "signatures": []}, items, "t1")

    # 기존 알림 유지 + 새 알림 추가
    items2 = [
        _item("H1", [_alert()]),
        _item("H2", [_alert(atype="SIGNAL", message="이상 신호", value=1)]),
    ]
    new, state2 = core.diff_new(state, items2, "t2")
    assert len(new) == 1
    assert new[0]["hbl_no"] == "H2"

    # 기존 알림 소멸 → 서명 제거
    _, state3 = core.diff_new(state2, [_item("H1", [_alert()])], "t3")
    assert len(state3["signatures"]) == 1


# ---------- 상태 파일 ----------

def test_state_roundtrip(tmp_path):
    path = tmp_path / "tray_state.json"
    assert core.load_state(path)["initialized"] is False
    state = {"initialized": True, "signatures": ["a", "b"], "last_computed_at": "t"}
    core.save_state(path, state)
    assert core.load_state(path) == state

    # 깨진 파일은 초기 상태로
    path.write_text("{broken", encoding="utf-8")
    assert core.load_state(path)["initialized"] is False
