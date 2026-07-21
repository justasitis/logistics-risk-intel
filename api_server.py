
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

from fastapi import FastAPI, HTTPException, Query

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