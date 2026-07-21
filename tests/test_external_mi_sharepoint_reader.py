"""backend/app/services/external_mi_sharepoint_reader.py 테스트.

후보 파일 탐색 우선순위와 스키마 검증(정상/불량 JSON)을
tmp 폴터 기반으로 검증한다. SharePoint 실경로는 사용하지 않는다.
"""
from __future__ import annotations

import json
import os
import time

import pytest

from backend.app.services.external_mi_sharepoint_reader import (
    FILE_NAME,
    find_external_mi_candidates_file,
    read_external_mi_candidates,
)


def _envelope(**overrides):
    payload = {
        "source_stage": "EXTERNAL_GEMINI_CANDIDATES",
        "generation_status": "SUCCESS",
        "candidates": [
            {
                "candidate_id": "cand-1",
                "headline": "테스트 헤드라인",
                "short_summary": "테스트 요약",
            }
        ],
    }
    payload.update(overrides)
    return payload


def _write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8",
        )
    return path


class TestFindCandidatesFile:
    def test_missing_root_returns_none(self, tmp_path):
        assert find_external_mi_candidates_file(
            tmp_path / "nonexistent"
        ) is None

    def test_no_file_returns_none(self, tmp_path):
        assert find_external_mi_candidates_file(tmp_path) is None

    def test_preferred_path_wins(self, tmp_path):
        preferred = _write(
            tmp_path / "MI" / "current" / FILE_NAME, _envelope(),
        )
        _write(tmp_path / FILE_NAME, _envelope())
        assert find_external_mi_candidates_file(tmp_path) == preferred

    def test_direct_root_file_second(self, tmp_path):
        direct = _write(tmp_path / FILE_NAME, _envelope())
        _write(tmp_path / "archive" / FILE_NAME, _envelope())
        assert find_external_mi_candidates_file(tmp_path) == direct

    def test_current_dir_beats_other_nested(self, tmp_path):
        current = _write(
            tmp_path / "sub" / "current" / FILE_NAME, _envelope(),
        )
        _write(tmp_path / "archive" / FILE_NAME, _envelope())
        assert find_external_mi_candidates_file(tmp_path) == current

    def test_same_priority_prefers_newest_mtime(self, tmp_path):
        older = _write(tmp_path / "a" / FILE_NAME, _envelope())
        newer = _write(tmp_path / "b" / FILE_NAME, _envelope())
        past = time.time() - 3600
        os.utime(older, (past, past))
        assert find_external_mi_candidates_file(tmp_path) == newer


class TestReadCandidates:
    def test_not_found_returns_warning_payload(self, tmp_path):
        result = read_external_mi_candidates(tmp_path)
        assert result["found"] is False
        assert result["candidate_count"] == 0
        assert result["candidate_envelope"] is None
        assert result["source_file"] is None
        assert result["warnings"]

    def test_valid_envelope(self, tmp_path):
        path = _write(tmp_path / FILE_NAME, _envelope())
        result = read_external_mi_candidates(tmp_path)
        assert result["found"] is True
        assert result["candidate_count"] == 1
        assert result["source_file"] == str(path)
        assert result["source_file_name"] == FILE_NAME
        assert result["source_size_bytes"] > 0
        assert len(result["source_sha256"]) == 64
        envelope = result["candidate_envelope"]
        assert envelope["candidates"][0]["candidate_id"] == "cand-1"
        assert result["warnings"] == []

    def test_utf8_bom_accepted(self, tmp_path):
        path = tmp_path / FILE_NAME
        path.write_bytes(
            b"\xef\xbb\xbf" + json.dumps(_envelope()).encode("utf-8")
        )
        result = read_external_mi_candidates(tmp_path)
        assert result["found"] is True

    def test_broken_json_raises(self, tmp_path):
        _write(tmp_path / FILE_NAME, "{ broken")
        with pytest.raises(ValueError, match="JSON 형식"):
            read_external_mi_candidates(tmp_path)

    def test_non_object_json_raises(self, tmp_path):
        _write(tmp_path / FILE_NAME, "[1, 2, 3]")
        with pytest.raises(ValueError, match="객체"):
            read_external_mi_candidates(tmp_path)

    def test_wrong_source_stage_raises(self, tmp_path):
        _write(
            tmp_path / FILE_NAME,
            _envelope(source_stage="SOMETHING_ELSE"),
        )
        with pytest.raises(ValueError, match="source_stage"):
            read_external_mi_candidates(tmp_path)

    def test_schema_violation_raises(self, tmp_path):
        # headline 필수 필드 누락
        _write(
            tmp_path / FILE_NAME,
            _envelope(candidates=[{"candidate_id": "c1"}]),
        )
        with pytest.raises(ValueError, match="스키마"):
            read_external_mi_candidates(tmp_path)

    def test_non_success_status_adds_warning(self, tmp_path):
        _write(
            tmp_path / FILE_NAME,
            _envelope(generation_status="PARTIAL"),
        )
        result = read_external_mi_candidates(tmp_path)
        assert result["found"] is True
        assert any(
            "generation_status" in warning
            for warning in result["warnings"]
        )

    def test_file_size_limit(self, tmp_path):
        _write(tmp_path / FILE_NAME, _envelope())
        with pytest.raises(ValueError, match="초과"):
            read_external_mi_candidates(
                tmp_path, max_file_size_mb=0,
            )

    def test_existing_warnings_preserved(self, tmp_path):
        _write(
            tmp_path / FILE_NAME,
            _envelope(warnings=["기존 경고"]),
        )
        result = read_external_mi_candidates(tmp_path)
        assert "기존 경고" in result["warnings"]
