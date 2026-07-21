from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..core.mi_settings import get_mi_settings


class MiRunRepository:
    def __init__(self) -> None:
        self.root = Path(get_mi_settings().mi_run_store_dir)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, analysis_id: str) -> Path:
        safe_id = "".join(char for char in analysis_id if char.isalnum() or char in "-_")
        if not safe_id:
            raise ValueError("invalid analysis_id")
        return self.root / f"{safe_id}.json"

    def save(self, analysis_id: str, payload: dict[str, Any]) -> None:
        self._path(analysis_id).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load(self, analysis_id: str) -> dict[str, Any]:
        path = self._path(analysis_id)
        if not path.exists():
            raise FileNotFoundError(analysis_id)
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise RuntimeError("stored MI run is invalid")
        return value
