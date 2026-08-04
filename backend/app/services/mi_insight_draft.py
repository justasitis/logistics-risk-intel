"""월간 인사이트 초안 생성 (Actify/Dify + 재료 수집).

재료:
1. 승인 MI 이벤트 — mi_runs 저장소(mtime 최신 순)에서 대상 월과 기간이 겹치는 이벤트
2. 리드타임 하이라이트 — leadtime_report_service 재사용 (B-LAP 실패 시 생략, 부분 성공)
3. 스케줄 이상 요약 — overview와 동일 파이프라인의 build_dashboard_summary (실패 시 생략)

Actify 호출 방식은 변경하지 않고, Dify 응답 파싱은 mi_refiner 패턴을 준수한다.
초안은 자동 발송되지 않으며 사람이 검토·확정한다(HITL).
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from ..core.mi_settings import get_mi_settings
from .actify_client import ActifyClient
from .insight_draft_store import InsightDraftStore, revised_now
from .mi_refiner import _extract_json
from .mi_repository import MiRunRepository

logger = logging.getLogger(__name__)

PROMPT_PATH = (
    Path(__file__).resolve().parents[1] / "prompts" / "mi_monthly_insight_prompt.txt"
)

RUN_SCAN_LIMIT = 50
EVENT_FIELDS = (
    "event_id", "headline", "summary", "severity", "direction", "impact_path",
    "event_type", "affected_corridors", "valid_from", "valid_to",
)


class InsightSection(BaseModel):
    key: str
    title: str
    body: str

    model_config = {"extra": "forbid"}


class InsightDraft(BaseModel):
    # key_changes: 참고 리포트의 "핵심변화 1~3" Executive Summary에 해당
    key_changes: list[str] = Field(default_factory=list)
    sections: list[InsightSection] = Field(default_factory=list)
    monitoring_points: list[str] = Field(default_factory=list)
    disclaimer: str = ""


class ActifyNotConfiguredError(RuntimeError):
    """Actify 미설정 (라우트에서 503)."""


# ---------- 재료 1: 승인 MI 이벤트 ----------

def _month_range(month: str) -> tuple[date, date]:
    """대상 월의 첫날과 다음 달 첫날 반환 (비교: from < next, to >= start)."""
    start = date.fromisoformat(f"{month}-01")
    next_month = (
        date(start.year + 1, 1, 1)
        if start.month == 12
        else date(start.year, start.month + 1, 1)
    )
    return start, next_month


def _events_from_run(run: dict[str, Any]) -> list[dict[str, Any]]:
    """run payload에서 승인/활성 이벤트 추출 (canonical 우선, 없으면 refine 결과)."""
    canonical = run.get("canonical_payload")
    if isinstance(canonical, dict) and isinstance(canonical.get("events"), list):
        return canonical["events"]
    response = run.get("response")
    if isinstance(response, dict) and isinstance(response.get("events"), list):
        return response["events"]
    return []


def collect_mi_events(month: str) -> list[dict[str, Any]]:
    """대상 월과 기간이 겹치는 승인 MI 이벤트를 요약 필드만 모아 반환."""
    start, next_month = _month_range(month)
    collected: list[dict[str, Any]] = []
    seen: set[str] = set()

    for run in MiRunRepository().list_recent(RUN_SCAN_LIMIT):
        for event in _events_from_run(run):
            valid_from = str(event.get("valid_from") or "")[:10]
            valid_to = str(event.get("valid_to") or "")[:10]
            try:
                from_date = date.fromisoformat(valid_from) if valid_from else None
                to_date = date.fromisoformat(valid_to) if valid_to else None
            except ValueError:
                continue
            # 대상 월과 기간 겹침: valid_from < 다음 달 1일 and (valid_to 없음 or >= 월 1일)
            if from_date is not None and from_date >= next_month:
                continue
            if to_date is not None and to_date < start:
                continue
            key = str(event.get("event_id") or event.get("headline") or "")
            if key in seen:
                continue
            seen.add(key)
            collected.append(
                {field: event.get(field) for field in EVENT_FIELDS}
            )
    return collected


# ---------- 재료 2: 리드타임 하이라이트 ----------

def collect_leadtime_highlights(month: str) -> dict[str, Any] | None:
    """전월 대비 Avg 변화 상위 항로 추출. B-LAP 실패 시 None(부분 성공)."""
    try:
        from services.leadtime_report_service import fetch_leadtime_report

        report = fetch_leadtime_report(months=3, forecast_months=2)
    except Exception:
        logger.exception("리드타임 재료 수집 실패 — 생략하고 진행")
        return None

    highlights: list[dict[str, Any]] = []
    for group in report.get("groups", []):
        for row in group.get("rows", []):
            if row.get("stat") != "Avg":
                continue
            cells: dict[str, float] = {
                key: value
                for key, value in row.get("cells", {}).items()
                if any(
                    col["key"] == key and col["kind"] == "actual"
                    for col in report.get("month_columns", [])
                )
            }
            months_sorted = sorted(cells)
            if len(months_sorted) < 2:
                continue
            prev, curr = cells[months_sorted[-2]], cells[months_sorted[-1]]
            highlights.append(
                {
                    "route": group.get("name"),
                    "country": row.get("country_label"),
                    "month": months_sorted[-1],
                    "avg_lt": curr,
                    "delta": round(curr - prev, 1),
                }
            )
    highlights.sort(key=lambda h: abs(h["delta"]), reverse=True)
    return {
        "generated_at": report.get("generated_at"),
        "top_changes": highlights[:5],
    }


# ---------- 재료 3: 스케줄 이상 요약 ----------

def collect_schedule_summary() -> dict[str, Any] | None:
    """overview와 동일 파이프라인의 요약. 실패 시 None(부분 성공)."""
    try:
        from services.anomaly_engine import (
            build_dashboard_summary,
            evaluate_schedule_anomalies,
        )
        from services.datalake_schedule_client import (
            fetch_bl_history_for_transports,
            fetch_bl_info,
        )
        from services.schedule_history_service import (
            build_schedule_metrics,
            build_transport_snapshot,
        )

        info_df = fetch_bl_info(etd_from=date.today().replace(day=1))
        snapshot_df = build_transport_snapshot(info_df, active_only=True)
        transport_keys = [
            (
                str(row.get("cmpy_cd") or ""),
                str(row.get("plnt_cd") or ""),
                str(row.get("trpr_no") or ""),
            )
            for row in snapshot_df.to_dict(orient="records")
        ]
        history_df = fetch_bl_history_for_transports(transport_keys)
        metrics_df = build_schedule_metrics(snapshot_df, history_df)
        _, events = evaluate_schedule_anomalies(metrics_df)
        return build_dashboard_summary(metrics_df, events)
    except Exception:
        logger.exception("스케줄 요약 재료 수집 실패 — 생략하고 진행")
        return None


# ---------- 초안 생성 ----------

def generate_insight_draft(
    month: str | None = None,
    include_leadtime: bool = True,
    regenerate: bool = False,
) -> dict[str, Any]:
    """재료 수집 → Actify 초안 생성 → 저장소 기록 후 반환.

    동일 월 기존 초안이 있고 regenerate=False이면 Actify 호출 없이
    기존 초안을 regenerated=False로 반환한다.
    """
    target_month = month or date.today().isoformat()[:7]
    store = InsightDraftStore()

    if not regenerate and store.exists(target_month):
        record = store.load(target_month)
        return {**record, "regenerated": False}

    settings = get_mi_settings()
    if not settings.configured:
        raise ActifyNotConfiguredError(
            "Actify(사내 Dify)가 설정되지 않았습니다. 환경변수를 확인하세요."
        )

    events = collect_mi_events(target_month)
    leadtime = (
        collect_leadtime_highlights(target_month) if include_leadtime else None
    )
    schedule = collect_schedule_summary()

    input_payload = {
        "month": target_month,
        "approved_mi_events": events,
        "leadtime_highlights": leadtime,
        "schedule_summary": schedule,
    }
    prompt = (
        PROMPT_PATH.read_text(encoding="utf-8")
        + "\n\n[INPUT JSON]\n"
        + json.dumps(input_payload, ensure_ascii=False)
    )

    result = ActifyClient(settings).call(prompt, conversation_id="")
    payload = _extract_json(result.answer)
    try:
        draft = InsightDraft.model_validate(payload)
    except ValidationError as exc:
        logger.error("인사이트 초안 스키마 검증 실패: %s / 원본=%s", exc, result.answer)
        raise RuntimeError("Actify 응답이 인사이트 스키마와 일치하지 않습니다") from exc

    record = store.save(
        target_month,
        {
            "draft": draft.model_dump(),
            "materials_summary": {
                "events_used": len(events),
                "leadtime_used": leadtime is not None,
                "summary_used": schedule is not None,
            },
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        },
    )
    return {**record, "regenerated": True}


def save_revised_draft(month: str, draft: dict[str, Any]) -> dict[str, Any]:
    """편집본 저장 (PUT) — 스키마 검증 후 revised_at 갱신."""
    allowed = {"key_changes", "sections", "monitoring_points", "disclaimer"}
    unknown = set(draft) - allowed
    if unknown:
        raise ValueError(f"초안에 허용되지 않는 필드: {', '.join(sorted(unknown))}")
    store = InsightDraftStore()
    validated = InsightDraft.model_validate(draft)
    try:
        record = store.load(month)
    except Exception:
        record = {
            "materials_summary": {
                "events_used": 0,
                "leadtime_used": False,
                "summary_used": False,
            },
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        }
    record = {**record, "draft": validated.model_dump()}
    return store.save(month, revised_now(record))
