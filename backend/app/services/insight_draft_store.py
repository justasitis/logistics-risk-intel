"""월간 인사이트 초안 저장소 (파일 기반, atomic write — mi_repository 패턴 준용).

draft_id 규칙: INS-<YYYYMM> (월별 1건). 동일 월 재생성/편집은 같은 ID로 덮어쓰며,
편집 저장(PUT)은 revised_at을 갱신한다.
저장 위치: INSIGHT_DRAFT_STORE_DIR (기본 backend/data/insight_drafts,
resolve_synced_path로 SharePoint 동기화 폴터 패턴 지원).
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from ..core.mi_settings import get_mi_settings


def draft_id_for_month(month: str) -> str:
    """'2026-07' → 'INS-202607'"""
    return "INS-" + month.replace("-", "")


class InsightDraftNotFoundError(Exception):
    pass


class InsightDraftStore:
    def __init__(self) -> None:
        self.root = Path(get_mi_settings().insight_draft_store_dir)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, month: str) -> Path:
        safe = "".join(char for char in month if char.isalnum() or char in "-_")
        if not safe:
            raise ValueError("invalid month")
        return self.root / f"{draft_id_for_month(safe)}.json"

    def exists(self, month: str) -> bool:
        return self._path(month).exists()

    def load(self, month: str) -> dict[str, Any]:
        path = self._path(month)
        if not path.exists():
            raise InsightDraftNotFoundError(month)
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise RuntimeError("stored insight draft is invalid")
        return value

    def save(self, month: str, record: dict[str, Any]) -> dict[str, Any]:
        """레코드 저장 (atomic write). draft_id/month는 여기서 강제한다."""
        record = {
            **record,
            "draft_id": draft_id_for_month(month),
            "month": month,
        }
        path = self._path(month)
        tmp_path = path.with_suffix(".json.tmp")
        tmp_path.write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp_path, path)
        return record


def revised_now(record: dict[str, Any]) -> dict[str, Any]:
    """편집본 저장용 revised_at 갱신."""
    return {**record, "revised_at": datetime.now().isoformat(timespec="seconds")}
