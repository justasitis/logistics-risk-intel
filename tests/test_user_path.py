"""backend/app/core/user_path.py 테스트 — {username} 치환."""
from __future__ import annotations

import getpass

from backend.app.core import user_path
from backend.app.core.user_path import current_username, expand_username, resolve_synced_path


class TestCurrentUsername:
    def test_username_env_preferred(self, monkeypatch):
        monkeypatch.setenv("USERNAME", "envuser01")
        assert current_username() == "envuser01"

    def test_fallback_to_getpass(self, monkeypatch):
        monkeypatch.delenv("USERNAME", raising=False)
        monkeypatch.setattr(getpass, "getuser", lambda: "fallback01")
        assert current_username() == "fallback01"


class TestExpandUsername:
    def test_replaces_placeholder(self, monkeypatch):
        monkeypatch.setenv("USERNAME", "milkg")
        value = expand_username(
            r"C:\Users\{username}\SK on\Global물류팀 - LogisticsRisk"
        )
        assert value == r"C:\Users\milkg\SK on\Global물류팀 - LogisticsRisk"

    def test_replaces_multiple_occurrences(self, monkeypatch):
        monkeypatch.setenv("USERNAME", "u1")
        assert expand_username("{username}/{username}") == "u1/u1"

    def test_no_placeholder_returned_as_is(self, monkeypatch):
        # USERNAME이 달라도 플레이스홀더가 없으면 그대로다.
        monkeypatch.setenv("USERNAME", "whoever")
        assert expand_username(r"C:\dev\static") == r"C:\dev\static"

    def test_empty_string(self):
        assert expand_username("") == ""


class TestResolveSyncedPath:
    """resolve_synced_path — PC마다 다른 OneDrive 동기화 폴터명 흡수."""

    def _make(self, tmp_path, folder_name, with_ais=True):
        root = tmp_path / "user" / "SK on" / folder_name
        root.mkdir(parents=True)
        if with_ais:
            (root / "AIS").mkdir()
        return root

    def test_existing_path_returned_as_is(self, tmp_path):
        real = self._make(tmp_path, "Global물류팀 - LogisticsRisk")
        result = resolve_synced_path(str(real))
        assert result == str(real)

    def test_alternate_folder_name_recognized(self, tmp_path):
        # 표준 이름으로 설정됐지만 실제로는 "SK on - LogisticsRisk"로 동기화된 경우
        self._make(tmp_path, "SK on - LogisticsRisk")
        configured = str(
            tmp_path / "user" / "SK on" / "Global물류팀 - LogisticsRisk" / "MI" / "mi_runs"
        )
        result = resolve_synced_path(configured)
        assert "SK on - LogisticsRisk" in result
        assert result.endswith("mi_runs")

    def test_canonical_folder_name_recognized(self, tmp_path):
        # 반대: "SK on - ..."으로 설정됐지만 실제는 표준 이름
        self._make(tmp_path, "Global물류팀 - LogisticsRisk")
        configured = str(
            tmp_path / "user" / "SK on" / "SK on - LogisticsRisk" / "manual_coordinates.json"
        )
        result = resolve_synced_path(configured)
        assert "Global물류팀 - LogisticsRisk" in result
        assert result.endswith("manual_coordinates.json")

    def test_prefers_folder_with_ais_or_mi(self, tmp_path):
        self._make(tmp_path, "LogisticsRisk-backup", with_ais=False)
        self._make(tmp_path, "SK on - LogisticsRisk", with_ais=True)
        configured = str(
            tmp_path / "user" / "SK on" / "Global물류팀 - LogisticsRisk"
        )
        result = resolve_synced_path(configured)
        assert "SK on - LogisticsRisk" in result

    def test_not_found_returns_original(self, tmp_path, monkeypatch):
        # 실제 PC 홈 폴터의 동기화 폴터에 오염되지 않도록 home을 격리
        monkeypatch.setattr(
            user_path.Path, "home",
            classmethod(lambda cls: tmp_path / "no-home"),
        )
        configured = str(
            tmp_path / "user" / "SK on" / "Global물류팀 - LogisticsRisk"
        )
        assert resolve_synced_path(configured) == configured

    def test_no_logisticsrisk_segment_returns_original(self, tmp_path):
        configured = str(tmp_path / "user" / "other" / "file.json")
        assert resolve_synced_path(configured) == configured

    def test_username_expansion_still_applied(self, tmp_path, monkeypatch):
        self._make(tmp_path, "SK on - LogisticsRisk")
        monkeypatch.setenv("USERNAME", "so23159")
        user_dir = tmp_path / "so23159"
        (user_dir / "SK on" / "SK on - LogisticsRisk" / "MI").mkdir(parents=True)
        configured = str(
            user_dir / "SK on" / "Global물류팀 - LogisticsRisk"
        ).replace("so23159", "{username}")
        result = resolve_synced_path(configured)
        assert "so23159" in result
        assert "SK on - LogisticsRisk" in result

    def test_new_folder_name_recognized(self, tmp_path):
        # 새 동기화 폴터 "M365_TtNUJmLE - 데이터_접근금지" 도 마커로 탐지된다.
        self._make(tmp_path, "M365_TtNUJmLE - 데이터_접근금지")
        configured = str(
            tmp_path / "user" / "SK on" / "M365_TtNUJmLE - 데이터_접근금지" / "MI" / "mi_runs"
        )
        # 경로가 존재하면 그대로 반환
        (tmp_path / "user" / "SK on" / "M365_TtNUJmLE - 데이터_접근금지" / "MI" / "mi_runs").mkdir(parents=True)
        assert resolve_synced_path(configured) == configured

    def test_new_folder_name_found_by_marker(self, tmp_path):
        # 설정은 새 이름인데 실제 폴터가 구 이름인 경우에도 탐색 치환된다.
        self._make(tmp_path, "M365_TtNUJmLE - 데이터_접근금지")
        configured = str(
            tmp_path / "user" / "SK on" / "Global물류팀 - LogisticsRisk" / "MI"
        )
        result = resolve_synced_path(configured)
        assert "M365_TtNUJmLE - 데이터_접근금지" in result
