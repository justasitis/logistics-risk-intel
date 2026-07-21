"""L2 수급 영향도 시뮬레이션 API.

1차: 품목 마스터 샘플(eta 내장) → 2차(현재): B-LAP 실데이터 연동.
도착 물량은 inventory_arrivals.fetch_item_arrivals()가 bl_info 품목 라인과
운송 스냅샷/이력 메트릭을 조인해 집계한다. 수급 기준값(보유재고·일소요량·
미니멈)은 backend/data/inventory_stock_params.json(런타임 편집, git 미추적)을
읽는다. B-LAP 조회 실패 시 샘플 inventory_items.json으로 fallback한다
(개발·데모 환경에서 화면을 유지하기 위함).

순수 함수 inventory_sim.simulate()의 시그니처/로직은 변경하지 않는다.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ...services import inventory_arrivals, inventory_sim

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parents[3]
SAMPLE_ITEMS_PATH = _BACKEND_DIR / "data" / "inventory_items.json"
STOCK_PARAMS_PATH = _BACKEND_DIR / "data" / "inventory_stock_params.json"

# 수급 기준값 미설정 품목의 가정값 (warning과 함께 사용)
ASSUMED_DAILY_USAGE = 100
ASSUMED_ON_HAND = 2000
ASSUMED_MIN_LEVEL = 500
PARAMS_WARNING = "수급 기준값 미설정 — 가정값으로 계산"

router = APIRouter(
    prefix="/api/inventory",
    tags=["Inventory Impact Simulation"],
)


def _load_json(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_stock_params() -> dict[str, Any]:
    if not STOCK_PARAMS_PATH.exists():
        return {}
    try:
        return _load_json(STOCK_PARAMS_PATH)
    except Exception:
        logger.exception("수급 기준값 파일 파싱 실패: %s", STOCK_PARAMS_PATH)
        return {}


def _merge_params(item: dict[str, Any], params: dict[str, Any] | None) -> dict[str, Any]:
    """집계 품목에 수급 기준값 병합. 없으면 가정값 + params_missing."""
    merged = {
        "destination": "",
        "corridor": "",
        "pol": "",
        **item,
    }
    if params:
        merged["daily_usage"] = params.get("daily_usage", ASSUMED_DAILY_USAGE)
        merged["on_hand_units"] = params.get("on_hand_units", ASSUMED_ON_HAND)
        merged["min_level_units"] = params.get("min_level_units", ASSUMED_MIN_LEVEL)
        merged["destination"] = params.get("destination", "")
        merged["params_missing"] = False
    else:
        merged["daily_usage"] = ASSUMED_DAILY_USAGE
        merged["on_hand_units"] = ASSUMED_ON_HAND
        merged["min_level_units"] = ASSUMED_MIN_LEVEL
        merged["params_missing"] = True
    return merged


def _items_from_blap(params_store: dict[str, Any]) -> list[dict[str, Any]]:
    arrivals = inventory_arrivals.fetch_item_arrivals()
    return [
        _merge_params({**item, "source": "blap"}, params_store.get(item["item_id"]))
        for item in arrivals
    ]


def _items_from_sample(params_store: dict[str, Any]) -> list[dict[str, Any]]:
    data = _load_json(SAMPLE_ITEMS_PATH)
    return [
        _merge_params({**item, "source": "sample"}, params_store.get(item["item_id"]))
        for item in data.get("items", [])
    ]


def _get_items() -> list[dict[str, Any]]:
    """B-LAP 우선, 실패 시 샘플 fallback."""
    params_store = _load_stock_params()
    try:
        items = _items_from_blap(params_store)
        if items:
            return items
        logger.warning("B-LAP 품목 집계 0건 — 샘플 데이터로 fallback")
    except Exception:
        logger.exception("B-LAP 품목 집계 실패 — 샘플 데이터로 fallback")
    return _items_from_sample(params_store)


@router.get("/items")
def get_inventory_items() -> dict[str, Any]:
    try:
        return {"items": _get_items()}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="품목 마스터 파일이 없습니다")
    except Exception:
        logger.exception("품목 데이터 처리 실패")
        raise HTTPException(status_code=500, detail="품목 데이터 처리 중 오류가 발생했습니다")


class SimulateBody(BaseModel):
    item_id: str
    extra_delay_days: int = Field(default=0, ge=0, le=60)
    horizon_days: int = Field(default=45, ge=14, le=120)


@router.post("/simulate")
def simulate_inventory(body: SimulateBody) -> dict[str, Any]:
    try:
        items = _get_items()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="품목 마스터 파일이 없습니다")
    except Exception:
        logger.exception("품목 데이터 처리 실패")
        raise HTTPException(status_code=500, detail="품목 데이터 처리 중 오류가 발생했습니다")

    item = next((i for i in items if i.get("item_id") == body.item_id), None)
    if item is None:
        raise HTTPException(
            status_code=404,
            detail=f"품목을 찾을 수 없습니다: {body.item_id}",
        )

    try:
        result = inventory_sim.simulate(
            item,
            body.extra_delay_days,
            body.horizon_days,
            date.today(),
        )
    except Exception:
        logger.exception("수급 시뮬레이션 실패: %s", body.item_id)
        raise HTTPException(status_code=500, detail="시뮬레이션 처리 중 오류가 발생했습니다")

    if item.get("params_missing"):
        result["warning"] = PARAMS_WARNING
    return result
