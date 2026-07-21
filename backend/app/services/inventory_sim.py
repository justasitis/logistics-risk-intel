"""L2 수급 영향도 시뮬레이션 — 순수 함수 모듈.

표준 라이브러리만 사용(pydantic/httpx 등 외부 의존성 0).
향후 Dify Code 노드로 이식될 자산이므로 이 파일 단독으로 동작해야 한다.

핵심 아이디어: ETA 계획/현실 두 곡선으로 일 단위 잔고를 계산하고,
미니멈 레벨 하회·재고 소진 위험을 지표로 변환한다. 최종 판단은 사람(HITL).
"""
from datetime import date, timedelta

RISK_LEVELS = ("OK", "WATCH", "SHORTAGE_RISK", "STOCKOUT")

WATCH_THRESHOLD_RATIO = 1.2  # 현실 곡선 최저치가 미니멈의 120% 이내 → WATCH


def _parse(iso: str) -> date:
    return date.fromisoformat(iso)


def _arrival_days(shipments: list, key: str, extra_days: int, today: date, horizon: int) -> dict:
    """day_offset → 도착 수량 집계. 기간 밖 도착은 제외."""
    arrivals: dict[int, float] = {}
    for s in shipments:
        eta = _parse(s[key]) + timedelta(days=extra_days)
        d = (eta - today).days
        if 0 <= d <= horizon:
            arrivals[d] = arrivals.get(d, 0) + s["qty"]
    return arrivals


def _build_series(on_hand: float, daily_usage: float, arrivals: dict, today: date, horizon: int) -> list:
    series = []
    arrived = 0
    for t in range(horizon + 1):
        arrived += arrivals.get(t, 0)
        series.append(
            {
                "day": t,
                "date": (today + timedelta(days=t)).isoformat(),
                "balance": on_hand + arrived - daily_usage * t,
            }
        )
    return series


def _windows(series: list, threshold_ok) -> list:
    """조건을 만족하는 연속 구간 [{start, end, days}] 추출."""
    out = []
    start = None
    end = None
    for p in series:
        if threshold_ok(p["balance"]):
            if start is None:
                start = p
            end = p
        elif start is not None:
            out.append({"start": start["date"], "end": end["date"], "days": end["day"] - start["day"] + 1})
            start = None
    if start is not None:
        out.append({"start": start["date"], "end": end["date"], "days": end["day"] - start["day"] + 1})
    return out


def simulate(item: dict, extra_delay_days: int = 0, horizon_days: int = 45, today: date = None) -> dict:
    """품목 1개의 재고 곡선(plan/current)과 위험 지표를 계산.

    item: 품목 마스터 레코드(dict). today: 기준일(테스트 주입용, None이면 오늘).
    """
    if today is None:
        today = date.today()

    on_hand = item["on_hand_units"]
    daily_usage = item["daily_usage"]
    min_level = item["min_level_units"]
    unit = item.get("unit", "units")
    shipments = item.get("shipments", [])

    arrivals_plan = _arrival_days(shipments, "eta_plan", 0, today, horizon_days)
    arrivals_current = _arrival_days(shipments, "eta_current", extra_delay_days, today, horizon_days)

    series_plan = _build_series(on_hand, daily_usage, arrivals_plan, today, horizon_days)
    series_current = _build_series(on_hand, daily_usage, arrivals_current, today, horizon_days)

    below_min_windows = _windows(series_current, lambda b: b < min_level)
    stockout_windows = _windows(series_current, lambda b: b < 0)

    min_point = min(series_current, key=lambda p: p["balance"])
    # stockout 방지에 필요한 수량 = 최대 누적 부족량
    gap_qty = max(0, -min_point["balance"])

    delays = [(_parse(s["eta_current"]) - _parse(s["eta_plan"])).days for s in shipments]
    max_delay_days = (max(delays) if delays else 0) + extra_delay_days

    if stockout_windows:
        risk_level = "STOCKOUT"
    elif below_min_windows:
        risk_level = "SHORTAGE_RISK"
    elif min_point["balance"] <= min_level * WATCH_THRESHOLD_RATIO:
        risk_level = "WATCH"
    else:
        risk_level = "OK"

    actions = []
    if gap_qty > 0:
        actions.append(
            {
                "type": "AIR_UPGRADE",
                "qty": gap_qty,
                "text_ko": f"재고 소진이 예상됩니다. 약 {gap_qty:,}{unit}의 긴급 항공 전환(에어 업그레이드)을 검토하세요.",
            }
        )
    if max_delay_days > 0:
        actions.append(
            {
                "type": "PULL_FORWARD_ORDER",
                "days": max_delay_days,
                "text_ko": f"최대 {max_delay_days}일의 입고 지연이 예상됩니다. 후속 발주를 {max_delay_days}일 앞당기는 방안을 검토하세요.",
            }
        )

    return {
        "item_id": item.get("item_id"),
        "params": {
            "extra_delay_days": extra_delay_days,
            "horizon_days": horizon_days,
            "today": today.isoformat(),
            "min_level_units": min_level,
            "unit": unit,
        },
        "series_plan": series_plan,
        "series_current": series_current,
        "metrics": {
            "min_balance": min_point["balance"],
            "min_balance_date": min_point["date"],
            "below_min_windows": below_min_windows,
            "stockout_windows": stockout_windows,
            "gap_qty": gap_qty,
            "max_delay_days": max_delay_days,
            "risk_level": risk_level,
        },
        "actions": actions,
    }
