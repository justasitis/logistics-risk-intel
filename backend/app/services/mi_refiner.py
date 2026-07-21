from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ..core.mi_settings import get_mi_settings
from ..schemas.mi_ai import (
    Evidence,
    LocationRef,
    RefineRequest,
    RefineResponse,
    RefinedMiEvent,
)
from .actify_client import ActifyClient
from .mi_location_resolver import load_location_master, resolve_locations
from .mi_repository import MiRunRepository

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "mi_refine_prompt.txt"


def _model_dump(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()


def _strip_code_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = _strip_code_fence(text)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            raise RuntimeError("Actify response does not contain a JSON object")
        value = json.loads(cleaned[start:end + 1])
    if not isinstance(value, dict):
        raise RuntimeError("Actify JSON top-level must be an object")
    return value


def _event_id(cluster_key: str, valid_from: str) -> str:
    seed = f"{cluster_key}|{valid_from}"
    return "MI-" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10].upper()


def _safe_float(value: Any, default: float = 0.5) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_enum(value: Any, allowed: set[str], default: str) -> str:
    text = str(value or "").strip().upper()
    return text if text in allowed else default


def _build_prompt(request: RefineRequest) -> str:
    template = PROMPT_PATH.read_text(encoding="utf-8")
    master = load_location_master()
    allowed_locations = [
        {
            "code": code,
            "name": item.get("name"),
            "location_type": item.get("location_type"),
            "default_radius_km": item.get("default_radius_km"),
        }
        for code, item in master.items()
    ]

    input_payload = {
        "company_codes": request.company_codes,
        "supplemental_context": request.supplemental_context,
        "allowed_location_master": allowed_locations,
        "external_candidates": [
            _model_dump(candidate)
            for candidate in request.candidate_envelope.candidates
        ],
    }
    return f"{template}\n\n[INPUT JSON]\n{json.dumps(input_payload, ensure_ascii=False)}"


def _collect_evidence(
    source_candidate_ids: list[str],
    request: RefineRequest,
) -> list[Evidence]:
    candidate_map = {
        candidate.candidate_id: candidate
        for candidate in request.candidate_envelope.candidates
    }
    evidence: list[Evidence] = []
    seen: set[str] = set()

    for candidate_id in source_candidate_ids:
        candidate = candidate_map.get(candidate_id)
        if not candidate:
            continue
        for item in candidate.evidence:
            key = item.url or item.article_id
            if key in seen:
                continue
            seen.add(key)
            evidence.append(item)
    return evidence


def refine_candidates(request: RefineRequest) -> RefineResponse:
    settings = get_mi_settings()
    if not settings.configured:
        raise RuntimeError("Actify is not configured")

    if len(request.candidate_envelope.candidates) > settings.mi_max_candidates:
        raise ValueError(
            f"candidate count exceeds MI_VDI_MAX_CANDIDATES={settings.mi_max_candidates}"
        )

    result = ActifyClient(settings).call(_build_prompt(request), conversation_id="")
    payload = _extract_json(result.answer)
    raw_events = payload.get("events")
    if not isinstance(raw_events, list):
        raise RuntimeError("Actify JSON must contain an events array")

    allowed_status = {"ACTIVE", "WATCH", "IMPROVING", "RESOLVED"}
    allowed_type = {
        "ROUTE_DISRUPTION", "PORT_CONGESTION", "WEATHER", "LABOR_STRIKE",
        "GEOPOLITICAL", "INFRASTRUCTURE", "CAPACITY_SHORTAGE", "CARRIER_ISSUE",
        "RATE_SURGE", "REGULATION", "DANGEROUS_GOODS", "OTHER",
    }
    allowed_severity = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
    allowed_mode = {"SEA", "AIR", "RAIL", "ROAD", "MULTIMODAL"}

    events: list[RefinedMiEvent] = []
    warnings: list[str] = []

    for index, raw in enumerate(raw_events):
        if not isinstance(raw, dict):
            warnings.append(f"events[{index}] ignored: not an object")
            continue

        cluster_key = re.sub(
            r"[^a-z0-9가-힣]+",
            "-",
            str(raw.get("cluster_key") or raw.get("headline") or "event").lower(),
        ).strip("-")[:120]
        valid_from = str(raw.get("valid_from") or datetime.now(timezone.utc).date().isoformat())
        source_candidate_ids = list(dict.fromkeys(
            str(item) for item in raw.get("source_candidate_ids", []) if str(item)
        ))

        location_refs = raw.get("location_refs") if isinstance(raw.get("location_refs"), list) else []
        resolved_locations, unresolved_locations = resolve_locations([
            LocationRef(**item)
            for item in location_refs
            if isinstance(item, dict)
        ])

        transport_modes = [
            str(item).upper()
            for item in raw.get("transport_modes", [])
            if str(item).upper() in allowed_mode
        ]

        normalized = {
            **raw,
            "event_id": str(raw.get("event_id") or _event_id(cluster_key, valid_from)),
            "source_candidate_ids": source_candidate_ids,
            "cluster_key": cluster_key,
            "status": _normalize_enum(raw.get("status"), allowed_status, "WATCH"),
            "event_type": _normalize_enum(raw.get("event_type"), allowed_type, "OTHER"),
            "severity": _normalize_enum(raw.get("severity"), allowed_severity, "LOW"),
            "confidence": max(0.0, min(1.0, _safe_float(raw.get("confidence"), 0.5))),
            "source_type": "INTERNAL_REFINED_MI",
            "first_seen_at": valid_from,
            "last_updated_at": datetime.now(timezone.utc).isoformat(),
            "valid_from": valid_from,
            "valid_to": raw.get("valid_to") or None,
            "transport_modes": transport_modes,
            "location_refs": location_refs,
            "affected_locations": [_model_dump(item) for item in resolved_locations],
            "unresolved_locations": [_model_dump(item) for item in unresolved_locations],
            "evidence": [
                _model_dump(item)
                for item in _collect_evidence(source_candidate_ids, request)
            ],
            "review_status": "PENDING",
        }

        try:
            events.append(RefinedMiEvent(**normalized))
        except (ValidationError, ValueError, TypeError) as exc:
            warnings.append(f"events[{index}] validation failed: {exc}")

    analysis_id = "MI-RUN-" + uuid.uuid4().hex[:12].upper()
    response = RefineResponse(
        analysis_id=analysis_id,
        generated_at=datetime.now(timezone.utc),
        source_candidate_count=len(request.candidate_envelope.candidates),
        events=events,
        warnings=warnings,
    )

    MiRunRepository().save(
        analysis_id,
        {
            "stage": "REFINED",
            "conversation_id": result.conversation_id,
            "request": _model_dump(request),
            "response": _model_dump(response),
        },
    )
    return response
