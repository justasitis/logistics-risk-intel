from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException

from ...core.stopby_settings import get_stopby_settings
from ...services.stopby_route_builder import (
    build_stopby_routes,
)


router = APIRouter(
    prefix="/api/routes/stopby",
    tags=["Stopby Route Geometry"],
)


@router.get("/health")
def health() -> dict[str, Any]:
    settings = get_stopby_settings()

    try:
        import searoute

        version = getattr(
            searoute,
            "__version__",
            "unknown",
        )
        available = True
        error = None
    except Exception as exc:
        version = None
        available = False
        error = f"{type(exc).__name__}: {exc}"

    return {
        "configured": True,
        "searoute_available": available,
        "searoute_version": version,
        "searoute_error": error,
        "europe_blank_default": (
            settings.europe_blank_default
        ),
        "route_algorithm": settings.route_algorithm,
        "maximum_routes": settings.maximum_routes,
    }


@router.post("")
def generate(
    payload: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    routes = payload.get("routes")
    transports = payload.get("transports")

    if not isinstance(routes, dict):
        raise HTTPException(
            status_code=422,
            detail="routes FeatureCollection이 필요합니다.",
        )

    if not isinstance(transports, list):
        raise HTTPException(
            status_code=422,
            detail="transports 배열이 필요합니다.",
        )

    try:
        return build_stopby_routes(
            routes,
            transports,
        )
    except ModuleNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "searoute가 설치되지 않았습니다. "
                "python -m pip install searoute를 실행하세요."
            ),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Stopby 경유항로 생성 실패: "
                f"{type(exc).__name__}: {exc}"
            ),
        ) from exc
