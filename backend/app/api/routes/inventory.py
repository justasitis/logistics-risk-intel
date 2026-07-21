"""L2 수급 영향도 시뮬레이션 API.

v2 샌드박스에서 백포트. 순수 함수 inventory_sim.simulate()에 품목 마스터를 전달해
재고 곡선과 위험 지표를 계산한다. 최종 판단은 수급 담당자(HITL).

NOTE(후속 과제): shipments의 eta_plan/eta_current는 현재 품목 마스터에 내장된
샘플 값이다. B-LAP 실 ETA 연동 시 이 라우터의 입력 조립부만 교체한다
(simulate() 시그니처/로직은 Dify 이식 자산이므로 변경하지 않는다).
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ...services import inventory_sim

logger = logging.getLogger(__name__)

ITEMS_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "inventory_items.json"
)

router = APIRouter(
    prefix="/api/inventory",
    tags=["Inventory Impact Simulation"],
)


def _load_items() -> dict[str, Any]:
    with open(ITEMS_PATH, encoding="utf-8") as f:
        return json.load(f)


@router.get("/items")
def get_inventory_items() -> dict[str, Any]:
    try:
        return _load_items()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="품목 마스터 파일이 없습니다")
    except Exception:
        logger.exception("품목 마스터 로드 실패")
        raise HTTPException(status_code=500, detail="품목 데이터 처리 중 오류가 발생했습니다")


class SimulateBody(BaseModel):
    item_id: str
    extra_delay_days: int = Field(default=0, ge=0, le=60)
    horizon_days: int = Field(default=45, ge=14, le=120)


@router.post("/simulate")
def simulate_inventory(body: SimulateBody) -> dict[str, Any]:
    try:
        data = _load_items()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="품목 마스터 파일이 없습니다")
    except Exception:
        logger.exception("품목 마스터 로드 실패")
        raise HTTPException(status_code=500, detail="품목 데이터 처리 중 오류가 발생했습니다")

    item = next(
        (i for i in data.get("items", []) if i.get("item_id") == body.item_id),
        None,
    )
    if item is None:
        raise HTTPException(
            status_code=404,
            detail=f"품목을 찾을 수 없습니다: {body.item_id}",
        )

    try:
        return inventory_sim.simulate(
            item,
            body.extra_delay_days,
            body.horizon_days,
            date.today(),
        )
    except Exception:
        logger.exception("수급 시뮬레이션 실패: %s", body.item_id)
        raise HTTPException(status_code=500, detail="시뮬레이션 처리 중 오류가 발생했습니다")
