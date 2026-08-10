
"""

api_server.py


 

Vue 3 대시보드용 FastAPI 백엔드.

실행:

    python -m uvicorn api_server:app --reload --host 127.0.0.1 --port 8000

"""


 

from __future__ import annotations

# 프로젝트 루트 .env를 환경변수로 로드한다 (서비스 모듈 import보다 먼저 실행되어야 함).
# python-dotenv는 pydantic-settings의 의존성으로 함께 설치된다.
from pathlib import Path as _Path

try:
    from dotenv import load_dotenv as _load_dotenv

    _load_dotenv(_Path(__file__).resolve().parent / ".env")
except ImportError:  # dotenv 미설치 환경에서는 OS 환경변수만 사용
    pass



 

from datetime import date, datetime, timedelta

import math

import time

from typing import Any


 

import numpy as np

import pandas as pd

from fastapi import Body, FastAPI, HTTPException, Query

import json
import logging
import os
import re

from pydantic import BaseModel, ValidationError

from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes.mi_ai import router as mi_ai_router

from backend.app.api.routes.marinesia import router as marinesia_router

from backend.app.api.routes.stopby_routes import router as stopby_routes_router

from backend.app.api.routes.inventory import router as inventory_router


 

from services.anomaly_engine import (

    build_dashboard_summary,

    evaluate_schedule_anomalies,

)

from services.dashboard_geo_service import build_schedule_map_geojson

from services.datalake_schedule_client import (

    fetch_bl_history_for_transport,

    fetch_bl_history_for_transports,

    fetch_bl_info,

    fetch_bl_info_for_transport,

)

from services.schedule_history_service import (

    build_schedule_metrics,

    build_transport_snapshot,

)

from services.schedule_timeline_service import build_transport_timeline


 

from backend.app.api.routes.manual_coordinates import (

    router as manual_coordinates_router,

)


 

app = FastAPI(

    title="SK-ON Logistics Risk API",

    version="0.4.0",

    description="B-LAP 일정 이상탐지 및 Vue 지도 대시보드 API",

)

logger = logging.getLogger(__name__)


 

app.add_middleware(

    CORSMiddleware,

    allow_origins=[

        "http://localhost:5173",

        "http://127.0.0.1:5173",

        "http://localhost:4173",

        "http://127.0.0.1:4173",

    ],

    allow_credentials=False,

    allow_methods=["*"],

    allow_headers=["*"],

)


 

@app.middleware("http")

async def ensure_utf8_json_response(request, call_next):

    response = await call_next(request)


 

    content_type = response.headers.get("content-type", "")


 

    if (

        content_type.startswith("application/json")

        and "charset=" not in content_type.lower()

    ):

        response.headers["content-type"] = (

            "application/json; charset=utf-8"

        )


 

    return response


 

app.include_router(mi_ai_router)

app.include_router(marinesia_router)

app.include_router(stopby_routes_router)

app.include_router(inventory_router)

app.include_router(

    manual_coordinates_router,

)


 

_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}

CACHE_TTL_SECONDS = 300


 

def _clean_value(value: Any) -> Any:

    if value is None:

        return None


 

    if isinstance(value, (pd.Timestamp, datetime, date)):

        if pd.isna(value):

            return None

        return value.isoformat()


 

    if isinstance(value, np.generic):

        return value.item()


 

    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):

        return None


 

    try:

        if pd.isna(value):

            return None

    except (TypeError, ValueError):

        pass


 

    if isinstance(value, dict):

        return {key: _clean_value(item) for key, item in value.items()}

    if isinstance(value, list):

        return [_clean_value(item) for item in value]


 

    return value


 

def _records(df: pd.DataFrame) -> list[dict[str, Any]]:

    if df.empty:

        return []


 

    return [

        {key: _clean_value(value) for key, value in row.items()}

        for row in df.to_dict(orient="records")

    ]


 

def _cache_key(

    companies: list[str],

    etd_days: int,

    history_days: int,

    recent_window_days: int,

    max_info_rows: int,

) -> str:

    return "|".join(

        [

            ",".join(sorted(companies)),

            str(etd_days),

            str(history_days),

            str(recent_window_days),

            str(max_info_rows),

        ]

    )


 

@app.get("/api/health")

def health() -> dict[str, Any]:

    import os


 

    return {

        "status": "ok",

        "service": "logistics-risk-api",

        "version": "0.4.0",

        "generated_at": datetime.now().isoformat(timespec="seconds"),

        "datalake_credentials_configured": bool(

            os.environ.get("DATALAKE_USERNAME")

            and os.environ.get("DATALAKE_PASSWORD")

        ),

    }


 

@app.get("/api/schedule/overview")

def schedule_overview(

    company: list[str] = Query(default=[]),

    etd_days: int = Query(default=365, ge=30, le=1_500),

    history_days: int = Query(default=180, ge=14, le=1_500),

    recent_window_days: int = Query(default=14, ge=7, le=90),

    max_info_rows: int = Query(default=20_000, ge=100, le=100_000),

    max_events: int = Query(default=200, ge=1, le=2_000),

    max_map_routes: int = Query(default=300, ge=10, le=1_000),

    refresh: bool = Query(default=False),

) -> dict[str, Any]:

    key = _cache_key(

        company,

        etd_days,

        history_days,

        recent_window_days,

        max_info_rows,

    )


 

    if not refresh and key in _CACHE:

        cached_at, payload = _CACHE[key]

        if time.time() - cached_at <= CACHE_TTL_SECONDS:

            return {**payload, "cache_hit": True}


 

    try:

        info_df = fetch_bl_info(

            etd_from=date.today() - timedelta(days=etd_days),

            companies=company or None,

            max_rows=max_info_rows,

        )


 

        snapshot_df = build_transport_snapshot(

            info_df,

            active_only=True,

        )


 

        transport_keys = [

            (

                str(row.get("cmpy_cd") or ""),

                str(row.get("plnt_cd") or ""),

                str(row.get("trpr_no") or ""),

            )

            for row in snapshot_df.to_dict(orient="records")

        ]


 

        history_df = fetch_bl_history_for_transports(

            transport_keys,

            changed_from=date.today() - timedelta(days=history_days),

        )


 

        metrics_df = build_schedule_metrics(

            snapshot_df,

            history_df,

            recent_window_days=recent_window_days,

        )

        enriched_df, events = evaluate_schedule_anomalies(metrics_df)

        summary = build_dashboard_summary(enriched_df, events)

        map_data = build_schedule_map_geojson(

            enriched_df,

            max_routes=max_map_routes,

        )


 

        transport_columns = [

            "transport_key", "cmpy_cd", "cmpy_nm", "plnt_cd",

            "trpr_no", "hbl_no", "mbl_no",

            "pol", "pol_name", "pod", "pod_name",

            "vessel_name", "voyage_no",

            "current_etd", "current_eta",

            "delivery_request_date", "delivery_eta",

            "delivery_req_breach_days",

            "sppl_names", "item_names", "item_cds",

            "po_list", "po_nos",

            "etd_initial", "eta_initial",

            "po_count", "item_count",

            "quantity_sum", "quantity_unit",

            "etd_delay_count_recent", "eta_delay_count_recent",

            "etd_net_delay_days", "eta_net_delay_days",

            "planned_lead_time_days", "projected_lead_time_days",

            "lead_time_variance_days",

            "severity", "risk_score", "anomaly_signals",

        ]

        available_columns = [

            column for column in transport_columns

            if column in enriched_df.columns

        ]


 

        if not enriched_df.empty:

            severity_order = {

                "CRITICAL": 4,

                "HIGH": 3,

                "MEDIUM": 2,

                "LOW": 1,

                "NORMAL": 0,

            }

            enriched_df = enriched_df.copy()

            enriched_df["_severity_rank"] = (

                enriched_df["severity"].map(severity_order).fillna(0)

            )

            enriched_df = enriched_df.sort_values(

                ["_severity_rank", "risk_score"],

                ascending=False,

            ).drop(columns=["_severity_rank"])


 

        payload = {

            "generated_at": datetime.now().isoformat(timespec="seconds"),

            "cache_hit": False,

            "filters": {

                "companies": company,

                "etd_days": etd_days,

                "history_days": history_days,

                "recent_window_days": recent_window_days,

            },

            "source_counts": {

                "info_rows": int(len(info_df)),

                "active_transports": int(len(snapshot_df)),

                "history_rows": int(len(history_df)),

                "map_routes": int(map_data["route_count"]),

                "missing_port_count": int(len(map_data["missing_ports"])),

            },

            "summary": summary,

            "events": [

                _clean_value(item)

                for item in events[:max_events]

            ],

            "transports": _records(

                enriched_df[available_columns].head(1_000)

                if not enriched_df.empty

                else pd.DataFrame()

            ),

            "map": _clean_value(map_data),

        }


 

        _CACHE[key] = (time.time(), payload)

        return payload


 

    except RuntimeError as exc:

        raise HTTPException(status_code=502, detail=str(exc)) from exc

    except ValueError as exc:

        raise HTTPException(status_code=422, detail=str(exc)) from exc

    except Exception as exc:

        raise HTTPException(

            status_code=500,

            detail=(

                "일정 이상탐지 처리 실패: "

                f"{type(exc).__name__}: {exc}"

            ),

        ) from exc


 

@app.get("/api/schedule/timeline")

def schedule_timeline(

    trpr_no: str = Query(min_length=1),

    cmpy_cd: str = Query(default=""),

    plnt_cd: str = Query(default=""),

    history_days: int = Query(default=1_500, ge=30, le=3_000),

    include_no_change: bool = Query(default=False),

) -> dict[str, Any]:

    """

    선택한 Transportation No.의 ETD/ETA 변경 Timeline을 반환한다.


 

    Overview와 달리 완료 운송건도 조회할 수 있다.

    """

    try:

        info_df = fetch_bl_info_for_transport(

            trpr_no=trpr_no,

            cmpy_cd=cmpy_cd or None,

            plnt_cd=plnt_cd or None,

            max_rows=5_000,

        )


 

        snapshot_df = build_transport_snapshot(

            info_df,

            active_only=False,

        ) if not info_df.empty else pd.DataFrame()


 

        history_df = fetch_bl_history_for_transport(

            trpr_no=trpr_no,

            cmpy_cd=cmpy_cd or None,

            plnt_cd=plnt_cd or None,

            changed_from=(

                date.today()

                - timedelta(days=history_days)

            ),

            max_rows=20_000,

        )


 

        if snapshot_df.empty and history_df.empty:

            raise HTTPException(

                status_code=404,

                detail=f"운송번호 {trpr_no}의 Snapshot/History를 찾지 못했습니다.",

            )


 

        snapshot_row = (

            snapshot_df.iloc[0]

            if not snapshot_df.empty

            else None

        )


 

        payload = build_transport_timeline(

            snapshot_row,

            history_df,

            cmpy_cd=cmpy_cd,

            plnt_cd=plnt_cd,

            trpr_no=trpr_no,

            include_no_change=include_no_change,

        )


 

        return _clean_value(

            {

                "generated_at": datetime.now().isoformat(

                    timespec="seconds"

                ),

                **payload,

            }

        )


 

    except HTTPException:

        raise

    except RuntimeError as exc:

        raise HTTPException(status_code=502, detail=str(exc)) from exc

    except ValueError as exc:

        raise HTTPException(status_code=422, detail=str(exc)) from exc

    except Exception as exc:

        raise HTTPException(

            status_code=500,

            detail=(

                "일정 Timeline 처리 실패: "

                f"{type(exc).__name__}: {exc}"

            ),

        ) from exc


# ---------- 선박 MMSI 인벤토리 ----------
# '선박 MMSI 관리' 탭 전용. 대시보드 조회(법인 필터)와 무관하게
# 법인 구분 없이 최근 1년 활성 운송의 선박명을 집계한다.
VESSEL_INVENTORY_ETD_DAYS = 365
VESSEL_INVENTORY_MAX_ROWS = 20_000
VESSEL_INVENTORY_SELECT_COLUMNS = [
    "cmpy_cd", "plnt_cd", "trpr_no", "vessel_nm",
    "dprt", "dprt_nm", "arvl", "arvl_nm",
    "eta", "eta_date", "ata", "dlvy_ata", "cmpl_yn",
]
# 프런트 services/vesselMmsi.ts의 INVALID_VESSEL_NAMES와 동일 기준.
VESSEL_NAME_PLACEHOLDERS = frozenset({
    "", "-", "NA", "N/A", "NONE", "NULL", "UNKNOWN", "UNKNOWN VESSEL",
    "TBA", "TBD", "TBN", "TO BE ANNOUNCED", "TO BE NAMED",
    "미정", "선박미정", "선명미정",
})


def _is_usable_vessel_name(value: Any) -> bool:
    name = str(value or "").strip()
    return len(name) >= 2 and name.upper() not in VESSEL_NAME_PLACEHOLDERS


def _build_vessel_inventory(snapshot_df: pd.DataFrame) -> list[dict[str, Any]]:
    """활성 운송 Snapshot을 선박명(IF 원문, trim) 기준으로 집계한다."""
    if snapshot_df.empty or "vessel_name" not in snapshot_df.columns:
        return []

    work = snapshot_df.copy()
    work["_vessel"] = work["vessel_name"].fillna("").astype(str).str.strip()
    work = work[work["_vessel"].map(_is_usable_vessel_name)]

    vessels: list[dict[str, Any]] = []
    for vessel_name, group in work.groupby("_vessel", sort=False):
        # 법인 구분 없이 묶으므로 같은 trpr_no가 여러 법인 행으로
        # 나뉘어 있을 수 있다 — 운송 수는 유니크 trpr_no 기준.
        trpr_nos = sorted({
            str(value).strip()
            for value in group["trpr_no"].dropna()
            if str(value).strip()
        })
        lanes: set[str] = set()
        for row in group.to_dict(orient="records"):
            pol = str(row.get("pol_name") or row.get("pol") or "").strip()
            pod = str(row.get("pod_name") or row.get("pod") or "").strip()
            if not pol and not pod:
                continue
            lanes.add(f"{pol or '?'}–{pod or '?'}")
        eta_values = pd.to_datetime(
            group["current_eta"], errors="coerce",
        ).dropna()
        vessels.append({
            "vessel_name": str(vessel_name),
            "shipment_count": len(trpr_nos),
            "trpr_nos": trpr_nos[:5],
            "lanes": sorted(lanes),
            "latest_eta": (
                eta_values.max().isoformat() if not eta_values.empty else None
            ),
        })

    vessels.sort(
        key=lambda item: (-item["shipment_count"], item["vessel_name"]),
    )
    return vessels


@app.get("/api/vessels/inventory")
def vessel_inventory(
    refresh: bool = Query(default=False),
) -> dict[str, Any]:
    """선박 MMSI 관리 탭 전용 선박 인벤토리 (법인 구분 없음)."""
    key = "vessels|inventory"
    if not refresh and key in _CACHE:
        cached_at, payload = _CACHE[key]
        if time.time() - cached_at <= CACHE_TTL_SECONDS:
            return {**payload, "cache_hit": True}

    try:
        info_df = fetch_bl_info(
            etd_from=(
                date.today() - timedelta(days=VESSEL_INVENTORY_ETD_DAYS)
            ),
            select_columns=VESSEL_INVENTORY_SELECT_COLUMNS,
            max_rows=VESSEL_INVENTORY_MAX_ROWS,
        )
        snapshot_df = build_transport_snapshot(info_df, active_only=True)
        payload = _clean_value({
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "cache_hit": False,
            "transport_count": int(len(snapshot_df)),
            "vessels": _build_vessel_inventory(snapshot_df),
        })
        _CACHE[key] = (time.time(), payload)
        return payload
    except RuntimeError as exc:
        # 데이터레이크 남부(서버 안쪽) 예외 문자열은 응답에 노출하지 않고 로그만 남긴다.
        logger.exception("선박 인벤토리 데이터레이크 조회 실패")
        raise HTTPException(
            status_code=502,
            detail="데이터레이크 조회에 실패했습니다. 잠시 후 다시 시도해 주세요.",
        ) from exc
    except Exception as exc:
        logger.exception("선박 인벤토리 집계 실패")
        raise HTTPException(
            status_code=500,
            detail="선박 인벤토리 집계에 실패했습니다. 잠시 후 다시 시도해 주세요.",
        ) from exc


@app.get("/api/report/leadtime")
def leadtime_report(
    months: int = Query(default=12, ge=3, le=36),
    forecast_months: int = Query(default=3, ge=1, le=6),
    refresh: bool = Query(default=False),
) -> dict[str, Any]:
    """항로별 리드타임 리포트 (B-LAP 자동 집계)."""
    key = f"leadtime|{months}|{forecast_months}"
    if not refresh and key in _CACHE:
        cached_at, payload = _CACHE[key]
        if time.time() - cached_at <= CACHE_TTL_SECONDS:
            return {**payload, "cache_hit": True}

    try:
        from services.leadtime_report_service import fetch_leadtime_report

        payload = _apply_leadtime_overrides(
            fetch_leadtime_report(
                months=months,
                forecast_months=forecast_months,
            )
        )
        _CACHE[key] = (time.time(), payload)
        return payload
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "리드타임 리포트 처리 실패: "
                f"{type(exc).__name__}: {exc}"
            ),
        ) from exc


 

# ---------- MI 리포트 게시본(스냅샷) ----------
# 지정 사용자만 SharePoint MI 폴터에 게시본을 저장하고,
# 모든 사용자는 라이브 집계 대신 게시본을 열어 본다.
REPORT_PUBLISH_USERS = {
    u.strip().lower()
    for u in os.environ.get(
        "REPORT_PUBLISH_USERS", "so23132,so23364"
    ).split(",")
    if u.strip()
}
REPORT_SNAPSHOT_RELATIVE_PATH = _Path("MI") / "report_snapshot.json"


def _report_snapshot_path() -> _Path:
    from backend.app.core.marinesia_settings import get_marinesia_settings

    return get_marinesia_settings().sharepoint_root / REPORT_SNAPSHOT_RELATIVE_PATH


def _current_username_lower() -> str:
    from backend.app.core.user_path import current_username

    return current_username().strip().lower()


@app.get("/api/report/snapshot")
def get_report_snapshot() -> dict[str, Any]:
    """게시본 조회 — 전 사용자 열람. can_publish로 갱신 권한 여부를 알린다."""
    path = _report_snapshot_path()
    snapshot = None
    if path.exists():
        try:
            snapshot = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            snapshot = None
    return {
        "exists": snapshot is not None,
        "can_publish": _current_username_lower() in REPORT_PUBLISH_USERS,
        "snapshot": snapshot,
    }


@app.get("/api/me")
def get_current_user() -> dict[str, Any]:
    """현재 사용자 정보 — 외부 MI 정제 탭 관리 권한 판정용.

    사용자명은 서버 프로세스의 OS 로그인 사용자(user_path.current_username)이며,
    관리 권한은 REPORT_PUBLISH_USERS 목록을 그대로 재사용한다.
    """
    username = _current_username_lower()
    return {
        "username": username,
        "can_manage_mi": username in REPORT_PUBLISH_USERS,
    }


@app.post("/api/report/snapshot/publish")
def publish_report_snapshot() -> dict[str, Any]:
    """게시본 갱신 — 지정 사용자만. 현재 리드타임 집계 + 인사이트 초안을 저장."""
    username = _current_username_lower()
    if username not in REPORT_PUBLISH_USERS:
        raise HTTPException(
            status_code=403, detail="게시 권한이 없는 사용자입니다."
        )

    from backend.app.services.insight_draft_store import InsightDraftStore
    from services.leadtime_report_service import fetch_leadtime_report

    # /api/report/leadtime 과 동일 파이프라인 (override 반영)
    try:
        report = _apply_leadtime_overrides(
            fetch_leadtime_report(months=12, forecast_months=3)
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    month = date.today().isoformat()[:7]
    insight = None
    try:
        insight = {**InsightDraftStore().load(month), "regenerated": False}
    except Exception:
        # 초안이 아직 없으면 리드타임만 게시한다.
        insight = None

    snapshot = {
        "published_at": datetime.now().isoformat(timespec="seconds"),
        "published_by": username,
        "month": month,
        "report": report,
        "insight": insight,
        "gap": None,
    }
    # ETA-ATA Gap 요약도 게시본에 포함 (best-effort — 실패 시 None)
    try:
        from services.eta_ata_gap_service import fetch_eta_ata_gap

        snapshot["gap"] = fetch_eta_ata_gap()
    except Exception:
        logger.exception("Gap 집계 실패 — 게시본에서 제외하고 진행")

    # 파일 쓰기는 atomic (tmp → os.replace)
    path = _report_snapshot_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(snapshot, ensure_ascii=False), encoding="utf-8",
    )
    os.replace(tmp, path)
    return snapshot


 

@app.get("/api/anomaly/eta-ata-gap")
def eta_ata_gap_report(
    weeks: int | None = Query(default=None, ge=4, le=16),
    refresh: bool = Query(default=False),
) -> dict[str, Any]:
    """ETA-ATA Gap 주차별 집계 + 추세/경고 판정 (협의체장 요구).

    weeks 미지정 시 gap_thresholds 설정값을 쓴다.
    """
    key = f"eta-ata-gap|{weeks}"
    if not refresh and key in _CACHE:
        cached_at, payload = _CACHE[key]
        if time.time() - cached_at <= CACHE_TTL_SECONDS:
            return {**payload, "cache_hit": True}

    try:
        from services.eta_ata_gap_service import fetch_eta_ata_gap

        payload = fetch_eta_ata_gap(weeks=weeks)
        payload = {**payload, "cache_hit": False}
        _CACHE[key] = (time.time(), payload)
        return payload
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "ETA-ATA Gap 집계 실패: "
                f"{type(exc).__name__}: {exc}"
            ),
        ) from exc


# 주의: /groups는 /delay-decomposition보다 먼저 등록해 경로 충돌을 피한다.
@app.get("/api/anomaly/delay-decomposition/groups")
def delay_decomposition_groups() -> dict[str, Any]:
    """지연 분해 대상 항로 그룹 목록 — 데이터레이크 호출 없는 경량 엔드포인트.

    첫 조회 전 드롭다운을 채우기 위한 설정값 조회.
    """
    from services.delay_decomposition_service import list_delay_groups

    return {"groups": list_delay_groups()}


@app.get("/api/anomaly/delay-decomposition")
def delay_decomposition_report(
    group_id: str = Query(default="ADRIA_SUEZ"),
    months: int = Query(default=12, ge=1, le=36),
    refresh: bool = Query(default=False),
) -> dict[str, Any]:
    """도착지연 분해(출항지연+항해 증감) & 선사 정시성 집계."""
    key = f"delay-decomposition|{group_id}|{months}"
    if not refresh and key in _CACHE:
        cached_at, payload = _CACHE[key]
        if time.time() - cached_at <= CACHE_TTL_SECONDS:
            return {**payload, "cache_hit": True}

    try:
        from services.delay_decomposition_service import (
            fetch_delay_decomposition,
        )

        payload = fetch_delay_decomposition(group_id=group_id, months=months)
        payload = {**payload, "cache_hit": False}
        _CACHE[key] = (time.time(), payload)
        return payload
    except ValueError as exc:
        # 지원하지 않는 group_id — 남부(서버 안쪽) 예외 문자열은
        # 응답에 노출하지 않고 로그만 남긴다.
        logger.warning("지연 분해 요청 거부: %s", exc)
        raise HTTPException(
            status_code=404,
            detail="지원하지 않는 항로 그룹입니다.",
        ) from exc
    except RuntimeError as exc:
        logger.exception("지연 분해 데이터레이크 조회 실패")
        raise HTTPException(
            status_code=502,
            detail="데이터레이크 조회에 실패했습니다. 잠시 후 다시 시도해 주세요.",
        ) from exc
    except Exception as exc:
        logger.exception("지연 분해 집계 실패")
        raise HTTPException(
            status_code=500,
            detail="도착지연 분해 집계에 실패했습니다. 잠시 후 다시 시도해 주세요.",
        ) from exc


 

ROUTE_MASTER_ALLOWED_DIMS = {
    "cmpy_nm",
    "plnt_nm",
    "lsp_nm",
    "bsns_ccd_nm",
    "trpr_mode",
    "dprt_pair",
    "to_stlc_pair",
}
# 쌍 묶음 구분조건 — 하나의 체크로 코드+이름 열을 동시에 그룹핑/표시한다.
ROUTE_MASTER_PAIR_DIMS = {
    "dprt_pair": ["dprt", "dprt_nm"],
    "to_stlc_pair": ["to_stlc_cd", "to_stlc_nm"],
}
# 항상 포함되는 기본 열 (도착지). 출발지/최종사이트는 구분조건 선택 시에만
# 그룹핑·표시되므로 미선택 시 해당 열 없이 재집계된다.
ROUTE_MASTER_BASE_COLUMNS = ["arvl", "arvl_nm"]
ROUTE_MASTER_MAX_ROWS = 500
# trpr_mode 코드 라벨 — 100 해상, 300 Rail+Truck (사용자 확인),
# 200 육상(Direct Truck)은 추정. 항공 코드는 미확인.
TRPR_MODE_LABELS = {
    "100": "해상",
    "200": "육상",
    "300": "Rail+Truck",
}
# 경로 마스터 그룹화에 필요한 컬럼만 서버측 프로젝션 — 전체 88컬럼을
# 받으면 5만 행 조회가 수백 MB가 되어 탭이 멈춘 것처럼 보인다.
ROUTE_MASTER_SELECT_COLUMNS = [
    "trpr_no",
    "cmpy_nm", "plnt_nm", "lsp_nm", "bsns_ccd_nm", "trpr_mode",
    "dprt", "dprt_nm", "arvl", "arvl_nm", "to_stlc_cd", "to_stlc_nm",
]


@app.get("/api/routes/master")
def route_master(
    companies: list[str] = Query(default=[]),
    dims: list[str] = Query(default=[]),
    etd_days: int = Query(default=365, ge=30, le=1_500),
    etd_from: str | None = Query(default=None),
    etd_to: str | None = Query(default=None),
    refresh: bool = Query(default=False),
) -> dict[str, Any]:
    """PORT TO PORT + 최종 도착지 조합 마스터 (구분자 선택 그룹화)."""
    selected_dims = list(dict.fromkeys(dims))
    invalid_dims = [
        dim for dim in selected_dims
        if dim not in ROUTE_MASTER_ALLOWED_DIMS
    ]
    if invalid_dims:
        raise HTTPException(
            status_code=422,
            detail=(
                f"허용되지 않은 dims: {invalid_dims} "
                f"(허용: {sorted(ROUTE_MASTER_ALLOWED_DIMS)})"
            ),
        )

    def _parse_day(value: str | None, name: str) -> date | None:
        if value is None or not value.strip():
            return None
        text = value.strip()
        # Python 3.11+의 fromisoformat은 YYYYMMDD도 받으므로
        # 계약 형식(YYYY-MM-DD)을 먼저 강제한다.
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            raise HTTPException(
                status_code=422,
                detail=f"{name}은 YYYY-MM-DD 형식이어야 합니다: {value}",
            )
        try:
            return date.fromisoformat(text)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"{name}은 YYYY-MM-DD 형식이어야 합니다: {value}",
            ) from exc

    from_day = _parse_day(etd_from, "etd_from")
    to_day = _parse_day(etd_to, "etd_to")
    if from_day and to_day and from_day > to_day:
        raise HTTPException(
            status_code=422,
            detail="etd_from이 etd_to보다 늦습니다.",
        )
    # 기간 미지정이면 etd_days 상대 방식(기존 동작), from만 있으면 from~today.
    effective_from = (
        from_day if from_day else date.today() - timedelta(days=etd_days)
    )

    cache_key = _cache_key(
        companies,
        etd_days,
        from_day.isoformat() if from_day else "-",
        to_day.isoformat() if to_day else "-",
        hash(tuple(selected_dims)),
    )
    key = f"route-master|{cache_key}"
    if not refresh and key in _CACHE:
        cached_at, payload = _CACHE[key]
        if time.time() - cached_at <= CACHE_TTL_SECONDS:
            return {**payload, "cache_hit": True}

    try:
        info_df = fetch_bl_info(
            etd_from=effective_from,
            etd_to=to_day,
            companies=companies or None,
            select_columns=ROUTE_MASTER_SELECT_COLUMNS,
            max_rows=50_000,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # 쌍 묶음 dims를 실제 컬럼으로 확장하고, 기본 열(도착지)과 합쳐 중복 제거
    expanded_dims: list[str] = []
    for dim in selected_dims:
        expanded_dims.extend(ROUTE_MASTER_PAIR_DIMS.get(dim, [dim]))
    group_columns = list(dict.fromkeys(
        expanded_dims + ROUTE_MASTER_BASE_COLUMNS
    ))
    work = info_df.copy()
    for column in ["trpr_no", *group_columns]:
        if column not in work.columns:
            work[column] = ""
        work[column] = work[column].fillna("").astype(str).str.strip()

    # shipment_count는 PO 라인이 아니라 운송번호(trpr_no) 유니크 기준.
    grouped = (
        work.groupby(group_columns, dropna=False)["trpr_no"]
        .nunique()
        .reset_index(name="shipment_count")
        .sort_values(
            ["shipment_count", *group_columns],
            ascending=[False, *([True] * len(group_columns))],
        )
    )
    total_rows = int(len(grouped))
    truncated = total_rows > ROUTE_MASTER_MAX_ROWS
    records = grouped.head(ROUTE_MASTER_MAX_ROWS).to_dict("records")

    if "trpr_mode" in selected_dims:
        for record in records:
            mode_code = str(record.get("trpr_mode") or "")
            record["trpr_mode_label"] = TRPR_MODE_LABELS.get(
                mode_code, mode_code,
            )

    payload = _clean_value({
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "cache_hit": False,
        "total_rows": total_rows,
        "truncated": truncated,
        "rows": records,
    })
    _CACHE[key] = (time.time(), payload)
    return payload


 

FREIGHT_SERIES_LABELS = {
    "scfi": "SCFI",
    "kcci": "KCCI 종합",
    "kcci_usec": "KCCI 북미 동안 (USD/40')",
    "kcci_med": "KCCI 지중해 (USD/40')",
}
FREIGHT_INDICES_RELATIVE_PATH = (
    _Path("MI") / "freight_indices" / "freight_indices.json"
)


def _freight_indices_path() -> _Path | None:
    from backend.app.core.marinesia_settings import (
        get_marinesia_settings,
    )

    sharepoint_file = (
        get_marinesia_settings().sharepoint_root
        / FREIGHT_INDICES_RELATIVE_PATH
    )
    if sharepoint_file.is_file():
        return sharepoint_file

    fallback = (
        _Path(__file__).resolve().parent
        / "backend" / "data" / "freight_indices.json"
    )
    return fallback if fallback.is_file() else None


@app.get("/api/report/freight-indices")
def freight_indices() -> dict[str, Any]:
    """운임지수 시계열 (SharePoint 동기화 폴터, 없으면 backend/data 폴�)."""
    path = _freight_indices_path()
    if path is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "freight_indices.json을 찾지 못했습니다. "
                "SharePoint MI\\freight_indices 또는 backend/data를 "
                "확인하세요."
            ),
        )

    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=502,
            detail=f"운임지수 파일을 읽지 못했습니다: {exc}",
        ) from exc

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=502,
            detail="운임지수 파일의 최상위 구조가 객체가 아닙니다.",
        )

    series: list[dict[str, Any]] = []
    for key, label in FREIGHT_SERIES_LABELS.items():
        raw_points = payload.get(key)
        if raw_points is None:
            continue
        if not isinstance(raw_points, list):
            raise HTTPException(
                status_code=502,
                detail=f"운임지수 시리즈 {key}가 배열이 아닙니다.",
            )
        points: list[dict[str, Any]] = []
        for item in raw_points:
            if (
                not isinstance(item, dict)
                or "date" not in item
                or "value" not in item
            ):
                raise HTTPException(
                    status_code=502,
                    detail=(
                        f"운임지수 시리즈 {key}에 "
                        "date/value가 없는 항목이 있습니다."
                    ),
                )
            try:
                value = float(item["value"])
            except (TypeError, ValueError) as exc:
                raise HTTPException(
                    status_code=502,
                    detail=(
                        f"운임지수 시리즈 {key}의 value가 "
                        f"숫자가 아닙니다: {item['value']!r}"
                    ),
                ) from exc
            points.append({"date": str(item["date"]), "value": value})
        series.append({"key": key, "label": label, "points": points})

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_file": str(path),
        "series": series,
    }


 

class InsightDraftBody(BaseModel):
    month: str | None = None
    include_leadtime: bool = True
    regenerate: bool = False


class InsightDraftPutBody(BaseModel):
    draft: dict[str, Any]


@app.post("/api/report/insight-draft")
def insight_draft(body: InsightDraftBody = Body(...)) -> dict[str, Any]:
    """월간 인사이트 초안 자동 생성 (Actify)."""
    if body.month is not None:
        try:
            date.fromisoformat(f"{body.month}-01")
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail="month는 YYYY-MM 형식이어야 합니다",
            )
    try:
        from backend.app.services.mi_insight_draft import (
            ActifyNotConfiguredError,
            generate_insight_draft,
        )

        return generate_insight_draft(
            month=body.month,
            include_leadtime=body.include_leadtime,
            regenerate=body.regenerate,
        )
    except ActifyNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "인사이트 초안 처리 실패: "
                f"{type(exc).__name__}: {exc}"
            ),
        ) from exc


 

def _validate_month(month: str) -> None:
    try:
        date.fromisoformat(f"{month}-01")
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail="month는 YYYY-MM 형식이어야 합니다",
        )


@app.get("/api/report/insight-draft/{month}")
def get_insight_draft(month: str) -> dict[str, Any]:
    """저장된 월간 인사이트 초안 복원."""
    _validate_month(month)
    from backend.app.services.insight_draft_store import (
        InsightDraftNotFoundError,
        InsightDraftStore,
    )

    try:
        record = InsightDraftStore().load(month)
        return {**record, "regenerated": False}
    except InsightDraftNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"저장된 초안이 없습니다: {month}",
        )


@app.put("/api/report/insight-draft/{month}")
def put_insight_draft(month: str, body: InsightDraftPutBody) -> dict[str, Any]:
    """월간 인사이트 초안 편집본 저장 (revised_at 갱신)."""
    _validate_month(month)
    from backend.app.services.mi_insight_draft import save_revised_draft

    try:
        return save_revised_draft(month, body.draft)
    except (ValidationError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"초안 스키마가 올바르지 않습니다: {exc}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "인사이트 초안 저장 실패: "
                f"{type(exc).__name__}: {exc}"
            ),
        ) from exc


LEADTIME_OVERRIDES_PATH = (
    _Path(__file__).resolve().parent / "backend" / "data" / "leadtime_overrides.json"
)


def _load_leadtime_overrides() -> dict[str, float]:
    if not LEADTIME_OVERRIDES_PATH.exists():
        return {}
    try:
        data = json.loads(
            LEADTIME_OVERRIDES_PATH.read_text(encoding="utf-8")
        )
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_leadtime_overrides(overrides: dict[str, float]) -> None:
    LEADTIME_OVERRIDES_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = LEADTIME_OVERRIDES_PATH.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(overrides, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp, LEADTIME_OVERRIDES_PATH)
    # leadtime 캐시 무효화
    for key in [k for k in _CACHE if k.startswith("leadtime|")]:
        _CACHE.pop(key, None)


def _apply_leadtime_overrides(payload: dict[str, Any]) -> dict[str, Any]:
    """GET 응답에 수동 편집값 병합. edited_cells에 적용된 키 목록 반환."""
    overrides = _load_leadtime_overrides()
    if not overrides:
        return {**payload, "edited_cells": []}
    applied: list[str] = []
    for group in payload.get("groups", []):
        for row in group.get("rows", []):
            for month in list(row.get("cells", {}).keys()):
                key = (
                    f"{group['group_id']}|{row['country']}"
                    f"|{row['stat']}|{month}"
                )
                if key in overrides:
                    row["cells"][month] = overrides[key]
                    applied.append(key)
    return {**payload, "edited_cells": applied}


class LeadtimeOverridesBody(BaseModel):
    overrides: dict[str, float]


@app.put("/api/report/leadtime/overrides")
def put_leadtime_overrides(body: LeadtimeOverridesBody) -> dict[str, Any]:
    """리드타임 셀 수동 편집값 부분 병합 저장."""
    overrides = _load_leadtime_overrides()
    overrides.update(body.overrides)
    _save_leadtime_overrides(overrides)
    return {"saved": len(body.overrides), "total": len(overrides)}


@app.delete("/api/report/leadtime/overrides")
def delete_leadtime_overrides() -> dict[str, Any]:
    """리드타임 수동 편집값 전체 초기화."""
    _save_leadtime_overrides({})
    return {"deleted": True}


 

@app.post("/api/mi/registry/rebuild")
def rebuild_mi_registry() -> dict[str, Any]:
    """MI 이벤트 레지스트리 전체 재구축 (일자별 파일 재인입, 멱등)."""
    try:
        from backend.app.services import mi_event_registry

        return mi_event_registry.rebuild_registry()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "레지스트리 재구축 실패: "
                f"{type(exc).__name__}: {exc}"
            ),
        ) from exc


@app.get("/api/mi/registry")
def list_mi_registry(status: str | None = Query(default=None)) -> dict[str, Any]:
    """MI 이벤트 레지스트리 조회 (ACTIVE>IMPROVING>RESOLVED, 최신 last_seen 순)."""
    try:
        from backend.app.services import mi_event_registry

        return mi_event_registry.list_events(status=status)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "레지스트리 조회 실패: "
                f"{type(exc).__name__}: {exc}"
            ),
        ) from exc


@app.get("/api/mi/registry/map-zones")
def get_mi_registry_map_zones() -> list[dict[str, Any]]:
    """레지스트리 ACTIVE/IMPROVING 이벤트의 지도 영향권 (미승인, 추적 중)."""
    from backend.app.services import mi_event_registry

    try:
        return mi_event_registry.map_zones()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "레지스트리 영향권 조회 실패: "
                f"{type(exc).__name__}: {exc}"
            ),
        ) from exc


@app.get("/api/mi/approved/map-zones")
def get_mi_approved_map_zones() -> list[dict[str, Any]]:
    """최신 승인(canonical) MI 이벤트의 지도 영향권 (정제·승인 완료분)."""
    from backend.app.services import mi_approved_map

    try:
        return mi_approved_map.approved_map_zones()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="승인 이벤트 영향권 조회에 실패했습니다.",
        ) from exc


@app.get("/api/mi/registry/{event_id}")
def get_mi_registry_event(event_id: str) -> dict[str, Any]:
    """MI 이벤트 레지스트리 단건 조회."""
    from backend.app.services import mi_event_registry

    event = mi_event_registry.get_event(event_id)
    if event is None:
        raise HTTPException(
            status_code=404,
            detail=f"이벤트를 찾을 수 없습니다: {event_id}",
        )
    return event


 

# ---------- 관심화물(watchlist) + 알림 feed ----------

SIGNAL_LABELS = {
    "REPEATED_ETD_DELAY": "ETD 반복 지연",
    "REPEATED_ETA_DELAY": "ETA 반복 지연",
    "LEAD_TIME_ANOMALY": "Lead Time 증가",
    "LARGE_SCHEDULE_DELAY": "대규모 일정 지연",
    "DELIVERY_REQ_BREACH": "납기 초과",
}


class WatchlistBody(BaseModel):
    id: str
    label: str = ""


@app.get("/api/watchlist")
def get_watchlist() -> dict[str, Any]:
    from backend.app.services import watchlist_store

    return watchlist_store.load()


@app.post("/api/watchlist", status_code=201)
def add_watchlist(body: WatchlistBody) -> dict[str, Any]:
    from backend.app.services import watchlist_store

    try:
        return watchlist_store.add(body.id, body.label)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.delete("/api/watchlist/{item_id}")
def delete_watchlist(item_id: str) -> dict[str, Any]:
    from backend.app.services import watchlist_store

    if not watchlist_store.remove(item_id):
        raise HTTPException(
            status_code=404,
            detail=f"관심화물에 없습니다: {item_id}",
        )
    return {"deleted": item_id}


def _norm_hbl(value: Any) -> str:
    return str(value or "").replace(" ", "").upper()


def _cached_overview_transports() -> dict[str, dict[str, Any]]:
    """이미 계산된 overview 캐시가 있으면 HBL 인덱스로 재사용 (없으면 빈 dict)."""
    for _key, (_cached_at, payload) in _CACHE.items():
        if isinstance(payload, dict) and isinstance(payload.get("transports"), list):
            return {
                _norm_hbl(row.get("hbl_no")): row
                for row in payload["transports"]
                if _norm_hbl(row.get("hbl_no"))
            }
    return {}


def _transport_alerts_from_row(row: dict[str, Any]) -> list[dict[str, Any]]:
    """enriched transport 1행 → 알림 배열 (v1 타입)."""
    alerts: list[dict[str, Any]] = []
    breach = int(row.get("delivery_req_breach_days") or 0)
    if breach > 0:
        alerts.append(
            {
                "type": "DELIVERY_REQ_BREACH",
                "severity": "HIGH" if breach >= 7 else "MEDIUM",
                "message": f"납기 초과 +{breach}일",
                "value": breach,
            }
        )
    signals = row.get("anomaly_signals") or []
    if signals:
        labels = [SIGNAL_LABELS.get(s, str(s)) for s in signals]
        alerts.append(
            {
                "type": "SIGNAL",
                "severity": str(row.get("severity") or "MEDIUM"),
                "message": "이상 신호: " + ", ".join(labels),
                "value": len(signals),
            }
        )
    return alerts


def _enriched_transports_by_hbl(hbl_nos: list[str]) -> dict[str, dict[str, Any]]:
    """watch된 HBL만 직접 조회해 enriched transport 반환.

    전체 overview 계산(Denodo 전체 조회+이력 chunk)과 달리
    HBL 건당 소형 쿼리 2종(info/history)만 사용해 캐시 무관하게 가볍다.
    """
    from services.anomaly_engine import evaluate_schedule_anomalies
    from services.datalake_schedule_client import (
        fetch_bl_history_for_transports,
        fetch_bl_info,
    )
    from services.schedule_history_service import (
        build_schedule_metrics,
        build_transport_snapshot,
    )

    info_df = fetch_bl_info(hbl_nos=hbl_nos)
    snapshot_df = build_transport_snapshot(info_df, active_only=True)
    if snapshot_df.empty:
        return {}

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
    enriched_df, _events = evaluate_schedule_anomalies(metrics_df)

    result: dict[str, dict[str, Any]] = {}
    for row in enriched_df.to_dict(orient="records"):
        key = _norm_hbl(row.get("hbl_no"))
        if key and key not in result:
            result[key] = row
    return result


@app.get("/api/notifications")
def get_notifications() -> dict[str, Any]:
    """관심화물 알림 feed — 판단은 백엔드 단일 주체.

    조회 경로: overview 캐시에 이미 있으면 재사용, 없는 HBL은
    fetch_bl_info(hbl_nos=...) 직접 조회 (전체 overview 계산하지 않음).
    v1 알림 타입: DELIVERY_REQ_BREACH / SIGNAL / NOT_FOUND.
    (확장 여지: shortage 등 Item 기준정보 연동 알람)
    """
    from backend.app.services import watchlist_store

    watchlist = watchlist_store.load()
    items = watchlist.get("items", [])
    if not items:
        return {"computed_at": datetime.now().isoformat(timespec="seconds"),
                "cache_hit": False, "items": []}

    try:
        cached = _cached_overview_transports()
        hbl_nos = [str(i["id"]) for i in items if i.get("type") == "hbl"]
        missing = [h for h in hbl_nos if _norm_hbl(h) not in cached]
        fully_cached = not missing
        direct = _enriched_transports_by_hbl(missing) if missing else {}
        by_hbl = {**direct, **cached}
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "알림 feed 처리 실패: "
                f"{type(exc).__name__}: {exc}"
            ),
        ) from exc

    result_items: list[dict[str, Any]] = []
    for item in items:
        if item.get("type") != "hbl":
            continue
        hbl_no = item["id"]
        row = by_hbl.get(_norm_hbl(hbl_no))
        if row is None:
            alerts = [
                {
                    "type": "NOT_FOUND",
                    "severity": "LOW",
                    "message": "활성 운송에서 찾을 수 없습니다 (완료 또는 미존재 가능)",
                    "value": None,
                }
            ]
        else:
            alerts = _transport_alerts_from_row(row)
        result_items.append(
            {"hbl_no": hbl_no, "label": item.get("label", ""), "alerts": alerts}
        )

    return {
        "computed_at": datetime.now().isoformat(timespec="seconds"),
        "cache_hit": fully_cached,
        "items": result_items,
    }


 

@app.get("/api/mi/location-master")
def mi_location_master() -> dict[str, Any]:
    """위치 마스터 — 검토 패널의 위치 드롭다운/미해결 위치 매칭 선택지."""
    from backend.app.services.mi_location_resolver import load_location_master

    master = load_location_master()
    return {
        "locations": [
            {
                "code": code,
                "name": str(item.get("name") or ""),
                "location_type": str(item.get("location_type") or ""),
                "lat": item.get("lat"),
                "lon": item.get("lon"),
                "default_radius_km": item.get("default_radius_km", 100),
                "aliases": item.get("aliases", []),
            }
            for code, item in sorted(master.items())
        ]
    }


@app.post("/api/mi/registry/review")
def review_mi_registry() -> dict[str, Any]:
    """레지스트리 종합 정제 (Actify) — 제안만 반환, 자동 반영 없음 (HITL)."""
    from backend.app.services.mi_registry_review import (
        ActifyNotConfiguredError,
        generate_registry_review,
    )

    try:
        return generate_registry_review()
    except ActifyNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "레지스트리 종합 정제 실패: "
                f"{type(exc).__name__}: {exc}"
            ),
        ) from exc


class RegistryApplyBody(BaseModel):
    event_id: str
    suggested_status: str | None = None
    suggested_severity: str | None = None
    merge_with: str | None = None


@app.post("/api/mi/registry/apply")
def apply_mi_registry_proposal(body: RegistryApplyBody) -> dict[str, Any]:
    """종합 정제 제안 수락 반영 (건당 명시)."""
    from backend.app.services import mi_event_registry

    try:
        return mi_event_registry.apply_proposal(
            body.event_id,
            status=body.suggested_status,
            severity=body.suggested_severity,
            merge_with=body.merge_with,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"이벤트를 찾을 수 없습니다: {exc}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "제안 반영 실패: "
                f"{type(exc).__name__}: {exc}"
            ),
        ) from exc


 

# ---------- 업무 기준정보 설정 (config_store) ----------
# 하드코딩됐던 기준정보(항로 그룹, 임계값, 법인 매핑, 추론 규칙 등)를
# JSON 설정으로 노출한다. 읽기는 전원 허용, 쓰기/초기화는
# REPORT_PUBLISH_USERS 판정을 재사용한다.
# 주의: /catalog는 /{key}보다 먼저 등록해 경로 충돌을 피한다.


def _require_config_manager() -> None:
    """설정 쓰기 권한 확인 — REPORT_PUBLISH_USERS 판정 재사용."""
    if _current_username_lower() not in REPORT_PUBLISH_USERS:
        raise HTTPException(
            status_code=403, detail="설정 변경 권한이 없는 사용자입니다."
        )


@app.get("/api/config/catalog")
def config_catalog() -> dict[str, Any]:
    """설정 섹션 카탈로그 — 전 사용자 열람."""
    from services import config_store

    return {"sections": config_store.catalog()}


@app.get("/api/config/{key}")
def get_config_section(key: str) -> dict[str, Any]:
    """설정 섹션 조회 (현재 적용 데이터 포함) — 전 사용자 열람."""
    from services import config_store

    try:
        return config_store.describe(key, include_data=True)
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail="알 수 없는 설정 키입니다."
        ) from exc


@app.put("/api/config/{key}")
def put_config_section(
    key: str,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """설정 저장 — 관리자만. 검증 실패는 400(한국어 메시지)."""
    from services import config_store

    _require_config_manager()
    if not isinstance(body, dict) or "data" not in body:
        raise HTTPException(
            status_code=400, detail="요청 본문에 data 필드가 필요합니다."
        )
    try:
        config_store.validate_config(key, body["data"])
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail="알 수 없는 설정 키입니다."
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        config_store.save_config(key, body["data"])
    except OSError as exc:
        # 낸부 예외 문자열은 응답에 노출하지 않고 로그만 남긴다.
        logger.error("설정 저장 실패 (%s): %s", key, exc)
        raise HTTPException(
            status_code=500, detail="설정 저장에 실패했습니다."
        ) from exc
    # 설정 변경이 집계 결과에 즉시 반영되도록 캐시를 전체 비운다.
    _CACHE.clear()
    return {"ok": True}


@app.post("/api/config/{key}/reset")
def reset_config_section(key: str) -> dict[str, Any]:
    """설정 초기화 — 커스텀 파일 삭제 후 repo 기본값으로 복귀. 관리자만."""
    from services import config_store

    _require_config_manager()
    try:
        config_store.reset_config(key)
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail="알 수 없는 설정 키입니다."
        ) from exc
    except OSError as exc:
        logger.error("설정 초기화 실패 (%s): %s", key, exc)
        raise HTTPException(
            status_code=500, detail="설정 초기화에 실패했습니다."
        ) from exc
    _CACHE.clear()
    return {"ok": True}


# 프런트엔드 정적 서빙 — frontend/dist가 있으면 / 에 마운트한다.

# API 라우터는 위에서 먼저 등록되므로 /api/* 가 우선한다.

# exe 패키징 시에는 spec이 frontend/dist를 _MEIPASS에 포함시킨다.

_FRONTEND_DIST = _Path(__file__).resolve().parent / "frontend" / "dist"

if _FRONTEND_DIST.exists():

    from fastapi.staticfiles import StaticFiles as _StaticFiles

    app.mount(

        "/",

        _StaticFiles(directory=str(_FRONTEND_DIST), html=True),

        name="frontend",

    )
