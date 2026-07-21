from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import requests

from ..core.mi_settings import MiSettings, get_mi_settings


class ActifyError(RuntimeError):
    pass


@dataclass
class ActifyResult:
    answer: str
    conversation_id: str
    raw_response: dict[str, Any] | None = None


class ActifyClient:
    def __init__(self, settings: MiSettings | None = None) -> None:
        self.settings = settings or get_mi_settings()

    def _headers(self) -> dict[str, str]:
        if not self.settings.actify_api_key:
            raise ActifyError("ACTIFY_API_KEY is not configured")
        return {
            "Authorization": f"Bearer {self.settings.actify_api_key}",
            "Content-Type": "application/json",
        }

    def _payload(
        self,
        query: str,
        response_mode: str,
        conversation_id: str = "",
        inputs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.settings.actify_user:
            raise ActifyError("ACTIFY_USER is not configured")
        return {
            "inputs": inputs or {},
            "query": query,
            "response_mode": response_mode,
            "conversation_id": conversation_id,
            "user": self.settings.actify_user,
        }

    def call_blocking(
        self,
        query: str,
        conversation_id: str = "",
        inputs: dict[str, Any] | None = None,
    ) -> ActifyResult:
        response = requests.post(
            self.settings.actify_url,
            headers=self._headers(),
            json=self._payload(query, "blocking", conversation_id, inputs),
            timeout=self.settings.actify_timeout_seconds,
            verify=self.settings.actify_verify_ssl,
        )
        if response.status_code != 200:
            raise ActifyError(
                f"Actify HTTP {response.status_code}: {response.text[:1500]}"
            )

        data = response.json()
        answer = str(data.get("answer") or "").strip()
        if not answer:
            raise ActifyError(f"Actify response has no answer: {data}")
        return ActifyResult(
            answer=answer,
            conversation_id=str(data.get("conversation_id") or ""),
            raw_response=data,
        )

    def call_streaming(
        self,
        query: str,
        conversation_id: str = "",
        inputs: dict[str, Any] | None = None,
    ) -> ActifyResult:
        response = requests.post(
            self.settings.actify_url,
            headers=self._headers(),
            json=self._payload(query, "streaming", conversation_id, inputs),
            timeout=self.settings.actify_timeout_seconds,
            verify=self.settings.actify_verify_ssl,
            stream=True,
        )
        if response.status_code != 200:
            raise ActifyError(
                f"Actify HTTP {response.status_code}: {response.text[:1500]}"
            )

        chunks: list[str] = []
        resolved_conversation_id = conversation_id
        last_event: dict[str, Any] | None = None

        for line in response.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data:"):
                continue

            payload = line[5:].strip()
            if payload == "[DONE]":
                break

            try:
                event = json.loads(payload)
            except json.JSONDecodeError:
                continue

            last_event = event
            resolved_conversation_id = str(
                event.get("conversation_id") or resolved_conversation_id
            )
            event_name = event.get("event")
            if event_name in {"message", "agent_message"}:
                chunks.append(str(event.get("answer") or ""))
            elif event_name == "error":
                raise ActifyError(str(event))

        answer = "".join(chunks).strip()
        if not answer:
            raise ActifyError("Actify streaming response has no answer")

        return ActifyResult(
            answer=answer,
            conversation_id=resolved_conversation_id,
            raw_response=last_event,
        )

    def call(
        self,
        query: str,
        conversation_id: str = "",
        inputs: dict[str, Any] | None = None,
    ) -> ActifyResult:
        if self.settings.actify_response_mode == "streaming":
            return self.call_streaming(query, conversation_id, inputs)
        return self.call_blocking(query, conversation_id, inputs)
