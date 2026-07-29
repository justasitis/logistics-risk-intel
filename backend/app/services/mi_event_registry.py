"""MI 이벤트 레지스트리 (1단계 — 규칙 기반, LLM 변경 없음).

SharePoint MI\\current의 일자별 후보 파일(external_mi_candidates_YYMMDD.json)
시계열을 날짜 오름차순으로 인입해, "같은 사건"을 시그니처 매칭으로 추적한다.

[시그니처 매칭 규칙]
- 위치 집합: location_mentions 정규화(대문자·공백 제거) 집합
- 토큰 집합: cluster_hint + headline + risk_keyword_hints 를 소문자 토큰화한 집합
  (유사도는 Jaccard = |교집합| / |합집합|)
- 판정:
  ① 위치 집합이 완전히 같고 비어 있지 않으면 → 동일 이벤트 (강한 신호)
  ② 공유 위치가 1개 이상이고 Jaccard ≥ MI_REGISTRY_JACCARD(기본 0.4) → 동일
  ③ 양쪽 위치가 모두 비어 있으면 Jaccard ≥ MI_REGISTRY_JACCARD_NOLOC(기본 0.5) 필요
  ④ 한쪽만 위치가 있으면 → 다른 이벤트
- 복수 매칭 시 Jaccard가 가장 높은 이벤트 선택

[생명주기]
- 기준일(가장 최근 파일 날짜) 대비 마지막 목격일:
  MI_REGISTRY_IMPROVING_DAYS(기본 7)일+ → IMPROVING,
  MI_REGISTRY_RESOLVED_DAYS(기본 14)일+ → RESOLVED
- RESOLVED 이벤트가 재목격되면 ACTIVE로 재활성화(reactivated 플래그)
- severity는 규칙상 최고 등급 유지 (하락은 사람 판단 영역)

저장소: MI_EVENT_REGISTRY_FILE (기본 SharePoint MI\\mi_event_registry.json,
부모 폴터가 없으면 backend/data/mi_event_registry.json 폴�). atomic write.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import date
from pathlib import Path
from typing import Any

from ..core.marinesia_settings import get_marinesia_settings
from ..core.user_path import resolve_synced_path

# ---------- 환경 파라미터 ----------

DEFAULT_REGISTRY_SP_PATH = (
    r"C:\Users\{username}\SK on\Global물류팀 - LogisticsRisk\MI\mi_event_registry.json"
)
FALLBACK_REGISTRY_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "mi_event_registry.json"
)

SEVERITY_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
STATUS_ORDER = {"ACTIVE": 0, "IMPROVING": 1, "RESOLVED": 2}
MAX_SEVERITY = "CRITICAL"


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def _jaccard_threshold() -> float:
    return _env_float("MI_REGISTRY_JACCARD", 0.4)


def _jaccard_noloc_threshold() -> float:
    return _env_float("MI_REGISTRY_JACCARD_NOLOC", 0.5)


def _improving_days() -> int:
    return _env_int("MI_REGISTRY_IMPROVING_DAYS", 7)


def _resolved_days() -> int:
    return _env_int("MI_REGISTRY_RESOLVED_DAYS", 14)


def _max_dates() -> int:
    return _env_int("MI_REGISTRY_MAX_DATES", 30)


def _max_evidence() -> int:
    return _env_int("MI_REGISTRY_MAX_EVIDENCE", 50)


def registry_file_path() -> Path:
    """레지스트리 파일 경로: env 오버라이드 → SharePoint → backend/data 폴�."""
    override = os.environ.get("MI_EVENT_REGISTRY_FILE", "").strip()
    if override:
        return Path(override)
    resolved = Path(resolve_synced_path(DEFAULT_REGISTRY_SP_PATH))
    if resolved.parent.exists():
        return resolved
    return FALLBACK_REGISTRY_PATH


def current_dir_path() -> Path:
    """일자별 후보 파일 폴터: SharePoint 루트/MI/current."""
    override = os.environ.get("MI_CURRENT_DIR", "").strip()
    if override:
        return Path(override)
    return get_marinesia_settings().sharepoint_root / "MI" / "current"


# ---------- 날짜/토큰/시그니처 ----------

def parse_file_date(path: Path, payload: dict[str, Any]) -> date | None:
    """파일명의 YYMMDD 우선, 없으면 generated_at에서 날짜 파싱."""
    match = re.search(r"_(\d{6})\.json$", path.name)
    if match:
        digits = match.group(1)
        try:
            return date(2000 + int(digits[:2]), int(digits[2:4]), int(digits[4:6]))
        except ValueError:
            pass
    generated = str(payload.get("generated_at") or "")[:10]
    try:
        return date.fromisoformat(generated)
    except ValueError:
        return None


def _norm_loc(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).upper()


def _location_set(candidate: dict[str, Any]) -> set[str]:
    return {
        _norm_loc(loc)
        for loc in candidate.get("location_mentions", [])
        if _norm_loc(loc)
    }


def _token_set(candidate: dict[str, Any]) -> set[str]:
    text = " ".join(
        [
            str(candidate.get("cluster_hint") or ""),
            str(candidate.get("headline") or ""),
            *[str(k) for k in candidate.get("risk_keyword_hints", [])],
        ]
    ).lower()
    return {token for token in re.split(r"[^0-9a-z가-힣]+", text) if len(token) > 1}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _is_match(
    cand_locs: set[str],
    cand_tokens: set[str],
    event_locs: set[str],
    event_tokens: set[str],
) -> tuple[bool, float]:
    """(매칭 여부, Jaccard) — 규칙은 모듈 docstring 참고."""
    score = _jaccard(cand_tokens, event_tokens)
    if cand_locs and event_locs:
        if cand_locs == event_locs:
            return True, score
        if cand_locs & event_locs and score >= _jaccard_threshold():
            return True, score
        return False, score
    if not cand_locs and not event_locs:
        return score >= _jaccard_noloc_threshold(), score
    return False, score


def _event_id(candidate: dict[str, Any]) -> str:
    seed = "|".join(
        sorted(_location_set(candidate))
        + sorted(_token_set(candidate))[:8]
    )
    return "MIREG-" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8].upper()


# ---------- 저장소 ----------

def _load_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "reference_date": None, "events": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("events"), list):
        raise RuntimeError("레지스트리 파일 형식이 올바르지 않습니다")
    return data


def _save_registry(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


# ---------- 인입 ----------

def discover_day_files(current_dir: Path) -> list[tuple[date, Path, dict[str, Any]]]:
    """external_mi_candidates*.json 전부 탐색해 (날짜, 경로, payload) 반환 (날짜 오름차순)."""
    if not current_dir.exists():
        return []
    found: list[tuple[date, Path, dict[str, Any]]] = []
    for path in sorted(current_dir.glob("external_mi_candidates*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        file_date = parse_file_date(path, payload)
        if file_date is None:
            continue
        found.append((file_date, path, payload))
    found.sort(key=lambda item: (item[0], item[1].name))
    return found


def _apply_sighting(
    event: dict[str, Any],
    candidate: dict[str, Any],
    seen_date: date,
) -> None:
    """기존 이벤트에 목격 정보 누적."""
    # 재활성화 판정: 마지막 목격 이후 RESOLVED 기간 이상 공백 후 재목격
    if event.get("sighting_count", 0) > 0:
        gap = (seen_date - date.fromisoformat(event["last_seen"])).days
        if gap >= _resolved_days():
            event["reactivated"] = True

    seen_iso = seen_date.isoformat()
    if seen_iso > event["last_seen"]:
        event["last_seen"] = seen_iso
        # 최신 목격의 headline/summary를 대표로
        if candidate.get("headline"):
            event["headline"] = candidate["headline"]
        if candidate.get("short_summary"):
            event["summary"] = candidate["short_summary"]
    if seen_iso < event["first_seen"]:
        event["first_seen"] = seen_iso
    if seen_iso not in event["sighting_dates"]:
        event["sighting_dates"].append(seen_iso)
        event["sighting_dates"] = sorted(event["sighting_dates"])[-_max_dates():]
    event["sighting_count"] = event.get("sighting_count", 0) + 1

    # severity: 규칙상 최고 등급 유지 (하락은 기록만 — 현재 값 유지)
    cand_severity = str(candidate.get("severity") or "").upper()
    if SEVERITY_RANK.get(cand_severity, -1) > SEVERITY_RANK.get(event["severity"], -1):
        event["severity"] = cand_severity

    # 위치/회랑/키워드/후보 id 합집합 (순서 안정)
    for field, source in (
        ("locations", candidate.get("location_mentions", [])),
        ("corridors", candidate.get("corridor_mentions", [])),
        ("keywords", candidate.get("risk_keyword_hints", [])),
        ("source_candidate_ids", [candidate.get("candidate_id")]),
    ):
        for value in source:
            if value and value not in event[field]:
                event[field].append(value)

    # evidence 누적 (url/article_id 중복 제거, 상한)
    seen_keys = {
        str(e.get("url") or e.get("article_id") or "")
        for e in event["evidence"]
    }
    for item in candidate.get("evidence", []):
        if not isinstance(item, dict):
            continue
        key = str(item.get("url") or item.get("article_id") or "")
        if key and key not in seen_keys:
            seen_keys.add(key)
            event["evidence"].append(item)
    event["evidence"] = event["evidence"][:_max_evidence()]


def _new_event(candidate: dict[str, Any], seen_date: date) -> dict[str, Any]:
    seen_iso = seen_date.isoformat()
    return {
        "event_id": _event_id(candidate),
        "status": "ACTIVE",
        "first_seen": seen_iso,
        "last_seen": seen_iso,
        "sighting_count": 1,
        "sighting_dates": [seen_iso],
        "headline": candidate.get("headline") or "",
        "summary": candidate.get("short_summary") or "",
        "severity": str(candidate.get("severity") or "MEDIUM").upper(),
        "locations": list(dict.fromkeys(candidate.get("location_mentions", []))),
        "corridors": list(dict.fromkeys(candidate.get("corridor_mentions", []))),
        "keywords": list(dict.fromkeys(candidate.get("risk_keyword_hints", []))),
        "source_candidate_ids": [candidate.get("candidate_id")]
        if candidate.get("candidate_id")
        else [],
        "evidence": [
            item
            for item in candidate.get("evidence", [])
            if isinstance(item, dict)
        ][:_max_evidence()],
        "reactivated": False,
    }


def rebuild_registry(
    current_dir: Path | None = None,
    registry_file: Path | None = None,
) -> dict[str, Any]:
    """전체 일자 파일을 날짜 순으로 재인입해 레지스트리를 재구축 (멱등)."""
    current_dir = current_dir or current_dir_path()
    registry_file = registry_file or registry_file_path()

    day_files = discover_day_files(current_dir)
    events: list[dict[str, Any]] = []
    # 매칭용 시그니처 캐시 (이벤트 인덱스 → (locs, tokens))
    signatures: list[tuple[set[str], set[str]]] = []

    reference_date: date | None = None
    for file_date, _path, payload in day_files:
        reference_date = file_date
        for candidate in payload.get("candidates", []):
            if not isinstance(candidate, dict):
                continue
            cand_locs = _location_set(candidate)
            cand_tokens = _token_set(candidate)

            best_idx = -1
            best_score = -1.0
            for idx, (ev_locs, ev_tokens) in enumerate(signatures):
                matched, score = _is_match(cand_locs, cand_tokens, ev_locs, ev_tokens)
                if matched and score > best_score:
                    best_idx, best_score = idx, score

            if best_idx >= 0:
                _apply_sighting(events[best_idx], candidate, file_date)
                # 시그니처도 누적 반영 (다음 매칭 정확도)
                signatures[best_idx] = (
                    signatures[best_idx][0] | cand_locs,
                    signatures[best_idx][1] | cand_tokens,
                )
            else:
                events.append(_new_event(candidate, file_date))
                signatures.append((cand_locs, cand_tokens))

    # 생명주기 전이 (기준일 = 가장 최근 파일 날짜)
    if reference_date is not None:
        for event in events:
            last_seen = date.fromisoformat(event["last_seen"])
            silent_days = (reference_date - last_seen).days
            if silent_days >= _resolved_days():
                event["status"] = "RESOLVED"
            elif silent_days >= _improving_days():
                event["status"] = "IMPROVING"
            else:
                event["status"] = "ACTIVE"

    registry = {
        "version": 1,
        "reference_date": reference_date.isoformat() if reference_date else None,
        "events": events,
    }
    _save_registry(registry_file, registry)
    return {
        "files_processed": len(day_files),
        "reference_date": registry["reference_date"],
        "event_count": len(events),
        "registry_file": str(registry_file),
    }


# ---------- 조회 ----------

def list_events(
    status: str | None = None,
    registry_file: Path | None = None,
) -> dict[str, Any]:
    data = _load_registry(registry_file or registry_file_path())
    events = data["events"]
    if status:
        wanted = status.strip().upper()
        events = [e for e in events if e.get("status") == wanted]
    events = sorted(
        events,
        key=lambda e: (
            STATUS_ORDER.get(str(e.get("status")), 9),
            -int(str(e.get("last_seen") or "0").replace("-", "") or 0),
        ),
    )
    return {
        "reference_date": data.get("reference_date"),
        "events": events,
    }


def get_event(event_id: str, registry_file: Path | None = None) -> dict[str, Any] | None:
    data = _load_registry(registry_file or registry_file_path())
    for event in data["events"]:
        if event.get("event_id") == event_id:
            return event
    return None


# ---------- 지도 영향권 / 제안 반영 ----------

def map_zones(registry_file: Path | None = None) -> list[dict[str, Any]]:
    """ACTIVE/IMPROVING 이벤트의 locations를 위치 마스터로 좌표화.

    레지스트리 파일이 없거나 해석 불가 위치만 있으면 빈 배열.
    """
    from .mi_location_resolver import resolve_locations
    from ..schemas.mi_ai import LocationRef

    path = registry_file or registry_file_path()
    if not path.exists():
        return []
    data = _load_registry(path)

    zones: list[dict[str, Any]] = []
    for event in data["events"]:
        if event.get("status") not in ("ACTIVE", "IMPROVING"):
            continue
        refs = [
            LocationRef(code=str(loc), name=str(loc))
            for loc in event.get("locations", [])
        ]
        if not refs:
            continue
        resolved, _unresolved = resolve_locations(refs)
        if not resolved:
            continue
        zones.append(
            {
                "event_id": event.get("event_id"),
                "headline": event.get("headline"),
                "severity": event.get("severity"),
                "status": event.get("status"),
                "locations": [
                    {
                        "code": loc.code,
                        "name": loc.name,
                        "lat": loc.lat,
                        "lon": loc.lon,
                        "radius_km": loc.radius_km,
                    }
                    for loc in resolved
                ],
            }
        )
    return zones


def apply_proposal(
    event_id: str,
    status: str | None = None,
    severity: str | None = None,
    merge_with: str | None = None,
    registry_file: Path | None = None,
) -> dict[str, Any]:
    """종합 정제 제안 수락 반영 (HITL — 건당 명시 수락만).

    merge_with 지정 시 대상 이벤트를 event_id 쪽으로 병합(집합 합집합,
    first_seen min / last_seen max / 목격일·횟수·evidence 누적) 후 제거.
    """
    path = registry_file or registry_file_path()
    data = _load_registry(path)
    events = data["events"]

    target = next((e for e in events if e.get("event_id") == event_id), None)
    if target is None:
        raise KeyError(event_id)

    if status:
        status = status.upper()
        if status not in STATUS_ORDER:
            raise ValueError(f"status는 {', '.join(STATUS_ORDER)} 중 하나여야 합니다")
        target["status"] = status
    if severity:
        severity = severity.upper()
        if severity not in SEVERITY_RANK:
            raise ValueError(f"severity는 {', '.join(SEVERITY_RANK)} 중 하나여야 합니다")
        target["severity"] = severity

    if merge_with:
        source = next((e for e in events if e.get("event_id") == merge_with), None)
        if source is None:
            raise KeyError(merge_with)
        target["first_seen"] = min(target["first_seen"], source["first_seen"])
        target["last_seen"] = max(target["last_seen"], source["last_seen"])
        target["sighting_count"] = (
            target.get("sighting_count", 0) + source.get("sighting_count", 0)
        )
        target["sighting_dates"] = sorted(
            set(target.get("sighting_dates", []))
            | set(source.get("sighting_dates", []))
        )[-_max_dates():]
        for field in ("locations", "corridors", "keywords", "source_candidate_ids"):
            for value in source.get(field, []):
                if value and value not in target[field]:
                    target[field].append(value)
        seen_keys = {
            str(e.get("url") or e.get("article_id") or "")
            for e in target["evidence"]
        }
        for item in source.get("evidence", []):
            key = str(item.get("url") or item.get("article_id") or "")
            if key and key not in seen_keys:
                seen_keys.add(key)
                target["evidence"].append(item)
        target["evidence"] = target["evidence"][:_max_evidence()]
        target["merged_from"] = sorted(
            set(target.get("merged_from", [])) | {merge_with}
        )
        events.remove(source)

    _save_registry(path, data)
    return target
