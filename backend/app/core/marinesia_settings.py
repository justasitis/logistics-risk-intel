from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path


DEFAULT_SHAREPOINT_ROOT = Path(
    r"C:\Users\so23132\SK on\Global물류팀 - LogisticsRisk"
)


@dataclass(frozen=True)
class MarinesiaSettings:
    sharepoint_root: Path
    default_company: str
    live_hours: float
    stale_warning_hours: float
    max_file_size_mb: int

    @property
    def configured(self) -> bool:
        return bool(str(self.sharepoint_root).strip())


@lru_cache(maxsize=1)
def get_marinesia_settings() -> MarinesiaSettings:
    root_value = os.environ.get(
        "MARINESIA_SHAREPOINT_ROOT",
        str(DEFAULT_SHAREPOINT_ROOT),
    ).strip()

    return MarinesiaSettings(
        sharepoint_root=Path(root_value),
        default_company=os.environ.get(
            "MARINESIA_DEFAULT_COMPANY",
            "SKBA",
        ).strip().upper() or "SKBA",
        live_hours=float(
            os.environ.get("MARINESIA_LIVE_HOURS", "6")
        ),
        stale_warning_hours=float(
            os.environ.get("MARINESIA_STALE_WARNING_HOURS", "24")
        ),
        max_file_size_mb=int(
            os.environ.get("MARINESIA_MAX_FILE_SIZE_MB", "50")
        ),
    )
