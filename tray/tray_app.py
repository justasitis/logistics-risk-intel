"""트레이 알림박스 UI (pystray + windows-toasts).

얇은 껍데기: feed 폼링/토스트/트레이 아이콘만 담당, 판단 로직은 없다.
- 폼링 주기: TRAY_POLL_SECONDS (기본 600초)
- 서버: TRAY_SERVER_URL (기본 http://127.0.0.1:8000)
- 백엔드 다운 시: 아이콘 제목에 "연결 실패" 표시 후 조용히 재시도
"""
from __future__ import annotations

import logging
import sys
import threading
import webbrowser

import notifier_core  # noqa: E402  (같은 폴터 — spec에서도 tray/를 pathex로)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("tray_app")

APP_NAME = "LogisticsRiskTray"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _open_app() -> None:
    webbrowser.open(notifier_core.server_url())


def _create_image(count: int, failed: bool):
    """알림 수를 표시한 단순 아이콘 생성 (PIL 사용, 실패 시 기본 비트맵)."""
    try:
        from PIL import Image, ImageDraw

        size = 64
        color = (100, 116, 139) if failed else (37, 99, 235)
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.ellipse((2, 2, size - 2, size - 2), fill=color)
        if count > 0:
            text = str(min(count, 99))
            draw.text(
                (size / 2, size / 2),
                text,
                fill=(255, 255, 255),
                anchor="mm",
            )
        return image
    except Exception:
        logger.exception("아이콘 생성 실패 — 빈 이미지로 대체")
        try:
            from PIL import Image

            return Image.new("RGB", (64, 64), (37, 99, 235))
        except Exception:
            return None


def _toast(title: str, body: str) -> None:
    try:
        from windows_toasts import Toast, WindowsToaster

        toaster = WindowsToaster(title)
        toast = Toast([title, body])
        toaster.show_toast(toast)
    except Exception:
        logger.exception("토스트 표시 실패: %s / %s", title, body)


def _autostart_enabled() -> bool:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_NAME)
        return True
    except (OSError, FileNotFoundError):
        return False


def _set_autostart(enabled: bool) -> None:
    import winreg

    if enabled:
        if not getattr(sys, "frozen", False):
            logger.warning("시작 프로그램 등록은 exe(frozen) 실행 시에만 지원")
            return
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, sys.executable)
        logger.info("시작 프로그램 등록: %s", sys.executable)
    else:
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.DeleteValue(key, APP_NAME)
            logger.info("시작 프로그램 해제")
        except (OSError, FileNotFoundError):
            pass


class TrayNotifier:
    def __init__(self) -> None:
        self.alert_count = 0
        self.failed = False
        self._stop = threading.Event()

    def poll_once(self) -> None:
        """feed 1회 폼링 → 새 알림 토스트 → 아이콘 갱신."""
        result = notifier_core.fetch_alerts(notifier_core.server_url())
        if result is None:
            self.failed = True
            self.alert_count = 0
            logger.warning("백엔드 연결 실패 — 다음 주기에 재시도")
            return

        self.failed = False
        computed_at, items = result
        state_path = notifier_core.state_file_path()
        state = notifier_core.load_state(state_path)
        new_alerts, new_state = notifier_core.diff_new(state, items, computed_at)
        notifier_core.save_state(state_path, new_state)

        self.alert_count = sum(
            len(item.get("alerts", [])) for item in items
        )
        for alert in new_alerts:
            _toast(
                f"관심화물 알림 — {alert['hbl_no']}",
                str(alert.get("message") or ""),
            )
        logger.info(
            "폼링 완료: 전체 %d건, 신규 %d건", self.alert_count, len(new_alerts)
        )

    def poll_loop(self, icon) -> None:
        while not self._stop.is_set():
            try:
                self.poll_once()
            except Exception:
                logger.exception("폼링 오류")
            self._refresh_icon(icon)
            self._stop.wait(notifier_core.poll_seconds())

    def _refresh_icon(self, icon) -> None:
        icon.icon = _create_image(self.alert_count, self.failed)
        if self.failed:
            icon.title = "LogisticsRisk 트레이 — 백엔드 연결 실패"
        else:
            icon.title = f"LogisticsRisk 트레이 — 알림 {self.alert_count}건"

    def run(self) -> None:
        import pystray

        menu = pystray.Menu(
            pystray.MenuItem("지금 확인", lambda: threading.Thread(
                target=self.poll_once, daemon=True
            ).start()),
            pystray.MenuItem("앱 열기", lambda: _open_app()),
            pystray.MenuItem(
                "시작 프로그램 등록/해제",
                lambda: _set_autostart(not _autostart_enabled()),
            ),
            pystray.MenuItem("종료", lambda: self._shutdown()),
        )
        icon = pystray.Icon(
            APP_NAME,
            _create_image(0, False),
            "LogisticsRisk 트레이",
            menu,
        )
        self._icon = icon
        threading.Thread(target=self.poll_loop, args=(icon,), daemon=True).start()
        logger.info(
            "트레이 시작: 서버=%s, 주기=%ds",
            notifier_core.server_url(),
            notifier_core.poll_seconds(),
        )
        icon.run()

    def _shutdown(self) -> None:
        self._stop.set()
        self._icon.stop()


def main() -> None:
    TrayNotifier().run()


if __name__ == "__main__":
    main()
