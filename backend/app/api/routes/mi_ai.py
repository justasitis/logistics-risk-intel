from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from ...core.mi_settings import get_mi_settings
from ...schemas.mi_ai import (
    RefineRequest,
    RefineResponse,
    ReviewRequest,
    ReviewResponse,
)
from ...services.external_mi_sharepoint_reader import (
    read_external_mi_candidates,
)
from ...services.mi_refiner import refine_candidates
from ...services.mi_repository import MiRunRepository

router = APIRouter(prefix="/api/mi-ai", tags=["MI AI"])


def _model_dump(model):
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()


@router.get("/health")
def health() -> dict:
    settings = get_mi_settings()
    return {
        "configured": settings.configured,
        "model_service": "ACTIFY",
        "response_mode": settings.actify_response_mode,
        "endpoint": settings.actify_url if settings.configured else "",
    }


@router.get("/external-candidates/sharepoint")
def external_candidates_sharepoint() -> dict:
    try:
        return read_external_mi_candidates()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "SharePoint 동기화 파일을 읽지 못했습니다: "
                f"{type(exc).__name__}: {exc}"
            ),
        ) from exc


@router.post("/refine", response_model=RefineResponse)
def refine(request: RefineRequest) -> RefineResponse:
    try:
        return refine_candidates(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/review", response_model=ReviewResponse)
def review(request: ReviewRequest) -> ReviewResponse:
    approved = [
        event
        for event in request.events
        if event.review_status in {"APPROVED", "EDITED"}
    ]
    rejected = [
        event
        for event in request.events
        if event.review_status == "REJECTED"
    ]

    canonical_payload = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_type": "INTERNAL_REFINED_MI",
        "analysis_id": request.analysis_id,
        "events": [_model_dump(event) for event in approved],
    }

    repository = MiRunRepository()
    try:
        stored = repository.load(request.analysis_id)
    except FileNotFoundError:
        stored = {}

    stored.update(
        {
            "stage": "REVIEWED",
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "canonical_payload": canonical_payload,
            "review_events": [_model_dump(event) for event in request.events],
        }
    )
    repository.save(request.analysis_id, stored)

    return ReviewResponse(
        analysis_id=request.analysis_id,
        approved_count=len(approved),
        rejected_count=len(rejected),
        canonical_payload=canonical_payload,
    )


@router.get("/runs/{analysis_id}")
def get_run(analysis_id: str) -> dict:
    try:
        return MiRunRepository().load(analysis_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="analysis run not found") from exc
