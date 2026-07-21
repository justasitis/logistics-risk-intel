from __future__ import annotations

import os
from dataclasses import dataclass


def _bool_env(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class MiSettings:
    actify_base_url: str
    actify_endpoint_path: str
    actify_api_key: str
    actify_user: str
    actify_response_mode: str
    actify_timeout_seconds: int
    actify_verify_ssl: bool
    mi_max_candidates: int
    mi_run_store_dir: str

    @property
    def actify_url(self) -> str:
        return f"{self.actify_base_url.rstrip('/')}/{self.actify_endpoint_path.lstrip('/')}"

    @property
    def configured(self) -> bool:
        return bool(self.actify_base_url and self.actify_api_key and self.actify_user)


def get_mi_settings() -> MiSettings:
    return MiSettings(
        actify_base_url=os.environ.get(
            "ACTIFY_BASE_URL",
            "https://agentlab.sk-on.com/dify",
        ).strip(),
        actify_endpoint_path=os.environ.get(
            "ACTIFY_ENDPOINT_PATH",
            "/v1/chat-messages",
        ).strip(),
        actify_api_key=os.environ.get("ACTIFY_API_KEY", "").strip(),
        actify_user=os.environ.get("ACTIFY_USER", "").strip(),
        actify_response_mode=os.environ.get(
            "ACTIFY_RESPONSE_MODE",
            "blocking",
        ).strip().lower(),
        actify_timeout_seconds=max(
            30,
            int(os.environ.get("ACTIFY_TIMEOUT_SECONDS", "240")),
        ),
        actify_verify_ssl=_bool_env("ACTIFY_VERIFY_SSL", True),
        mi_max_candidates=max(
            1,
            int(os.environ.get("MI_VDI_MAX_CANDIDATES", "30")),
        ),
        mi_run_store_dir=os.environ.get(
            "MI_RUN_STORE_DIR",
            "backend/data/mi_runs",
        ).strip(),
    )
