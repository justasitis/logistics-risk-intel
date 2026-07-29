"""레지스트리 종합 정제 (Actify) — ACTIVE/IMPROVING 이벤트 검토 제안 생성.

이벤트를 건당 ~120토큰으로 압축해 Actify에 별내고, 응답은 **제안**으로만
반환한다(자동 반영 금지 — 수락은 apply_proposal로 건당 명시 처리).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from ..core.mi_settings import get_mi_settings
from .actify_client import ActifyClient
from .mi_event_registry import list_events, registry_file_path
from .mi_refiner import _extract_json

logger = logging.getLogger(__name__)

PROMPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "prompts" / "mi_registry_review_prompt.txt"
)

COMPACT_FIELDS = (
    "event_id", "headline", "severity", "status",
    "locations", "corridors", "last_seen", "sighting_count",
)


class ActifyNotConfiguredError(RuntimeError):
    """Actify 미설정 (라우트에서 503)."""


class ReviewProposal(BaseModel):
    event_id: str
    suggested_status: str
    suggested_severity: str
    merge_with: str | None = None
    reason: str = ""


class ReviewResponse(BaseModel):
    reviews: list[ReviewProposal] = Field(default_factory=list)
    notes: str = ""


def _compact_event(event: dict[str, Any]) -> dict[str, Any]:
    return {field: event.get(field) for field in COMPACT_FIELDS}


def generate_registry_review() -> dict[str, Any]:
    """ACTIVE+IMPROVING 이벤트를 압축 입력해 Actify 검토 제안 생성."""
    settings = get_mi_settings()
    if not settings.configured:
        raise ActifyNotConfiguredError(
            "Actify(사내 Dify)가 설정되지 않았습니다. 환경변수를 확인하세요."
        )

    data = list_events(registry_file=registry_file_path())
    events = [
        e for e in data.get("events", [])
        if e.get("status") in ("ACTIVE", "IMPROVING")
    ]
    if not events:
        return {"reviews": [], "notes": "검토 대상(ACTIVE/IMPROVING) 이벤트가 없습니다."}

    input_payload = {
        "events": [_compact_event(e) for e in events],
    }
    prompt = (
        PROMPT_PATH.read_text(encoding="utf-8")
        + "\n\n[INPUT JSON]\n"
        + json.dumps(input_payload, ensure_ascii=False)
    )

    result = ActifyClient(settings).call(prompt, conversation_id="")
    payload = _extract_json(result.answer)
    try:
        review = ReviewResponse.model_validate(payload)
    except ValidationError as exc:
        logger.error("레지스트리 검토 응답 스키마 검증 실패: %s / 원본=%s", exc, result.answer)
        raise RuntimeError("Actify 응답이 검토 스키마와 일치하지 않습니다") from exc

    # 존재하는 event_id만 남김 (LLM 환각 id 방어)
    known_ids = {e.get("event_id") for e in events}
    review.reviews = [r for r in review.reviews if r.event_id in known_ids]

    return review.model_dump()
