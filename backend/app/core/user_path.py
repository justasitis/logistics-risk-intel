"""경로 내 {username} 플레이스홀더를 현재 로그인 사용자명으로 치환한다.

SharePoint 동기화 폴터는 C:\\Users\\<컴퓨터 사용자명>\\... 형태라
앱을 여는 사람마다 경로가 달라진다. 설정값에 {username} 을 쓰면
실행 환경의 사용자명으로 자동 치환된다.
"""
from __future__ import annotations

import getpass
import os


def current_username() -> str:
    """현재 로그인 사용자명 (Windows 기준 USERNAME 우선)."""
    return os.environ.get("USERNAME") or getpass.getuser()


def expand_username(value: str) -> str:
    """문자열 내 {username} 을 현재 사용자명으로 치환."""
    if "{username}" not in value:
        return value
    return value.replace("{username}", current_username())
