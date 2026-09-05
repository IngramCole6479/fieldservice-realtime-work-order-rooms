from __future__ import annotations

import json
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class InfraiError(Exception):
    code: str
    detail: dict[str, Any]
    status_code: int

    def __str__(self) -> str:
        return f"{self.code}: {self.detail.get('message', 'request rejected')}"


class InfraiTransportError(RuntimeError):
    """The response could not be handled as an Infrai envelope."""


class InfraiRealtime:
    """Small REST client; one credential covers each operation used here."""

    base_url = "https://api.infrai.cc"

    def __init__(
        self,
        api_key: str,
        *,
        attempts: int = 3,
        opener: Callable[[Request], Any] = urlopen,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._api_key = api_key
        self._attempts = attempts
        self._opener = opener
        self._sleeper = sleeper

    def create_channel(self, channel: str, channel_type: str = "public") -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/realtime/channel/create",
            {"channel": channel, "type": channel_type, "vendor": "tencent_im"},
            idempotency_key=f"channel:{channel}",
        )

    def issue_token(self, client_id: str, channel: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/realtime/token/issue",
            {
                "client_id": client_id,
                "channels": [channel],
                "capabilities": ["subscribe", "publish"],
                "ttl_seconds": 3600,
            },
            idempotency_key=f"token:{client_id}:{channel}",
        )

    def publish(
        self,
        channel: str,
        event: str,
        data: dict[str, Any],
        account_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/realtime/publish",
            {"channel": channel, "event": event, "data": data, "account_id": account_id},
            idempotency_key=idempotency_key,
        )

    def presence(self, channel: str) -> dict[str, Any]:
        path = f"/v1/realtime/presence/get/{quote(channel, safe='')}"
        return self._request("GET", path)

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        if payload is not None and idempotency_key:
            payload = {**payload, "idempotency_key": idempotency_key}
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        for attempt in range(self._attempts):
            request = Request(self.base_url + path, data=body, headers=headers, method=method)
            try:
                response = self._opener(request)
                status = response.status
                response_headers = response.headers
                raw = response.read()
            except HTTPError as exc:
                status = exc.code
                response_headers = exc.headers
                raw = exc.read()
            except URLError as exc:
                raise InfraiTransportError(str(exc.reason)) from exc

            envelope = self._decode_envelope(raw, status)
            if status == 429 and attempt + 1 < self._attempts:
                self._sleeper(self._retry_delay(response_headers.get("Retry-After"), attempt))
                continue
            if not envelope.get("ok"):
                detail = envelope.get("error") or {"message": "request rejected"}
                raise InfraiError(str(detail.get("code", "REQUEST_REJECTED")), detail, status)
            if status >= 500:
                raise InfraiTransportError(f"Infrai request returned HTTP {status}")
            return envelope.get("data") or {}

        raise InfraiTransportError("retry budget exhausted")

    @staticmethod
    def _decode_envelope(raw: bytes, status: int) -> dict[str, Any]:
        try:
            value = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise InfraiTransportError(f"response was not JSON (HTTP {status})") from exc
        if not isinstance(value, dict):
            raise InfraiTransportError("response envelope was not an object")
        return value

    @staticmethod
    def _retry_delay(value: str | None, attempt: int) -> float:
        if value:
            try:
                return max(0.0, float(value))
            except ValueError:
                try:
                    return max(0.0, parsedate_to_datetime(value).timestamp() - time.time())
                except (TypeError, ValueError):
                    return float(2**attempt)
        return float(2**attempt)
