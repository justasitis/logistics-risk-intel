"""지도 라벨(간결 문구) 생성 — Actify LLM.

인사이트 초안 생성 시 함께 호출되어 레지스트리 이벤트를 권역 기준으로 묶고
지도 영향권 옆에 붙일 짧은 라벨 문구를 만든다. 결과는 SharePoint
MI/map_labels.json에 atomic 저장되며, 실패필도 인사이트 생성은 그대로
진행된다(best-effort). 라벨이 없는 이벤트는 프런트가 headline 폭을 쓴다.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from ..core.marinesia_settings import get_marinesia_settings
from ..core.mi_settings import get_mi_settings
from .actify_client import ActifyClient
from .mi_refiner import _extract_json

logger = logging.getLogger(__name__)

PROMPT_PATH = (
    Path(__file__).resolve().parents[1] / "prompts" / "mi_map_label_prompt.txt"
)
MAP_LABELS_RELATIVE_PATH = Path("MI") / "map_labels.json"
MAX_LABEL_LEN = 24  # 지도 박스에 들어갈 한글 기준 최대 길이


def map_labels_path() -> Path:
    return get_marinesia_settings().sharepoint_root / MAP_LABELS_RELATIVE_PATH


def load_map_labels() -> dict[str, str]:
    """event_id → short_label. 파일 없음/파손 시 빈 dict."""
    path = map_labels_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    labels = payload.get("labels")
    if not isinstance(labels, dict):
        return {}
    return {str(k): str(v) for k, v in labels.items()}


def _save_map_labels(labels: dict[str, str]) -> None:
    path = map_labels_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "labels": labels,
    }
    # 파일 쓰기는 atomic (tmp → os.replace)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    import os

    os.replace(tmp, path)


def generate_map_labels(events: list[dict[str, Any]]) -> dict[str, str]:
    """레지스트리 이벤트 → Actify → 지도 라벨 저장 후 반환.

    Actify 미설정/응답 파싱 실패 시 RuntimeError — 호출부에서 best-effort로 처리.
    """
    settings = get_mi_settings()
    if not settings.configured:
        raise RuntimeError("Actify(사내 Dify)가 설정되지 않았습니다.")

    targets = [
        {
            "event_id": e.get("event_id"),
            "headline": e.get("headline"),
            "summary": e.get("summary"),
            "severity": e.get("severity"),
            "status": e.get("status"),
            "locations": e.get("locations", []),
            "corridors": e.get("corridors", []),
        }
        for e in events
        if e.get("status") in ("ACTIVE", "IMPROVING")
    ]
    known_ids = {str(t["event_id"]) for t in targets if t.get("event_id")}
    if not targets:
        _save_map_labels({})
        return {}

    prompt = (
        PROMPT_PATH.read_text(encoding="utf-8")
        + "\n\n[INPUT JSON]\n"
        + json.dumps(targets, ensure_ascii=False)
    )
    result = ActifyClient(settings).call(prompt, conversation_id="")
    parsed = _extract_json(result.answer)

    items = parsed.get("labels") if isinstance(parsed, dict) else None
    if not isinstance(items, list):
        raise RuntimeError("Actify 지도 라벨 응답이 스키마와 일치하지 않습니다")

    labels: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        event_id = str(item.get("event_id") or "")
        label = str(item.get("short_label") or "").strip()
        # 레지스트리에 실존하는 이벤트의 라벨만 채택
        if event_id in known_ids and label:
            labels[event_id] = label[:MAX_LABEL_LEN]

    _save_map_labels(labels)
    return labels
