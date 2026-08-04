"""경로 내 {username} 플레이스홀더를 현재 로그인 사용자명으로 치환한다.

SharePoint 동기화 폴터는 C:\\Users\\<컴퓨터 사용자명>\\... 형태라
앱을 여는 사람마다 경로가 달라진다. 설정값에 {username} 을 쓰면
실행 환경의 사용자명으로 자동 치환된다.
"""
from __future__ import annotations

import getpass
import os
from pathlib import Path


def current_username() -> str:
    """현재 로그인 사용자명 (Windows 기준 USERNAME 우선)."""
    return os.environ.get("USERNAME") or getpass.getuser()


def expand_username(value: str) -> str:
    """문자열 내 {username} 을 현재 사용자명으로 치환."""
    if "{username}" not in value:
        return value
    return value.replace("{username}", current_username())


# 동기화 폴터 판별 마커 (소문자 비교) — OneDrive는 PC/계정마다 폴터명을
# 다르게 만든다 (예: "Global물류팀 - LogisticsRisk", "SK on - LogisticsRisk",
# "M365_TtNUJmLE - 데이터_접근금지"). 새 동기화 폴터로 바뀌면 여기에 추가한다.
SYNC_FOLDER_MARKERS = ("logisticsrisk", "데이터_접근금지")


def _is_sync_folder(name: str) -> bool:
    lowered = name.lower()
    return any(marker in lowered for marker in SYNC_FOLDER_MARKERS)


def _find_synced_folder(home: Path) -> Path | None:
    """OneDrive 루트 후보 아래에서 마커가 포함된 동기화 폴터를 찾는다.

    AIS 또는 MI 하위 폴터가 있는 것을 우선한다.
    """
    if not home.exists():
        return None
    matches: list[Path] = []
    for root in home.iterdir():
        if not root.is_dir():
            continue
        try:
            children = list(root.iterdir())
        except OSError:
            continue
        for child in children:
            if child.is_dir() and _is_sync_folder(child.name):
                matches.append(child)
    if not matches:
        return None
    for candidate in matches:
        if (candidate / "AIS").exists() or (candidate / "MI").exists():
            return candidate
    return matches[0]


def resolve_synced_path(value: str) -> str:
    """{username} 치환 후, 경로가 없으면 동기화 폴터명 차이를 흡수한다.

    설정 경로에 마커 세그먼트가 포함되어 있고 실제 폴터가
    다른 이름으로 동기화된 경우, 탐색된 실제 폴터명으로 교체한 경로를 반환한다.
    찾지 못하면 원래 경로를 그대로 반환한다.
    """
    resolved = expand_username(value)
    path = Path(resolved)
    if path.exists():
        return resolved

    segment = next(
        (part for part in path.parts if _is_sync_folder(part)),
        None,
    )
    if segment is None:
        return resolved

    seg_idx = list(path.parts).index(segment)
    if seg_idx < 2:
        return resolved

    homes = [Path(*path.parts[: seg_idx - 1]), Path.home()]
    for home in homes:
        found = _find_synced_folder(home)
        if found is not None:
            new_parts = [
                found.name if part == segment else part for part in path.parts
            ]
            return str(Path(*new_parts))
    return resolved
