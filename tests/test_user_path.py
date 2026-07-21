"""backend/app/core/user_path.py 테스트 — {username} 치환."""
from __future__ import annotations

import getpass

from backend.app.core import user_path
from backend.app.core.user_path import current_username, expand_username


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
