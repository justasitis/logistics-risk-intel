from __future__ import annotations

import json
import os
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
        # SharePoint 동기화 폴터를 저장소로 쓸 경우를 대비해 atomic write:
        # 임시 파일에 쓴 뒤 교체하여 다른 사용자가 부분 파일을 읽지 않게 한다.
        path = self._path(analysis_id)
        tmp_path = path.with_suffix(".json.tmp")
        tmp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp_path, path)

    def load(self, analysis_id: str) -> dict[str, Any]:
        path = self._path(analysis_id)
        if not path.exists():
            raise FileNotFoundError(analysis_id)
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise RuntimeError("stored MI run is invalid")
        return value
