from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ...core.marinesia_settings import get_marinesia_settings
from ...services.marinesia_sharepoint_reader import (
    discover_marinesia_files,
    read_marinesia_latest,
)


router = APIRouter(
    prefix="/api/marinesia",
    tags=["Marinesia SharePoint AIS"],
)


@router.get("/health")
def health() -> dict:
    settings = get_marinesia_settings()
    discovery = discover_marinesia_files(settings)
    latest = discovery["files"]["latest"]

    return {
        "configured": settings.configured,
        "root": str(settings.sharepoint_root),
        "root_exists": discovery["root_exists"],
        "latest_file_found": latest is not None,
        "latest_file": latest,
        "default_company": settings.default_company,
        "live_hours": settings.live_hours,
        "stale_warning_hours": settings.stale_warning_hours,
    }


@router.get("/files")
def files() -> dict:
    return discover_marinesia_files()


@router.get("/latest")
def latest(
    company: list[str] = Query(default=[]),
) -> dict:
    try:
        return read_marinesia_latest(company)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "SharePoint 동기화 파일을 읽지 못했습니다: "
                f"{type(exc).__name__}: {exc}"
            ),
        ) from exc
