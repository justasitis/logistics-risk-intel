from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..schemas.mi_ai import AffectedLocation, LocationRef

MASTER_PATH = Path(__file__).resolve().parents[1] / "data" / "mi_location_master.json"


def load_location_master() -> dict[str, dict[str, Any]]:
    if not MASTER_PATH.exists():
        return {}
    payload = json.loads(MASTER_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("mi_location_master.json must be an object")
    return {
        str(code).upper(): item
        for code, item in payload.items()
        if isinstance(item, dict)
    }


def resolve_locations(
    refs: list[LocationRef],
) -> tuple[list[AffectedLocation], list[LocationRef]]:
    master = load_location_master()
    aliases: dict[str, str] = {}

    for code, item in master.items():
        aliases[code.lower()] = code
        name = str(item.get("name") or "").strip().lower()
        if name:
            aliases[name] = code
        for alias in item.get("aliases", []):
            aliases[str(alias).strip().lower()] = code

    resolved: list[AffectedLocation] = []
    unresolved: list[LocationRef] = []
    seen: set[str] = set()

    for ref in refs:
        requested_code = ref.code.strip().upper()
        code = requested_code if requested_code in master else aliases.get(ref.name.strip().lower(), "")
        if not code or code not in master:
            unresolved.append(ref)
            continue
        if code in seen:
            continue

        item = master[code]
        default_radius = float(item.get("default_radius_km", 100))
        requested_radius = ref.radius_km or default_radius
        radius = max(default_radius * 0.5, min(float(requested_radius), default_radius * 2.0))
        resolved.append(
            AffectedLocation(
                code=code,
                name=str(item["name"]),
                location_type=str(item["location_type"]),
                lat=float(item["lat"]),
                lon=float(item["lon"]),
                radius_km=round(radius, 1),
            )
        )
        seen.add(code)

    return resolved, unresolved
