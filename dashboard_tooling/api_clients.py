from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Callable
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dashboard_tooling.config import DatadogAuthConfig, DynatraceAuthConfig


class ApiClientError(RuntimeError):
    pass


class RateLimitError(ApiClientError):
    pass


Transport = Callable[[Request], object]

# Number of retries on transient failures (5xx, network errors, rate limits)
_MAX_RETRIES = 3
# Seconds to wait between retries; doubled each attempt
_RETRY_BASE_DELAY = 2.0


def _default_transport(request: Request):
    return urlopen(request, timeout=60)  # nosec B310 — URLs are env-configured API endpoints, not user input


def _retry_delay(exc: Exception, attempt: int) -> float:
    if isinstance(exc, HTTPError) and exc.code == 429:
        retry_after = exc.headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass
    return _RETRY_BASE_DELAY * (2 ** attempt)


@dataclass
class JsonHttpClient:
    transport: Transport = _default_transport

    def _execute(self, request: Request, url: str) -> str:
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                with self.transport(request) as response:
                    return response.read().decode("utf-8")
            except HTTPError as exc:
                if exc.code == 429:
                    if attempt < _MAX_RETRIES - 1:
                        time.sleep(_retry_delay(exc, attempt))
                        last_exc = exc
                        continue
                    raise RateLimitError(f"rate limited after {_MAX_RETRIES} attempts for {url}") from exc
                if exc.code >= 500 and attempt < _MAX_RETRIES - 1:
                    time.sleep(_retry_delay(exc, attempt))
                    last_exc = exc
                    continue
                raise ApiClientError(f"HTTP {exc.code} for {url}: {exc.reason}") from exc
            except Exception as exc:  # pragma: no cover
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(_retry_delay(exc, attempt))
                    last_exc = exc
                    continue
                raise ApiClientError(f"request failed for {url}: {exc}") from exc
        raise ApiClientError(f"request failed after {_MAX_RETRIES} attempts for {url}: {last_exc}") from last_exc

    def get_json(self, url: str, headers: dict[str, str], *, query: dict[str, str] | None = None) -> object:
        final_url = url
        if query:
            final_url = f"{url}?{urlencode(query, doseq=True)}"
        request = Request(final_url, headers=headers, method="GET")
        payload = self._execute(request, final_url)
        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ApiClientError(f"invalid JSON response from {final_url}") from exc

    def request_json(self, method: str, url: str, headers: dict[str, str], *, body: object | None = None) -> object:
        payload_bytes = None
        request_headers = dict(headers)
        if body is not None:
            payload_bytes = json.dumps(body).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        request = Request(url, headers=request_headers, data=payload_bytes, method=method)
        payload = self._execute(request, url)
        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ApiClientError(f"invalid JSON response from {url}") from exc


class DynatraceDashboardApiClient:
    def __init__(self, config: DynatraceAuthConfig, http: JsonHttpClient | None = None) -> None:
        self.config = config
        self.http = http or JsonHttpClient()

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Api-Token {self.config.api_token}",
            "Accept": "application/json",
        }

    def list_dashboards(self) -> list[dict[str, object]]:
        payload = self.http.get_json(f"{self.config.base_url}/api/config/v1/dashboards", self._headers)
        dashboards = payload.get("dashboards", []) if isinstance(payload, dict) else []
        return [item for item in dashboards if isinstance(item, dict)]

    def get_dashboard(self, dashboard_id: str) -> dict[str, object]:
        payload = self.http.get_json(f"{self.config.base_url}/api/config/v1/dashboards/{dashboard_id}", self._headers)
        if not isinstance(payload, dict):
            raise ApiClientError(f"unexpected dashboard payload for Dynatrace dashboard {dashboard_id}")
        return payload

    def export_dashboards(self) -> dict[str, object]:
        dashboards: list[dict[str, object]] = []
        for item in self.list_dashboards():
            dashboard_id = str(item.get("id") or "")
            if not dashboard_id:
                continue
            full = self.get_dashboard(dashboard_id)
            full.setdefault("id", dashboard_id)
            dashboards.append(full)
        return {"dashboards": dashboards}


class DatadogDashboardApiClient:
    def __init__(self, config: DatadogAuthConfig, http: JsonHttpClient | None = None) -> None:
        self.config = config
        self.http = http or JsonHttpClient()

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "DD-API-KEY": self.config.api_key,
            "DD-APPLICATION-KEY": self.config.app_key,
            "Accept": "application/json",
        }

    def list_dashboards(self) -> list[dict[str, object]]:
        payload = self.http.get_json(f"{self.config.api_url}/api/v1/dashboard", self._headers)
        dashboards = payload.get("dashboards", []) if isinstance(payload, dict) else []
        return [item for item in dashboards if isinstance(item, dict)]

    def get_dashboard(self, dashboard_id: str) -> dict[str, object]:
        payload = self.http.get_json(f"{self.config.api_url}/api/v1/dashboard/{dashboard_id}", self._headers)
        if not isinstance(payload, dict):
            raise ApiClientError(f"unexpected dashboard payload for Datadog dashboard {dashboard_id}")
        return payload

    def export_dashboards(self) -> dict[str, object]:
        dashboards: list[dict[str, object]] = []
        for item in self.list_dashboards():
            dashboard_id = str(item.get("id") or "")
            if not dashboard_id:
                continue
            full = self.get_dashboard(dashboard_id)
            full.setdefault("id", dashboard_id)
            for key in ("title", "url", "description", "author_handle", "tags"):
                if key in item and key not in full:
                    full[key] = item[key]
            dashboards.append(full)
        return {"dashboards": dashboards}

    def create_dashboard(self, dashboard: dict[str, object]) -> dict[str, object]:
        payload = self.http.request_json(
            "POST",
            f"{self.config.api_url}/api/v1/dashboard",
            self._headers,
            body=dashboard,
        )
        if not isinstance(payload, dict):
            raise ApiClientError("unexpected Datadog create dashboard response")
        return payload

    def update_dashboard(self, dashboard_id: str, dashboard: dict[str, object]) -> dict[str, object]:
        payload = self.http.request_json(
            "PUT",
            f"{self.config.api_url}/api/v1/dashboard/{dashboard_id}",
            self._headers,
            body=dashboard,
        )
        if not isinstance(payload, dict):
            raise ApiClientError("unexpected Datadog update dashboard response")
        return payload
