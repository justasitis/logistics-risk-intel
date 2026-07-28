from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from pydantic import ValidationError

from ..core.marinesia_settings import get_marinesia_settings
from ..schemas.mi_ai import ExternalMiCandidateEnvelope


FILE_NAME = "external_mi_candidates.json"
PREFERRED_RELATIVE_PATH = Path("MI") / "current" / FILE_NAME
MAX_FILE_SIZE_MB = 20

# 일자별 파일명: external_mi_candidates_YYMMDD.json (최신 파일도 동일 형식)
DATED_FILE_PATTERN = re.compile(
    r"^external_mi_candidates_(\d{6})\.json$",
    re.IGNORECASE,
)


def _dated_file_date(path: Path) -> date | None:
    """파일명의 YYMMDD를 날짜로 파싱 (유효하지 않으면 None)."""
    match = DATED_FILE_PATTERN.match(path.name)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%y%m%d").date()
    except ValueError:
        return None


def _latest_dated_file(directory: Path) -> Path | None:
    """디렉터리에서 가장 최근 날짜의 일자별 후보 파일을 반환."""
    if not directory.is_dir():
        return None
    dated: list[tuple[date, float, Path]] = []
    for path in directory.iterdir():
        if not path.is_file():
            continue
        file_date = _dated_file_date(path)
        if file_date is not None:
            dated.append((file_date, path.stat().st_mtime, path))
    if not dated:
        return None
    dated.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return dated[0][2]


def _iso_from_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(
        timestamp,
        tz=timezone.utc,
    ).isoformat()


def _relative_parts(path: Path, root: Path) -> list[str]:
    try:
        relative = path.relative_to(root)
    except ValueError:
        relative = path
    return [part.lower() for part in relative.parts]


def _candidate_rank(path: Path, root: Path) -> tuple[int, float, str]:
    parts = _relative_parts(path, root)
    preferred = root / PREFERRED_RELATIVE_PATH

    try:
        is_preferred = path.resolve() == preferred.resolve()
    except OSError:
        is_preferred = path == preferred

    if is_preferred:
        priority = 0
    elif path.parent == root:
        priority = 1
    elif "current" in parts:
        priority = 2
    else:
        priority = 3

    stat = path.stat()
    return priority, -stat.st_mtime, str(path).lower()


def find_external_mi_candidates_file(root: Path) -> Path | None:
    if not root.exists() or not root.is_dir():
        return None

    preferred = root / PREFERRED_RELATIVE_PATH
    if preferred.is_file():
        return preferred

    # 일자별 파일(external_mi_candidates_YYMMDD.json)이 있으면 가장 최근 것
    dated = _latest_dated_file(root / "MI" / "current")
    if dated is not None:
        return dated

    direct = root / FILE_NAME
    if direct.is_file():
        return direct

    candidates = [
        path
        for path in root.rglob(FILE_NAME)
        if path.is_file()
    ]
    candidates += [
        path
        for path in root.rglob("external_mi_candidates_*.json")
        if path.is_file() and _dated_file_date(path) is not None
    ]

    if not candidates:
        return None

    return sorted(
        candidates,
        key=lambda path: _candidate_rank(path, root),
    )[0]


def _model_validate(value: Any) -> ExternalMiCandidateEnvelope:
    if hasattr(ExternalMiCandidateEnvelope, "model_validate"):
        return ExternalMiCandidateEnvelope.model_validate(value)
    return ExternalMiCandidateEnvelope.parse_obj(value)


def _model_dump(model: ExternalMiCandidateEnvelope) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()


def _read_stable_bytes(path: Path, max_file_size_mb: int) -> tuple[bytes, Any]:
    max_bytes = max_file_size_mb * 1024 * 1024
    before = path.stat()

    if before.st_size > max_bytes:
        raise ValueError(
            f"{path.name} 크기가 {max_file_size_mb}MB를 초과합니다."
        )

    payload = path.read_bytes()
    after = path.stat()

    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or len(payload) != after.st_size
    ):
        raise RuntimeError(
            "SharePoint가 파일을 동기화하는 중입니다. "
            "잠시 후 다시 새로고침하세요."
        )

    return payload, after


def read_external_mi_candidates(
    root: Path | None = None,
    max_file_size_mb: int = MAX_FILE_SIZE_MB,
) -> dict[str, Any]:
    resolved_root = root or get_marinesia_settings().sharepoint_root
    path = find_external_mi_candidates_file(resolved_root)

    if path is None:
        return {
            "found": False,
            "source_type": "SHAREPOINT",
            "source_root": str(resolved_root),
            "source_file": None,
            "source_file_name": None,
            "source_modified_at": None,
            "source_size_bytes": 0,
            "source_sha256": None,
            "candidate_count": 0,
            "candidate_envelope": None,
            "warnings": [
                "SharePoint 동기화 폴더에서 "
                "external_mi_candidates.json을 찾지 못했습니다."
            ],
        }

    payload, stat = _read_stable_bytes(path, max_file_size_mb)

    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(
            f"{path.name}을 UTF-8 또는 UTF-8 BOM으로 읽을 수 없습니다."
        ) from exc

    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{path.name} JSON 형식이 올바르지 않습니다: "
            f"line {exc.lineno}, column {exc.colno}"
        ) from exc

    if not isinstance(value, dict):
        raise ValueError(
            f"{path.name} 최상위 구조는 객체여야 합니다."
        )

    if value.get("source_stage") != "EXTERNAL_GEMINI_CANDIDATES":
        raise ValueError(
            "source_stage가 EXTERNAL_GEMINI_CANDIDATES가 아닙니다."
        )

    try:
        envelope = _model_validate(value)
    except ValidationError as exc:
        raise ValueError(
            f"{path.name}이 외부 MI 후보 스키마와 일치하지 않습니다: "
            f"{exc}"
        ) from exc

    if envelope.source_stage != "EXTERNAL_GEMINI_CANDIDATES":
        raise ValueError(
            "source_stage가 EXTERNAL_GEMINI_CANDIDATES가 아닙니다."
        )

    digest = hashlib.sha256(payload).hexdigest()
    warnings = list(envelope.warnings)

    if envelope.generation_status.upper() != "SUCCESS":
        warnings.append(
            "generation_status가 SUCCESS가 아닙니다. "
            "정제 전에 후보 내용을 확인하세요."
        )

    return {
        "found": True,
        "source_type": "SHAREPOINT",
        "source_root": str(resolved_root),
        "source_file": str(path),
        "source_file_name": path.name,
        "source_modified_at": _iso_from_timestamp(stat.st_mtime),
        "source_size_bytes": stat.st_size,
        "source_sha256": digest,
        "candidate_count": len(envelope.candidates),
        "candidate_envelope": _model_dump(envelope),
        "warnings": warnings,
    }
