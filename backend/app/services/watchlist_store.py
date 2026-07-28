"""관심화물(watchlist) 저장소 — 사용자별 파일.

구매원 개인의 관심 HBL 목록. 중앙 구독 관리(메일 주소록 등)는 만들지 않는다.
- 위치: WATCHLIST_DIR env 오버라이드 → SharePoint <루트>\\watchlist\\
  (resolve_synced_path, 폴터 없으면 backend/data/watchlist 폴�)
- 파일: watchlist_{username}.json (사용자 분리, current_username 기준)
- 쓰기: atomic write (tmp → os.replace)
- 항목: {"type": "hbl", "id": hbl_no, "label": str, "added_at": iso}
  (type으로 po 등 확장 여지)
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from ..core.user_path import current_username, resolve_synced_path

DEFAULT_WATCHLIST_SP_DIR = (
    r"C:\Users\{username}\SK on\Global물류팀 - LogisticsRisk\watchlist"
)
FALLBACK_WATCHLIST_DIR = (
    Path(__file__).resolve().parents[2] / "data" / "watchlist"
)


def watchlist_dir() -> Path:
    override = os.environ.get("WATCHLIST_DIR", "").strip()
    if override:
        return Path(override)
    resolved = Path(resolve_synced_path(DEFAULT_WATCHLIST_SP_DIR))
    if resolved.exists():
        return resolved
    return FALLBACK_WATCHLIST_DIR


def _safe(value: str) -> str:
    return "".join(char for char in value if char.isalnum() or char in "-_.")


def _path(username: str) -> Path:
    safe = _safe(username)
    if not safe:
        raise ValueError("invalid username")
    return watchlist_dir() / f"watchlist_{safe}.json"


def load(username: str | None = None) -> dict[str, Any]:
    username = username or current_username()
    path = _path(username)
    if not path.exists():
        return {"items": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise RuntimeError("watchlist 파일 형식이 올바르지 않습니다")
    return data


def _save(username: str, data: dict[str, Any]) -> None:
    path = _path(username)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def add(item_id: str, label: str = "", item_type: str = "hbl",
        username: str | None = None) -> dict[str, Any]:
    """항목 추가 (동일 type+id 중복 무시)."""
    username = username or current_username()
    data = load(username)
    item_id = item_id.strip()
    if not item_id:
        raise ValueError("id는 비어 있을 수 없습니다")
    for item in data["items"]:
        if item.get("type") == item_type and item.get("id") == item_id:
            return item  # 중복 무시
    item = {
        "type": item_type,
        "id": item_id,
        "label": label.strip(),
        "added_at": datetime.now().isoformat(timespec="seconds"),
    }
    data["items"].append(item)
    _save(username, data)
    return item


def remove(item_id: str, item_type: str = "hbl",
           username: str | None = None) -> bool:
    """항목 삭제. 있었으면 True."""
    username = username or current_username()
    data = load(username)
    before = len(data["items"])
    data["items"] = [
        item
        for item in data["items"]
        if not (item.get("type") == item_type and item.get("id") == item_id)
    ]
    if len(data["items"]) == before:
        return False
    _save(username, data)
    return True
