from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os


@dataclass(frozen=True)
class StopbySettings:
    europe_blank_default: str
    route_algorithm: str
    route_cache_size: int
    maximum_routes: int

    @property
    def enabled(self) -> bool:
        return True


@lru_cache(maxsize=1)
def get_stopby_settings() -> StopbySettings:
    default_value = os.environ.get(
        "EUROPE_BLANK_STOPBY_DEFAULT",
        "south_africa",
    ).strip().lower()

    if default_value not in {
        "",
        "south_africa",
        "suez",
    }:
        default_value = "south_africa"

    algorithm = os.environ.get(
        "SEAROUTE_ALGORITHM",
        "astar",
    ).strip().lower()

    if algorithm not in {"astar", "dijkstra"}:
        algorithm = "astar"

    return StopbySettings(
        europe_blank_default=default_value,
        route_algorithm=algorithm,
        route_cache_size=max(
            16,
            int(os.environ.get(
                "STOPBY_ROUTE_CACHE_SIZE",
                "512",
            )),
        ),
        maximum_routes=max(
            1,
            int(os.environ.get(
                "STOPBY_MAXIMUM_ROUTES",
                "5000",
            )),
        ),
    )
