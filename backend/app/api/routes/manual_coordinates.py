from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.app.services.manual_coordinate_store import (
    delete_manual_coordinate,
    get_manual_coordinate,
    list_manual_coordinates,
    manual_coordinate_health,
    upsert_manual_coordinate,
)


router = APIRouter(
    prefix="/api/coordinates/manual",
    tags=["manual-coordinates"],
)


class ManualCoordinateUpsert(BaseModel):
    location_name: str = ""
    country_code: str = ""
    company: str = ""
    latitude: float = Field(
        ge=-90,
        le=90,
    )
    longitude: float = Field(
        ge=-180,
        le=180,
    )
    note: str = ""
    updated_by: str = ""


@router.get("/health")
def health() -> dict[str, Any]:
    return manual_coordinate_health()


@router.get("")
def list_coordinates(
    company: str | None = Query(
        default=None,
    ),
) -> dict[str, Any]:
    items = list_manual_coordinates(
        company=company,
    )

    return {
        "scope": "GLOBAL",
        "count": len(items),
        "items": items,
    }


@router.get("/{location_code}")
def read_coordinate(
    location_code: str,
    company: str | None = Query(
        default=None,
    ),
) -> dict[str, Any]:
    item = get_manual_coordinate(
        location_code,
        company,
    )

    if not item:
        raise HTTPException(
            status_code=404,
            detail="등록된 수동 좌표가 없습니다.",
        )

    return item


@router.put("/{location_code}")
def save_coordinate(
    location_code: str,
    payload: ManualCoordinateUpsert,
) -> dict[str, Any]:
    try:
        item = upsert_manual_coordinate(
            location_code=location_code,
            location_name=payload.location_name,
            country_code=payload.country_code,
            company=payload.company,
            latitude=payload.latitude,
            longitude=payload.longitude,
            note=payload.note,
            updated_by=payload.updated_by,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    return item


@router.delete("/{location_code}")
def remove_coordinate(
    location_code: str,
    company: str | None = Query(
        default=None,
    ),
) -> dict[str, Any]:
    deleted = delete_manual_coordinate(
        location_code,
        company,
    )

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail="삭제할 수동 좌표가 없습니다.",
        )

    return {
        "deleted": True,
        "scope": "GLOBAL",
        "location_code": location_code,
    }
