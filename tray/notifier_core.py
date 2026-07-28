"""트레이 알림박스 핵심 로직 (UI 분리 — 순수 함수/상태만, 테스트 가능).

얇은 껍데기 원칙: 알림 판단은 백엔드 GET /api/notifications가 하고,
이 모듈은 feed를 폼링해 "새 알림"만 골라낸다.

[최초 실행 동작 명세]
상태 파일이 없는 최초 폼링에서는 토스트 없이 현재 서명만 저장한다.
(기존 누적 알림이 한꺼번에 토스트로 쏟아지는 것을 방지)
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import requests

DEFAULT_SERVER_URL = "http://127.0.0.1:8000"
DEFAULT_POLL_SECONDS = 600


def server_url() -> str:
    return os.environ.get("TRAY_SERVER_URL", "").strip() or DEFAULT_SERVER_URL


def poll_seconds() -> int:
    try:
        return int(os.environ.get("TRAY_POLL_SECONDS", "").strip() or DEFAULT_POLL_SECONDS)
    except ValueError:
        return DEFAULT_POLL_SECONDS


def state_file_path() -> Path:
    """상태 파일: frozen이면 exe 옆, 아니면 tray/ 폴터."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "tray_state.json"
    return Path(__file__).resolve().parent / "tray_state.json"


# ---------- feed 조회 ----------

def fetch_alerts(
    base_url: str,
    timeout: float = 10.0,
) -> tuple[str, list[dict[str, Any]]] | None:
    """GET /api/notifications → (computed_at, items). 실패 시 None (백엔드 다운 허용)."""
    try:
        response = requests.get(
            f"{base_url.rstrip('/')}/api/notifications",
            timeout=timeout,
        )
        if response.status_code != 200:
            return None
        data = response.json()
        items = data.get("items")
        if not isinstance(items, list):
            return None
        return str(data.get("computed_at") or ""), items
    except (requests.RequestException, ValueError):
        return None


# ---------- 서명/diff ----------

def alert_signature(hbl_no: str, alert: dict[str, Any]) -> str:
    """알림의 안정 해시 (hbl + type + value + message)."""
    seed = "|".join(
        [
            str(hbl_no),
            str(alert.get("type") or ""),
            str(alert.get("value") or ""),
            str(alert.get("message") or ""),
        ]
    )
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def flatten_signatures(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """feed items → {서명: 표시용 알림 레코드}."""
    flat: dict[str, dict[str, Any]] = {}
    for item in items:
        hbl_no = str(item.get("hbl_no") or "")
        for alert in item.get("alerts", []):
            signature = alert_signature(hbl_no, alert)
            flat[signature] = {
                "hbl_no": hbl_no,
                "type": alert.get("type"),
                "severity": alert.get("severity"),
                "message": alert.get("message"),
            }
    return flat


def diff_new(
    state: dict[str, Any],
    items: list[dict[str, Any]],
    computed_at: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """이전 상태 대비 신규 알림만 추출 + 갱신 상태 반환.

    state["initialized"]가 False(최초 실행)면 빈 목록 반환 + 상태만 저장.
    소멸한 알림의 서명은 상태에서 제거된다.
    """
    flat = flatten_signatures(items)
    initialized = bool(state.get("initialized"))
    old_signatures = set(state.get("signatures", []))

    new_alerts = (
        [record for signature, record in flat.items() if signature not in old_signatures]
        if initialized
        else []
    )
    new_state = {
        "initialized": True,
        "last_computed_at": computed_at,
        "signatures": sorted(flat.keys()),
    }
    return new_alerts, new_state


# ---------- 상태 파일 ----------

def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"initialized": False, "signatures": [], "last_computed_at": ""}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"initialized": False, "signatures": [], "last_computed_at": ""}


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
